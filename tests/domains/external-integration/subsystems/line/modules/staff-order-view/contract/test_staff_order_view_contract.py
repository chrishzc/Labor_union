"""Contracts for the verified LINE staff assignment-owned order view."""

from pathlib import Path

from api.schemas.line_staff_self_service import StaffOrderSearchRequest


ROOT = next(
    parent
    for parent in Path(__file__).resolve().parents
    if (parent / "requirements.txt").is_file() and (parent / "subsystems").is_dir()
)


def test_staff_order_page_loads_assigned_orders_before_optional_filtering() -> None:
    source = (ROOT / "line" / "static" / "staff_order_search.html").read_text(
        encoding="utf-8"
    )

    assert 'async function loadOrders(keyword = "")' in source
    assert "await loadOrders();" in source
    assert "請先輸入案件編號或客戶姓名" not in source


def test_staff_order_search_allows_unfiltered_assigned_order_query() -> None:
    request = StaffOrderSearchRequest(flow_id="flow-1")

    assert request.keyword == ""
