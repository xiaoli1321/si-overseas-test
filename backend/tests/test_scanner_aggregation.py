"""Unit tests for scanner confidence scoring and result aggregation."""
from __future__ import annotations

import pytest

from src.scanner.aggregation import (
    aggregate_scenario_results,
    ambiguity_penalty,
    compute_scenario_confidence,
    quality_penalty,
)


class TestQualityPenalty:
    """Tests for the quality_penalty helper."""

    def test_clear_quality(self) -> None:
        assert quality_penalty("clear") == 0

    def test_medium_quality(self) -> None:
        assert quality_penalty("medium") == 10

    def test_poor_quality(self) -> None:
        assert quality_penalty("poor") == 20

    def test_unknown_quality(self) -> None:
        assert quality_penalty("unknown") == 10


class TestAmbiguityPenalty:
    """Tests for the ambiguity_penalty helper."""

    def test_low_ambiguity(self) -> None:
        assert ambiguity_penalty("low") == 0

    def test_medium_ambiguity(self) -> None:
        assert ambiguity_penalty("medium") == 10

    def test_high_ambiguity(self) -> None:
        assert ambiguity_penalty("high") == 20

    def test_unknown_ambiguity(self) -> None:
        assert ambiguity_penalty("unknown") == 10


class TestComputeScenarioConfidence:
    """Tests for compute_scenario_confidence with various inputs."""

    def test_high_confidence(self) -> None:
        """Perfect match with clear image and low ambiguity."""
        result: dict = {
            "score": 10,
            "is_match": True,
            "core_features_hit": ["feature_a", "feature_b"],
            "exclusion_features_hit": [],
            "image_quality": "clear",
            "ambiguity_level": "low",
        }
        confidence = compute_scenario_confidence(result)
        # 50 + 10*5 + 15 - 0 - 0 - 0 = 115 -> min(100, 115) = 100
        assert confidence == 100

    def test_high_score_with_exclusion_hit(self) -> None:
        """Exclusion features hit should reduce confidence."""
        result: dict = {
            "score": 9,
            "is_match": True,
            "core_features_hit": ["feature_a"],
            "exclusion_features_hit": ["exclusion_x"],
            "image_quality": "clear",
            "ambiguity_level": "low",
        }
        confidence = compute_scenario_confidence(result)
        # 50 + 9*5 + 15 - 25 - 0 - 0 = 85
        assert confidence == 85

    def test_no_core_features_hit(self) -> None:
        """No core features hit should reduce confidence."""
        result: dict = {
            "score": 6,
            "is_match": True,
            "core_features_hit": [],
            "exclusion_features_hit": [],
            "image_quality": "clear",
            "ambiguity_level": "low",
        }
        confidence = compute_scenario_confidence(result)
        # 50 + 6*5 - 15 - 0 - 0 - 0 = 65
        assert confidence == 65

    def test_poor_quality_and_high_ambiguity(self) -> None:
        """Poor image quality and high ambiguity should reduce confidence."""
        result: dict = {
            "score": 7,
            "is_match": True,
            "core_features_hit": ["feature_a"],
            "exclusion_features_hit": [],
            "image_quality": "poor",
            "ambiguity_level": "high",
        }
        confidence = compute_scenario_confidence(result)
        # 50 + 7*5 + 15 - 0 - 20 - 20 = 60
        assert confidence == 60

    def test_not_match_penalty(self) -> None:
        """is_match=False should heavily penalize confidence (0.3 multiplier)."""
        result: dict = {
            "score": 8,
            "is_match": False,
            "core_features_hit": ["feature_a"],
            "exclusion_features_hit": [],
            "image_quality": "clear",
            "ambiguity_level": "low",
        }
        confidence = compute_scenario_confidence(result)
        # int((50 + 8*5 + 15 - 0 - 0 - 0) * 0.3) = int(105 * 0.3) = int(31.5) = 31
        assert confidence == 31

    def test_score_none(self) -> None:
        """None score should be treated as 0."""
        result: dict = {
            "score": None,
            "is_match": False,
            "core_features_hit": [],
            "exclusion_features_hit": [],
            "image_quality": "medium",
            "ambiguity_level": "high",
        }
        confidence = compute_scenario_confidence(result)
        # int((50 + 0*5 - 15 - 0 - 10 - 20) * 0.3) = int(5 * 0.3) = int(1.5) = 1
        assert confidence == 1

    def test_low_score_no_features(self) -> None:
        """Low score with no features and no match should produce floor confidence."""
        result: dict = {
            "score": 0,
            "is_match": False,
            "core_features_hit": [],
            "exclusion_features_hit": [],
            "image_quality": "poor",
            "ambiguity_level": "high",
        }
        confidence = compute_scenario_confidence(result)
        # (50 + 0 - 15 - 0 - 20 - 20) * 0.3 = (-5)*0.3 = -1.5 -> max(0, -1.5) = 0
        assert confidence == 0

    def test_missing_keys(self) -> None:
        """Missing dict keys should be handled gracefully."""
        result: dict = {}
        confidence = compute_scenario_confidence(result)
        # All defaults applied
        assert 0 <= confidence <= 100

    def test_missing_defaults(self) -> None:
        """Missing keys should fall back to medium image quality and high ambiguity."""
        result: dict = {"score": 5, "is_match": True}
        confidence = compute_scenario_confidence(result)
        # 50 + 5*5 - 15 - 10 - 20 = 50 + 25 - 15 - 10 - 20 = 30
        assert confidence == 30


