"""Pydantic models for scenario evaluation results."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class DetectorCategory(BaseModel):
    """A single matched category from the multi-class detector."""

    scenario_id: str = Field(description="故障小类 ID，如 assembly_failure")
    score: int = Field(default=0, ge=0, le=10, description="0-10 匹配分，越高越符合")
    reasoning: str = Field(default="", description="判定依据")
    responsibility: str = Field(
        default="", description="判责分类：产品本身损坏 或 用户操作问题"
    )


class DetectorOutput(BaseModel):
    """Wrapper model for detector structured output — LangChain requires a single model class."""

    categories: list[DetectorCategory] = Field(
        default_factory=list,
        description="Detected categories from multi-class screening",
    )


class ScenarioEvaluation(BaseModel):
    """Evaluation result for a single implantation-failure scenario."""

    scenario_id: str = Field(
        description="当前被评估的小类 ID，必须等于提示词中给出的 scenario_id"
    )
    score: int = Field(
        default=0, ge=0, le=10, description="0-10 的匹配分，越高表示越符合当前小类"
    )
    is_match: bool = Field(
        default=False, description="是否属于当前小类，通常 score >= threshold 时为 True"
    )
    core_features_hit: list[str] = Field(
        default_factory=list, description="待测图命中的当前小类核心正例证据"
    )
    exclusion_features_hit: list[str] = Field(
        default_factory=list, description="命中的排他、易混或反证特征"
    )
    different_features: list[str] = Field(
        default_factory=list, description="与当前小类不匹配或证据不足的关键差异"
    )
    image_quality: Literal["clear", "medium", "poor"] = Field(
        default="medium", description="待测图质量"
    )
    ambiguity_level: Literal["low", "medium", "high"] = Field(
        default="medium", description="当前小类判定歧义程度"
    )
    reasoning: str = Field(
        default="", description="简洁说明分数和结论依据，不输出冗长思考过程"
    )
    responsibility: str = Field(
        default="", description="判责分类：产品本身损坏 或 用户操作问题"
    )
