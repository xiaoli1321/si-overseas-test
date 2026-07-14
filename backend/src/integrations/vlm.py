import asyncio
import base64
import json
import logging
import os
from pathlib import Path
import time
from typing import Any

import jinja2
from langsmith.wrappers import wrap_openai
from pydantic import BaseModel, ConfigDict

from src.core.config import Settings, get_settings
from src.core.logging import current_millis, log_context

logger = logging.getLogger(__name__)


class VlmRequestError(RuntimeError):
    """A live VLM request exhausted retries and produced no trustworthy result."""


class GlucoseReading(BaseModel):
    value: float | None = None
    device_type: str | None = None  # "CGM" or "BGM"
    unit: str = "mmol/L"  # "mmol/L" or "mg/dL"
    is_valid: bool = True
    is_reproduced: bool = False


class VlmScenarioMatch(BaseModel):
    scenario: str = ""
    matched: bool = False
    confidence: float = 0.0
    reason: str = ""


class VlmAnalysisResult(BaseModel):
    is_cgm_device_present: bool = False
    is_reproduced_photo: bool = False
    needle_exposed: bool = False
    adhesive_detached: bool = False
    implanter_damage: bool = False
    glucose_readings: list[GlucoseReading] | None = None
    model_name: str = "deterministic-fallback"
    prompt_version: str = "application-failure-v1"
    source: str = "fallback"
    scenarios: list[VlmScenarioMatch] | None = None
    final_scenario: str | None = None
    final_confidence: float | None = None

    model_config = ConfigDict(extra="ignore")


