"""Contract tests for the deposit reversal UI HTTP client."""

from __future__ import annotations

from datetime import date

from ui.api_clients.client_deposit_reversal_api_client import (
    ClientDepositReversalApiClient,
)


class _Response:
    def __init__(self, body, *, status_code: int = 200) -> None:
        self._body = body
        self.status_code = status_code
        self.ok = status_code < 400

    def json(self):
        return self._body


class _Session:
    def __init__(self, responses) -> None:
        self._responses = iter(responses)
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return next(self._responses)


def _response(data):
    return _Response({"success": True, "data": data})


def test_deposit_reversal_client_carries_preview_version_and_apply_identity():
    session = _Session(
        [
            _response(
                {
                    "account_version": 4,
                    "candidate": {"reversal_amount_ntd": 1200},
                    "preview_fingerprint": "a" * 64,
                }
            ),
            _response(
                {
                    "case_no": "C-14",
                    "account_version": 5,
                    "original_ledger_entry_id": 42,
                    "reversal_amount_ntd": 1200,
                    "lifecycle_intent": "reconfirm_actual_start",
                    "anomaly_code": None,
                }
            ),
        ]
    )
    client = ClientDepositReversalApiClient(
        base_url="https://api.example",
        headers={"X-Internal-API-Key": "test"},
        session=session,
    )

    preview = client.preview(
        "C-14",
        42,
        date(2026, 8, 8),
        correlation_id="preview-14",
    )
    receipt = client.apply(
        "C-14",
        42,
        date(2026, 8, 8),
        preview,
        reason="bank receipt was reversed",
        idempotency_key="apply-14",
        correlation_id="apply-14",
    )

    assert receipt.account_version == 5
    assert session.calls[0][0].endswith("/deposit-reversal/preview")
    assert session.calls[1][0].endswith("/deposit-reversal/apply")
    assert session.calls[1][1]["json"]["expected_account_version"] == 4
    assert session.calls[1][1]["json"]["preview_fingerprint"] == "a" * 64
    assert session.calls[1][1]["headers"]["Idempotency-Key"] == "apply-14"
