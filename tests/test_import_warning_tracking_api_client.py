"""
File: test_import_warning_tracking_api_client.py
Description: 驗證匯入警示 UI client 分離 Preview、Apply receipt 與 receipt lookup。
"""

from api.schemas.import_warning_tracking import WarningTransitionBody
from ui.api_clients.import_warning_tracking_api_client import ImportWarningTrackingApiClient


class _Response:
    ok = True
    status_code = 200

    def json(self):
        return {"success": True, "message": "ok", "data": {"occurrence_identity": "warning-1", "before_status": "open", "after_status": "awaiting_external_confirmation", "resulting_version": 2, "receipt_identity": "a" * 64, "correlation_id": "warning-correlation-1", "replayed": False}}


class _Session:
    def request(self, *_args, **_kwargs):
        return _Response()


def test_client_validates_apply_result_as_typed_view() -> None:
    client = ImportWarningTrackingApiClient(base_url="http://test", headers={}, session=_Session())

    result = client.apply("warning-1", WarningTransitionBody(expected_version=1, target_status="awaiting_external_confirmation", reason_code="contact_started"), idempotency_key="warning-apply-1", correlation_id="warning-correlation-1")

    assert result.resulting_version == 2
    assert result.after_status == "awaiting_external_confirmation"
    assert result.receipt_identity == "a" * 64


def test_client_queries_terminal_receipt_as_typed_view() -> None:
    client = ImportWarningTrackingApiClient(base_url="http://test", headers={}, session=_Session())

    result = client.query_receipt("a" * 64)

    assert result.correlation_id == "warning-correlation-1"
    assert result.replayed is False
