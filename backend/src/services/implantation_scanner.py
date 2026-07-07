"""Implantation-failure scanner: detector → judger pipeline."""

from __future__ import annotations

import asyncio
import base64
import io
import logging
from pathlib import Path
import time
from typing import Any

from PIL import Image, ImageOps

from src.core.config import get_settings
from src.core.logging import current_millis, log_context
from src.scanner import ImplantationScanner
from src.scanner.detector import DetectorPipeline

logger = logging.getLogger(__name__)

# ── Log-safe helpers ──────────────────────────────────────────────────────────

_REF_TRUNCATE_LEN = 80


def _log_safe_ref(image_ref: str) -> str:
    """Return image_ref truncated if it's a long data URL, else as-is."""
    if image_ref.startswith("data:") and len(image_ref) > _REF_TRUNCATE_LEN:
        return image_ref[:_REF_TRUNCATE_LEN] + "..."
    return image_ref


# Lazy singleton instances — avoid heavy init at module-import time.
_scanner_instance: ImplantationScanner | None = None
_detector_instance: DetectorPipeline | None = None


def _get_scanner() -> ImplantationScanner:
    global _scanner_instance
    if _scanner_instance is None:
        settings = get_settings()
        _scanner_instance = ImplantationScanner(
            settings,
            ref_dir=settings.scanner_ref_dir,
            templates_dir=settings.scanner_templates_dir,
        )
    return _scanner_instance


def _get_detector() -> DetectorPipeline:
    global _detector_instance
    if _detector_instance is None:
        settings = get_settings()
        _detector_instance = DetectorPipeline(settings)
    return _detector_instance


def _encode_image_ref(image_ref: str) -> tuple[str, str] | None:
    """Encode an image reference to (b64_data, media_type). Returns None on failure."""
    try:
        if not image_ref.startswith("data:") and (
            image_ref.startswith("/") or Path(image_ref).exists()
        ):
            from src.scanner.cache import encode_and_resize_image

            return encode_and_resize_image(Path(image_ref), max_side=1600, quality=80)
        if image_ref.startswith("data:"):
            header, raw_b64 = image_ref.split(",", 1)
            raw_bytes = base64.b64decode(raw_b64)
            with Image.open(io.BytesIO(raw_bytes)) as img:
                img = ImageOps.exif_transpose(img)
                img.thumbnail((1600, 1600))
                if img.mode != "RGB":
                    img = img.convert("RGB")
                buffer = io.BytesIO()
                img.save(buffer, format="JPEG", quality=80, optimize=True)
                resized_b64 = base64.b64encode(buffer.getvalue()).decode("utf-8")
            return resized_b64, "image/jpeg"
        if "," in image_ref:
            header, b64_data = image_ref.split(",", 1)
            media_type = header.split(";")[0].replace("data:", "")
            return b64_data, media_type
        return image_ref, "image/jpeg"
    except (OSError, ValueError) as exc:
        logger.error(
            "Image encoding failed",
            extra=log_context(
                "scanner.encode_failed",
                image_ref=_log_safe_ref(image_ref),
                error=str(exc),
            ),
        )
        return None


async def scan_implantation_photos(image_refs: list[str]) -> list[dict[str, Any]]:
    """Run the detector → judger pipeline on uploaded photos.

    All user images of the same device are batched into a single detector
    call, then a single judger call per candidate scenario.  This gives the
    VLM full visual context (e.g. two different angles of the same defect)
    while reducing API costs.

    Returns a list with exactly one result dict per device.
    The dict retains the same per-result structure for backward compat:
      {
        "image": first_image_ref,
        "predicted_scenario_id": ...,
        "predicted_name": ...,
        ...
      }
    """
    settings = get_settings()

    if not settings.dashscope_api_key or not image_refs:
        logger.info(
            "Implantation scanner skipped",
            extra=log_context(
                "scanner.implantation_skipped",
                image_count=len(image_refs),
                api_key_configured=bool(settings.dashscope_api_key),
            ),
        )
        return []

    started = time.perf_counter()

    # 1. Encode all images — partial failures are tolerated
    encoded_images: list[tuple[str, str, str]] = []  # (b64, media_type, ref)
    encode_errors: list[dict[str, Any]] = []
    for ref in image_refs:
        encoded = _encode_image_ref(ref)
        if encoded is None:
            encode_errors.append({"image_ref": ref, "error": "encode_failed"})
        else:
            b64, mtype = encoded
            encoded_images.append((b64, mtype, ref))

    if not encoded_images:
        logger.error(
            "All implantation photos failed encoding",
            extra=log_context(
                "scanner.all_encode_failed",
                image_count=len(image_refs),
                error_count=len(encode_errors),
            ),
        )
        return [
            {
                "image": image_refs[0] if image_refs else "",
                "predicted_scenario_id": None,
                "predicted_name": "评估失败",
                "predicted_anomaly": False,
                "top_score": None,
                "confidence": 0,
                "decision_reason": "All images failed encoding.",
                "scenario_results": [],
                "image_errors": encode_errors,
                "latency_sec": 0,
                "success": False,
            }
        ]

    if encode_errors:
        logger.warning(
            "Some implantation photos failed encoding, proceeding with partial set",
            extra=log_context(
                "scanner.partial_encode",
                total=len(image_refs),
                encoded=len(encoded_images),
                failed=len(encode_errors),
            ),
        )

    try:
        scanner = _get_scanner()
        detector = _get_detector()

        # 2. Run detector once with all images
        candidates = await asyncio.to_thread(detector.run, encoded_images)

        if not candidates:
            logger.info(
                "Detector returned no candidates; treating as no implantation failure",
                extra=log_context(
                    "scanner.detector_empty", image_count=len(encoded_images)
                ),
            )
            return [
                {
                    "image": encoded_images[0][2],
                    "predicted_scenario_id": None,
                    "predicted_name": "未识别/正常",
                    "predicted_anomaly": False,
                    "top_score": None,
                    "confidence": 0,
                    "decision_reason": "Detector found no matching failure scenarios.",
                    "scenario_results": [],
                    "image_errors": encode_errors or None,
                    "latency_sec": 0,
                    "success": True,
                }
            ]

        # 3. Run judger on candidates (parallel per scenario)
        candidate_ids = [c["scenario_id"] for c in candidates]
        scanner_result = await asyncio.to_thread(
            scanner._run_judger_on_candidates,  # type: ignore[arg-type]
            encoded_images,
            candidate_ids,
        )

        # 4. Aggregate
        from src.scanner.aggregation import aggregate_scenario_results

        aggregate = aggregate_scenario_results(scanner_result)

        logger.info(
            "Implantation scanner pipeline completed",
            extra=log_context(
                "scanner.pipeline_completed",
                duration_ms=current_millis(started),
                image_count=len(image_refs),
            ),
        )

        result = {
            "image": encoded_images[0][2],
            "predicted_scenario_id": aggregate["predicted_scenario_id"],
            "predicted_name": aggregate["predicted_name"],
            "predicted_anomaly": aggregate["predicted_scenario_id"] is not None,
            "top_score": aggregate["top_score"],
            "confidence": aggregate["confidence"],
            "decision_reason": aggregate["decision_reason"],
            "scenario_results": scanner_result,
            "image_errors": encode_errors or None,
            "latency_sec": 0,
            "success": True,
        }
        return [result]

    except Exception as exc:
        logger.exception(
            "Implantation scanner pipeline failed",
            extra=log_context(
                "scanner.pipeline_failed",
                duration_ms=current_millis(started),
                image_count=len(image_refs),
                error_type=type(exc).__name__,
            ),
        )
        return []
