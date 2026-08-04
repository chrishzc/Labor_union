"""Contract coverage for manual refund-return correction transport."""

from ui.api_clients.finance_import_api_client import FinanceImportApiClient


class _Response:
    ok = True
    status_code = 200

    def __init__(self, data):
        self._data = data

    def json(self):
        return {"success": True, "data": self._data}


class _Session:
    def __init__(self, responses):
        self._responses = iter(responses)
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return next(self._responses)


def test_refund_return_preview_and_apply_preserve_immutable_ledger_target():
    preview_payload = {
        "candidate": {
            "row_identity": "bank-row-1",
            "batch_identity": "batch-1",
            "classification_type": "client_refund_return",
            "owning_domain": "client_finance",
            "bank_amount_ntd": 500,
            "allocations": [{"obligation_identity": "refund:C-1", "amount_ntd": 500}],
            "reason": "銀行退匯已核對",
            "evidence": ["bank-return-notice"],
            "refund_ledger_entry_identity": "41",
            "candidate_fingerprint": "a" * 64,
        },
        "batch_version": 3,
        "canonical_fact_version": 4,
        "alert_version": 5,
        "preview_fingerprint": "b" * 64,
    }
    session = _Session([
        _Response(preview_payload),
        _Response({"job_id": "job-1", "status_url": "/api/v1/jobs/job-1"}),
    ])
    client = FinanceImportApiClient(
        base_url="https://api.example",
        headers={"X-Internal-API-Key": "test"},
        session=session,
    )

    preview = client.preview_correction(
        "bank-row-1",
        "client_refund_return",
        ["refund:C-1"],
        "銀行退匯已核對",
        ["bank-return-notice"],
        "correlation-preview",
        "41",
    )
    job = client.apply_correction(
        preview,
        idempotency_key="correction-key",
        correlation_id="correlation-apply",
    )

    assert job.job_id == "job-1"
    assert session.calls[0][2]["json"]["refund_ledger_entry_identity"] == "41"
    assert session.calls[1][2]["json"]["refund_ledger_entry_identity"] == "41"
    assert session.calls[1][2]["headers"]["Idempotency-Key"] == "correction-key"
