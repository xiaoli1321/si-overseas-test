import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from src.integrations.vlm import QwenVlClient, fallback_vlm_analysis
from src.rules.engine import run_rules
from src.rules.thresholds import default_thresholds


def _load_cases(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


async def _evaluate_case(case: dict[str, Any], *, live: bool) -> dict[str, Any]:
    image_ref = case["image_path"]
    analysis = await QwenVlClient().analyze_sensor_photos([image_ref]) if live else fallback_vlm_analysis([image_ref])
    result = run_rules(
        fault_category="Application failure",
        device={},
        glucose_series={"points": []},
        alarm={},
        threshold_config=default_thresholds(),
        file_ids=[image_ref, f"{image_ref}#2"],
        vision_analysis=analysis.model_dump(),
    )
    expected_min, expected_max = case["expected_score_range"]
    expected_features = case["expected_features"]
    features = result.evidence["vision"]["features"]
    feature_ok = (
        features["is_cgm_device_present"] == case["expected_cgm_present"]
        and features["is_reproduced_photo"] == case["expected_reproduced"]
        and all(features[key] == value for key, value in expected_features.items())
    )
    score = result.evidence["vision"]["score"]
    score_ok = expected_min <= score <= expected_max
    return {
        "case_id": case["case_id"],
        "ok": feature_ok and score_ok,
        "feature_ok": feature_ok,
        "score_ok": score_ok,
        "score": score,
        "verdict": result.verdict,
        "features": features,
    }


async def _main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate application-failure VLM structured scoring cases.")
    parser.add_argument(
        "--cases",
        default=".trellis/tasks/06-02-vlm-integration/vlm_test_cases.jsonl",
        help="Path to JSONL evaluation cases.",
    )
    parser.add_argument("--live", action="store_true", help="Call the configured VLM instead of deterministic fallback.")
    args = parser.parse_args()

    cases_path = Path(args.cases)
    cases = _load_cases(cases_path)
    results = [await _evaluate_case(case, live=args.live) for case in cases]
    print(json.dumps({"total": len(results), "passed": sum(1 for item in results if item["ok"]), "items": results}, indent=2))
    return 0 if all(item["ok"] for item in results) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(_main()))
