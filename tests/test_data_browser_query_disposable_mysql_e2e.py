"""
File: test_data_browser_query_disposable_mysql_e2e.py
Description: 以受控 lu_test MySQL 驗證六來源 allowlist、cursor、masking 與零寫入查詢。
"""

from __future__ import annotations

import os

import pytest

from infrastructure.mysql.data_browser_query_repository import (
    DataBrowserQueryRepository,
    DataBrowserSourceNotFound,
    canonical_source_ids,
)
from infrastructure.mysql.mysql_adapter import get_connection


DATABASE = os.getenv("LABOR_UNION_TEST_MYSQL_DATABASE")
pytestmark = pytest.mark.skipif(
    not DATABASE
    or not DATABASE.startswith("lu_test_")
    or os.getenv("DB_DATABASE") != DATABASE,
    reason="requires an explicitly configured lu_test_* MySQL database",
)


class _AuditedConnection:
    def __init__(self, connection) -> None:
        self.connection = connection
        self.statements: list[str] = []

    def cursor(self):
        return _AuditedCursor(self)

    def commit(self) -> None:
        raise AssertionError("Data Browser Query must not commit")

    def rollback(self) -> None:
        raise AssertionError("Data Browser Query must not rollback")


class _AuditedCursor:
    def __init__(self, owner: _AuditedConnection) -> None:
        self.owner = owner
        self.cursor_value = None

    def __enter__(self):
        self.cursor_value = self.owner.connection.cursor()
        return self

    def __exit__(self, *_):
        assert self.cursor_value is not None
        self.cursor_value.close()
        return False

    def execute(self, sql, params):
        assert sql.lstrip().upper().startswith("SELECT ")
        self.owner.statements.append(sql)
        assert self.cursor_value is not None
        return self.cursor_value.execute(sql, params)

    def fetchall(self):
        assert self.cursor_value is not None
        return self.cursor_value.fetchall()


def test_six_source_query_cursor_masking_and_zero_write_on_lu_test_mysql() -> None:
    connection = get_connection()
    audited = _AuditedConnection(connection)
    repository = DataBrowserQueryRepository(audited)
    try:
        pages = {
            source_id: repository.query_masked_page(
                source_id,
                limit=2,
                after=None,
                query=None,
            )
            for source_id in canonical_source_ids()
        }

        assert tuple(pages) == (
            "orders",
            "clients",
            "staff",
            "beclass_intake",
            "hcm_review",
            "bank_facts",
        )
        assert all(page.source_id == source_id for source_id, page in pages.items())
        cursor_source, first_page = next(
            (source_id, page)
            for source_id, page in pages.items()
            if page.next_cursor is not None
        )
        second_page = repository.query_masked_page(
            cursor_source,
            limit=2,
            after=first_page.next_cursor,
            query=None,
        )
        assert {row.row_identity for row in first_page.items}.isdisjoint(
            row.row_identity for row in second_page.items
        )

        for source_id in ("clients", "staff"):
            for row in pages[source_id].items:
                name_cell = next(
                    cell for cell in row.detail_cells if cell.field_id == "name"
                )
                assert name_cell.presentation == "masked"
                assert name_cell.value == "未提供" or "○" in str(name_cell.value)
        for row in pages["bank_facts"].items:
            amount_cell = next(
                cell for cell in row.detail_cells if cell.field_id == "amount"
            )
            assert amount_cell.value in {None, "NT$ ****"}

        statement_count = len(audited.statements)
        with pytest.raises(DataBrowserSourceNotFound):
            repository.query_masked_page(
                "unknown",
                limit=2,
                after=None,
                query=None,
            )
        with pytest.raises(ValueError, match="cursor_invalid"):
            repository.query_masked_page(
                "clients",
                limit=2,
                after="0",
                query=None,
            )
        assert len(audited.statements) == statement_count
        assert audited.statements
    finally:
        connection.close()
