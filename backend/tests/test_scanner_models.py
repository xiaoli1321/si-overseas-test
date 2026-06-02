"""Unit tests for scanner pydantic models."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.scanner.models import (
    ScenarioEvaluation,
)
from src.schemas.domain import ImplantationScanResult, ScenarioScore


class TestScenarioEvaluation:
    """Tests for ScenarioEvaluation model creation and defaults."""

    def test_default_values(self) -> None:
        """All default values should be set correctly for a valid model."""
        model = ScenarioEvaluation(scenario_id="test_scenario")
        assert model.scenario_id == "test_scenario"
        assert model.score == 0
        assert model.is_match is False
        assert model.core_features_hit == []
        assert model.exclusion_features_hit == []
        assert model.different_features == []
        assert model.image_quality == "medium"
        assert model.ambiguity_level == "medium"
        assert model.reasoning == ""

    def test_explicit_values(self) -> None:
        """Model should accept and store all explicit fields."""
        model = ScenarioEvaluation(
            scenario_id="assembly_failure",
            score=8,
            is_match=True,
            core_features_hit=["黑色空洞", "无凸出物"],
            exclusion_features_hit=["金属凸出"],
            different_features=["无白色导引针"],
            image_quality="clear",
            ambiguity_level="low",
            reasoning="High match with positive rules.",
        )
        assert model.scenario_id == "assembly_failure"
        assert model.score == 8
        assert model.is_match is True
        assert model.core_features_hit == ["黑色空洞", "无凸出物"]
        assert model.exclusion_features_hit == ["金属凸出"]
        assert model.different_features == ["无白色导引针"]
        assert model.image_quality == "clear"
        assert model.ambiguity_level == "low"
        assert model.reasoning == "High match with positive rules."

    def test_score_below_minimum_raises_error(self) -> None:
        """Score below 0 should raise ValidationError (Pydantic ge=0)."""
        with pytest.raises(ValidationError):
            ScenarioEvaluation(scenario_id="test", score=-5)

    def test_score_above_maximum_raises_error(self) -> None:
        """Score above 10 should raise ValidationError (Pydantic le=10)."""
        with pytest.raises(ValidationError):
            ScenarioEvaluation(scenario_id="test", score=15)

    def test_score_valid_range(self) -> None:
        """Score values within 0-10 should be accepted unchanged."""
        for valid_score in (0, 5, 10):
            model = ScenarioEvaluation(scenario_id="test", score=valid_score)
            assert model.score == valid_score

    def test_invalid_image_quality(self) -> None:
        """Invalid image_quality literal should raise ValidationError."""
        with pytest.raises(ValidationError):
            ScenarioEvaluation(scenario_id="test", image_quality="blurry")  # type: ignore[arg-type]

    def test_invalid_ambiguity_level(self) -> None:
        """Invalid ambiguity_level literal should raise ValidationError."""
        with pytest.raises(ValidationError):
            ScenarioEvaluation(scenario_id="test", ambiguity_level="unknown")  # type: ignore[arg-type]

    def test_missing_scenario_id(self) -> None:
        """Model creation without scenario_id should raise ValidationError."""
        with pytest.raises(ValidationError):
            ScenarioEvaluation()  # type: ignore[call-arg]



class TestScenarioScore:
    """Tests for domain ScenarioScore model."""

    def test_all_required_fields(self) -> None:
        """All required fields should be set correctly."""
        model = ScenarioScore(
            scenario_id="test_id",
            scenario_name="测试 / Test",
            score=8,
            is_match=True,
            confidence=75,
        )
        assert model.scenario_id == "test_id"
        assert model.scenario_name == "测试 / Test"
        assert model.score == 8
        assert model.is_match is True
        assert model.confidence == 75
        assert model.core_features_hit == []
        assert model.exclusion_features_hit == []
        assert model.reasoning == ""

    def test_explicit_values_with_optionals(self) -> None:
        """Optional fields should be accepted."""
        model = ScenarioScore(
            scenario_id="test_id",
            scenario_name="测试 / Test",
            score=8,
            is_match=True,
            confidence=75,
            core_features_hit=["feature_a"],
            exclusion_features_hit=["excl_x"],
            reasoning="High confidence match.",
        )
        assert model.core_features_hit == ["feature_a"]
        assert model.exclusion_features_hit == ["excl_x"]
        assert model.reasoning == "High confidence match."

    def test_missing_required_field_raises_error(self) -> None:
        """Missing required fields should raise ValidationError."""
        with pytest.raises(ValidationError):
            ScenarioScore(scenario_id="test_id")  # type: ignore[call-arg]

    def test_score_below_zero_raises_error(self) -> None:
        """Score below 0 should raise ValidationError."""
        with pytest.raises(ValidationError):
            ScenarioScore(scenario_id="t", scenario_name="T", score=-1, is_match=False, confidence=0)

    def test_score_above_ten_raises_error(self) -> None:
        """Score above 10 should raise ValidationError."""
        with pytest.raises(ValidationError):
            ScenarioScore(scenario_id="t", scenario_name="T", score=11, is_match=False, confidence=0)

    def test_confidence_below_zero_raises_error(self) -> None:
        """Confidence below 0 should raise ValidationError."""
        with pytest.raises(ValidationError):
            ScenarioScore(scenario_id="t", scenario_name="T", score=5, is_match=False, confidence=-1)

    def test_confidence_above_one_hundred_raises_error(self) -> None:
        """Confidence above 100 should raise ValidationError."""
        with pytest.raises(ValidationError):
            ScenarioScore(scenario_id="t", scenario_name="T", score=5, is_match=False, confidence=101)


class TestImplantationScanResult:
    """Tests for domain ImplantationScanResult model creation and serialization."""

    def test_default_values(self) -> None:
        """Default values should be set correctly."""
        result = ImplantationScanResult(image_name="test.jpg")
        assert result.image_name == "test.jpg"
        assert result.predicted_scenario_id is None
        assert result.predicted_name == ""
        assert result.top_score is None
        assert result.confidence == 0
        assert result.scenario_scores == []
        assert result.decision_reason == ""
        assert result.latency_sec == 0.0

    def test_explicit_values(self) -> None:
        """Model should accept all explicit fields."""
        scores = [
            ScenarioScore(
                scenario_id="assembly_failure",
                scenario_name="拾取失败 / Assembly failure",
                score=8,
                is_match=True,
                confidence=75,
            ),
        ]
        result = ImplantationScanResult(
            image_name="test.jpg",
            predicted_scenario_id="assembly_failure",
            predicted_name="拾取失败 / Assembly failure",
            top_score=8,
            confidence=75,
            scenario_scores=scores,
            decision_reason="最高置信度小类为 拾取失败 / Assembly failure，置信度 75%。",
            latency_sec=1.23,
        )
        assert result.image_name == "test.jpg"
        assert result.predicted_scenario_id == "assembly_failure"
        assert result.top_score == 8
        assert result.confidence == 75
        assert result.decision_reason == "最高置信度小类为 拾取失败 / Assembly failure，置信度 75%。"
        assert result.latency_sec == 1.23
        assert len(result.scenario_scores) == 1

    def test_serialization_to_dict(self) -> None:
        """Model should serialize to dict correctly."""
        result = ImplantationScanResult(
            image_name="photo.jpg",
            predicted_scenario_id="guide_needle_retention",
            predicted_name="导引针滞留 / Guide needle retention",
            top_score=9,
            confidence=85,
        )
        data = result.model_dump()
        assert data["image_name"] == "photo.jpg"
        assert data["predicted_scenario_id"] == "guide_needle_retention"
        assert data["top_score"] == 9
        assert data["confidence"] == 85
        assert data["scenario_scores"] == []

    def test_serialization_to_json(self) -> None:
        """Model should serialize to JSON string correctly."""
        result = ImplantationScanResult(image_name="test.jpg", predicted_name="测试")
        json_str = result.model_dump_json()
        assert '"predicted_name":"测试"' in json_str
        assert '"confidence":0' in json_str

    def test_round_trip(self) -> None:
        """Model should survive a serialize-then-deserialize round trip."""
        original = ImplantationScanResult(
            image_name="photo.jpg",
            predicted_scenario_id="early_launches",
            predicted_name="发射器提前发射 / Early launches",
            top_score=7,
            confidence=60,
            decision_reason="Match found.",
        )
        data = original.model_dump()
        restored = ImplantationScanResult(**data)
        assert restored.predicted_scenario_id == original.predicted_scenario_id
        assert restored.top_score == original.top_score
        assert restored.confidence == original.confidence
        assert restored.decision_reason == original.decision_reason
