"""
File: test_import_warning_tracking_api_client.py
Description: 驗證匯入警示 UI client 只接受 typed API envelope 與合法轉態結果。
"""

from api.schemas.import_warning_tracking import WarningTransitionBody
from ui.api_clients.import_warning_tracking_api_client import ImportWarningTrackingApiClient


class _Response:
    ok = True
    status_code = 200

    def json(self):
        return {"success": True, "message": "ok", "data": {"occurrence_identity": "warning-1", "expected_version": 1, "resulting_status": "awaiting_external_confirmation", "resulting_version": 2}}


class _Session:
    def request(self, *_args, **_kwargs):
        return _Response()


def test_client_validates_apply_result_as_typed_view() -> None:
    client = ImportWarningTrackingApiClient(base_url="http://test", headers={}, session=_Session())

    result = client.apply("warning-1", WarningTransitionBody(expected_version=1, target_status="awaiting_external_confirmation", reason_code="contact_started"), idempotency_key="warning-apply-1", correlation_id="warning-correlation-1")

    assert result.resulting_version == 2
    assert result.resulting_status == "awaiting_external_confirmation"
