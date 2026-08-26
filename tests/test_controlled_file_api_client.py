"""
File: test_controlled_file_api_client.py
Description: 驗證 controlled-file UI client 的 typed contract、路由與敏感 locator fail-closed 行為。
"""

from __future__ import annotations

import io

import pytest
import requests

from ui.api_clients.controlled_file_api_client import (
    ControlledFileApiClient,
    ControlledFileApiError,
    ControlledFileApplyReceiptView,
    ControlledFileIntent,
    ControlledFileOwner,
    ControlledFilePurpose,
    ControlledFileView,
)


FILE_ID = "cf_" + "a" * 32
RECEIPT_ID = "cfr_" + "b" * 32
STAGING_ID = "cfs_" + "c" * 32
DIGEST = "d" * 64
NOW = "2026-08-26T00:00:00Z"


class _Response:
    def __init__(self, *, ok=True, status_code=200, payload=None, content=b""):
        self.ok = ok
        self.status_code = status_code
        self._payload = payload
        self.content = content

    def json(self):
        return self._payload


class _Session:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return self.responses.pop(0)


def _intent():
    return ControlledFileIntent(
        staging_id=STAGING_ID,
        owner=ControlledFileOwner.ORDERS,
        purpose=ControlledFilePurpose.ORDER_NOTICE,
        subject_reference="ORD-1",
        object_key="notice",
        logical_folder="orders/ORD-1",
    )


def _candidate():
    return {
        **_intent().model_dump(mode="json"),
        "staging_version": 3,
        "filename": "NOTICE_ORD-1_SEQ-1.pdf",
        "mime_type": "application/pdf",
        "size_bytes": 12,
        "sha256_digest": DIGEST,
        "expires_at": NOW,
    }


def _file_view():
    return {
        "file_id": FILE_ID,
        "owner": "orders",
        "purpose": "order_notice",
        "subject_reference": "ORD-1",
        "filename": "NOTICE_ORD-1_SEQ-1.pdf",
        "logical_folder": "orders/ORD-1",
        "mime_type": "application/pdf",
        "size_bytes": 12,
        "version": 1,
        "status": "registered",
        "applied_at": NOW,
    }


def _receipt():
    return {
        "receipt_id": RECEIPT_ID,
        "outcome": "created",
        "file_id": FILE_ID,
        "owner": "orders",
        "purpose": "order_notice",
        "subject_reference": "ORD-1",
        "filename": "NOTICE_ORD-1_SEQ-1.pdf",
        "logical_folder": "orders/ORD-1",
        "version": 1,
        "sha256_digest": DIGEST,
        "mime_type": "application/pdf",
        "size_bytes": 12,
        "status": "registered",
        "applied_at": NOW,
        "receipt_type": "controlled_file_apply",
        "schema_version": "controlled-file-apply-receipt.v1",
    }


def test_preview_and_apply_use_canonical_routes_and_return_typed_views():
    session = _Session(
        [
            _Response(payload={"success": True, "data": {"candidate": _candidate(), "preview_fingerprint": "fp-1", "expected_staging_version": 3, "blockers": []}}),
            _Response(payload={"success": True, "data": _receipt()}),
        ]
    )
    client = ControlledFileApiClient(base_url="http://api", headers={}, session=session)

    preview = client.preview(_intent(), correlation_id="corr-1")
    receipt = client.apply(_intent(), preview, idempotency_key="idem-1", correlation_id="corr-2")

    assert preview.candidate.owner is ControlledFileOwner.ORDERS
    assert isinstance(receipt, ControlledFileApplyReceiptView)
    assert session.calls[0][1].endswith("/api/v1/storage/files/preview")
    assert session.calls[1][1].endswith("/api/v1/storage/files/apply")
    assert session.calls[1][2]["headers"]["Idempotency-Key"] == "idem-1"


def test_detail_and_receipt_are_typed_and_use_opaque_identifiers():
    session = _Session(
        [
            _Response(payload={"success": True, "data": _file_view()}),
            _Response(payload={"success": True, "data": _receipt()}),
        ]
    )
    client = ControlledFileApiClient(base_url="http://api", headers={}, session=session)

    detail = client.detail(FILE_ID)
    receipt = client.receipt(RECEIPT_ID)

    assert isinstance(detail, ControlledFileView)
    assert isinstance(receipt, ControlledFileApplyReceiptView)
    assert session.calls[0][1].endswith(f"/api/v1/storage/files/{FILE_ID}")
    assert session.calls[1][1].endswith(f"/api/v1/storage/receipts/{RECEIPT_ID}")


@pytest.mark.parametrize("forbidden_field", ["storage_locator", "path", "public_url"])
def test_public_models_fail_closed_on_locator_or_public_url_fields(forbidden_field):
    payload = _file_view()
    payload[forbidden_field] = "C:/secret/object.pdf"
    session = _Session([_Response(payload={"success": True, "data": payload})])
    client = ControlledFileApiClient(base_url="http://api", headers={}, session=session)

    with pytest.raises(ControlledFileApiError) as raised:
        client.detail(FILE_ID)

    assert raised.value.error.code == "controlled_file_invalid_response"


def test_transport_failure_becomes_a_typed_retryable_error():
    class _BrokenSession:
        def request(self, *args, **kwargs):
            raise requests.ConnectionError("offline")

    client = ControlledFileApiClient(base_url="http://api", headers={}, session=_BrokenSession())

    with pytest.raises(ControlledFileApiError) as raised:
        client.detail(FILE_ID)

    assert raised.value.error.code == "controlled_file_transport_error"
    assert raised.value.error.retryable is True


def test_stage_and_download_never_return_a_path_or_public_url():
    stage_payload = {
        "staging_id": STAGING_ID,
        "filename": "notice.pdf",
        "mime_type": "application/pdf",
        "size_bytes": 3,
        "sha256_digest": DIGEST,
        "expires_at": NOW,
    }
    session = _Session(
        [
            _Response(payload={"success": True, "data": stage_payload}),
            _Response(payload={}, content=b"pdf"),
        ]
    )
    client = ControlledFileApiClient(base_url="http://api", headers={}, session=session)

    staged = client.stage(
        io.BytesIO(b"pdf"),
        filename="notice.pdf",
        mime_type="application/pdf",
        idempotency_key="idem-stage",
        correlation_id="corr-stage",
        owner=ControlledFileOwner.ORDERS,
        purpose=ControlledFilePurpose.ORDER_NOTICE,
        subject_reference="ORD-1",
        object_key="notice",
        logical_folder="orders/ORD-1",
    )
    downloaded = client.download(FILE_ID)

    assert staged.staging_id == STAGING_ID
    assert downloaded == b"pdf"
    assert not hasattr(staged, "storage_locator")


def test_invalid_identifier_is_rejected_before_transport():
    session = _Session([])
    client = ControlledFileApiClient(base_url="http://api", headers={}, session=session)

    with pytest.raises(ValueError, match="file_id is invalid"):
        client.detail("../../secret")

    assert session.calls == []