class QwenVlClient:
    _prompt_template: Any = None  # cached jinja2 Template

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def _get_vlm_scenario_template(self) -> Any:
        """Load and cache the VLM scenario prompt template (lazy)."""
        if self._prompt_template is not None:
            return self._prompt_template
        from pathlib import Path
        from src.core.utils import resolve_path

        resolved = resolve_path("prompts/scanner/vlm_scenario_prompt.jinja2")
        if resolved:
            try:
                _env = jinja2.Environment(
                    loader=jinja2.FileSystemLoader(Path(resolved).parent)
                )
                self._prompt_template = _env.get_template(Path(resolved).name)
            except Exception:
                pass
        return self._prompt_template

    async def analyze_sensor_photos(self, image_refs: list[str]) -> VlmAnalysisResult:
        started = time.perf_counter()
        logger.info(
            "Sensor photo VLM analysis started",
            extra=log_context(
                "vlm.sensor_started",
                image_count=len(image_refs),
                model=self.settings.vlm_model,
                prompt_version=self.settings.vlm_prompt_version,
            ),
        )
        if not self._can_call_live_model(image_refs):
            res = fallback_vlm_analysis(image_refs, model_name=self.settings.vlm_model)
            res.prompt_version = self.settings.vlm_prompt_version
            logger.info(
                "Sensor photo VLM fallback used",
                extra=log_context(
                    "vlm.fallback_used",
                    duration_ms=current_millis(started),
                    image_count=len(image_refs),
                    source=res.source,
                    reason="live_model_unavailable",
                ),
            )
            return res

        last_error: Exception | None = None
        for attempt in range(max(1, self.settings.vlm_max_retries)):
            try:
                result = await self._call_live_model(image_refs)
                logger.info(
                    "Sensor photo VLM analysis completed",
                    extra=log_context(
                        "vlm.sensor_completed",
                        duration_ms=current_millis(started),
                        image_count=len(image_refs),
                        source=result.source,
                        scenario_count=len(result.scenarios or []),
                        final_scenario=str(result.final_scenario)
                        if result.final_scenario
                        else "None",
                        final_confidence=str(result.final_confidence)
                        if result.final_confidence is not None
                        else "None",
                    ),
                )
                return result
            except Exception as exc:  # pragma: no cover - live integration is opt-in.
                last_error = exc
                logger.error(
                    "Sensor photo VLM attempt failed",
                    extra=log_context(
                        "vlm.sensor_attempt_failed",
                        attempt=attempt + 1,
                        max_retries=self.settings.vlm_max_retries,
                        error_type=type(exc).__name__,
                    ),
                )

        fallback = fallback_vlm_analysis(image_refs, model_name=self.settings.vlm_model)
        fallback.prompt_version = self.settings.vlm_prompt_version
        fallback.source = f"fallback_after_error:{type(last_error).__name__ if last_error else 'unknown'}"
        logger.error(
            "Sensor photo VLM fallback used after live errors",
            extra=log_context(
                "vlm.fallback_used",
                duration_ms=current_millis(started),
                image_count=len(image_refs),
                source=fallback.source,
            ),
        )
        return fallback

    def _can_call_live_model(self, image_refs: list[str]) -> bool:
        if (
            not self.settings.vlm_enabled
            or not self.settings.dashscope_api_key
            or not image_refs
        ):
            return False
        resolved = _resolve_image_urls(image_refs)
        if len(resolved) != len(image_refs):
            logger.info(
                "Cannot call live VLM model because not all image refs resolved",
                extra=log_context(
                    "vlm.live_unavailable",
                    resolved_count=len(resolved),
                    image_count=len(image_refs),
                ),
            )
            return False
        return True

    async def _call_live_model(self, image_refs: list[str]) -> VlmAnalysisResult:
        from openai import AsyncOpenAI

        import os

        raw_client = AsyncOpenAI(
            api_key=self.settings.dashscope_api_key,
            base_url=self.settings.vlm_base_url,
        )
        if os.environ.get("LANGSMITH_API_KEY"):
            try:
                client = wrap_openai(raw_client)
            except Exception:
                client = raw_client
        else:
            client = raw_client
        image_urls = _resolve_image_urls(image_refs)

        scenarios_to_check = [
            "Adhesion failure",
            "Exposed Electrodes",
            "Guide needle retention",
            "Early launches",
            "Sensor falling out",
            "Assembly failure",
        ]

        # Fully concurrent — all 6 scenarios evaluated in parallel
        _sem = asyncio.Semaphore(len(scenarios_to_check))
        _VLM_TIMEOUT = 60  # seconds per scenario call

        # Use cached template (loaded once)
        scenario_template = self._get_vlm_scenario_template()

        async def _call_one(scenario: str) -> VlmScenarioMatch:
            """Evaluate a single scenario via VLM."""
            async with _sem:
                if scenario_template is not None:
                    prompt = scenario_template.render(scenario=scenario)
                else:
                    prompt = (
                        f"You are a professional quality assurance assistant for Continuous Glucose Monitoring (CGM) devices.\n"
                        f"Analyze the uploaded photo(s) of the sensor insertion site.\n"
                        f'Determine if the issue matches the scenario: "{scenario}".\n'
                        f"Return ONLY a JSON object with these keys:\n"
                        f'- "matched" (boolean): whether the photo matches this scenario.\n'
                        f'- "confidence" (float): confidence score from 0.0 to 10.0.\n'
                        f'- "reason" (string): brief explanation for your choice.'
                    )
                content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
                for url in image_urls:
                    content.append({"type": "image_url", "image_url": {"url": url}})

                try:
                    scenario_started = time.perf_counter()
                    logger.info(
                        "VLM LLM call",
                        extra=log_context(
                            "vlm.llm_call",
                            scenario=scenario,
                            prompt=prompt[:1000],
                            image_count=len(image_urls),
                            model=self.settings.vlm_model,
                        ),
                    )

                    response = await asyncio.wait_for(
                        client.chat.completions.create(
                            model=self.settings.vlm_model,
                            messages=[{"role": "user", "content": content}],
                            response_format={"type": "json_object"},
                        ),
                        timeout=_VLM_TIMEOUT,
                    )
                    raw_content = response.choices[0].message.content or "{}"
                    scenario_duration_ms = round(
                        (time.perf_counter() - scenario_started) * 1000, 1
                    )
                    usage = dict(response.usage or {})
                    logger.info(
                        "VLM LLM response",
                        extra=log_context(
                            "vlm.llm_response",
                            scenario=scenario,
                            raw_content=raw_content,
                            duration_ms=scenario_duration_ms,
                            model=self.settings.vlm_model,
                            usage=usage,
                        ),
                    )

                    match_res = VlmScenarioMatch.model_validate_json(raw_content)
                    logger.info(
                        "VLM scenario result",
                        extra=log_context(
                            "vlm.scenario_result",
                            scenario=scenario,
                            matched=match_res.matched,
                            confidence=match_res.confidence,
                            reason=match_res.reason[:200] if match_res.reason else "",
                        ),
                    )
                except asyncio.TimeoutError:
                    logger.error(
                        "VLM scenario call timed out",
                        extra=log_context(
                            "vlm.scenario_timeout",
                            scenario=scenario,
                            timeout=_VLM_TIMEOUT,
                        ),
                    )
                    match_res = VlmScenarioMatch(
                        scenario=scenario,
                        matched=False,
                        confidence=0.0,
                        reason=f"VLM call timed out after {_VLM_TIMEOUT}s",
                    )
                except Exception as e:
                    logger.error(
                        "VLM scenario call failed",
                        extra=log_context(
                            "vlm.scenario_failed",
                            scenario=scenario,
                            error_type=type(e).__name__,
                        ),
                    )
                    match_res = VlmScenarioMatch(
                        scenario=scenario,
                        matched=False,
                        confidence=0.0,
                        reason=f"VLM call failed: {str(e)}",
                    )

                match_res.scenario = scenario
                return match_res

        tasks = [_call_one(s) for s in scenarios_to_check]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        scenarios_results: list[VlmScenarioMatch] = []
        for r in results:
            if isinstance(r, VlmScenarioMatch):
                scenarios_results.append(r)
            else:
                # Catches BaseException (CancelledError, etc.) — _call_one catches Exception
                logger.error(
                    "VLM concurrent gather raised unexpected exception",
                    extra=log_context(
                        "vlm.gather_exception",
                        error_type=type(r).__name__,
                    ),
                )
                scenarios_results.append(
                    VlmScenarioMatch(
                        scenario="unknown",
                        matched=False,
                        confidence=0.0,
                        reason=f"VLM concurrent call failed: {str(r)}",
                    )
                )

        matched_scenarios = [s for s in scenarios_results if s.matched]
        if matched_scenarios:
            best_match = max(matched_scenarios, key=lambda s: s.confidence)
            final_scenario = best_match.scenario
            final_confidence = best_match.confidence
            logger.info(
                "VLM final scenario selected",
                extra=log_context(
                    "vlm.final_selection",
                    final_scenario=str(final_scenario) if final_scenario else "None",
                    final_confidence=str(final_confidence)
                    if final_confidence is not None
                    else "None",
                    matched_scenarios=[
                        {"scenario": s.scenario, "confidence": s.confidence}
                        for s in matched_scenarios
                    ],
                    all_scenarios=[
                        {
                            "scenario": s.scenario,
                            "matched": s.matched,
                            "confidence": s.confidence,
                            "reason": s.reason[:100] if s.reason else "",
                        }
                        for s in scenarios_results
                    ],
                ),
            )
        else:
            # No fault scenarios matched — engine will default to "None of the above"
            logger.info(
                "VLM no scenario matched",
                extra=log_context(
                    "vlm.no_match",
                    all_scenarios=[
                        {
                            "scenario": s.scenario,
                            "matched": s.matched,
                            "confidence": s.confidence,
                            "reason": s.reason[:100] if s.reason else "",
                        }
                        for s in scenarios_results
                    ],
                ),
            )
            # No fault scenarios matched — engine will default to "None of the above"
            final_scenario = None
            final_confidence = None

        return VlmAnalysisResult(
            is_cgm_device_present=True,
            scenarios=scenarios_results,
            final_scenario=final_scenario,
            final_confidence=final_confidence,
            model_name=self.settings.vlm_model,
            prompt_version="application-failure-multi-turn-v1",
            source="qwen-vl",
        )

    async def analyze_glucose_readings(
        self, image_refs: list[str]
    ) -> VlmAnalysisResult:
        started = time.perf_counter()
        logger.info(
            "Glucose reading VLM analysis started",
            extra=log_context(
                "vlm.glucose_started",
                image_count=len(image_refs),
                model=self.settings.vlm_model,
            ),
        )
        if not self._can_call_live_model(image_refs):
            result = fallback_glucose_analysis(
                image_refs, model_name=self.settings.vlm_model
            )
            logger.info(
                "Glucose reading VLM fallback used",
                extra=log_context(
                    "vlm.fallback_used",
                    duration_ms=current_millis(started),
                    image_count=len(image_refs),
                    source=result.source,
                    reason="live_model_unavailable",
                ),
            )
            return result

        last_error: Exception | None = None
        for attempt in range(max(1, self.settings.vlm_max_retries)):
            try:
                result = await asyncio.to_thread(
                    self._call_live_glucose_model, image_refs
                )
                logger.info(
                    "Glucose reading VLM analysis completed",
                    extra=log_context(
                        "vlm.glucose_completed",
                        duration_ms=current_millis(started),
                        image_count=len(image_refs),
                        source=result.source,
                        reading_count=len(result.glucose_readings or []),
                    ),
                )
                return result
            except Exception as exc:  # pragma: no cover
                last_error = exc
                logger.error(
                    "Glucose reading VLM attempt failed",
                    extra=log_context(
                        "vlm.glucose_attempt_failed",
                        attempt=attempt + 1,
                        max_retries=self.settings.vlm_max_retries,
                        error_type=type(exc).__name__,
                    ),
                )

        logger.error(
            "Glucose reading VLM failed after retries",
            extra=log_context(
                "vlm.glucose_failed",
                duration_ms=current_millis(started),
                image_count=len(image_refs),
                error_type=type(last_error).__name__ if last_error else "unknown",
                error_message=str(last_error) if last_error else "",
            ),
        )
        detail = str(last_error) if last_error else "unknown VLM failure"
        raise VlmRequestError(
            f"Live glucose VLM request failed after {max(1, self.settings.vlm_max_retries)} attempt(s): "
            f"{type(last_error).__name__ if last_error else 'UnknownError'}: {detail or 'no details returned'}"
        ) from last_error

    def _call_live_glucose_model(self, image_refs: list[str]) -> VlmAnalysisResult:
        from openai import OpenAI

        logger.info(
            "Live glucose VLM request started",
            extra=log_context(
                "vlm.glucose_live_started", model=self.settings.vlm_model
            ),
        )

        client = OpenAI(
            api_key=self.settings.dashscope_api_key,
            base_url=self.settings.vlm_base_url,
            timeout=self.settings.vlm_request_timeout_seconds,
            # Retry in analyze_glucose_readings so each attempt and the final
            # error are observable; do not hide a long SDK retry loop here.
            max_retries=0,
        )
        content: list[dict[str, Any]] = [
            {"type": "text", "text": self.settings.vlm_system_prompt_glucose}
        ]
        for image_url in _resolve_image_urls(image_refs):
            content.append({"type": "image_url", "image_url": {"url": image_url}})

        response = client.chat.completions.create(
            model=self.settings.vlm_model,
            messages=[{"role": "user", "content": content}],
            response_format={"type": "json_object"},
        )
        raw_content = response.choices[0].message.content or "{}"
        parsed = VlmAnalysisResult.model_validate_json(raw_content)
        parsed.model_name = self.settings.vlm_model
        parsed.prompt_version = "glucose-readings-v1"
        parsed.source = "qwen-vl"
        return parsed


