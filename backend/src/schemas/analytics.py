from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class AnalyticsEventRequest(BaseModel):
    event_name: str = Field(validation_alias="eventName")
    source: str | None = None
    properties: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(populate_by_name=True)


class AnalyticsSummaryResponse(BaseModel):
    total: int
    by_event: dict[str, int] = Field(serialization_alias="byEvent")
    by_source: dict[str, int] = Field(serialization_alias="bySource")


# --- Strict Event Property Schemas ---


class EventContextSchema(BaseModel):
    user_id: int = Field(description="User ID")
    username: str = Field(description="Username/Email")
    role: str = Field(description="User role")
    distributor_id: int | None = Field(default=None, description="Distributor ID")
    distributor_name: str | None = Field(default=None, description="Distributor Name")
    channel: Literal["web", "openapi"] = Field(
        default="web", description="Business channel that initiated the event"
    )


class LoginEventProperties(EventContextSchema):
    status: Literal["success", "failure"] = Field(description="Login status")
    fail_reason: Literal["invalid_password", "user_not_found"] | None = Field(
        default=None, description="Failure reason"
    )


class DeviceQueryEventProperties(EventContextSchema):
    entry_source: Literal["shortcut", "recommendation"] = Field(
        default="shortcut", description="Page entry source"
    )
    fault_category: str = Field(
        default="Data accuracy", description="Selected fault category"
    )
    query_type: Literal["single", "batch", "search"] = Field(description="Query type")
    serial_no: str | None = Field(default=None, description="Queried SN")
    batch_count: int = Field(default=1, description="Number of SNs in query")
    query_count: int = Field(default=1, description="Number of SNs queried")
    serial_nos: list[str] = Field(default_factory=list, description="Queried SN list")


class DiagnosisCompletedEventProperties(EventContextSchema):
    record_id: int = Field(description="Diagnosis Record ID")
    serial_no: str = Field(description="Device SN")
    fault_category: str = Field(description="Diagnosed fault category")
    fault_subtype: str | None = Field(
        default=None, description="Diagnosed fault subtype"
    )
    verdict: str = Field(description="Diagnosis verdict decision")
    judgment_source: Literal["AI (VLM)", "Rule Engine"] = Field(
        description="Decision source engine"
    )
    has_images: bool = Field(description="Whether photos were uploaded")


class VerdictAdoptionEventProperties(EventContextSchema):
    record_id: int = Field(description="Diagnosis Record ID")
    serial_no: str = Field(description="Device SN")
    fault_category: str = Field(description="Diagnosed fault category")
    fault_subtype: str | None = Field(
        default=None, description="Diagnosed fault subtype"
    )
    verdict: str = Field(description="Diagnosis verdict decision")
    feedback_status: Literal["adopted", "rejected"] = Field(
        description="Adoption feedback status"
    )
    reject_reason: str | None = Field(
        default=None, description="Feedback reject reason"
    )
