"""Multi-class detector: first-pass screening across all 6 implantation-failure scenarios.

Message flow (matches reference §6):
  1. SystemMessage(§1.1 detector_system_prompt.jinja2)   — background + role + task + wearing process + category list
  2. HumanMessage(§2 gs1_intro)                           — all 11 product components + structure images (one message)
  3. HumanMessage(§3 gs1_failure)                         — all 6 scenarios + case images (one message)
  4. HumanMessage(§1.3 detector_task.jinja2 + user image)  — scoring rules + multi-class classification task
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from src.core.llm_trace import LlmTraceCallback
from src.core.logging import current_millis, log_context

_DATA_URL_PREFIX = "data:image"


def _log_safe_ref(image_ref: str, max_len: int = 80) -> str:
    """Truncate data URLs in log messages to avoid bloating log storage."""
    if image_ref.startswith(_DATA_URL_PREFIX) and len(image_ref) > max_len:
        return image_ref[:max_len] + "..."
    return image_ref


from src.scanner.cache import encode_and_resize_image, list_reference_files
from src.scanner.models import DetectorCategory, DetectorOutput
from src.scanner.evaluator import DEFAULT_FAULT_SCENARIOS
from src.scanner.prompts import (
    build_detector_system_prompt,
    build_product_structure_text,
    build_failure_scenarios_text,
    build_detector_task,
    PRODUCT_STRUCTURES,
    CASE_IMAGE_MAP,
    GS1_STRUCTURES_DIR,
    GS1_CASES_DIR,
    list_image_files,
)

logger = logging.getLogger(__name__)

# Detector threshold: minimum score to pass a candidate to the judger.
# Set low to favor recall over precision — the judger will filter.
DETECTOR_PASS_THRESHOLD = 5


class DetectorPipeline:
    """Multi-class detector that screens an image against all 6 failure scenarios.

    Calls the VLM once with a reference §6 message sequence.
    Returns candidates whose score >= DETECTOR_PASS_THRESHOLD.
    """

    def __init__(self, settings: Any, templates_dir: str | None = None) -> None:
        self.settings = settings

        self.api_key = settings.dashscope_api_key
        self.api_base = settings.vlm_base_url
        self.model_name = settings.vlm_model

        self.fault_scenarios = DEFAULT_FAULT_SCENARIOS
        self.product_structures = PRODUCT_STRUCTURES

        self._llm: Any = None

        # Pre-load reference images at init time
        self.structure_images: dict[str, list[tuple[str, str]]] = (
            self._load_structure_images()
        )
        self.case_images: dict[str, list[tuple[str, str]]] = self._load_case_images()

    def _load_structure_images(self) -> dict[str, list[tuple[str, str]]]:
        """Pre-encode GS1 product structure images per component directory.

        Returns {component_dir: [(b64, media_type), ...]}, first image per component.
        Returns empty dict if structures directory doesn't exist.
        """
        result: dict[str, list[tuple[str, str]]] = {}
        structures_dir = Path(GS1_STRUCTURES_DIR)
        if not structures_dir.exists():
            logger.info(
                "GS1 structure images directory not found; detector runs without §2 visuals",
                extra=log_context(
                    "detector.gs1_structures_missing", path=str(GS1_STRUCTURES_DIR)
                ),
            )
            return result

        for comp in self.product_structures:
            comp_dir = structures_dir / comp["dir"]
            if not comp_dir.exists():
                continue
            images = list_image_files(comp_dir)
            if not images:
                continue
            # Take first image per component to keep token usage bounded
            try:
                b64, media_type = encode_and_resize_image(
                    images[0], max_side=800, quality=80
                )
                result[comp["dir"]] = [(b64, media_type)]
            except Exception as exc:
                logger.warning(
                    "Failed to encode structure image",
                    extra=log_context(
                        "detector.structure_encode_failed",
                        path=str(images[0]),
                        error=str(exc),
                    ),
                )

        logger.info(
            "GS1 structure images pre-loaded",
            extra=log_context(
                "detector.structures_loaded",
                component_count=len(result),
            ),
        )
        return result

    def _load_case_images(self) -> dict[str, list[tuple[str, str]]]:
        """Pre-encode GS1 case images per scenario using flat CASE_IMAGE_MAP.

        Returns {scenario_id: [(b64, media_type), ...]}.
        Returns empty dict if cases directory doesn't exist.
        """
        cases_dir = Path(GS1_CASES_DIR)
        if not cases_dir.exists():
            logger.info(
                "GS1 case images directory not found; detector runs §3 TEXT-only",
                extra=log_context(
                    "detector.gs1_cases_missing", path=str(GS1_CASES_DIR)
                ),
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
                        "Failed to encode case image",
                        extra=log_context(
                            "detector.case_encode_failed",
                            path=str(img_path),
                            error=str(exc),
                        ),
                    )
            if encoded:
                result[sid] = encoded

        logger.info(
            "GS1 case images pre-loaded",
            extra=log_context(
                "detector.cases_loaded",
                scenario_count=len(result),
                total_images=sum(len(v) for v in result.values()),
            ),
        )
        return result

    def _get_llm(self) -> Any:
        """Get or create the structured LLM for detector output."""
        if self._llm is None:
            llm = ChatOpenAI(
                model=self.model_name,
                openai_api_key=self.api_key,
                openai_api_base=self.api_base,
                temperature=0.0,
                extra_body={"enable_thinking": False},
            )
            self._llm = llm.with_structured_output(
                DetectorOutput, method="json_schema"
            )
        return self._llm

    def _build_gs1_intro_message(self) -> HumanMessage:
        """Build §2 gs1_intro: one HumanMessage with all 11 components + structure images."""
        text = build_product_structure_text(self.product_structures)
        image_parts: list[dict[str, Any]] = []
        for comp in self.product_structures:
            if comp["dir"] in self.structure_images:
                for b64, media_type in self.structure_images[comp["dir"]]:
                    image_parts.append(
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{media_type};base64,{b64}"},
                        }
                    )
        if image_parts:
            return HumanMessage(content=[{"type": "text", "text": text}] + image_parts)
        return HumanMessage(content=text)

    def _build_gs1_failure_message(self) -> HumanMessage:
        """Build §3 gs1_failure: one HumanMessage with all 6 scenarios + case images."""
        text = build_failure_scenarios_text(self.fault_scenarios)
        image_parts: list[dict[str, Any]] = []
        for scenario in self.fault_scenarios:
            sid = scenario["scenario_id"]
            if sid in self.case_images:
                for b64, media_type in self.case_images[sid]:
                    image_parts.append(
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{media_type};base64,{b64}"},
                        }
                    )
        if image_parts:
            return HumanMessage(content=[{"type": "text", "text": text}] + image_parts)
        return HumanMessage(content=text)

    def run(
        self,
        images: list[tuple[str, str, str]],
    ) -> list[dict[str, Any]]:
        """Run the detector on one or more user images of the same device.

        All images are sent in a single call so the VLM sees the full visual
        context (e.g. two different angles of the same defect).

        Builds the §6 reference message sequence:
          1. SystemMessage(§1.1) — static system prompt with category list
          2. HumanMessage(§2 gs1_intro) — all 11 components + structure images
          3. HumanMessage(§3 gs1_failure) — all 6 failure scenarios + case images
          4. HumanMessage(§1.3 task + user images) — scoring + multi-class classification

        Args:
            images: List of (b64_data, media_type, image_name) tuples.

        Returns:
            List of candidate dicts with scenario_id, score, reasoning.
            Empty list if no candidates pass the threshold.
        """
        started = time.perf_counter()
        image_count = len(images)
        first_name = images[0][2] if images else ""

        try:
            structured_llm = self._get_llm()
        except Exception as exc:
            logger.error(
                "Detector LLM init failed",
                extra=log_context("detector.llm_init_failed", error=str(exc)),
            )
            return []

        # §1.1 — SystemMessage (static system prompt)
        messages: list = [SystemMessage(content=build_detector_system_prompt())]

        # §2 — gs1_intro: all 11 product components with structure images
        messages.append(self._build_gs1_intro_message())

        # §3 — gs1_failure: all 6 failure scenarios with case images
        messages.append(self._build_gs1_failure_message())

        # §1.3 — Task: scoring rules + multi-class classification with user images
        task_text = build_detector_task()
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
            trace_cb = LlmTraceCallback(tag="detector")
            response: DetectorOutput = structured_llm.invoke(
                messages, config={"callbacks": [trace_cb]}
            )

            logger.info(
                "Detector raw response",
                extra=log_context(
                    "detector.raw_response",
                    image_count=image_count,
                    category_count=len(response.categories or []),
                    categories=[
                        f"{c.scenario_id}:{c.score}"
                        for c in (response.categories or [])
                    ],
                ),
            )

            candidates = []
            for cat in response.categories or []:
                cat_id = cat.scenario_id
                # Validate scenario_id against known list
                if cat_id not in [s["scenario_id"] for s in self.fault_scenarios]:
                    logger.warning(
                        "Detector returned unknown scenario_id",
                        extra=log_context(
                            "detector.unknown_scenario", scenario_id=cat_id
                        ),
                    )
                    continue

                score = max(0, min(10, int(cat.score)))
                candidates.append(
                    {
                        "scenario_id": cat_id,
                        "score": score,
                        "reasoning": cat.reasoning or "",
                    }
                )

            # Filter by threshold
            passed = [c for c in candidates if c["score"] >= DETECTOR_PASS_THRESHOLD]

            duration_ms = current_millis(started)
            logger.info(
                "Detector completed",
                extra=log_context(
                    "detector.completed",
                    duration_ms=duration_ms,
                    image_count=image_count,
                    image_name=_log_safe_ref(first_name),
                    candidate_count=len(candidates),
                    passed_count=len(passed),
                    passed_ids=[c["scenario_id"] for c in passed],
                ),
            )

            return passed

        except Exception as exc:
            duration_ms = current_millis(started)
            logger.error(
                "Detector inference failed",
                extra=log_context(
                    "detector.failed",
                    duration_ms=duration_ms,
                    image_count=image_count,
                    image_name=_log_safe_ref(first_name),
                    error=str(exc),
                ),
            )
            return []
