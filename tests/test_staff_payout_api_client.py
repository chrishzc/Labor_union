from api.schemas.staff_payout import (
    StaffOverpaymentRecoveryMatchingApplyBody,
    StaffOverpaymentRecoveryMatchingPreviewBody,
)
from ui.api_clients.staff_payout_api_client import StaffPayoutApiClient


class _Response:
    ok = True
    status_code = 200
    headers: dict[str, str] = {}

    def __init__(self, payload: object) -> None:
        self._payload = payload

    def json(self) -> object:
        return self._payload


class _Session:
    def __init__(self, payload: object) -> None:
        self._payload = payload
        self.calls: list[dict[str, object]] = []

    def request(self, method, url, **kwargs):
        self.calls.append({"method": method, "url": url, **kwargs})
        return _Response(self._payload)


def test_staff_recovery_matching_client_posts_typed_preview_payload() -> None:
    session = _Session({"success": True, "data": _preview_payload()})
    client = StaffPayoutApiClient(base_url="http://api.test", headers={}, session=session)

    preview = client.preview_overpayment_recovery_matching(
        StaffOverpaymentRecoveryMatchingPreviewBody(
            recovery_identity="recovery-1", finance_import_row_id=17
        ),
        "correlation-1",
    )

    assert preview.finance_import_row_identity == "finance-import-row:17"
    assert session.calls == [{
        "method": "POST",
        "url": "http://api.test/api/v1/staff-payables/overpayment-recoveries/matching/preview",
        "headers": {"X-Correlation-ID": "correlation-1"},
        "json": {"recovery_identity": "recovery-1", "finance_import_row_id": 17},
        "timeout": 15.0,
    }]


def test_staff_recovery_matching_client_posts_typed_apply_payload() -> None:
    session = _Session({"success": True, "data": _receipt_payload()})
    client = StaffPayoutApiClient(base_url="http://api.test", headers={}, session=session)
    body = StaffOverpaymentRecoveryMatchingApplyBody(
        recovery_identity="recovery-1", finance_import_row_id=17,
        expected_recovery_version=2, expected_staff_payables_version=5,
        preview_fingerprint="a" * 64, reason="matched evidence",
    )

    receipt = client.apply_overpayment_recovery_matching(
        body, "idempotency-1", "correlation-1"
    )

    assert receipt.matching_identity == "matching-1"
    assert session.calls[0]["headers"] == {
        "Idempotency-Key": "idempotency-1", "X-Correlation-ID": "correlation-1"
    }
    assert session.calls[0]["json"] == body.model_dump(mode="json")


def _preview_payload() -> dict[str, object]:
    return {
        "recovery_identity": "recovery-1", "staff_id": 7,
        "finance_import_row_identity": "finance-import-row:17",
        "recovery_version": 2, "staff_payables_version": 5,
        "preview_fingerprint": "a" * 64,
    }


def _receipt_payload() -> dict[str, object]:
    return {
        "matching_identity": "matching-1", "matching_version": 1,
        "recovery_identity": "recovery-1", "staff_id": 7,
        "finance_import_row_identity": "finance-import-row:17",
        "recovery_version": 2, "staff_payables_version": 5,
    }
