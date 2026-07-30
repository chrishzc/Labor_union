import ast
from pathlib import Path

from ui.pages.order.tab2_assign import _build_sync_request
from ui.pages.order.tab2_assign import _single_caregiver_covers_service_period


ROOT = Path(__file__).resolve().parents[1]


def _function_source(path: str, function_name: str) -> str:
    source = (ROOT / path).read_text(encoding="utf-8")
    tree = ast.parse(source)
    node = next(
        item
        for item in tree.body
        if isinstance(item, ast.FunctionDef) and item.name == function_name
    )
    return ast.get_source_segment(source, node) or ""


def test_scheduling_page_owns_exact_three_product_tabs():
    show = _function_source("ui/pages/03_calendar.py", "show")
    assert '["服務人員月曆", "月嫂配對中心", "案件人力配置"]' in show
    assert "render_matching_center" in show
    assert "render_case_staffing" in show


def test_alert_center_deep_links_to_the_central_matching_tab():
    alerts = (ROOT / "ui/pages/06_finance_alerts.py").read_text(encoding="utf-8")
    calendar = (ROOT / "ui/pages/03_calendar.py").read_text(encoding="utf-8")
    order_shell = (ROOT / "ui/pages/02_orders.py").read_text(encoding="utf-8")

    assert '"多月嫂排班"' in alerts
    assert 'queue_target_key="multi_caregiver_matching_case_picker"' in alerts
    assert "current_queue_item(_MATCHING_QUEUE_KEY)" in calendar
    assert "preferred_case_no=str(queue_item" in calendar
    assert "月嫂配對中心" not in order_shell


def test_case_staffing_uses_one_to_four_rows_and_preview_apply():
    render = _function_source(
        "ui/pages/scheduling/case_staffing.py", "render_case_staffing"
    )
    assert "[1, 2, 3, 4]" in render
    assert "assignment-synchronization/preview" in render
    assert "assignment-synchronization/apply" in render
    assert "取消候選" in render
    assert "取消調整" in render
    assert "_build_sync_request(selected)" in render
    assert 'selected.get("staff_id")' in render


def test_case_staffing_normalizes_blank_optional_and_actual_dates():
    request = _build_sync_request(
        {
            "client_name": "測試客戶",
            "service_days": 3,
            "service_hours_per_day": 8,
            "floor_fee": 0,
            "deposit_date": "",
            "start_date": "2026-08-01",
            "end_date": "2026-08-03",
            "actual_start_date": "",
            "actual_end_date": "",
        }
    )
    assert request["deposit_date"] is None
    assert request["actual_start_date"] == "2026-08-01"
    assert request["actual_end_date"] == "2026-08-03"


def test_matching_center_restores_original_matching_and_uses_multi_fallback():
    wrapper = _function_source(
        "ui/pages/scheduling/matching_center.py", "render_matching_center"
    )
    original = _function_source(
        "ui/pages/order/tab2_assign.py", "_render_tab2_assign"
    )
    availability = _function_source(
        "ui/pages/order/tab2_assign.py",
        "_single_caregiver_covers_service_period",
    )
    assert "_render_tab2_assign" in wrapper
    assert "multi_segment_renderer=_render_multi_segment_matching" in wrapper
    assert "multi_segment_preview_renderer=" in wrapper
    assert "發送 訂單資訊-1" in original
    assert "更新月嫂意願" in original
    assert "傳送履歷給客戶" in original
    assert "預覽訂單與指派同步" in original
    assert "single_caregiver_available is False" in original
    assert "multi_segment_renderer(target_order, staff_list)" in original
    assert "測試顯示多月嫂配對" in original
    assert "_development_preview_is_enabled()" in original
    assert '"segment_count": 1' not in availability
    assert "caregiver-single-eligibility/check" in availability


def test_single_caregiver_gate_uses_complete_full_period_combinations(monkeypatch):
    captured = {}

    def fake_request(path, **kwargs):
        captured["path"] = path
        captured["payload"] = kwargs["payload"]
        return {"complete_combinations": [{"staff_ids": [531]}]}

    monkeypatch.setattr(
        "ui.pages.order.tab2_assign._api_request",
        fake_request,
    )
    assert _single_caregiver_covers_service_period(
        {
            "case_no": "115000015",
            "start_date": "2026-12-06",
            "end_date": "2026-12-20",
        },
        headers={"X-Internal-API-Key": "test"},
    )
    assert captured["payload"]["start_date"] == "2026-12-06"
    assert captured["payload"]["end_date"] == "2026-12-20"


def test_single_caregiver_gate_opens_multi_segment_only_when_empty(monkeypatch):
    monkeypatch.setattr(
        "ui.pages.order.tab2_assign._api_request",
        lambda *args, **kwargs: {"complete_combinations": []},
    )
    assert not _single_caregiver_covers_service_period(
        {
            "case_no": "115000015",
            "start_date": "2026-12-06",
            "service_days": 15,
        },
        headers={"X-Internal-API-Key": "test"},
    )


def test_multi_segment_fallback_supports_editable_partial_results():
    render = _function_source(
        "ui/pages/scheduling/matching_center.py",
        "_render_multi_segment_matching",
    )
    assert "[2, 3, 4]" in render
    assert "可獨自承接完整期間" in render
    assert "未覆蓋日期" in render
    assert "聯繫與確認意願" in render
    assert "傳送履歷" in render
    assert "matching-plans/active" in render
    assert "訂金入帳後轉正式指派" in render
    assert "availability-locks/{lock_id}/convert" in render
    assert "preview_only" in render
    assert "測試預覽不會建立方案" in render


def test_calendar_warns_before_discarding_unsaved_leave_drafts():
    render = _function_source("ui/pages/03_calendar.py", "_render_staff_calendar")
    assert "_calendar_has_unsaved_leave_changes" in render
    assert "放棄未儲存調整並切換" in render
    assert "留在本月" in render
    assert "正在查看：" in render
    assert "_normalise_calendar_schedule_map" in render
    assert "訂單完成" in render


def test_calendar_does_not_render_multi_caregiver_assignment_module():
    render = _function_source(
        "ui/pages/03_calendar.py", "_render_staff_calendar"
    )
    assert "_render_multi_caregiver_panel" not in render
    assert "多月嫂指派排班" not in render
    assert "_render_assignment_leave_resolution" in render


def test_calendar_leave_resolution_is_assignment_owned_preview_then_apply():
    render = _function_source(
        "ui/pages/03_calendar.py", "_render_assignment_leave_resolution"
    )
    assert "already selected assignment" in render
    assert "leave-resolution/batch-preview" in render
    assert "leave-resolution/batch-apply" in render
    assert "調整前／調整後" in render
    assert "阻擋原因" in render
    assert "確認並套用" in render
    assert "/rest-dates\"" not in render


def test_calendar_distinguishes_waiting_deposit_locks_from_formal_service():
    render = _function_source("ui/pages/03_calendar.py", "_render_staff_calendar")
    assert "waiting_deposit_lock" in render
    assert "已鎖定／待成立" in render
    assert "服務工作日" in render


def test_case_staffing_blocks_apply_until_actual_hours_are_conserved():
    render = _function_source(
        "ui/pages/scheduling/case_staffing.py",
        "render_case_staffing",
    )
    assert 'preview.get("sync_status") == "requires_allocation"' in render
    assert "時數尚未守恆，無法套用" in render
    assert "請調整月嫂或服務區段後重新預覽" in render
