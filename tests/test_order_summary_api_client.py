from ui.api_clients.order_summary_api_client import OrderSummaryApiClient


class _Response:
    status_code = 200
    ok = True
    headers: dict[str, str] = {}

    def __init__(self, payload: object) -> None:
        self._payload = payload

    def json(self) -> object:
        return self._payload


def test_order_summary_client_validates_the_typed_page_without_a_generic_envelope(monkeypatch):
    payload = {
        "success": True,
        "data": {
            "items": [{
                "case_no": "LEGACY-1",
                "client_name": "歷史客戶",
                "order_status": "服務中",
                "staff_name": None,
                "identity_status": None,
                "start_date": "2026-08-01",
                "end_date": None,
                "actual_start_date": None,
                "actual_end_date": None,
                "service_days": 1,
                "total_employer_self_pay_payable": 0,
            }],
            "next_cursor": None,
            "etag": "a" * 64,
        },
        "message": "ok",
    }
    monkeypatch.setattr(
        "ui.api_clients.order_summary_api_client.requests.Session.get",
        lambda *_args, **_kwargs: _Response(payload),
    )

    result = OrderSummaryApiClient(base_url="http://api.test", headers={}).query()

    assert result.page is not None
    assert result.page.items[0].identity_status is None
