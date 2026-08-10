from __future__ import annotations

from ui.api_clients.order_calendar_detail_api_client import OrderCalendarDetailApiClient


class _Response:
    ok = True
    status_code = 200

    def json(self):
        return {"success": True, "data": {"case_no": "C-1", "service_mode": "週休1日"}}


class _Session:
    def get(self, url, *, headers, timeout):
        self.url = url
        return _Response()


def test_calendar_detail_uses_canonical_typed_route() -> None:
    session = _Session()
    detail = OrderCalendarDetailApiClient(base_url="http://api.test", headers={}, session=session).query("C-1")
    assert detail.service_mode == "週休1日"
    assert session.url.endswith("/api/v1/orders/C-1/calendar-detail")
