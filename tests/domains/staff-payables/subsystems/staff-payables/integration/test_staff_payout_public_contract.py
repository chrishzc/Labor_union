"""
File: test_staff_payout_public_contract.py
Description: 驗證 Staff Payout Preview 以 strict typed candidate 取代 raw dict，且 JobAccepted 不被誤作付款完成。
"""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.dependencies.admin_auth import require_system_admin
from api.dependencies.staff_payout import get_staff_payout_application
from api.routes.staff_payout import _preview_payload, router
from api.schemas.jobs import JobAcceptedResponse
from api.schemas.staff_payout import StaffPayoutPreviewView
from domains.staff_payables.reconciliation import (
    StaffPayableStatus,
    StaffPayoutCandidate,
    StaffPayoutEventStatus,
    StaffPayoutEventType,
    StaffPayoutLedgerEventCandidate,
)
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.money import MoneyNTD
from subsystems.staff_payables.payout_reconciliation import StaffPayoutReconciliationPreview


class _PreviewOnlyPayoutApplication:
    """只提供零寫入 Preview，供 HTTP public-contract 驗證使用。"""

    def __init__(self, preview: StaffPayoutReconciliationPreview) -> None:
        self._preview = preview

    def preview(self, _selection, _correlation_id) -> StaffPayoutReconciliationPreview:
        return self._preview


def test_preview_candidate_is_a_strict_typed_union_not_raw_dict():
    fingerprint = PreviewFingerprint("a" * 64)
    candidate = StaffPayoutCandidate(
        staff_id=7,
        bank_total=MoneyNTD(1000),
        obligation_total=MoneyNTD(1000),
        allocations=(),
        fingerprint=fingerprint,
        events=(
            StaffPayoutLedgerEventCandidate(
                "payout:7:1", StaffPayoutEventType.PAYOUT,
                StaffPayoutEventStatus.SUCCEEDED, 7, MoneyNTD(1000), "bank:1",
            ),
        ),
        obligation_links=(),
        resulting_status=StaffPayableStatus.COMPLETED,
    )
    view = _preview_payload(
        StaffPayoutReconciliationPreview(candidate, 4, 9, fingerprint),
        StaffPayoutEventType.PAYOUT,
    )
    assert isinstance(view, StaffPayoutPreviewView)
    assert view.candidate.staff_id == 7
    assert view.candidate.events[0].amount.amount == 1000
    assert StaffPayoutPreviewView.model_fields["candidate"].annotation is not dict


def test_job_accepted_is_queue_receipt_not_payout_completion_receipt():
    accepted = JobAcceptedResponse(job_id="job-1", status_url="/api/v1/jobs/job-1")
    assert not hasattr(accepted, "resulting_status")
    assert not hasattr(accepted, "event_count")


def test_preview_route_serializes_closed_candidate_union_without_a_payment_receipt():
    fingerprint = PreviewFingerprint("b" * 64)
    candidate = StaffPayoutCandidate(
        staff_id=8,
        bank_total=MoneyNTD(1200),
        obligation_total=MoneyNTD(1200),
        allocations=(),
        fingerprint=fingerprint,
        events=(
            StaffPayoutLedgerEventCandidate(
                "payout:8:1", StaffPayoutEventType.PAYOUT,
                StaffPayoutEventStatus.SUCCEEDED, 8, MoneyNTD(1200), "bank:8",
            ),
        ),
        obligation_links=(),
        resulting_status=StaffPayableStatus.COMPLETED,
    )
    application = _PreviewOnlyPayoutApplication(
        StaffPayoutReconciliationPreview(candidate, 5, 12, fingerprint)
    )
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_system_admin] = lambda: object()
    app.dependency_overrides[get_staff_payout_application] = lambda: application
    try:
        response = TestClient(app).post(
            "/api/v1/staff-payables/payout/preview",
            headers={"X-Correlation-ID": "staff-payout-public-contract"},
            json={"finance_import_row_ids": [8], "obligation_identities": ["obligation:8"]},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["data"]["candidate"]["bank_total"] == {"amount": 1200}
    assert payload["data"]["candidate"]["resulting_status"] == "completed"
    assert "event_count" not in payload["data"]