def fallback_vlm_analysis(
    image_refs: list[str], *, model_name: str = "deterministic-fallback"
) -> VlmAnalysisResult:
    text = " ".join(image_refs).lower()
    is_present = bool(image_refs)
    is_fraud = False

    if any(
        token in text
        for token in ("landscape", "unrelated", "black", "empty", "invalid")
    ):
        is_present = False
    if any(token in text for token in ("reproduced", "screen", "fraud")):
        is_fraud = True

    # Determine matched scenario
    matched_scenario = None
    confidence = 0.0
    reason = "No application-failure visual defect was identified."

    if is_present and not is_fraud:
        if "assembly" in text:
            matched_scenario = "Assembly failed"
            confidence = 8.5
            reason = "Applicator button pressed but needle not released."
        elif "needle" in text or "retention" in text:
            matched_scenario = "Guiding needle retention"
            confidence = 8.5
            reason = "Soft probe retained inside needle."
        elif "electrode" in text or "exposed" in text:
            matched_scenario = "Exposed Electrodes"
            confidence = 8.5
            reason = "Electrode wire bent outside shell."
        elif (
            "adhesive" in text
            or "patch" in text
            or "detached" in text
            or "peeled" in text
        ):
            matched_scenario = "Adhesive detaching"
            confidence = 8.5
            reason = "Glue layer detached from tape."
        elif "broken" in text or "damage" in text or "crack" in text:
            matched_scenario = "Implanter damage"
            confidence = 8.5
            reason = "Implanter casing cracked."
        else:
            matched_scenario = None
            confidence = 0.0
            reason = "No specific application-failure visual defect was identified."

    scenarios_results = [
        VlmScenarioMatch(
            scenario="Assembly failed",
            matched=matched_scenario == "Assembly failed",
            confidence=8.5 if matched_scenario == "Assembly failed" else 0.0,
            reason=reason
            if matched_scenario == "Assembly failed"
            else "Applicator button functions normally.",
        ),
        VlmScenarioMatch(
            scenario="Guiding needle retention",
            matched=matched_scenario == "Guiding needle retention",
            confidence=8.5 if matched_scenario == "Guiding needle retention" else 0.0,
            reason=reason
            if matched_scenario == "Guiding needle retention"
            else "Guiding needle fully retracted.",
        ),
        VlmScenarioMatch(
            scenario="Exposed Electrodes",
            matched=matched_scenario == "Exposed Electrodes",
            confidence=8.5 if matched_scenario == "Exposed Electrodes" else 0.0,
            reason=reason
            if matched_scenario == "Exposed Electrodes"
            else "No exposed electrode wire.",
        ),
        VlmScenarioMatch(
            scenario="Adhesive detaching",
            matched=matched_scenario == "Adhesive detaching",
            confidence=8.5 if matched_scenario == "Adhesive detaching" else 0.0,
            reason=reason
            if matched_scenario == "Adhesive detaching"
            else "Adhesive layer intact.",
        ),
        VlmScenarioMatch(
            scenario="Implanter damage",
            matched=matched_scenario == "Implanter damage",
            confidence=8.5 if matched_scenario == "Implanter damage" else 0.0,
            reason=reason
            if matched_scenario == "Implanter damage"
            else "No structural crack found.",
        ),
    ]

    return VlmAnalysisResult(
        model_name=model_name,
        is_cgm_device_present=is_present,
        is_reproduced_photo=is_fraud,
        needle_exposed="exposed" in text or "needle" in text,
        adhesive_detached="adhesive" in text or "detached" in text,
        implanter_damage="broken" in text or "damage" in text,
        scenarios=scenarios_results,
        final_scenario=matched_scenario,
        final_confidence=confidence,
    )


