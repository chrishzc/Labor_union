from datetime import date

import pytest

from ui.api_clients.order_cancellation_api_client import (
    OrderCancellationApiClient,
    OrderCancellationApiError,
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


def _confirmed_days():
    return [{"service_date": date(2026, 8, 2), "staff_id": 7, "reason": None}]


def _client_finance_impact(**overrides):
    impact = {
        "case_no": "C-1",
        "expected_account_version": 4,
        "resulting_account_version": 5,
        "stage_plans": [],
        "actions": [],
        "settlement": {
            "deposit_settled": False,
            "all_formal_obligations_settled": False,
            "fingerprint": "b" * 64,
        },
        "blockers": [],
        "fingerprint": "c" * 64,
    }
    impact.update(overrides)
    return impact


def _preview_data(*, client_finance_impact=None):
    return {
        "cancellation_date": "2026-08-03",
        "actual_end_date": "2026-08-02",
        "confirmed_service_days": [
            {"service_date": "2026-08-02", "staff_id": 7, "reason": None}
        ],
        "official_service_day_count": 1,
        "official_service_hours": 8,
        "order_version": 2,
        "scheduling_version": 3,
        "scheduling_generation": 1,
        "client_finance_version": 4,
        "payroll_version": 5,
        "scheduling": {},
        "client_finance_impact": client_finance_impact or _client_finance_impact(),
        "payroll_impact": {},
        "lifecycle_impact": {},
        "preview_fingerprint": "a" * 64,
    }


def test_cancellation_client_carries_preview_versions_and_confirmed_days():
    session = FakeSession([
        _response({
            "case_no": "C-1", "lifecycle_status": "in_service",
            "actual_start_date": "2026-08-02", "contracted_service_days": 30,
            "service_hours_per_day": 8, "service_started": True,
            "service_data_locked": False, "order_version": 2,
            "scheduling_version": 3, "scheduling_generation": 1,
            "client_finance_version": 4, "payroll_version": 5,
            "confirmed_service_days": [{"service_date": "2026-08-02", "staff_id": 7, "reason": None}],
            "caregiver_options": [{"staff_id": 7, "display_name": "Caregiver 7"}],
        }),
        _response(_preview_data()),
        _response({
            "case_no": "C-1", "order_version": 3, "scheduling_version": 4,
            "scheduling_generation": 2, "client_finance_version": 5,
            "payroll_version": 6, "lifecycle_status": "cancelled",
            "actual_end_date": "2026-08-02", "official_service_day_count": 1,
            "official_service_hours": 8, "cancelled_assignment_ids": [11],
            "created_assignment_keys": ["C-1:cancellation:1"],
            "preview_fingerprint": "a" * 64,
        }),
    ])
    client = OrderCancellationApiClient(
        base_url="https://api.example", headers={}, session=session
    )

    assert client.query("C-1").caregiver_options[0].staff_id == 7
    preview = client.preview("C-1", _confirmed_days(), correlation_id="corr-1")
    receipt = client.apply(
        "C-1", _confirmed_days(), preview, reason="客戶確認取消",
        idempotency_key="key-1", correlation_id="corr-2",
    )

    assert receipt.lifecycle_status == "cancelled"
    assert session.calls[1][2]["json"]["confirmed_service_days"] == [{
        "service_date": "2026-08-02", "staff_id": 7, "reason": None,
    }]
    assert session.calls[2][2]["json"]["expected_payroll_version"] == 5
    assert session.calls[2][2]["headers"]["Idempotency-Key"] == "key-1"


def test_cancellation_client_rejects_direction_amount_schema_drift():
    invalid_action = {
        "action": "create_refund",
        "payment_stage": "first",
        "obligation_identity": "client-obligation:C-1:first",
        "before_amount": {"amount": 10000},
        "after_amount": {"amount": 8000},
        "obligation_amount": {"amount": 2000},
        "before_due_date": "2026-08-01",
        "after_due_date": "2026-08-02",
        "source_obligation_identity": None,
        "direction": "refund_due",
        "direction_amount_ntd": 0,
    }
    session = FakeSession([
        _response(
            _preview_data(
                client_finance_impact=_client_finance_impact(
                    actions=[invalid_action]
                )
            )
        )
    ])
    client = OrderCancellationApiClient(
        base_url="https://api.example", headers={}, session=session
    )

    with pytest.raises(OrderCancellationApiError) as caught:
        client.preview("C-1", _confirmed_days(), correlation_id="corr-1")

    assert "回傳格式不正確" in str(caught.value)
