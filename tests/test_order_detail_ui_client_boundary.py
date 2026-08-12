from __future__ import annotations

from api.schemas.order_detail import OrderDetailView
from ui.api_clients.order_detail_api_client import OrderDetailApiClient
from ui.pages.order import tab1_overview


def _detail_payload() -> dict[str, object]:
    return {
        "case_no": "CASE-1", "client_id": 1, "staff_id": None,
        "client_name": "測試客戶", "staff_name": None, "order_status": "服務中",
        "identity_status": "一般市民", "cancel_reason": None, "line_group_id": None,
        "contract_identity": None, "actual_start_date": None, "actual_end_date": None,
        "deposit_date": None, "start_date": "2026-08-01", "end_date": "2026-08-02",
        "service_days": 2, "service_hours_per_day": 8, "deposit_service_days": None,
        "floor_fee": 0, "custom_rest_dates": None,
    }


class _Response:
    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, object]:
        return self._payload


def test_order_detail_client_returns_a_typed_view(monkeypatch) -> None:
    payload = {"success": True, "data": _detail_payload(), "message": "ok"}
    monkeypatch.setattr(
        "ui.api_clients.order_detail_api_client.requests.get",
        lambda *_args, **_kwargs: _Response(payload),
    )

    detail = OrderDetailApiClient(base_url="http://api.test", headers={}).query("CASE-1")

    assert isinstance(detail, OrderDetailView)
    assert detail.start_date.isoformat() == "2026-08-01"


def test_order_detail_client_rejects_an_untyped_payload(monkeypatch) -> None:
    payload = {"success": True, "data": {"case_no": "CASE-1"}, "message": "ok"}
    monkeypatch.setattr(
        "ui.api_clients.order_detail_api_client.requests.get",
        lambda *_args, **_kwargs: _Response(payload),
    )

    try:
        OrderDetailApiClient(base_url="http://api.test", headers={}).query("CASE-1")
    except RuntimeError as error:
        assert str(error) == "案件完整資料回應格式不正確。"
    else:
        raise AssertionError("invalid detail payload must not reach the UI")


def test_overview_converts_only_the_typed_detail_view_for_the_editor(monkeypatch) -> None:
    captured: dict[str, object] = {}
    detail = OrderDetailView.model_validate(_detail_payload())
    monkeypatch.setattr(tab1_overview, "st", _ContainerStreamlit())
    monkeypatch.setattr(tab1_overview, "resolve_api_base_url", lambda: "http://api.test")
    monkeypatch.setattr(tab1_overview, "build_admin_headers", lambda: {})
    monkeypatch.setattr(tab1_overview.OrderDetailApiClient, "query", lambda *_args: detail)
    monkeypatch.setattr(tab1_overview, "render_editor", lambda **kwargs: captured.update(kwargs))

    tab1_overview._render_selected_order("CASE-1")

    assert captured["orders_data"] == [detail.model_dump(mode="json")]


def test_overview_does_not_request_details_before_an_order_is_selected(monkeypatch) -> None:
    screen = _UnselectedOverviewStreamlit()
    monkeypatch.setattr(tab1_overview, "st", screen)
    monkeypatch.setattr(
        tab1_overview,
        "_render_selected_order",
        lambda _case_no: (_ for _ in ()).throw(AssertionError("detail request is premature")),
    )

    tab1_overview._render_tab1_overview(
        [{"case_no": "CASE-1", "order_status": "訂單成立"}]
    )

    assert "請先選擇案件，再載入完整資料。" in screen.messages


def test_order_selector_starts_without_a_default_case(monkeypatch) -> None:
    screen = _SelectorStreamlit()
    monkeypatch.setattr(tab1_overview, "st", screen)

    selected_case_no = tab1_overview._select_case_number(
        [{"case_no": "CASE-1", "order_status": "訂單成立"}]
    )

    assert selected_case_no is None
    assert screen.selectbox_kwargs["index"] is None
    assert screen.selectbox_kwargs["key"] == "tab1_order_select_v2"


class _ContainerStreamlit:
    def container(self, **_kwargs) -> _ContainerStreamlit:
        return self

    def __enter__(self) -> _ContainerStreamlit:
        return self

    def __exit__(self, *_args) -> bool:
        return False

    def error(self, _message: str) -> None:
        raise AssertionError("typed detail view must render without an error")


class _UnselectedOverviewStreamlit:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def subheader(self, _title: str) -> None:
        return None

    def multiselect(self, _label: str, **_kwargs) -> list[str]:
        return []

    def write(self, _message: str) -> None:
        return None

    def selectbox(self, _label: str, **_kwargs) -> None:
        return None

    def info(self, message: str) -> None:
        self.messages.append(message)


class _SelectorStreamlit:
    def __init__(self) -> None:
        self.selectbox_kwargs: dict[str, object] = {}

    def selectbox(self, _label: str, **kwargs) -> None:
        self.selectbox_kwargs = kwargs
        return None