def fallback_glucose_analysis(
    image_refs: list[str], *, model_name: str = "deterministic-fallback"
) -> VlmAnalysisResult:
    import re

    logger.info(
        "Fallback glucose analysis started",
        extra=log_context(
            "vlm.glucose_fallback_started",
            image_count=len(image_refs),
            model=model_name,
        ),
    )
    readings = []
    default_vals = [(4.0, "CGM"), (6.0, "BGM"), (3.0, "CGM"), (4.0, "BGM")]
    for idx, ref in enumerate(image_refs):
        if ref.startswith("data:image/"):
            text = ""
            is_val = True
            is_rep = False
            val, dtype = default_vals[idx % 4]
        else:
            text = ref.lower()
            is_val = not any(
                token in text for token in ("invalid", "unreadable", "empty", "black")
            )
            is_rep = any(token in text for token in ("reproduced", "screen", "fraud"))

            val, dtype = default_vals[idx % 4]
            match = re.search(r"(\d+\.\d+|\d+)", ref)
            if match:
                val = float(match.group(1))

        readings.append(
            GlucoseReading(
                value=val if is_val else None,
                device_type=dtype,
                unit="mmol/L",
                is_valid=is_val,
                is_reproduced=is_rep,
            )
        )
    result = VlmAnalysisResult(
        model_name=model_name, source="fallback", glucose_readings=readings
    )
    logger.info(
        "Fallback glucose analysis completed",
        extra=log_context(
            "vlm.glucose_fallback_completed",
            image_count=len(image_refs),
            reading_count=len(result.glucose_readings or []),
            model=model_name,
        ),
    )
    return result


