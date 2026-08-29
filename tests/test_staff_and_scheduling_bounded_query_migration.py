"""Prevent UI callers from regressing to unbounded staff or order reads."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routes import staff as staff_router


ROOT = Path(__file__).resolve().parents[1]


def test_staff_summary_route_uses_database_bounded_cursor_query():
    source = (ROOT / "api/routes/staff.py").read_text(encoding="utf-8")

    assert '@router.get("/summaries"' in source
    assert "page_size: int = Query(default=200, ge=1, le=200)" in source
    assert "get_staff_summary_application" in source
    assert "StaffSummaryQueryRequest" in source
    assert "get_connection" not in source
    assert ".execute(" not in source
    assert "cursor()" not in source


def test_finance_page_uses_typed_bounded_staff_summary_query():
    source = (ROOT / "ui/pages/04_finance.py").read_text(encoding="utf-8")

    assert "StaffSummaryApiClient" in source
    assert '"/api/v1/staff"' not in source
    assert "_load_order_summaries" in source
    assert "page_size=200" in source


def test_scheduling_page_uses_order_summary_cursor_pagination():
    source = (ROOT / "ui/pages/03_calendar.py").read_text(encoding="utf-8")

    assert "query_text=query_text" in source
    assert "scheduling_order_search" in source
    assert "_render_scheduling_order_pagination" in source
    assert "scheduling_{workspace}_order_after_case_no" in source
    assert 'page_size=50' in source
    assert "StaffSummaryApiClient" in source
    assert "_render_staff_summary_pagination" in source
    assert '"/api/v1/staff"' not in source


def test_leave_substitution_uses_bounded_staff_summary_pagination():
    source = (ROOT / "ui/pages/scheduling/leave_substitution_panel.py").read_text(
        encoding="utf-8"
    )

    assert "StaffSummaryApiClient" in source
    assert "page_size=200" in source
    assert "_render_staff_option_pagination" in source
    assert '"/api/v1/staff"' not in source


def test_legacy_staff_list_endpoint_is_retired():
    source = (ROOT / "api/routes/staff.py").read_text(encoding="utf-8")

    assert "status_code=410" in source
    assert 'get_table_data("staff")' not in source

    app = FastAPI()
    app.include_router(staff_router.router)
    response = TestClient(app).get("/api/v1/staff")
    assert response.status_code == 410


def test_holiday_management_is_a_separate_scheduling_workspace():
    source = (ROOT / "ui/pages/03_calendar.py").read_text(encoding="utf-8")
    staff_calendar_source = source[
        source.index("def _render_staff_calendar()"):
        source.index("def _render_scheduling_workspace")
    ]

    assert '"國定假日管理"' in source
    assert 'if workspace == "國定假日管理":' in source
    assert "render_holiday_management()" in source
    assert "render_holiday_management()" not in staff_calendar_source


def test_order_overview_loads_full_order_only_after_selection():
    source = (ROOT / "ui/pages/order/tab1_overview.py").read_text(encoding="utf-8")

    assert "OrderDetailApiClient" in source
    assert ".query(selected_case_no)" in source


def test_order_detail_route_uses_typed_selected_case_projection():
    source = (ROOT / "api/routes/orders.py").read_text(encoding="utf-8")

    assert "get_order_detail_application" in source
    assert "OrderDetailView" in source
    assert "db_service.get_order_by_case_no(case_no)" not in source
