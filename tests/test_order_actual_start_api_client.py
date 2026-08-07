from datetime import date

from ui.api_clients.order_actual_start_api_client import ActualStartApiClient


class FakeResponse:
    ok = True
    status_code = 200

    def __init__(self, body): self._body = body
    def json(self): return self._body


class FakeSession:
    def __init__(self, responses): self.responses, self.calls = iter(responses), []
    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return next(self.responses)


def _response(data): return FakeResponse({"success": True, "data": data})


def test_actual_start_client_uses_preview_versions_for_apply():
    session = FakeSession([
        _response({"case_no": "C-1", "current_actual_start_date": None, "planned_start_date": "2026-08-01", "service_data_locked": False, "order_version": 2, "scheduling_version": 3, "scheduling_generation": 1, "client_finance_version": 4, "payroll_version": 5}),
        _response({"before_actual_start_date": None, "after_actual_start_date": "2026-08-02", "actual_end_date": "2026-08-31", "order_version": 2, "scheduling_version": 3, "scheduling_generation": 1, "client_finance_version": 4, "payroll_version": 5, "actual_start": {}, "scheduling": {}, "client_finance_impact": {}, "payroll_impact": {}, "lifecycle_impact": {}, "preview_fingerprint": "b" * 64}),
        _response({"case_no": "C-1", "order_version": 3, "scheduling_version": 4, "scheduling_generation": 2, "client_finance_version": 5, "payroll_version": 6, "lifecycle_status": "in_service", "service_data_lock_formed": True, "cancelled_assignment_ids": [], "created_assignment_keys": [], "official_service_day_count": 30, "official_service_hours": 240, "preview_fingerprint": "b" * 64}),
    ])
    client = ActualStartApiClient(base_url="https://api.example", headers={}, session=session)

    assert client.query("C-1").planned_start_date == date(2026, 8, 1)
    preview = client.preview("C-1", date(2026, 8, 2), correlation_id="corr-1")
    assert client.apply("C-1", preview, reason="客戶確認", idempotency_key="key-1", correlation_id="corr-2").lifecycle_status == "in_service"
    assert session.calls[2][2]["json"]["expected_payroll_version"] == 5
