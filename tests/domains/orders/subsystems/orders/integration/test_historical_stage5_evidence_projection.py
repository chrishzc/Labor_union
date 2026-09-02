from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from types import SimpleNamespace

from infrastructure.mysql.order_summary_query_repository import _ORDER_SUMMARY_PAGE_SQL
from infrastructure.mysql.orders_card_projection_repository import _ORDERS_CARD_PROJECTION_SQL
from subsystems.orders.card_projection_query import OrdersCardProjectionQueryService
from subsystems.orders.summary_query import OrderSummaryQueryRequest, OrderSummaryQueryService


def _card_row():
    return {
        "case_no": "CASE-HIST-1",
        "client_id": 7,
        "client_source_version": datetime(2026, 9, 2, 8, 0),
        "phone": "0912345678",
        "address": "台北市測試路 1 號",
        "lifecycle_version": 4,
        "requires_cooking": 0,
        "floor_fee": Decimal("0"),
        "actual_start_date": None,
        "actual_end_date": None,
        "historical_receipt_id": 81,
        "historical_source_start_date": date(2026, 9, 3),
        "historical_source_end_date": date(2026, 10, 2),
        "historical_paired_staff_name": "月嫂甲",
        "deposit_obligation_count": 0,
        "deposit_amount_ntd": None,
        "deposit_obligation_identity": None,
        "deposit_obligation_status": None,
        "deposit_projection_state": None,
        "deposit_allocated_ntd": None,
        "deposit_source_version": None,
        "deposit_settled_on": None,
        "scheduling_version": None,
        "assignment_id": None,
        "assignment_staff_id": None,
        "assignment_sequence": None,
        "assigned_start_date": None,
        "assigned_end_date": None,
        "assignment_status": None,
        "staff_name": None,
        "staff_source_version": None,
    }


def test_stage5_card_projection_keeps_future_historical_source_without_claiming_actual_start():
    service = OrdersCardProjectionQueryService(
        SimpleNamespace(fetch_by_case_no=lambda case_no: (_card_row(),))
    )

    projection = service.query("CASE-HIST-1")

    assert projection.actual_start_date.value is None
    assert projection.historical_source_start_date.value == date(2026, 9, 3)
    assert projection.historical_source_end_date.value == date(2026, 10, 2)
    assert projection.historical_paired_staff_name.value == "月嫂甲"
    assert projection.historical_source_start_date.source_version == "81"
    assert projection.assignment_segments.value is None


def test_summary_carries_historical_source_period_without_overwriting_actual_dates():
    row = {
        "case_no": "CASE-HIST-1",
        "client_name": "客戶甲",
        "order_status": "歷史訂單－未服務",
        "staff_name": "月嫂甲",
        "identity_status": "verified",
        "start_date": date(2026, 8, 27),
        "end_date": date(2026, 9, 25),
        "actual_start_date": None,
        "actual_end_date": None,
        "historical_source_start_date": date(2026, 9, 3),
        "historical_source_end_date": date(2026, 10, 2),
        "service_days": 30,
        "total_employer_self_pay_payable": 0,
    }
    service = OrderSummaryQueryService(
        SimpleNamespace(fetch_page=lambda **_kwargs: (row,))
    )

    item = service.query(OrderSummaryQueryRequest(1, None)).items[0]

    assert item.start_date == date(2026, 8, 27)
    assert item.actual_start_date is None
    assert item.historical_source_start_date == date(2026, 9, 3)
    assert item.historical_source_end_date == date(2026, 10, 2)
    assert item.staff_name == "月嫂甲"


def test_sql_reads_latest_adopted_historical_pairing_evidence_as_read_only_projection():
    for sql in (_ORDER_SUMMARY_PAGE_SQL, _ORDERS_CARD_PROJECTION_SQL):
        assert "historical_order_adoption_receipts" in sql
        assert "historical_order_pairing_evidence" in sql
        assert "historical_source_start_date" in sql
        assert "historical_source_end_date" in sql
    assert "historical_paired_staff_name" in _ORDERS_CARD_PROJECTION_SQL
