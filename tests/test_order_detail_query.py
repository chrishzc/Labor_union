from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

from subsystems.orders.detail_query import (
    OrderDetailContractError,
    OrderDetailNotFoundError,
    OrderDetailQueryService,
)


def _row() -> dict[str, object]:
    return {
        "case_no": "CASE-1", "client_id": 1, "staff_id": None,
        "client_name": "Client", "staff_name": None, "order_status": "服務中",
        "identity_status": "一般市民", "cancel_reason": None, "line_group_id": None,
        "contract_identity": None, "actual_start_date": None, "actual_end_date": None,
        "deposit_date": date(2026, 1, 1), "start_date": date(2026, 1, 5),
        "end_date": date(2026, 1, 24), "service_days": 20,
        "service_hours_per_day": 8, "deposit_service_days": None,
        "floor_fee": Decimal("1200"), "custom_rest_dates": "[\"2026-01-10\"]",
    }


def _service(row: object) -> OrderDetailQueryService:
    return OrderDetailQueryService(
        SimpleNamespace(fetch_by_case_no=lambda _case_no: row)
    )


def test_query_returns_only_declared_complete_detail_fields() -> None:
    detail = _service(_row()).query("CASE-1")

    assert detail.case_no == "CASE-1"
    assert detail.floor_fee == 1200
    assert detail.start_date == date(2026, 1, 5)


def test_query_rejects_undeclared_repository_field() -> None:
    row = _row()
    row["unexpected"] = "not allowed"

    with pytest.raises(OrderDetailContractError, match="fields"):
        _service(row).query("CASE-1")


def test_query_rejects_noncanonical_date_type() -> None:
    row = _row()
    row["start_date"] = "2026-01-05"

    with pytest.raises(OrderDetailContractError, match="start_date"):
        _service(row).query("CASE-1")


def test_query_reports_missing_selected_case() -> None:
    with pytest.raises(OrderDetailNotFoundError):
        _service(None).query("CASE-1")


def test_query_rejects_blank_case_number_before_repository_call() -> None:
    with pytest.raises(ValueError):
        _service(_row()).query(" ")
