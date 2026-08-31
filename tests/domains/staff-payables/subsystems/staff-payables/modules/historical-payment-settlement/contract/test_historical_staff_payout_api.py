from __future__ import annotations

from datetime import date

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from api.dependencies.admin_auth import require_admin
from api.dependencies.staff_payout import get_historical_staff_payout_workflow
from api.routes.staff_payout import router
from domains.staff_payables.historical_payout import (
    HistoricalStaffConfirmationKind,
    HistoricalStaffObligation,
    HistoricalStaffPayoutCandidate,
    HistoricalStaffPayoutFacts,
    HistoricalStaffPayoutIntent,
    HistoricalStaffPayoutProjection,
    HistoricalStaffSourceAvailability,
)
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.errors import ErrorCategory, TypedError
from shared_kernel.identities import CorrelationId, ExpectedVersion
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.staff_payables.historical_payment_settlement import (
    HistoricalStaffPayoutPreview,
    HistoricalStaffPayoutError,
    HistoricalStaffPayoutReadback,
    HistoricalStaffPayoutReceipt,
)


CASE_NO = "H-STAFF-API-1"
STAFF_ID = 9
FINGERPRINT = PreviewFingerprint("b" * 64)


def _intent() -> HistoricalStaffPayoutIntent:
    return HistoricalStaffPayoutIntent(
        CASE_NO,
        STAFF_ID,
        HistoricalStaffConfirmationKind.PAID,
        ("staff-obligation:api:1",),
        date(2025, 2, 3),
        None,
        HistoricalStaffSourceAvailability.UNRECOVERABLE,
        "payout-reference:8",
    )


def _obligation() -> HistoricalStaffObligation:
    return HistoricalStaffObligation(
        "staff-obligation:api:1",
        CASE_NO,
        STAFF_ID,
        1800,
        4,
        "payable_to_staff",
        "open",
    )


class _Application:
    def __init__(self) -> None:
        self.applied = None

    def query(self, case_no, staff_id):
        assert (case_no, staff_id) == (CASE_NO, STAFF_ID)
        return HistoricalStaffPayoutFacts(case_no, staff_id, 6, 42, True, (), (_obligation(),))

    def preview(self, intent):
        assert intent == _intent()
        return HistoricalStaffPayoutPreview(
            HistoricalStaffPayoutCandidate(intent, 6, 42, (_obligation(),), 1800, (), FINGERPRINT)
        )

    def apply(self, request):
        self.applied = request
        return HistoricalStaffPayoutReceipt(
            "historical-staff-payout:event:1",
            CASE_NO,
            STAFF_ID,
            ("staff-obligation:api:1",),
            1800,
            7,
            FINGERPRINT,
        )

    def readback(self, case_no, staff_id):
        assert (case_no, staff_id) == (CASE_NO, STAFF_ID)
        facts = HistoricalStaffPayoutFacts(case_no, staff_id, 7, 42, True, (), (_obligation(),))
        projections = (HistoricalStaffPayoutProjection("staff-obligation:api:1", 1800, 4),)
        return HistoricalStaffPayoutReadback(facts, projections, True)


def _client(application: _Application) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_admin] = lambda: AdminPrincipal(
        8, "payables-admin", "Payables Admin", "system_admin"
    )
    app.dependency_overrides[get_historical_staff_payout_workflow] = lambda: application
    return TestClient(app)


def test_staff_payables_historical_contract_exposes_query_preview_apply_and_fresh_readback() -> None:
    application = _Application()
    client = _client(application)
    intent = {
        "case_no": CASE_NO,
        "staff_id": STAFF_ID,
        "confirmation_kind": "paid",
        "obligation_identities": ["staff-obligation:api:1"],
        "payment_date": "2025-02-03",
        "payment_date_unknown_reason": None,
        "source_availability": "unrecoverable",
        "evidence_reference": "payout-reference:8",
    }

    query = client.get(
        f"/api/v1/staff-payables/historical-payouts/{CASE_NO}/{STAFF_ID}"
    )
    preview = client.post("/api/v1/staff-payables/historical-payouts/preview", json=intent)
    apply = client.post(
        "/api/v1/staff-payables/historical-payouts/apply",
        headers={"Idempotency-Key": "historical-staff:api:1", "X-Correlation-ID": "corr-staff-api"},
        json={
            **intent,
            "expected_staff_payables_version": 6,
            "expected_adoption_receipt_id": 42,
            "preview_fingerprint": FINGERPRINT.value,
            "reason": "Confirm adopted pre-system payout.",
        },
    )
    readback = client.get(
        f"/api/v1/staff-payables/historical-payouts/{CASE_NO}/{STAFF_ID}/readback"
    )

    assert [response.status_code for response in (query, preview, apply, readback)] == [200, 200, 200, 200]
    assert query.json()["data"]["staff_payables_version"] == 6
    assert preview.json()["data"]["preview_fingerprint"] == FINGERPRINT.value
    assert apply.json()["data"]["resulting_staff_payables_version"] == 7
    assert readback.json()["data"]["owner_terminal"] is True
    assert application.applied.actor.actor_id == "payables-admin"


def test_staff_payables_historical_contract_requires_authenticated_internal_principal() -> None:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_admin] = lambda: (_ for _ in ()).throw(
        HTTPException(status_code=401, detail="authentication_required")
    )

    response = TestClient(app).get(
        f"/api/v1/staff-payables/historical-payouts/{CASE_NO}/{STAFF_ID}"
    )

    assert response.status_code == 401


def test_staff_payables_historical_stale_is_a_closed_typed_conflict() -> None:
    class StaleApplication(_Application):
        def apply(self, request):
            raise HistoricalStaffPayoutError(
                TypedError(
                    ErrorCategory.CONFLICT,
                    "historical_staff_payout_candidate_stale",
                    "Historical Staff Payables payout could not be applied.",
                    CorrelationId("corr-staff-api"),
                    current_version=ExpectedVersion(7),
                )
            )

    response = _client(StaleApplication()).post(
        "/api/v1/staff-payables/historical-payouts/apply",
        headers={"Idempotency-Key": "historical-staff:api:1", "X-Correlation-ID": "corr-staff-api"},
        json={
            "case_no": CASE_NO,
            "staff_id": STAFF_ID,
            "confirmation_kind": "paid",
            "obligation_identities": ["staff-obligation:api:1"],
            "payment_date": "2025-02-03",
            "payment_date_unknown_reason": None,
            "source_availability": "unrecoverable",
            "evidence_reference": "payout-reference:8",
            "expected_staff_payables_version": 6,
            "expected_adoption_receipt_id": 42,
            "preview_fingerprint": FINGERPRINT.value,
            "reason": "Confirm adopted pre-system payout.",
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"]["error"]["code"] == "historical_staff_payout_candidate_stale"
    assert response.json()["detail"]["error"]["current_version"] == 7
