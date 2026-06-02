"""Confidence scoring and result aggregation for scenario evaluations."""

from __future__ import annotations

from typing import Any, Dict, List

_THRESHOLD = 7


def quality_penalty(value: str) -> int:
    return {"clear": 0, "medium": 10, "poor": 20}.get(value, 10)


def ambiguity_penalty(value: str) -> int:
    return {"low": 0, "medium": 10, "high": 20}.get(value, 10)


def compute_scenario_confidence(result: Dict[str, Any]) -> int:
    score = float(result.get("score") or 0)
    is_match = bool(result.get("is_match", False))
    core_features_hit = bool(result.get("core_features_hit"))
    exclusion_features_hit = bool(result.get("exclusion_features_hit"))
    image_quality = str(result.get("image_quality") or "medium")
    ambiguity_level = str(result.get("ambiguity_level") or "high")

    confidence = 50
    confidence += int(score * 5)
    confidence += 15 if core_features_hit else -15
    confidence -= 25 if exclusion_features_hit else 0
    confidence -= quality_penalty(image_quality)
    confidence -= ambiguity_penalty(ambiguity_level)
    if not is_match:
        confidence = int(confidence * 0.3)
    return max(0, min(100, round(confidence)))


def aggregate_scenario_results(
    scenario_results: List[Dict[str, Any]],
) -> Dict[str, Any]:
    successful_results = [
        result for result in scenario_results if result.get("success")
    ]
    if not successful_results:
        return {
            "predicted_scenario_id": None,
            "predicted_name": "评估失败",
            "top_score": None,
            "second_scenario_id": None,
            "second_score": None,
            "confidence": 0,
            "matched_candidates": [],
            "all_scenario_scores": [],
            "decision_reason": "所有小类评估均失败，无法聚合。",
        }

    for result in successful_results:
        result["confidence"] = compute_scenario_confidence(result)

    _amb_level = {"low": 0, "medium": 1, "high": 2}

    ordered = sorted(
        successful_results,
        key=lambda item: (
            float(item.get("confidence") or 0),
            float(item.get("score") or 0),
            -len(item.get("exclusion_features_hit") or []),
            -len(item.get("different_features") or []),
            -_amb_level.get(str(item.get("ambiguity_level") or "high"), 2),
        ),
        reverse=True,
    )
    top_result = ordered[0]
    second_result = ordered[1] if len(ordered) > 1 else None

    any_match = any(
        r.get("is_match")
        and float(r.get("score", 0)) >= float(r.get("threshold", _THRESHOLD))
        for r in successful_results
    )
    if not any_match:
        return {
            "predicted_scenario_id": None,
            "predicted_name": "未识别/正常",
            "top_score": top_result.get("score"),
            "second_scenario_id": None,
            "second_score": None,
            "confidence": 0,
            "matched_candidates": [],
            "all_scenario_scores": [
                {
                    "scenario_id": r["scenario_id"],
                    "scenario_name": r["scenario_name"],
                    "score": r["score"],
                    "confidence": r["confidence"],
                    "is_match": r["is_match"],
                    "success": r["success"],
                }
                for r in ordered
            ],
            "decision_reason": "所有小类均未命中（全部 is_match=false 或 score<阈值），判定为正常或未识别。",
        }

    predicted_scenario_id = top_result["scenario_id"]
    predicted_name = top_result["scenario_name"]
    top_confidence = top_result["confidence"]

    decision_reason = f"最高置信度小类为 {predicted_name}，置信度 {top_confidence}%。"

    return {
        "predicted_scenario_id": predicted_scenario_id,
        "predicted_name": predicted_name,
        "top_score": top_result.get("score"),
        "second_scenario_id": (second_result or {}).get("scenario_id"),
        "second_score": (second_result or {}).get("score"),
        "confidence": top_confidence,
        "matched_candidates": [
            {
                "scenario_id": result["scenario_id"],
                "scenario_name": result["scenario_name"],
                "score": result["score"],
                "confidence": result["confidence"],
            }
            for result in ordered
        ],
        "all_scenario_scores": [
            {
                "scenario_id": result["scenario_id"],
                "scenario_name": result["scenario_name"],
                "score": result["score"],
                "confidence": result["confidence"],
                "is_match": result["is_match"],
                "success": result["success"],
            }
            for result in ordered
        ],
        "decision_reason": decision_reason,
    }
