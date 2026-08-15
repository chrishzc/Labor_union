"""
File: test_client_beclass_import_api_client.py
Description: 驗證 Client BeClass API client 的 typed Preview／Apply multipart 契約。
"""

from ui.api_clients.client_beclass_import_api_client import ClientBeClassImportApiClient


class _Response:
    ok = True
    status_code = 200

    def __init__(self, data) -> None:
        self._data = data

    def json(self):
        return {"data": self._data, "message": "ok"}


class _Session:
    def __init__(self, response) -> None:
        self.response = response
        self.kwargs = None

    def request(self, *args, **kwargs):
        self.kwargs = kwargs
        return self.response


def test_apply_binds_preview_fingerprint_and_command_headers():
    session = _Session(_Response(_receipt()))
    client = ClientBeClassImportApiClient(base_url="http://api", headers={}, session=session)

    receipt = client.apply_workbook(
        "client.xlsx", b"xlsx", preview_fingerprint="b" * 64,
        idempotency_key="client-key", correlation_id="corr",
    )

    assert receipt.created_count == 1
    assert session.kwargs["data"]["preview_fingerprint"] == "b" * 64
    assert session.kwargs["headers"]["Idempotency-Key"] == "client-key"


def _receipt():
    return {
        "source_content_digest": "a" * 64,
        "source_row_count": 1,
        "created_count": 1,
        "exact_replay_count": 0,
        "review_required_count": 0,
        "existing_conflict_count": 0,
        "existing_source_count": 0,
        "replayed_workbook": False,
    }
