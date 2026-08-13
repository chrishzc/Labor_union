from ui.api_clients.order_terms_api_client import OrderTermsApiClient


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


def _terms(): return {"planned_start_date": "2026-08-01", "service_days": 30, "service_hours_per_day": 8, "requires_cooking": True, "floor_fee_ntd": 0, "service_time": {"start_time": "09:00:00", "end_time": "17:00:00", "end_day_offset": 0}}


def test_terms_client_carries_preview_versions_into_apply():
    session = FakeSession([
        _response({"case_no": "C-1", "order_version": 2, "scheduling_version": 3, "scheduling_generation": 1, "client_finance_version": 4, "payroll_version": 5, "service_data_locked": False, "terms": _terms()}),
        _response({"before": _terms(), "after": _terms(), "order_version": 2, "scheduling_version": 3, "scheduling_generation": 1, "client_finance_version": 4, "payroll_version": 5, "scheduling": {}, "client_finance_impact": {}, "payroll_impact": {}, "lifecycle_impact": {}, "preview_fingerprint": "c" * 64}),
        _response({"case_no": "C-1", "order_version": 3, "scheduling_version": 4, "scheduling_generation": 2, "client_finance_version": 5, "payroll_version": 6, "lifecycle_status": "active", "service_data_lock_formed": False, "cancelled_assignment_ids": [], "created_assignment_keys": [], "official_service_day_count": 30, "official_service_hours": 240, "preview_fingerprint": "c" * 64}),
    ])
    client = OrderTermsApiClient(base_url="https://api.example", headers={}, session=session)
    assert client.query("C-1").terms.service_days == 30
    preview = client.preview("C-1", _terms(), correlation_id="corr-1")
    assert client.apply("C-1", _terms(), preview, reason="修正合約", idempotency_key="key-1", correlation_id="corr-2").order_version == 3
    assert session.calls[2][2]["json"]["expected_client_finance_version"] == 4
