"""
File: test_staff_historical_import_api_client.py
Description: 驗證 Staff historical-only API client 的 Preview／Apply multipart 契約。
"""

from ui.api_clients.staff_historical_import_api_client import StaffHistoricalImportApiClient


class _Response:
    ok = True
    status_code = 200

    def json(self):
        return {"data": _receipt(), "message": "ok"}


class _Session:
    def __init__(self) -> None:
        self.kwargs = None

    def request(self, *args, **kwargs):
        self.kwargs = kwargs
        return _Response()


def test_apply_sends_source_revision_preview_and_command_headers():
    session = _Session()
    client = StaffHistoricalImportApiClient(base_url="http://api", headers={}, session=session)

    receipt = client.apply_workbook(
        "staff.xlsx", b"xlsx", source_revision="refresh-1",
        preview_fingerprint="b" * 64, idempotency_key="staff-key", correlation_id="corr",
    )

    assert receipt.created_count == 1
    assert session.kwargs["data"] == {"source_revision": "refresh-1"}
    assert session.kwargs["headers"]["X-Preview-Fingerprint"] == "b" * 64


def _receipt():
    return {
        "source_content_digest": "a" * 64,
        "source_row_count": 1,
        "created_count": 1,
        "adopted_existing_count": 0,
        "exact_replay_count": 0,
        "blocked_identity_count": 0,
        "identity_conflict_count": 0,
        "review_required_count": 0,
        "preview_fingerprint": "b" * 64,
        "replayed_workbook": False,
    }
