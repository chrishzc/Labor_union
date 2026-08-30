from __future__ import annotations

import pytest

from api.schemas.data_browser import (
    DataBrowserSourceCorrectionPreviewView,
    DataBrowserSourceCorrectionReceiptView,
)
from ui.api_clients.data_browser_correction_api_client import (
    DataBrowserCorrectionApiClient,
    DataBrowserCorrectionApiError,
)


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


def test_data_browser_correction_client_validates_preview_and_receipt_identity():
    session = _Session(
        [
            {
                "success": True,
                "message": "ok",
                "data": {
                    "table": "clients",
                    "row_id": 7,
                    "changes": {
                        "phone": {"before": "0911", "after": "0922"}
                    },
                    "preview_fingerprint": "a" * 64,
                },
            },
            {
                "success": True,
                "message": "ok",
                "data": {
                    "table": "clients",
                    "row_id": 7,
                    "changed_fields": ["phone"],
                },
            },
        ]
    )
    client = DataBrowserCorrectionApiClient(
        base_url="http://api.test",
        headers={"Authorization": "Bearer test"},
        session=session,
    )

    preview = client.preview("clients", 7, {"phone": "0922"})
    receipt = client.apply(
        "clients",
        7,
        {"phone": "0922"},
        preview,
        reason="人工核對",
        idempotency_key="correction-7",
    )

    assert isinstance(preview, DataBrowserSourceCorrectionPreviewView)
    assert isinstance(receipt, DataBrowserSourceCorrectionReceiptView)
    assert session.calls[0][1]["json"] == {"updates": {"phone": "0922"}}
    assert session.calls[1][1]["headers"]["Idempotency-Key"] == "correction-7"
    assert session.calls[1][1]["json"] == {
        "updates": {"phone": "0922"},
        "preview_fingerprint": "a" * 64,
        "reason": "人工核對",
    }


def test_data_browser_correction_client_blocks_mismatched_receipt():
    preview = DataBrowserSourceCorrectionPreviewView.model_validate(
        {
            "table": "clients",
            "row_id": 7,
            "changes": {"phone": {"before": "0911", "after": "0922"}},
            "preview_fingerprint": "a" * 64,
        }
    )
    session = _Session(
        [
            {
                "success": True,
                "message": "ok",
                "data": {
                    "table": "clients",
                    "row_id": 8,
                    "changed_fields": ["phone"],
                },
            }
        ]
    )

    with pytest.raises(DataBrowserCorrectionApiError):
        DataBrowserCorrectionApiClient(
            base_url="http://api.test",
            headers={},
            session=session,
        ).apply(
            "clients",
            7,
            {"phone": "0922"},
            preview,
            reason="人工核對",
            idempotency_key="correction-7",
        )
