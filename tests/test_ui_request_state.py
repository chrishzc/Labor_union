from ui.request_state import accept_request_result, begin_request, request_snapshot
from pathlib import Path


def test_newer_generation_rejects_a_stale_result_without_overwriting_loading_state():
    state = {}
    first_request = begin_request(state, "orders")
    second_request = begin_request(state, "orders")

    assert not accept_request_result(state, "orders", first_request, item_count=1)
    assert request_snapshot(state, "orders") == second_request
    assert state["orders:stale_generation"] == 1


def test_current_request_records_ready_empty_and_error_states():
    state = {}
    ready = begin_request(state, "matching")
    assert accept_request_result(state, "matching", ready, item_count=2)
    assert request_snapshot(state, "matching").status == "ready"

    empty = begin_request(state, "matching")
    assert accept_request_result(state, "matching", empty, item_count=0)
    assert request_snapshot(state, "matching").status == "empty"

    failed = begin_request(state, "matching")
    assert accept_request_result(
        state, "matching", failed, item_count=0, error_message="connection failed"
    )
    assert request_snapshot(state, "matching").status == "error"


def test_orders_and_matching_pages_wire_the_generation_adapter_to_visible_states():
    root = Path(__file__).resolve().parents[1]
    orders_source = (root / "ui/pages/02_orders.py").read_text(encoding="utf-8")
    matching_source = (root / "ui/pages/03_calendar.py").read_text(encoding="utf-8")

    assert 'begin_request(st.session_state, "orders_summary_request")' in orders_source
    assert 'with st.spinner("正在載入案件摘要與月嫂清單…")' in orders_source
    assert "已忽略過期的案件摘要回應" in orders_source
    assert "目前沒有符合條件的案件摘要。" in orders_source
    assert 'begin_request(st.session_state, "scheduling_matching_request")' in matching_source
    assert 'with st.spinner("正在載入月嫂配對案件與人員…")' in matching_source
    assert "已忽略過期的配對資料回應" in matching_source
    assert "目前沒有符合條件的配對案件或可用人員。" in matching_source
