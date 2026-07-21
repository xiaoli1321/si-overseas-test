from datetime import UTC, datetime
import mimetypes
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import Base


def utc_now() -> datetime:
    return datetime.now(UTC)


class Distributor(Base):
    """经销商表：存储经销商名称及类型"""

    __tablename__ = "distributors"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    distributor_type: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


class User(Base):
    """用户表：存储系统登录账号、角色（如 dealer 经销商、admin 管理员）及所属经销商"""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    distributor_id: Mapped[int | None] = mapped_column(
        ForeignKey("distributors.id"), index=True, nullable=True
    )
    distributor_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    username: Mapped[str] = mapped_column(
        String(100), unique=True, index=True, nullable=False
    )
    password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), default="dealer", nullable=False)
    created_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), index=True, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    distributor: Mapped[Distributor | None] = relationship()

    @property
    def email(self) -> str:
        return self.username

    @email.setter
    def email(self, value: str) -> None:
        self.username = value


class Threshold(Base):
    """阈值配置表：存储每个用户/角色生效的判定规则阈值参数版本及配置 JSON 串"""

    __tablename__ = "thresholds"
    __table_args__ = (
        UniqueConstraint("user_id", "version", name="uq_threshold_user_version"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), index=True, nullable=False
    )
    config_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, index=True, nullable=False
    )
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)
    restored_from: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    @property
    def is_hidden(self) -> bool:
        return self.is_deleted

    @is_hidden.setter
    def is_hidden(self, value: bool) -> None:
        self.is_deleted = value

    @property
    def config(self) -> dict[str, Any]:
        return self.config_json

    @config.setter
    def config(self, value: dict[str, Any]) -> None:
        self.config_json = value


class BatchTask(Base):
    """批量诊断任务表：存储同故障批次运行的任务状态（成功/失败数、总数、进度等）"""

    __tablename__ = "batch_tasks"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), index=True, nullable=False
    )
    fault_category: Mapped[str] = mapped_column(String(50), nullable=False)
    total_count: Mapped[int] = mapped_column(Integer, nullable=False)
    success_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(
        String(50), default="pending", index=True, nullable=False
    )
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    records: Mapped[list["DetectRecord"]] = relationship(back_populates="batch_task")


class DetectRecord(Base):
    """故障诊断记录表：存储每个设备（SN）的诊断主分类、子分类、判定结论及规则匹配证据链"""

    __tablename__ = "detect_records"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    distributor_id: Mapped[int | None] = mapped_column(
        ForeignKey("distributors.id"), index=True, nullable=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), index=True, nullable=False
    )
    batch_task_id: Mapped[int | None] = mapped_column(
        ForeignKey("batch_tasks.id"), index=True, nullable=True
    )
    serial_no: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    source: Mapped[str] = mapped_column(
        String(20), default="web", nullable=False, index=True
    )
    device_type: Mapped[str] = mapped_column(String(100), nullable=False)
    fault_category: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    fault_subtype: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), default="pending", index=True, nullable=False
    )
    verdict: Mapped[str | None] = mapped_column(String(100), nullable=True)
    issue_detected: Mapped[str | None] = mapped_column(String(100), nullable=True)
    reasons: Mapped[str | None] = mapped_column(Text, nullable=True)
    threshold_id: Mapped[int | None] = mapped_column(
        ForeignKey("thresholds.id"), nullable=True
    )
    threshold_snapshot: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True
    )
    adoption_status: Mapped[str] = mapped_column(
        String(20), default="none", nullable=False
    )
    reject_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    adopted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_visible_in_workbench: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    evidence: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    batch_task: Mapped[BatchTask | None] = relationship(back_populates="records")
    distributor: Mapped[Distributor | None] = relationship()

    @property
    def feedback_status(self) -> str:
        return self.adoption_status

    @feedback_status.setter
    def feedback_status(self, value: str) -> None:
        self.adoption_status = value


class OpenApiIdempotencyKey(Base):
    """Deduplicates partner retries before an async detection is scheduled."""

    __tablename__ = "openapi_idempotency_keys"
    __table_args__ = (
        UniqueConstraint("user_id", "idempotency_key", name="uq_openapi_idempotency_user_key"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), index=True, nullable=False
    )
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    detect_record_id: Mapped[int | None] = mapped_column(
        ForeignKey("detect_records.id"), nullable=True
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )


class ChatSession(Base):
    """AI 对话会话表：存储用户与客服诊断助手的多轮对话 Session 主体"""

    __tablename__ = "chat_sessions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), index=True, nullable=False
    )
    title: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    messages: Mapped[list["ChatMessage"]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        order_by=lambda: ChatMessage.created_at,
    )


class ChatMessage(Base):
    """AI 对话消息表：存储多轮会话中的具体每条消息（Role: user/assistant/system, 消息内容，选项推荐）"""

    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("chat_sessions.id", ondelete="CASCADE"), index=True, nullable=False
    )
    role: Mapped[str] = mapped_column(String(100), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    options: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    session: Mapped[ChatSession] = relationship(back_populates="messages")


class UploadedFile(Base):
    """上传文件表：存储用户上传的诊断凭证图片信息（文件名、存储路径、大小、MimeType等）"""

    __tablename__ = "uploaded_files"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), index=True, nullable=False
    )
    detect_record_id: Mapped[int | None] = mapped_column(
        ForeignKey("detect_records.id"), nullable=True
    )
    filename: Mapped[str] = mapped_column(String(100), nullable=False)
    storage_backend: Mapped[str] = mapped_column(
        String(100), default="local", nullable=False
    )
    object_key: Mapped[str] = mapped_column(String(255), nullable=False)
    file_size: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    @property
    def public_url(self) -> str:
        return f"/api/v1/files/{self.id}"

    @property
    def mime_type(self) -> str | None:
        if not self.filename:
            return "application/octet-stream"
        guessed, _ = mimetypes.guess_type(self.filename)
        return guessed or "image/png"


class AuditLog(Base):
    """审计日志表：记录敏感业务操作记录（如阈值修改、用户修改等）"""

    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), index=True, nullable=False
    )
    action: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    target_type: Mapped[str | None] = mapped_column(
        String(80), index=True, nullable=True
    )
    target_id: Mapped[str | None] = mapped_column(
        String(120), index=True, nullable=True
    )
    status: Mapped[str] = mapped_column(
        String(20), default="success", index=True, nullable=False
    )
    event_metadata: Mapped[dict[str, Any] | None] = mapped_column(
        "metadata", JSONB, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