class TestAggregateScenarioResults:
    """Tests for aggregate_scenario_results with various inputs."""

    def test_empty_input(self) -> None:
        """Empty list should return a no-match result."""
        result = aggregate_scenario_results([])
        assert result["predicted_scenario_id"] is None
        assert result["predicted_name"] == "评估失败"
        assert result["top_score"] is None
        assert result["confidence"] == 0
        assert result["all_scenario_scores"] == []

    def test_all_failed_results(self) -> None:
        """All results with success=False should return no-match."""
        scenarios = [
            {"scenario_id": "s1", "scenario_name": "S1", "score": None, "success": False},
            {"scenario_id": "s2", "scenario_name": "S2", "score": None, "success": False},
        ]
        result = aggregate_scenario_results(scenarios)
        assert result["predicted_scenario_id"] is None
        assert result["predicted_name"] == "评估失败"
        assert result["confidence"] == 0

    def test_single_matching_result(self) -> None:
        """Single successful matching result should be selected."""
        scenarios = [
            {
                "scenario_id": "assembly_failure",
                "scenario_name": "拾取失败 / Assembly failure",
                "score": 8,
                "is_match": True,
                "core_features_hit": ["黑色空洞"],
                "exclusion_features_hit": [],
                "different_features": [],
                "image_quality": "clear",
                "ambiguity_level": "low",
                "success": True,
            },
        ]
        result = aggregate_scenario_results(scenarios)
        assert result["predicted_scenario_id"] == "assembly_failure"
        assert result["confidence"] > 50
        assert result["second_scenario_id"] is None

    def test_multiple_results_selects_top(self) -> None:
        """Multiple successful results should pick the highest confidence."""
        scenarios = [
            {
                "scenario_id": "assembly_failure",
                "scenario_name": "拾取失败 / Assembly failure",
                "score": 8,
                "is_match": True,
                "core_features_hit": ["黑色空洞"],
                "exclusion_features_hit": [],
                "different_features": [],
                "image_quality": "clear",
                "ambiguity_level": "low",
                "success": True,
            },
            {
                "scenario_id": "guide_needle_retention",
                "scenario_name": "导引针滞留 / Guide needle retention",
                "score": 3,
                "is_match": False,
                "core_features_hit": [],
                "exclusion_features_hit": [],
                "different_features": ["白色导引针"],
                "image_quality": "clear",
                "ambiguity_level": "low",
                "success": True,
            },
        ]
        result = aggregate_scenario_results(scenarios)
        assert result["predicted_scenario_id"] == "assembly_failure"
        assert result["second_scenario_id"] == "guide_needle_retention"

    def test_no_match_returns_none(self) -> None:
        """When no scenario has is_match=True above threshold, return none."""
        scenarios = [
            {
                "scenario_id": "assembly_failure",
                "scenario_name": "拾取失败 / Assembly failure",
                "score": 3,
                "is_match": False,
                "core_features_hit": [],
                "exclusion_features_hit": [],
                "different_features": [],
                "image_quality": "medium",
                "ambiguity_level": "high",
                "success": True,
                "threshold": 7,
            },
        ]
        result = aggregate_scenario_results(scenarios)
        assert result["predicted_scenario_id"] is None
        assert result["predicted_name"] == "未识别/正常"
        assert result["confidence"] == 0

    def test_ordering_by_multiple_criteria(self) -> None:
        """Results should be ordered by confidence, then score, then penalties."""
        scenarios = [
            {
                "scenario_id": "s1",
                "scenario_name": "Scenario 1",
                "score": 9,
                "is_match": True,
                "core_features_hit": ["f1"],
                "exclusion_features_hit": [],
                "different_features": [],
                "image_quality": "clear",
                "ambiguity_level": "low",
                "success": True,
            },
            {
                "scenario_id": "s2",
                "scenario_name": "Scenario 2",
                "score": 9,
                "is_match": True,
                "core_features_hit": ["f2"],
                "exclusion_features_hit": [],
                "different_features": ["diff1"],
                "image_quality": "clear",
                "ambiguity_level": "low",
                "success": True,
            },
        ]
        result = aggregate_scenario_results(scenarios)
        # s1 has fewer different_features, should be ranked first
        assert result["all_scenario_scores"][0]["scenario_id"] == "s1"
        assert result["all_scenario_scores"][1]["scenario_id"] == "s2"

    def test_all_scenario_scores_in_output(self) -> None:
        """All successful scenario scores should appear in output."""
        scenarios = [
            {
                "scenario_id": "s1",
                "scenario_name": "S1",
                "score": 8,
                "is_match": True,
                "core_features_hit": ["f1"],
                "exclusion_features_hit": [],
                "different_features": [],
                "image_quality": "clear",
                "ambiguity_level": "low",
                "success": True,
            },
            {
                "scenario_id": "s2",
                "scenario_name": "S2",
                "score": 5,
                "is_match": False,
                "core_features_hit": [],
                "exclusion_features_hit": [],
                "different_features": [],
                "image_quality": "medium",
                "ambiguity_level": "high",
                "success": True,
            },
        ]
        result = aggregate_scenario_results(scenarios)
        assert len(result["all_scenario_scores"]) == 2
        score_ids = {s["scenario_id"] for s in result["all_scenario_scores"]}
        assert score_ids == {"s1", "s2"}
