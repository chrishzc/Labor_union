"""
File: test_hcm_import_api_client.py
Description: 驗證 HCM API client 的 multipart command 與 strict receipt 邊界。
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
        self.request_kwargs = None

    def request(self, *args, **kwargs):
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


def test_client_surfaces_typed_http_error():
    client = HcmImportApiClient(base_url="http://api", headers={}, session=_Session(_Response(409, {"detail": {"code": "conflict"}})))

    with pytest.raises(HcmImportApiError, match="conflict"):
        client.ingest_workbook("hcm.xlsx", b"xlsx", idempotency_key="key", correlation_id="corr")


def _receipt():
    return {
        "source_content_digest": "a" * 64,
        "source_row_count": 1,
        "inserted_count": 1,
        "exact_replay_count": 0,
        "review_required_count": 0,
        "failed_count": 0,
        "replayed_workbook": False,
    }
