from datetime import date

from ui.api_clients.case_architecture_bootstrap_api_client import (
    CaseArchitectureBootstrapApiClient,
)


class FakeResponse:
    ok = True
    status_code = 200

    def __init__(self, body):
        self._body = body

    def json(self):
        return self._body


class FakeSession:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return next(self.responses)


def _response(data):
    return FakeResponse({"success": True, "data": data})


def _preview():
    return {
        "case_no": "C-1", "order_version": 4, "source_identity_status": "ready",
        "client_payment_policy_version": "client-v1", "client_hourly_rate_ntd": 300,
        "deposit_service_days": 2, "deposit_due_date": "2026-08-04",
        "first_payment_due_date": "2026-08-05", "payroll_policy_version": "payroll-v1",
        "payroll_policy_kind": "hourly", "payroll_hourly_rate_ntd": 200,
        "scheduling_version": 1, "scheduling_generation": 2, "mutation": "create",
        "preview_fingerprint": "a" * 64,
    }


def test_client_reads_status_and_applies_typed_preview():
    session = FakeSession([
        _response({"case_no": "C-1", "ready": False, "scheduling_version": 0, "scheduling_generation": 0, "service_time_complete": True, "recommendation": None, "domain_blockers": []}),
        _response(_preview()),
        _response({"case_no": "C-1", "order_version": 4, "client_finance_version": 1, "payroll_version": 1, "scheduling_version": 1, "scheduling_generation": 2, "bootstrap_created": True, "bootstrap_event_id": 9, "preview_fingerprint": "a" * 64}),
    ])
    client = CaseArchitectureBootstrapApiClient(base_url="https://api.example", headers={"Authorization": "Bearer token"}, session=session)

    assert client.status("C-1").ready is False
    preview = client.preview("C-1", {key: value for key, value in _preview().items() if key in {"client_payment_policy_version", "client_hourly_rate_ntd", "deposit_service_days", "deposit_due_date", "first_payment_due_date", "payroll_policy_version"}}, correlation_id="corr-1")
    receipt = client.apply("C-1", preview, reason="補建舊案件根狀態", idempotency_key="key-1", correlation_id="corr-2")

    assert receipt.bootstrap_event_id == 9
    assert session.calls[1][2]["json"]["deposit_due_date"] == date(2026, 8, 4).isoformat()
    assert session.calls[2][2]["headers"]["Idempotency-Key"] == "key-1"
