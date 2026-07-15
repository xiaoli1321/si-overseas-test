from datetime import datetime
from typing import Literal, Any

from pydantic import (
    AliasChoices,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


FaultCategory = Literal[
    "Data accuracy", "Sensor falling off", "Sensor Abnormal", "Application failure"
]
AgentIntentType = Literal["fault_category", "other_cgm", "unrelated", "unknown"]
RecordStatus = Literal["pending", "processing", "completed", "failed"]
Verdict = Literal["Replacement Eligible", "Not Eligible", "Under Review"]
FeedbackStatus = Literal["adopted", "rejected", "none"]


class LoginRequest(BaseModel):
    email: str
    password: str


class CreateUserRequest(BaseModel):
    email: str
    password: str = Field(min_length=8, max_length=128)
    role: Literal["manager", "dealer"] = "dealer"
    distributor_name: str = Field(
        min_length=1,
        max_length=100,
        validation_alias=AliasChoices("distributor_name", "distributorName"),
    )

    model_config = ConfigDict(populate_by_name=True)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not normalized:
            raise ValueError("email is required")
        return normalized

    @field_validator("distributor_name")
    @classmethod
    def normalize_distributor_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("distributor_name is required")
        return normalized


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    id: int
    distributor_name: str
    email: str = Field(validation_alias=AliasChoices("email", "username"))
    role: str


class DeviceResponse(BaseModel):
    serial_no: str
    device_type: str
    device_status: int
    activation_status: str
    activated_at: datetime
    wear_days: float
    latest_upload_at: datetime
    service_card_status: str
    fall_off_status: str


class DeviceSearchRequest(BaseModel):
    query: str = Field(
        default="", validation_alias=AliasChoices("query", "keyword", "sn", "serialNo")
    )
    serial_nos: list[str] = Field(
        default_factory=list,
        validation_alias=AliasChoices("serial_nos", "serialNos", "sns"),
    )

    model_config = ConfigDict(populate_by_name=True)

    def search_terms(self) -> list[str]:
        raw_terms = [*self.query.replace(",", "\n").splitlines(), *self.serial_nos]
        terms: list[str] = []
        seen = set()
        for value in raw_terms:
            term = value.strip()
            key = term.upper()
            if not term or key in seen:
                continue
            terms.append(term)
            seen.add(key)
        return terms


class GlucosePoint(BaseModel):
    timestamp: datetime
    glucose: float
    unit: str = "mmol/L"
    alarm_status: int = 0


class AgentClassifyRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)


class AgentClassifyResponse(BaseModel):
    fault_category: FaultCategory | None
    intent_type: AgentIntentType = "unknown"
    confidence: float = 0.0
    message: str
    manual_review: bool
    source: str = "keyword_fallback"
    fallback_used: bool = True


class ThresholdResponse(BaseModel):
    id: int
    version: int
    config: dict
    is_active: bool
    remark: str | None = None
    restored_from: int | None = None
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ThresholdSaveRequest(BaseModel):
    config: dict = Field(default_factory=dict)
    remark: str | None = None

    @model_validator(mode="before")
    @classmethod
    def accept_frontend_profile(cls, data: object) -> object:
        if isinstance(data, dict) and "config" not in data:
            remark = data.get("remark")
            if "rules" in data:
                config_data = {"rules": data["rules"]}
                if "display" in data:
                    config_data["display"] = data["display"]
            else:
                config_data = {
                    k: v
                    for k, v in data.items()
                    if k
                    not in (
                        "remark",
                        "restored_from",
                        "version",
                        "savedAt",
                        "restoredFrom",
                    )
                }
            return {"config": config_data, "remark": remark}
        return data


class ThresholdRollbackRequest(BaseModel):
    remark: str | None = None


class UpdateRemarkRequest(BaseModel):
    remark: str | None = None


class DetectionCreateRequest(BaseModel):
    serial_no: str = Field(validation_alias=AliasChoices("serial_no", "serialNo", "sn"))
    fault_category: FaultCategory = Field(
        validation_alias=AliasChoices("fault_category", "faultCategory")
    )
    file_ids: list[str] = Field(
        default_factory=list, validation_alias=AliasChoices("file_ids", "fileIds")
    )

    model_config = ConfigDict(populate_by_name=True)

    @field_validator("serial_no")
    @classmethod
    def normalize_serial_no(cls, value: str) -> str:
        normalized = value.strip().upper()
        if not normalized:
            raise ValueError("serial_no is required")
        return normalized


