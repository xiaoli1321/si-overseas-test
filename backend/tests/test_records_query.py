"""Tests for record query filters and stats aggregation in store.py.

These tests compile SQL queries from the repository functions and verify
that the generated SQL includes the correct WHERE clauses for each filter.
This approach avoids requiring a real database and is consistent with the
existing test_account_scope.py pattern.
"""

from datetime import datetime
import importlib
from pathlib import Path

import pytest
from sqlalchemy import select

from src.models.tables import DetectRecord
from src.repositories.store import _build_records_query, iter_records_for_export, list_records


def _sql_text(query: object) -> str:
    return str(query.compile(compile_kwargs={"literal_binds": True}))


class TestBuildRecordsQuery:
    """Verify _build_records_query generates correct WHERE clauses for all supported filters."""

    def test_base_query_includes_user_scope_and_visibility(self) -> None:
        query = _build_records_query(42)
        sql = _sql_text(query)

        assert "detect_records.user_id = 42" in sql
        assert "is_visible_in_workbench" in sql

    def test_source_filter(self) -> None:
        query = _build_records_query(42, source="web")
        sql = _sql_text(query)

        assert "source" in sql
        assert "web" in sql

    def test_fault_category_filter(self) -> None:
        query = _build_records_query(42, fault_category="Sensor falling off")
        sql = _sql_text(query)

        assert "fault_category" in sql
        assert "Sensor falling off" in sql

    def test_verdict_filter(self) -> None:
        query = _build_records_query(42, verdict="Replacement Eligible")
        sql = _sql_text(query)

        assert "verdict" in sql
        assert "Replacement Eligible" in sql

    def test_serial_no_ilike_filter(self) -> None:
        query = _build_records_query(42, serial_no="ABC123")
        sql = _sql_text(query)

        assert "serial_no" in sql.lower()
        assert "LIKE" in sql.upper()
        assert "%ABC123%" in sql

    def test_date_from_filter(self) -> None:
        dt = datetime(2026, 1, 1, 0, 0, 0)
        query = _build_records_query(42, date_from=dt)
        sql = _sql_text(query)

        assert "created_at >=" in sql

    def test_date_to_filter(self) -> None:
        dt = datetime(2026, 12, 31, 23, 59, 59)
        query = _build_records_query(42, date_to=dt)
        sql = _sql_text(query)

        assert "created_at <=" in sql

    def test_conclusion_issue_detected_filter(self) -> None:
        query = _build_records_query(42, conclusion="Issue Detected")
        sql = _sql_text(query)

        assert "issue_detected" in sql
        assert "Issue Detected" in sql

    def test_conclusion_no_issue_filter(self) -> None:
        query = _build_records_query(42, conclusion="No Issue")
        sql = _sql_text(query)

        # Should filter for NOT "Issue Detected" OR NULL
        assert "issue_detected" in sql
        assert "IS NULL" in sql.upper() or "!=" in sql

    def test_combined_filters(self) -> None:
        dt_from = datetime(2026, 1, 1)
        dt_to = datetime(2026, 6, 30, 23, 59, 59)
        query = _build_records_query(
            42,
            fault_category="Data accuracy",
            serial_no="P225",
            date_from=dt_from,
            date_to=dt_to,
            conclusion="Issue Detected",
        )
        sql = _sql_text(query)

        assert "fault_category" in sql
        assert "Data accuracy" in sql
        assert "%P225%" in sql
        assert "created_at >=" in sql
        assert "created_at <=" in sql
        assert "issue_detected" in sql

    def test_no_filters_only_user_scope(self) -> None:
        query = _build_records_query(42)
        sql = _sql_text(query)

        # Should NOT contain optional filter clauses
        assert "%%" not in sql  # No ILIKE wildcard
        assert "Replacement Eligible" not in sql
        assert "Sensor falling off" not in sql
        assert "Issue Detected" not in sql

    def test_user_isolation(self) -> None:
        """Different user IDs produce different scope filters."""
        query_a = _build_records_query(1)
        query_b = _build_records_query(2)
        sql_a = _sql_text(query_a)
        sql_b = _sql_text(query_b)

        assert "user_id = 1" in sql_a
        assert "user_id = 2" in sql_b
        assert "user_id = 1" not in sql_b


class _MockRow:
    """Row-like object for window-function query results (row[0] + row.total)."""

    def __init__(self, entity: object, total: int) -> None:
        self._entity = entity
        self.total = total

    def __getitem__(self, index: int) -> object:
        if index == 0:
            return self._entity
        raise IndexError(index)


class _MockScalars:
    def __init__(self, row_count: int) -> None:
        self._row_count = row_count

    def all(self) -> list[object]:
        if self._row_count == 0:
            return []
        return [object() for _ in range(self._row_count)]


