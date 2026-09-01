"""
File: test_historical_order_adoption_api_client.py
Description: 驗證 Orders historical workbook UI client 的 multipart 與 strict response 邊界。
"""

from __future__ import annotations

import pytest

from ui.api_clients.historical_order_adoption_api_client import HistoricalOrderAdoptionApiClient, HistoricalOrderAdoptionApiError


class _Response:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    @property
    def ok(self):
        return self.status_code < 400

    def json(self):
        return self._payload


class _Session:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def request(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return self.response


def test_preview_and_apply_validate_typed_views():
    preview_payload = _preview_payload()
    preview_session = _Session(_Response(200, {"success": True, "data": preview_payload}))
    client = HistoricalOrderAdoptionApiClient(base_url="http://api", headers={}, session=preview_session)

    preview = client.preview_workbook("orders.xlsx", b"workbook")
    assert preview.source_row_count == 1
    assert preview_session.calls[0][1]["data"] is None

    receipt_session = _Session(_Response(200, {"success": True, "data": _receipt_payload()}))
    receipt_client = HistoricalOrderAdoptionApiClient(base_url="http://api", headers={}, session=receipt_session)
    receipt = receipt_client.apply_workbook("orders.xlsx", b"workbook", preview_fingerprint=preview.preview_fingerprint, idempotency_key="key", correlation_id="corr")
    assert receipt.replayed_workbook is False
    assert receipt_session.calls[0][1]["data"]["preview_fingerprint"] == preview.preview_fingerprint


def test_typed_error_is_preserved():
    client = HistoricalOrderAdoptionApiClient(
        base_url="http://api", headers={}, session=_Session(_Response(409, {"detail": {"code": "historical_order_workbook_idempotency_conflict"}})),
    )
    try:
        client.preview_workbook("orders.xlsx", b"workbook")
    except HistoricalOrderAdoptionApiError as error:
        assert error.code == "historical_order_workbook_idempotency_conflict"
    else:
        raise AssertionError("expected typed API error")


def test_preview_and_receipt_reject_non_conserved_status_counts():
    preview_payload = _preview_payload()
    preview_payload["status_counts"] = {
        "cancelled_0": 0, "deposit_paid_1": 0, "discussion_2": 0, "invalid_or_blank": 0,
    }
    client = HistoricalOrderAdoptionApiClient(
        base_url="http://api", headers={}, session=_Session(_Response(200, {"success": True, "data": preview_payload})),
    )
    with pytest.raises(HistoricalOrderAdoptionApiError, match="historical_order_import_response_invalid"):
        client.preview_workbook("orders.xlsx", b"workbook")

    receipt_payload = _receipt_payload()
    receipt_payload["status_counts"] = {
        "cancelled_0": 0, "deposit_paid_1": 0, "discussion_2": 0, "invalid_or_blank": 0,
    }
    receipt_client = HistoricalOrderAdoptionApiClient(
        base_url="http://api", headers={}, session=_Session(_Response(200, {"success": True, "data": receipt_payload})),
    )
    with pytest.raises(HistoricalOrderAdoptionApiError, match="historical_order_import_response_invalid"):
        receipt_client.apply_workbook(
            "orders.xlsx", b"workbook", preview_fingerprint="2" * 64,
            idempotency_key="key", correlation_id="corr",
        )


def _preview_payload():
    return {
        "source_content_digest": "0" * 64, "sheet_identity": "1" * 64, "source_row_count": 1,
        "adopted_count": 1, "unmatched_case_count": 0, "review_required_count": 0, "current_conflict_count": 0,
        "assignment_candidate_count": 0, "evidence_only_pairing_count": 0,
        "status_counts": {"cancelled_0": 0, "deposit_paid_1": 1, "discussion_2": 0, "invalid_or_blank": 0},
        "preview_fingerprint": "2" * 64,
    }


def _receipt_payload():
    return {
        "source_content_digest": "0" * 64, "source_row_count": 1, "adopted_count": 1,
        "unmatched_case_count": 0, "review_required_count": 0, "current_conflict_count": 0,
        "assignments_created": 0, "replayed_rows": 0, "replayed_workbook": False,
        "status_counts": {"cancelled_0": 0, "deposit_paid_1": 1, "discussion_2": 0, "invalid_or_blank": 0},
        "review_references": [],
    }
