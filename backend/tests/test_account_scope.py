from types import SimpleNamespace

import pytest
from sqlalchemy import select

from src.core.exceptions import BusinessValidationError, NotFoundError
from src.models.tables import AuditLog, ChatSession, DetectRecord, UploadedFile
from src.repositories.scopes import apply_user_scope, require_user_scope
from src.services.detections import validate_file_ownership


def _sql_text(query: object) -> str:
    return str(query.compile(compile_kwargs={"literal_binds": True}))


def test_apply_user_scope_should_filter_query_by_user_id() -> None:
    query = apply_user_scope(select(DetectRecord), DetectRecord, 42)

    compiled = _sql_text(query)

    assert "detect_records.user_id = 42" in compiled


def test_apply_user_scope_should_filter_chat_queries_by_user_id() -> None:
    query = apply_user_scope(select(ChatSession), ChatSession, 42)

    compiled = _sql_text(query)

    assert "chat_sessions.user_id = 42" in compiled


def test_apply_user_scope_should_filter_uploaded_file_queries_by_user_id() -> None:
    query = apply_user_scope(select(UploadedFile), UploadedFile, 42)

    compiled = _sql_text(query)

    assert "uploaded_files.user_id = 42" in compiled


def test_apply_user_scope_should_filter_audit_log_queries_by_user_id() -> None:
    query = apply_user_scope(select(AuditLog), AuditLog, 42)

    compiled = _sql_text(query)

    assert "audit_logs.user_id = 42" in compiled





def test_require_user_scope_should_allow_same_account_resource() -> None:
    resource = SimpleNamespace(id=10, user_id=7)

    scoped = require_user_scope(resource, 7, "Resource was not found.")

    assert scoped is resource


def test_require_user_scope_should_hide_cross_account_resource() -> None:
    resource = SimpleNamespace(id=10, user_id=8)

    with pytest.raises(NotFoundError, match="Resource was not found."):
        require_user_scope(resource, 7, "Resource was not found.")


def test_require_user_scope_should_hide_missing_resource() -> None:
    with pytest.raises(NotFoundError, match="Resource was not found."):
        require_user_scope(None, 7, "Resource was not found.")


@pytest.mark.asyncio
async def test_validate_file_ownership_should_allow_scoped_files(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_list_uploaded_files(_: object, user_id: int, file_ids: list[str]) -> list[SimpleNamespace]:
        assert user_id == 7
        assert file_ids == ["file-a"]
        return [SimpleNamespace(id="file-a", user_id=7)]

    monkeypatch.setattr("src.services.detections.list_uploaded_files", fake_list_uploaded_files)

    await validate_file_ownership(SimpleNamespace(), 7, ["file-a"])


@pytest.mark.asyncio
async def test_validate_file_ownership_should_hide_unscoped_files(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_list_uploaded_files(_: object, user_id: int, file_ids: list[str]) -> list[SimpleNamespace]:
        assert user_id == 7
        assert file_ids == ["file-a"]
        return []

    monkeypatch.setattr("src.services.detections.list_uploaded_files", fake_list_uploaded_files)

    with pytest.raises(BusinessValidationError, match="File ID file-a does not exist."):
        await validate_file_ownership(SimpleNamespace(), 7, ["file-a"])
