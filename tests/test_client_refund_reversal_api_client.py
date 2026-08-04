"""Contract tests for the canonical refund UI HTTP client."""

import pytest
from pydantic import ValidationError

from ui.api_clients.client_refund_reversal_api_client import ClientRefundReversalApiClient
from api.schemas.client_refund_reversal import ClientRefundApplyBody, ClientRefundPreviewBody


class _Response:
    def __init__(self, body):
        self._body = body

    def json(self):
        return self._body

    def raise_for_status(self):
        return None


class _Session:
    def __init__(self, responses):
        self._responses = iter(responses)
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append(("GET", url, kwargs))
        return next(self._responses)

    def post(self, url, **kwargs):
        self.calls.append(("POST", url, kwargs))
        return next(self._responses)


def _response(data):
    return _Response({"success": True, "data": data})


def test_client_uses_distinct_subsidy_return_apply_path_and_idempotency_header():
    session = _Session([
        _response({"case_no": "C-1", "account_version": 2, "refund_obligations": [], "subsidy_return_obligations": [], "reversal_targets": [], "refund_return_targets": []}),
        _response({"account_version": 2, "candidate": {}, "preview_fingerprint": "a" * 64}),
        _response({"case_no": "C-1", "correction_type": "refund", "account_version": 3, "correction_identity": "b" * 64, "ledger_entry_count": 1, "allocation_count": 1, "affected_obligations": ["subsidy:C-1"]}),
    ])
    client = ClientRefundReversalApiClient(base_url="https://api.example", headers={"X-Internal-API-Key": "test"}, session=session)

    assert client.query("C-1").account_version == 2
    preview_body = ClientRefundPreviewBody(finance_import_row_ids=[4], obligation_identities=["subsidy:C-1"])
    assert client.preview_subsidy_return("C-1", preview_body).account_version == 2
    apply_body = ClientRefundApplyBody(**preview_body.model_dump(), expected_account_version=2, preview_fingerprint="a" * 64, reason="銀行出款已確認")
    assert client.apply_subsidy_return("C-1", apply_body, "subsidy-key").account_version == 3
    assert session.calls[2][1].endswith("/subsidy-return/apply")
    assert session.calls[2][2]["headers"]["Idempotency-Key"] == "subsidy-key"


def test_query_rejects_unowned_pending_bank_rows():
    session = _Session([
        _response({
            "case_no": "C-1",
            "account_version": 2,
            "refund_obligations": [],
            "subsidy_return_obligations": [],
            "reversal_targets": [],
            "refund_return_targets": [],
            "refund_bank_facts": [{"finance_import_row_id": 99}],
        }),
    ])
    client = ClientRefundReversalApiClient(
        base_url="https://api.example",
        headers={"X-Internal-API-Key": "test"},
        session=session,
    )

    with pytest.raises(ValidationError):
        client.query("C-1")
