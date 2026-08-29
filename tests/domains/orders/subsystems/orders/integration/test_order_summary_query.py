"""
File: test_order_summary_query.py
Description: 驗證訂單摘要讀模型、游標與待補件欄位空值契約。
"""

from datetime import date, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest

from domains.orders.lifecycle import OrderLifecycleScope
from subsystems.orders.summary_query import (
    OrderSummaryContractError,
    OrderSummaryQueryRequest,
    OrderSummaryQueryService,
)


def _row(case_no: str = "CASE-1") -> dict[str, object]:
    return {
        "case_no": case_no,
        "client_name": "Client",
        "order_status": "ACTIVE",
        "staff_name": None,
        "identity_status": "verified",
        "start_date": date(2026, 1, 1),
        "end_date": date(2026, 1, 2),
        "actual_start_date": None,
        "actual_end_date": None,
        "service_days": 2,
        "total_employer_self_pay_payable": Decimal("1200"),
    }


def _service(rows: object) -> OrderSummaryQueryService:
    return OrderSummaryQueryService(
        SimpleNamespace(fetch_page=lambda **_arguments: rows)
    )


def test_query_returns_canonical_page_and_stable_etag() -> None:
    request = OrderSummaryQueryRequest(page_size=1, after_case_no=None)
    page = _service((_row("CASE-1"), _row("CASE-2"))).query(request)

    assert [item.case_no for item in page.items] == ["CASE-1"]
    assert page.next_cursor == "CASE-1"
    assert page.etag == "77ff6591a030269e0f595550548cfdb1ef1b86b0ed2e25fba2ecdf193060964a"


def test_query_passes_case_or_client_search_text_to_repository() -> None:
    captured = {}
    service = OrderSummaryQueryService(
        SimpleNamespace(fetch_page=lambda **arguments: captured.update(arguments) or (_row(),))
    )

    service.query(OrderSummaryQueryRequest(50, None, "陳小姐"))

    assert captured["query_text"] == "陳小姐"
    assert captured["lifecycle_scope"] is OrderLifecycleScope.ALL


def test_query_passes_unfinished_lifecycle_scope_to_repository() -> None:
    captured = {}
    service = OrderSummaryQueryService(
        SimpleNamespace(fetch_page=lambda **arguments: captured.update(arguments) or (_row(),))
    )

    service.query(OrderSummaryQueryRequest(50, None, None, OrderLifecycleScope.UNFINISHED))

    assert captured["lifecycle_scope"] is OrderLifecycleScope.UNFINISHED


def test_query_rejects_non_tuple_repository_page() -> None:
    with pytest.raises(OrderSummaryContractError, match="must be a tuple"):
        _service([_row()]).query(OrderSummaryQueryRequest(1, None))


def test_query_rejects_duplicate_case_numbers() -> None:
    with pytest.raises(OrderSummaryContractError, match="duplicate case numbers"):
        _service((_row("CASE-1"), _row("CASE-1"))).query(
            OrderSummaryQueryRequest(2, None)
        )


def test_query_rejects_datetime_for_date_projection() -> None:
    row = _row()
    row["start_date"] = datetime(2026, 1, 1)

    with pytest.raises(OrderSummaryContractError, match="start_date must be a date"):
        _service((row,)).query(OrderSummaryQueryRequest(1, None))


def test_query_preserves_legacy_rows_with_unknown_identity_or_planned_end() -> None:
    row = _row()
    row["identity_status"] = None
    row["end_date"] = None

    page = _service((row,)).query(OrderSummaryQueryRequest(1, None))

    assert page.items[0].identity_status is None
    assert page.items[0].end_date is None


def test_query_preserves_pending_case_without_planned_terms() -> None:
    row = _row()
    row.update({
        "order_status": "待補件",
        "start_date": None,
        "end_date": None,
        "service_days": None,
        "total_employer_self_pay_payable": None,
    })

    page = _service((row,)).query(OrderSummaryQueryRequest(1, None))

    item = page.items[0]
    assert item.order_status == "待補件"
    assert item.start_date is None
    assert item.service_days is None
    assert item.total_employer_self_pay_payable is None


def test_query_keeps_import_review_case_visible_when_client_name_is_missing() -> None:
    row = _row("113000012")
    row["client_name"] = None

    page = _service((row,)).query(OrderSummaryQueryRequest(1, None))

    assert page.items[0].client_name == "待補姓名（113000012）"


def test_query_normalizes_legacy_zero_days_without_a_planned_start() -> None:
    row = _row()
    row.update({"start_date": None, "end_date": None, "service_days": 0})

    page = _service((row,)).query(OrderSummaryQueryRequest(1, None))

    assert page.items[0].service_days is None


def test_query_rejects_zero_days_when_a_planned_start_exists() -> None:
    row = _row()
    row["service_days"] = 0

    with pytest.raises(OrderSummaryContractError, match="service_days must be a positive integer"):
        _service((row,)).query(OrderSummaryQueryRequest(1, None))


@pytest.mark.parametrize("page_size", [0, 201])
def test_request_rejects_invalid_page_size(page_size: int) -> None:
    with pytest.raises(ValueError):
        OrderSummaryQueryRequest(page_size, None)


def test_request_rejects_blank_search_text() -> None:
    with pytest.raises(ValueError):
        OrderSummaryQueryRequest(50, None, "   ")