class _MockResult:
    def __init__(self, total: int = 0, row_count: int = 0) -> None:
        self._total = total
        self._row_count = row_count

    def all(self) -> list[_MockRow]:
        if self._row_count == 0:
            return []
        return [_MockRow(object(), self._total) for _ in range(self._row_count)]

    def scalars(self) -> _MockScalars:
        return _MockScalars(self._row_count)


class _CapturingDb:
    """Fake AsyncSession that captures queries and returns controlled results.

    Supports both .scalars().all() (for entity queries) and .all()
    (for window-function queries via _MockResult).
    """

    def __init__(self, total: int = 0, row_count: int = 0) -> None:
        self.queries: list[object] = []
        self._total = total
        self._row_count = row_count

    async def execute(self, query: object) -> _MockResult:
        self.queries.append(query)
        return _MockResult(self._total, self._row_count)


@pytest.mark.asyncio
async def test_iter_records_for_export_uses_stable_keyset_ordering() -> None:
    db = _CapturingDb()

    batches = [
        batch
        async for batch in iter_records_for_export(
            db,
            42,
            fault_category="Data accuracy",
            batch_size=250,
        )
    ]

    assert batches == []
    assert len(db.queries) == 1
    sql = _sql_text(db.queries[0])
    assert "fault_category" in sql
    assert "Data accuracy" in sql
    assert "ORDER BY detect_records.created_at DESC, detect_records.id DESC" in sql
    assert "LIMIT 250" in sql


@pytest.mark.asyncio
async def test_list_records_empty_result_returns_zero_total() -> None:
    """Verify list_records returns ([], 0) when no rows match, with single query."""
    db = _CapturingDb(total=0, row_count=0)
    records, total = await list_records(db, 42)
    assert records == []
    assert total == 0
    assert len(db.queries) == 1


@pytest.mark.asyncio
async def test_list_records_uses_single_query_with_window_function() -> None:
    """Verify list_records executes exactly one query containing count(*) over()."""
    db = _CapturingDb(total=10, row_count=3)
    records, total = await list_records(db, 42, page=1, page_size=3)
    assert len(records) == 3
    assert total == 10
    assert len(db.queries) == 1
    sql = _sql_text(db.queries[0])
    assert "count(*) OVER ()" in sql
    assert "ORDER BY" in sql
    assert "LIMIT 3" in sql


@pytest.mark.asyncio
async def test_list_records_passes_through_filters() -> None:
    """Verify filters in list_records appear in the single SQL query."""
    db = _CapturingDb(total=5, row_count=0)
    await list_records(
        db,
        42,
        fault_category="Sensor falling off",
        verdict="Replacement Eligible",
        serial_no="ABC123",
        page=2,
        page_size=10,
    )
    assert len(db.queries) == 1
    sql = _sql_text(db.queries[0])
    assert "Sensor falling off" in sql
    assert "Replacement Eligible" in sql
    assert "%ABC123%" in sql
    assert "OFFSET 10" in sql  # (page-1) * page_size
    assert "LIMIT 10" in sql


def test_detect_record_query_index_migration_defines_expected_indexes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration_path = (
        Path(__file__).parents[1]
        / "migrations"
        / "versions"
        / "1f3d4c5b6a78_add_detect_records_query_indexes.py"
    )
    spec = importlib.util.spec_from_file_location(
        "detect_records_indexes",
        migration_path,
    )
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    created: list[tuple[str, str, list[str]]] = []

    def fake_create_index(
        name: str,
        table: str,
        columns: list[str],
        unique: bool,
    ) -> None:
        assert unique is False
        created.append((name, table, columns))

    monkeypatch.setattr(migration.op, "create_index", fake_create_index)

    migration.upgrade()

    assert (
        "ix_detect_records_user_visible_created_at",
        "detect_records",
        ["user_id", "is_visible_in_workbench", "created_at"],
    ) in created
    assert (
        "ix_detect_records_user_visible_fault_cat_created_at",
        "detect_records",
        ["user_id", "is_visible_in_workbench", "fault_category", "created_at"],
    ) in created
    assert (
        "ix_detect_records_user_visible_status_created_at",
        "detect_records",
        ["user_id", "is_visible_in_workbench", "status", "created_at"],
    ) in created
    assert (
        "ix_detect_records_user_visible_verdict_created_at",
        "detect_records",
        ["user_id", "is_visible_in_workbench", "verdict", "created_at"],
    ) in created
    assert (
        "ix_detect_records_user_visible_issue_created_at",
        "detect_records",
        ["user_id", "is_visible_in_workbench", "issue_detected", "created_at"],
    ) in created
