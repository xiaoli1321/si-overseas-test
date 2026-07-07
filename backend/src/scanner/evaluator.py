"""Implantation-failure judger: reference §6 single-category verification pipeline.

Message flow (matches reference §6):
  1. SystemMessage(§1.2 judger_system_prompt.jinja2)        — background + role + task + wearing process (no category list)
  2. HumanMessage(§2 gs1_intro)                              — all 11 product components + structure images (one message)
  3. HumanMessage(§4 single-category)                        — target scenario text + its case images
  4. HumanMessage(§1.3 judger_task.jinja2 + user image)      — scoring rules + single-class task with {{category}}
"""

from __future__ import annotations

import concurrent.futures
import logging
import threading
import time
from pathlib import Path
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from src.core.llm_trace import LlmTraceCallback
from src.core.logging import current_millis, log_context

from .cache import encode_and_resize_image
from .models import ScenarioEvaluation
from .prompts import (
    build_judger_system_prompt,
    build_judger_task,
    build_product_structure_text,
    build_failure_scenarios_text,
    PRODUCT_STRUCTURES,
    CASE_IMAGE_MAP,
    GS1_STRUCTURES_DIR,
    GS1_CASES_DIR,
    list_image_files,
    scenario_name,
)

logger = logging.getLogger(__name__)

DEFAULT_THRESHOLD = 7.0

DEFAULT_FAULT_SCENARIOS: list[dict[str, Any]] = [
    {
        "scenario_id": "assembly_failure",
        "order": 1,
        "name_cn": "拾取失败",
        "name_en": "Assembly failure",
        "threshold": 7,
        "system_prompt": "组装失败：小圆孔黑色空洞无凸出物，或组件残留在青色植入器内部腔体",
        "positive_rules": [
            "佩戴后小圆孔明显凹陷：暗色/黑色，无金属反光，无凸出物",
            "组件残留在青色植入器内部腔体中",
        ],
        "negative_rules": [
            "金属凸出、白色导引针、完整发射器脱落、传感器在口外侧端面",
        ],
        "exclusion_rules": [],
        "core_cause": "在组装敷贴器和传感器组件包时，用户按压力度不够或操作不当，导致传感电极没有完全与发射器组合成闭合结构，出现凹陷或错位。",
        "judgment_conditions": [
            "佩戴后小圆孔明显凹陷呈暗色/黑色，无金属反光，无凸出物（对应于小圆孔凹陷）",
            "传感器组件残留或卡在青色敷贴器内部腔体中（对应于组件残留在腔体）",
        ],
        "responsibility": "用户操作问题",
    },
    {
        "scenario_id": "guide_needle_retention",
        "order": 2,
        "name_cn": "导引针滞留",
        "name_en": "Guide needle retention",
        "threshold": 7,
        "system_prompt": "导引针滞留：传感器在皮肤上，中央有白色塑料导引针竖起",
        "positive_rules": [
            "传感器在皮肤上，中央有白色塑料短柱竖起",
        ],
        "negative_rules": [
            "未贴肤、金属色、黑色空洞",
        ],
        "exclusion_rules": [],
        "core_cause": "导引针在发射过程中随传感器一同弹出，但因内部结构故障，导引针完成刺破皮肤后没有正确回弹，滞留在传感器上。",
        "judgment_conditions": [
            "传感器已贴附在皮肤上，传感器中央有白色塑料导引针竖起未回弹",
        ],
        "responsibility": "产品本身损坏",
    },
    {
        "scenario_id": "early_launches",
        "order": 3,
        "name_cn": "发射器提前发射",
        "name_en": "Early launches",
        "threshold": 7,
        "system_prompt": "提前发射：植入器内腔持平，组件散落在外部，未贴肤",
        "positive_rules": [
            "植入器内腔持平，组件在外部散落",
        ],
        "negative_rules": [
            "内腔凹陷、已贴肤、组件在内部腔体",
        ],
        "exclusion_rules": [],
        "core_cause": "用户在组装过程中不小心提前按下了敷贴器上的发射按钮，或未取下安全扣即进行其他操作，导致传感器提前弹出，未能在皮肤上正确植入。",
        "judgment_conditions": [
            "敷贴器内部腔体持平（弹簧已释放），传感器组件散落在外部，未贴附在皮肤上",
            "安全扣已取下或不在原位，发射器支架与敷贴器外边缘已平行",
        ],
        "responsibility": "用户操作问题",
        "negative_discrimination": [
            "传感器已经成功植入皮肤表面并贴附在皮肤上，无论导引针处于什么状态，均说明发射过程已成功完成，不属于提前发射",
        ],
    },
    {
        "scenario_id": "sensor_falling_out",
        "order": 4,
        "name_cn": "传感器脱落",
        "name_en": "Sensor falling out",
        "threshold": 7,
        "system_prompt": "发射器脱落：完整发射器脱落，在防尘盖上，植入器内腔凹陷",
        "positive_rules": [
            "完整发射器脱落，在防尘盖上，内腔凹陷",
        ],
        "negative_rules": [
            "组件有黑洞、内腔持平、已贴肤",
        ],
        "exclusion_rules": [],
        "core_cause": "发射器在敷贴器内部的固定结构不稳定或受运输影响，导致发射器在正常植入前就从敷贴器的发射器支架上脱落。",
        "judgment_conditions": [
            "完整发射器（含传感器）已从敷贴器中脱落，掉落在防尘盖上或外部",
            "敷贴器内部腔体凹陷（发射器支架仍在内腔中）",
        ],
        "responsibility": "产品本身损坏",
    },
    {
        "scenario_id": "adhesion_failure",
        "order": 5,
        "name_cn": "发射器被带离皮肤",
        "name_en": "Adhesion failure",
        "threshold": 7,
        "system_prompt": "传感器被带离皮肤：完整传感器贴片粘在青色植入器开口端面外侧",
        "positive_rules": [
            "青色植入器口外侧端面粘着完整传感器贴片",
        ],
        "negative_rules": [
            "组件在内部腔体、空腔、仍在皮肤上、散落",
        ],
        "exclusion_rules": [],
        "core_cause": "传感器背胶粘性不够，或敷贴器上的发射器支架与传感器扣合太紧，导致传感器发射后未能贴附在皮肤上，反而被敷贴器带离皮肤。",
        "judgment_conditions": [
            "青色敷贴器开口端面外侧粘着完整的传感器贴片",
            "皮肤上无传感器残留，敷贴器与传感器未正常分离",
        ],
        "responsibility": "产品本身损坏",
    },
    {
        "scenario_id": "exposed_electrodes",
        "order": 6,
        "name_cn": "电极外漏",
        "name_en": "Exposed Electrodes",
        "threshold": 7,
        "system_prompt": "电极外漏：传感器在皮肤上，孔内有银白色金属针状凸出",
        "positive_rules": [
            "传感器在皮肤上，孔内有银白色金属针状凸出",
        ],
        "negative_rules": [
            "暗色空洞、未贴肤、白色导引针",
        ],
        "exclusion_rules": [],
        "core_cause": "用户在植入过程中选择了较硬或肌肉较多的部位，导致传感器电极未能完全植入皮下，向外凸出。",
        "judgment_conditions": [
            "传感器已贴附在皮肤上，但传感器中央的小孔内有银白色金属针状物凸出，摸起来有刮手感",
        ],
        "responsibility": "产品本身损坏",
    },
]


