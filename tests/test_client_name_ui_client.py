from __future__ import annotations

import pytest

from api.schemas.orders import ClientNamePreviewView, ClientNameReceiptView
from ui.api_clients.client_name_api_client import ClientNameApiClient, ClientNameApiError


class _Response:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _Session:
    def __init__(self, payloads):
        self._payloads = iter(payloads)
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return _Response(next(self._payloads))


def test_client_name_preview_apply_use_typed_views_and_preserve_command_shape():
    preview_payload = {
        "case_no": "CASE-97",
        "before_client_name": "原姓名",
        "after_client_name": "新姓名",
        "terms_impact": "none",
        "scheduling_impact": "none",
        "preview_fingerprint": "a" * 64,
    }
    session = _Session(
        [
            {"success": True, "message": "ok", "data": preview_payload},
            {
                "success": True,
                "message": "ok",
                "data": {
                    "case_no": "CASE-97",
                    "client_name": "新姓名",
                    "changed": True,
                },
            },
        ]
    )
    client = ClientNameApiClient(
        base_url="http://api.test",
        headers={"Authorization": "Bearer test"},
        session=session,
    )

    preview = client.preview("CASE-97", " 新姓名 ")
    receipt = client.apply(
        "CASE-97",
        preview,
        reason="人工核對",
        idempotency_key="client-name-1",
    )

    assert isinstance(preview, ClientNamePreviewView)
    assert isinstance(receipt, ClientNameReceiptView)
    assert session.calls[0][1]["json"] == {"client_name": "新姓名"}
    assert session.calls[1][1]["json"] == {
        "client_name": "新姓名",
        "preview_fingerprint": "a" * 64,
        "reason": "人工核對",
    }
    assert session.calls[1][1]["headers"]["Idempotency-Key"] == "client-name-1"


def test_client_name_client_rejects_raw_projection_drift():
    session = _Session(
        [
            {
                "success": True,
                "message": "ok",
                "data": {
                    "case_no": "CASE-97",
                    "before_client_name": None,
                    "after_client_name": "新姓名",
                    "terms_impact": "none",
                    "scheduling_impact": "none",
                    "preview_fingerprint": "a" * 64,
                    "raw_client_row": {"identity_status": "private"},
                },
            }
        ]
    )

    with pytest.raises(ClientNameApiError):
        ClientNameApiClient(
            base_url="http://api.test",
            headers={},
            session=session,
        ).preview("CASE-97", "新姓名")
