"""Focused regression coverage for the bounded Staff roster summary."""

from __future__ import annotations

from collections.abc import Mapping

import pytest

from api.schemas.staff_summary import StaffSummaryView
from infrastructure.mysql.staff_summary_query_repository import (
    MySqlStaffSummaryQueryRepository,
)
from subsystems.staff.summary_query import (
    StaffSummaryContractError,
    StaffSummaryQueryRequest,
    StaffSummaryQueryService,
)


class _SummaryRepository:
    def __init__(self, rows: tuple[Mapping[str, object], ...]) -> None:
        self._rows = rows

    def fetch_page(
        self,
        *,
        after_id: int | None,
        page_size: int,
        staff_id: int | None,
    ) -> tuple[Mapping[str, object], ...]:
        del after_id, page_size, staff_id
        return self._rows


class _Cursor:
    def __init__(self) -> None:
        self.sql: str | None = None
        self.params: tuple[object, ...] | None = None

    def __enter__(self) -> _Cursor:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        del exc_type, exc, tb

    def execute(self, sql: str, params: tuple[object, ...]) -> None:
        self.sql = sql
        self.params = params

    def fetchall(self) -> list[dict[str, object]]:
        return [
            {
                "id": 7,
                "name": "測試月嫂",
                "phone": "0912345678",
                "education": "高職",
            }
        ]


class _Connection:
    def __init__(self) -> None:
        self.cursor_instance = _Cursor()

    def cursor(self) -> _Cursor:
        return self.cursor_instance


def test_staff_summary_exposes_canonical_education():
    service = StaffSummaryQueryService(
        _SummaryRepository(
            (
                {
                    "id": 7,
                    "name": "測試月嫂",
                    "phone": "0912345678",
                    "education": " 高職 ",
                },
            )
        )
    )

    page = service.query(StaffSummaryQueryRequest(page_size=20))

    assert page.items[0].education == "高職"
    view = StaffSummaryView.model_validate(page.items[0], from_attributes=True)
    assert view.model_dump() == {
        "id": 7,
        "name": "測試月嫂",
        "phone": "0912345678",
        "education": "高職",
    }


def test_staff_summary_rejects_non_roster_internal_fields():
    service = StaffSummaryQueryService(
        _SummaryRepository(
            (
                {
                    "id": 7,
                    "name": "測試月嫂",
                    "phone": "0912345678",
                    "education": "高職",
                    "emergency_contact_name": "內部聯絡人",
                },
            )
        )
    )

    with pytest.raises(StaffSummaryContractError, match="not canonical"):
        service.query(StaffSummaryQueryRequest(page_size=20))


def test_mysql_staff_summary_projection_reads_education_without_internal_fields():
    connection = _Connection()
    repository = MySqlStaffSummaryQueryRepository(connection)

    rows = repository.fetch_page(after_id=None, page_size=20, staff_id=None)

    assert rows[0]["education"] == "高職"
    assert connection.cursor_instance.params == (0, 21)
    sql = connection.cursor_instance.sql
    assert sql is not None
    assert "id, name, phone, education" in sql
    assert "emergency_contact" not in sql
    assert "admin_notes" not in sql