class ImplantationScanner:
    """Single-category judger for implantation-failure verification.

    Uses the reference §6 judger message flow:
      1. SystemMessage(§1.2) — static judger system prompt
      2. HumanMessage(§2 gs1_intro) — all 11 product components + structure images
      3. HumanMessage(§4 single-category) — target scenario text + its case images
      4. HumanMessage(§1.3 task + user image) — scoring + single-class task with {{category}}

    Called by the pipeline after the multi-class detector has identified candidates.
    """

    def __init__(self, settings: Any, ref_dir: str, templates_dir: str) -> None:
        self.settings = settings
        self.ref_dir = Path(ref_dir)
        self.templates_dir = templates_dir

        self.api_key = settings.dashscope_api_key
        self.api_base = settings.vlm_base_url
        self.model_name = settings.vlm_model

        self.fault_scenarios = DEFAULT_FAULT_SCENARIOS

        self._llm_cache: dict[str, Any] = {}
        self._llm_cache_lock = threading.Lock()

        # Pre-build §2 gs1_intro (structure images) at init time
        self.gs1_structure_images: dict[str, list[tuple[str, str]]] = (
            self._load_structure_images()
        )

        # Pre-load GS1 case images via flat CASE_IMAGE_MAP
        self.gs1_case_images: dict[str, list[tuple[str, str]]] = (
            self._load_case_images()
        )

        logger.info(
            "Implantation scanner (judger) initialized",
            extra=log_context(
                "judger.initialized",
                model=self.model_name,
                structure_component_count=len(self.gs1_structure_images),
                case_scenario_count=len(self.gs1_case_images),
            ),
        )

    def _load_structure_images(self) -> dict[str, list[tuple[str, str]]]:
        """Pre-encode GS1 product structure images, first image per component."""
        result: dict[str, list[tuple[str, str]]] = {}
        structures_dir = Path(GS1_STRUCTURES_DIR)
        if not structures_dir.exists():
            logger.info(
                "GS1 structure images not found; judger runs without §2 visuals",
                extra=log_context(
                    "judger.gs1_structures_missing", path=str(GS1_STRUCTURES_DIR)
                ),
            )
            return result

        for comp in PRODUCT_STRUCTURES:
            comp_dir = structures_dir / comp["dir"]
            if not comp_dir.exists():
                continue
            images = list_image_files(comp_dir)
            if not images:
                continue
            try:
                b64, media_type = encode_and_resize_image(
                    images[0], max_side=800, quality=80
                )
                result[comp["dir"]] = [(b64, media_type)]
            except Exception as exc:
                logger.warning(
                    "Failed to encode judger structure image",
                    extra=log_context(
                        "judger.structure_encode_failed",
                        path=str(images[0]),
                        error=str(exc),
                    ),
                )

        logger.info(
            "GS1 structure images pre-loaded for judger",
            extra=log_context("judger.structures_loaded", component_count=len(result)),
        )
        return result

    def _load_case_images(self) -> dict[str, list[tuple[str, str]]]:
        """Pre-load GS1 case images via flat CASE_IMAGE_MAP."""
        cases_dir = Path(GS1_CASES_DIR)
        if not cases_dir.exists():
            logger.info(
                "GS1 case images not found; judger runs §4 TEXT-only",
                extra=log_context("judger.gs1_cases_missing", path=str(GS1_CASES_DIR)),
            )
            return {}

        result: dict[str, list[tuple[str, str]]] = {}
        for sid, filenames in CASE_IMAGE_MAP.items():
            encoded: list[tuple[str, str]] = []
            for fname in filenames:
                img_path = cases_dir / fname
                if not img_path.exists():
                    continue
                try:
                    b64, media_type = encode_and_resize_image(
                        img_path, max_side=800, quality=80
                    )
                    encoded.append((b64, media_type))
                except Exception as exc:
                    logger.warning(
                        "Failed to encode judger case image",
                        extra=log_context(
                            "judger.case_encode_failed",
                            path=str(img_path),
                            error=str(exc),
                        ),
                    )
            if encoded:
                result[sid] = encoded

        logger.info(
            "GS1 case images pre-loaded for judger",
            extra=log_context(
                "judger.cases_loaded",
                scenario_count=len(result),
                total_images=sum(len(v) for v in result.values()),
            ),
        )
        return result

    def _get_structured_llm(
        self,
        output_model: Any = None,
    ) -> Any:
        """Return a cached ChatOpenAI instance with structured output binding.

        Thread-safe: uses a lock around the cache read-then-write path.
        """
        model_cls = output_model or ScenarioEvaluation
        model_key = model_cls.__name__
        key = f"{self.model_name}|{self.api_key}|{self.api_base}|{model_key}"
        with self._llm_cache_lock:
            cached = self._llm_cache.get(key)
            if cached is not None:
                return cached
            llm = ChatOpenAI(
                model=self.model_name,
                openai_api_key=self.api_key,
                openai_api_base=self.api_base,
                temperature=0.0,
                extra_body={"enable_thinking": False},
            )
            self._llm_cache[key] = llm.with_structured_output(
                model_cls, method="json_schema"
            )
            return self._llm_cache[key]

    def _build_gs1_intro_message(self) -> HumanMessage:
        """Build §2 gs1_intro: one HumanMessage with all 11 components + structure images."""
        text = build_product_structure_text(PRODUCT_STRUCTURES)
        image_parts: list[dict[str, Any]] = []
        for comp in PRODUCT_STRUCTURES:
            if comp["dir"] in self.gs1_structure_images:
                for b64, media_type in self.gs1_structure_images[comp["dir"]]:
                    image_parts.append(
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{media_type};base64,{b64}"},
                        }
                    )
        if image_parts:
            return HumanMessage(content=[{"type": "text", "text": text}] + image_parts)
        return HumanMessage(content=text)

    def _run_judger_on_candidates(
        self,
        images: list[tuple[str, str, str]],
        candidate_ids: list[str],
    ) -> list[dict[str, Any]]:
        """Run the judger on selected candidate scenarios using all user images."""
        candidates = [
            sc for sc in self.fault_scenarios if sc["scenario_id"] in candidate_ids
        ]
        if not candidates:
            return []

        results: list[dict[str, Any]] = []
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=len(candidates),
        ) as executor:
            futures = {
                executor.submit(
                    self._evaluate_scenario_as_judger,
                    scenario=sc,
                    images=images,
                ): sc
                for sc in candidates
            }
            for future in concurrent.futures.as_completed(futures):
                results.append(future.result())
        return results

    def _evaluate_scenario_as_judger(
        self,
        *,
        scenario: dict[str, Any],
        images: list[tuple[str, str, str]],
    ) -> dict[str, Any]:
        """Evaluate one scenario using the §6 reference judger message flow.

        Message sequence:
          1. SystemMessage(§1.2) — static judger system prompt
          2. HumanMessage(§2 gs1_intro) — all 11 components + structure images
          3. HumanMessage(§4 single-category) — target scenario text + its case images
          4. HumanMessage(§1.3 task + user images) — scoring + single-class task
        """
        scenario_id = scenario["scenario_id"]
        threshold = float(scenario.get("threshold", DEFAULT_THRESHOLD))
        category_name = scenario.get("name_cn", scenario_id)

        result: dict[str, Any] = {
            "scenario_id": scenario_id,
            "model_reported_scenario_id": None,
            "scenario_name": scenario_name(scenario),
            "threshold": threshold,
            "score": None,
            "is_match": False,
            "core_features_hit": [],
            "exclusion_features_hit": [],
            "different_features": [],
            "image_quality": "medium",
            "ambiguity_level": "high",
            "reasoning": "",
            "latency_sec": 0.0,
            "success": False,
            "error_msg": "",
        }

        # ---- §1.2 — SystemMessage (static) ----
        messages: list[Any] = [SystemMessage(content=build_judger_system_prompt())]

        # ---- §2 — gs1_intro: all 11 components with structure images (one message) ----
        messages.append(self._build_gs1_intro_message())

        # ---- §4 — Single-category failure text + its case images ----
        failure_text = build_failure_scenarios_text(
            self.fault_scenarios,
            target_category=category_name,
        )
        image_parts: list[dict[str, Any]] = []
        if scenario_id in self.gs1_case_images:
            for b64, mtype in self.gs1_case_images[scenario_id]:
                image_parts.append(
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{mtype};base64,{b64}"},
                    }
                )
        if image_parts:
            messages.append(
                HumanMessage(
                    content=[{"type": "text", "text": failure_text}] + image_parts
                )
            )
        else:
            messages.append(HumanMessage(content=failure_text))

        # ---- §1.3 — Task message with user image(s) ----
        task_text = build_judger_task(category_name, scenario_id)
        content: list[dict[str, Any]] = [{"type": "text", "text": task_text}]
        for b64, media_type, _name in images:
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{media_type};base64,{b64}"},
                }
            )
        messages.append(HumanMessage(content=content))

        try:
            structured_llm = self._get_structured_llm()
        except Exception as exc:
            result["error_msg"] = f"LLM init failed: {exc}"
            return result

        start_time = time.perf_counter()
        try:
            trace_cb = LlmTraceCallback(tag=f"judger.{scenario_id}")
            response = structured_llm.invoke(messages, config={"callbacks": [trace_cb]})
            latency = time.perf_counter() - start_time
            score = max(0, min(10, int(response.score)))

            result.update(
                {
                    "scenario_id": scenario_id,
                    "model_reported_scenario_id": response.scenario_id,
                    "score": score,
                    "is_match": bool(score >= threshold),
                    "core_features_hit": response.core_features_hit,
                    "exclusion_features_hit": response.exclusion_features_hit,
                    "different_features": response.different_features,
                    "image_quality": response.image_quality,
                    "ambiguity_level": response.ambiguity_level,
                    "reasoning": response.reasoning,
                    "latency_sec": latency,
                    "success": True,
                }
            )
        except Exception as exc:
            latency = time.perf_counter() - start_time
            result["latency_sec"] = latency
            result["error_msg"] = f"Inference/parse failure: {exc}"

        return result
