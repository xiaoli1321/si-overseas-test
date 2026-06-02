from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ChatMessageResponse(BaseModel):
    id: str
    session_id: str
    role: str
    content: str
    options: list[dict[str, Any]] | None = None
    created_at: datetime = Field(serialization_alias="createdAt")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    @field_validator("id", "session_id", mode="before")
    @classmethod
    def coerce_to_str(cls, v: Any) -> str:
        return str(v) if v is not None else v


class ChatSessionResponse(BaseModel):
    id: str
    title: str
    created_at: datetime = Field(serialization_alias="createdAt")
    updated_at: datetime = Field(serialization_alias="updatedAt")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    @field_validator("id", mode="before")
    @classmethod
    def coerce_to_str(cls, v: Any) -> str:
        return str(v) if v is not None else v


class ChatSessionDetailResponse(BaseModel):
    id: str
    title: str
    created_at: datetime = Field(serialization_alias="createdAt")
    updated_at: datetime = Field(serialization_alias="updatedAt")
    messages: list[ChatMessageResponse] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    @field_validator("id", mode="before")
    @classmethod
    def coerce_to_str(cls, v: Any) -> str:
        return str(v) if v is not None else v


class CreateChatSessionRequest(BaseModel):
    id: str
    title: str = "New device judgment"


class SendMessageRequest(BaseModel):
    id: str
    role: str
    content: str
    options: list[dict[str, Any]] | None = None


class CreateChatTurnRequest(BaseModel):
    id: str
    assistant_id: str = Field(
        serialization_alias="assistantId",
        validation_alias="assistantId",
    )
    content: str

    model_config = ConfigDict(populate_by_name=True)


class ChatTurnResponse(BaseModel):
    user_message: ChatMessageResponse = Field(serialization_alias="userMessage")
    assistant_message: ChatMessageResponse = Field(
        serialization_alias="assistantMessage"
    )

    model_config = ConfigDict(populate_by_name=True)


class UpdateChatSessionRequest(BaseModel):
    title: str
