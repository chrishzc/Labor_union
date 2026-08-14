"""
File: test_hcm_import_api_client.py
Description: 驗證 HCM API client 的 multipart Preview／Apply 與 strict result 邊界。
"""

from __future__ import annotations

import pytest

from ui.api_clients.hcm_import_api_client import HcmImportApiClient, HcmImportApiError


class _Response:
    def __init__(self, status_code, payload) -> None:
        self.status_code = status_code
        self._payload = payload

    @property
    def ok(self):
        return self.status_code < 400

    def json(self):
        return self._payload


class _Session:
    def __init__(self, response) -> None:
        self.response = response
        self.request_args = None
        self.request_kwargs = None

    def request(self, *args, **kwargs):
        self.request_args = args
        self.request_kwargs = kwargs
        return self.response


def test_client_sends_multipart_and_validates_receipt():
    response = _Response(200, {"data": _receipt(), "message": "done"})
    session = _Session(response)
    client = HcmImportApiClient(base_url="http://api", headers={"Authorization": "Bearer token"}, session=session)

    receipt = client.ingest_workbook("hcm.xlsx", b"xlsx", idempotency_key="key", correlation_id="corr")

    assert receipt.inserted_count == 1
    assert session.request_kwargs["headers"]["Idempotency-Key"] == "key"
    assert session.request_kwargs["files"]["workbook"][0] == "hcm.xlsx"


def test_client_supports_preview_then_apply():
    preview_session = _Session(_Response(200, {"data": _preview(), "message": "preview"}))
    preview_client = HcmImportApiClient(base_url="http://api", headers={}, session=preview_session)
    preview = preview_client.preview_workbook("hcm.xlsx", b"xlsx")

    apply_session = _Session(_Response(200, {"data": _receipt(), "message": "applied"}))
    apply_client = HcmImportApiClient(base_url="http://api", headers={}, session=apply_session)
    apply_client.apply_workbook(
        "hcm.xlsx", b"xlsx", preview_fingerprint=preview.preview_fingerprint,
        idempotency_key="key", correlation_id="corr",
    )

    assert preview.ready_count == 1
    assert preview_session.request_kwargs["headers"].get("Idempotency-Key") is None
    assert apply_session.request_kwargs["headers"]["X-Preview-Fingerprint"] == "b" * 64


def test_client_targets_the_historical_hcm_workbook_contract():
    preview_session = _Session(_Response(200, {"data": _preview(), "message": "preview"}))
    client = HcmImportApiClient(base_url="http://api", headers={}, session=preview_session)

    preview = client.preview_historical_workbook("history.xlsx", b"xlsx")

    assert preview.ready_count == 1
    assert preview_session.request_args[1].endswith("/historical-workbooks/preview")


def test_client_surfaces_typed_http_error():
    client = HcmImportApiClient(base_url="http://api", headers={}, session=_Session(_Response(409, {"detail": {"code": "conflict"}})))

    with pytest.raises(HcmImportApiError, match="conflict"):
        client.ingest_workbook("hcm.xlsx", b"xlsx", idempotency_key="key", correlation_id="corr")


def _receipt():
    return {
        "source_content_digest": "a" * 64,
        "source_row_count": 1,
        "inserted_count": 1,
        "inserted_with_warning_count": 0,
        "exact_replay_count": 0,
        "review_required_count": 0,
        "failed_count": 0,
        "replayed_workbook": False,
    }


def _preview():
    return {
        "source_content_digest": "a" * 64,
        "source_row_count": 1,
        "ready_count": 1,
        "ready_with_warning_count": 0,
        "review_required_count": 0,
        "preview_fingerprint": "b" * 64,
    }