def _resolve_image_urls(image_refs: list[str]) -> list[str]:
    urls: list[str] = []
    for ref in image_refs:
        if ref.startswith("data:image/") or ref.startswith(("http://", "https://")):
            urls.append(ref)
            continue

        if "cgm-bgm-pair" in ref or "implant-photo" in ref:
            logger.info(
                "Skipping live VLM resolution for mock reference",
                extra=log_context("vlm.mock_ref_skipped"),
            )
            continue

        # Try resolving the path (robust search under CWD and backend/)
        path = Path(ref)
        if not path.is_file():
            alt_path = Path("backend") / ref
            if alt_path.is_file():
                path = alt_path

        if path.is_file():
            try:
                mime = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
                encoded = base64.b64encode(path.read_bytes()).decode("ascii")
                urls.append(f"data:{mime};base64,{encoded}")
            except Exception as e:
                logger.error(
                    "Failed to read and encode VLM image file",
                    extra=log_context(
                        "vlm.image_file_encode_failed",
                        error_type=type(e).__name__,
                    ),
                )
        else:
            logger.error(
                "VLM image reference not found or invalid",
                extra=log_context("vlm.image_ref_invalid", cwd=str(Path.cwd())),
            )

    return urls


def vlm_result_from_json(value: str | dict[str, Any]) -> VlmAnalysisResult:
    if isinstance(value, str):
        return VlmAnalysisResult.model_validate(json.loads(value))
    return VlmAnalysisResult.model_validate(value)