class OpenApiDetectionCreateRequest(BaseModel):
    serial_no: str | None = Field(
        default=None, validation_alias=AliasChoices("serial_no", "serialNo", "sn")
    )
    device_name: str | None = Field(
        default=None, validation_alias=AliasChoices("device_name", "deviceName")
    )
    fault_category: FaultCategory = Field(
        validation_alias=AliasChoices("fault_category", "faultCategory")
    )
    file_ids: list[str] | None = Field(
        default_factory=list, validation_alias=AliasChoices("file_ids", "fileIds")
    )
    threshold_config: dict | None = Field(
        default=None, validation_alias=AliasChoices("threshold_config", "thresholdConfig")
    )

    model_config = ConfigDict(populate_by_name=True)

    @field_validator("file_ids", mode="before")
    @classmethod
    def normalize_file_ids(cls, value: object) -> object:
        # OpenAPI callers may explicitly send `fileIds: null`; treat that the
        # same as an omitted field so it follows the curve-only path.
        return [] if value is None else value

    @model_validator(mode="after")
    def normalize_identifier(self) -> "OpenApiDetectionCreateRequest":
        self.serial_no = self.serial_no.strip().upper() if self.serial_no else None
        self.device_name = self.device_name.strip().upper() if self.device_name else None
        if not self.serial_no and not self.device_name:
            raise ValueError("serialNo or deviceName is required")
        if self.threshold_config is not None:
            from src.rules.thresholds import validate_threshold_profile

            try:
                self.threshold_config = validate_threshold_profile(self.threshold_config)
            except ValueError as exc:
                raise ValueError(f"Invalid thresholdConfig: {exc}") from exc
        return self


class BatchDetectionCreateRequest(BaseModel):
    serial_nos: list[str] = Field(
        min_length=1,
        max_length=50,
        validation_alias=AliasChoices("serial_nos", "serialNos", "sns"),
    )
    fault_category: FaultCategory = Field(
        validation_alias=AliasChoices("fault_category", "faultCategory")
    )
    device_files: dict[str, list[str]] | None = Field(
        default=None,
        validation_alias=AliasChoices("device_files", "deviceFiles", "device_files"),
    )

    model_config = ConfigDict(populate_by_name=True)

    @field_validator("serial_nos")
    @classmethod
    def normalize_serials(cls, values: list[str]) -> list[str]:
        normalized = []
        seen = set()
        for value in values:
            serial = value.strip().upper()
            if serial and serial not in seen:
                normalized.append(serial)
                seen.add(serial)
        if not normalized:
            raise ValueError("serial_nos must contain at least one valid SN")
        return normalized


class DetectRecordResponse(BaseModel):
    id: int
    batch_task_id: int | None
    serial_no: str
    device_type: str
    fault_category: str
    fault_subtype: str | None
    status: str
    verdict: str | None
    issue_detected: str | None
    reasons: str | None
    threshold_id: int | None
    threshold_snapshot: dict | None
    feedback_status: str = Field(
        validation_alias=AliasChoices("feedback_status", "adoption_status")
    )
    reject_reason: str | None
    adopted_at: datetime | None = None
    error_message: str | None
    created_at: datetime
    updated_at: datetime
    evidence: dict | None

    model_config = ConfigDict(from_attributes=True)


class BatchTaskResponse(BaseModel):
    id: int
    fault_category: str
    total_count: int
    success_count: int
    failed_count: int
    status: str
    created_at: datetime
    updated_at: datetime
    records: list[DetectRecordResponse] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class FeedbackRequest(BaseModel):
    feedback_status: Literal["adopted", "rejected"] | None = Field(
        default=None, validation_alias=AliasChoices("feedback_status", "feedbackStatus")
    )
    verdict_adoption: Literal["Yes", "No", "Not recorded"] | None = Field(
        default=None,
        validation_alias=AliasChoices("verdictAdoption", "verdict_adoption"),
    )
    reject_reason: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "reject_reason", "rejectReason", "verdictRejectionReason"
        ),
    )

    model_config = ConfigDict(populate_by_name=True)


class UploadedFileResponse(BaseModel):
    id: str
    filename: str
    storage_backend: str
    object_key: str
    public_url: str | None
    mime_type: str | None
    file_size: int | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @field_validator("id", mode="before")
    @classmethod
    def coerce_id_to_str(cls, v: Any) -> str:
        return str(v) if v is not None else v


class DashboardStatsResponse(BaseModel):
    total: int
    allowed: int
    not_allowed: int
    pending: int


class ScenarioScore(BaseModel):
    """Per-scenario score entry within an implantation scan result."""

    scenario_id: str = Field(description="小类 ID")
    scenario_name: str = Field(description="小类名称")
    score: int = Field(ge=0, le=10, description="匹配分 0-10")
    is_match: bool = Field(description="是否匹配当前小类")
    confidence: int = Field(ge=0, le=100, description="置信度 0-100")
    core_features_hit: list[str] = Field(
        default_factory=list, description="命中的核心正例特征"
    )
    exclusion_features_hit: list[str] = Field(
        default_factory=list, description="命中的排他特征"
    )
    reasoning: str = Field(default="", description="评分依据")


class ImplantationScanResult(BaseModel):
    """Aggregated result of a full implantation-failure scanner evaluation."""

    image_name: str = Field(description="待测图片文件名")
    scenario_scores: list[ScenarioScore] = Field(
        default_factory=list, description="所有小类的评分结果"
    )
    predicted_scenario_id: str | None = Field(default=None, description="预测的小类 ID")
    predicted_name: str = Field(default="", description="预测的小类名称")
    top_score: int | None = Field(default=None, ge=0, le=10, description="最高匹配分")
    confidence: int = Field(default=0, ge=0, le=100, description="聚合置信度")
    decision_reason: str = Field(default="", description="判定依据说明")
    latency_sec: float = Field(default=0.0, ge=0, description="扫描耗时（秒）")


class BatchDeleteRequest(BaseModel):
    record_ids: list[int] = Field(
        validation_alias=AliasChoices("record_ids", "recordIds")
    )
