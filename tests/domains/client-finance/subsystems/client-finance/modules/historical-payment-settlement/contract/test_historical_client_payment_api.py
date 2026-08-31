from __future__ import annotations

from datetime import date

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from api.dependencies.admin_auth import require_admin
from api.dependencies.client_payments import get_historical_client_payment_workflow
from api.routes.client_payments import router
from domains.client_finance.historical_payment import (
    HistoricalClientConfirmationKind,
    HistoricalClientDirection,
    HistoricalClientObligation,
    HistoricalClientPaymentCandidate,
    HistoricalClientPaymentFacts,
    HistoricalClientPaymentIntent,
    HistoricalClientPaymentProjection,
    HistoricalClientSourceAvailability,
)
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.errors import ErrorCategory, TypedError
from shared_kernel.identities import CorrelationId, ExpectedVersion
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.client_finance.historical_payment_settlement import (
    HistoricalClientPaymentPreview,
    HistoricalClientPaymentError,
    HistoricalClientPaymentReadback,
    HistoricalClientPaymentReceipt,
)


CASE_NO = "H-CLIENT-API-1"
FINGERPRINT = PreviewFingerprint("a" * 64)


def _intent() -> HistoricalClientPaymentIntent:
    return HistoricalClientPaymentIntent(
        CASE_NO,
        HistoricalClientDirection.RECEIVABLE_FROM_CLIENT,
        HistoricalClientConfirmationKind.PAID,
        ("client-obligation:api:1",),
        date(2025, 1, 8),
        None,
        HistoricalClientSourceAvailability.MISSING,
        "ledger-reference:12",
    )


def _obligation() -> HistoricalClientObligation:
    return HistoricalClientObligation(
        "client-obligation:api:1",
        CASE_NO,
        "first",
        HistoricalClientDirection.RECEIVABLE_FROM_CLIENT,
        1200,
        3,
        "open",
    )


class _Application:
    def __init__(self) -> None:
        self.applied = None

    def query(self, case_no):
        assert case_no == CASE_NO
        return HistoricalClientPaymentFacts(case_no, 7, 41, True, (), (_obligation(),))

    def preview(self, intent):
        assert intent == _intent()
        return HistoricalClientPaymentPreview(
            HistoricalClientPaymentCandidate(intent, 7, 41, (_obligation(),), 1200, (), FINGERPRINT)
        )

    def apply(self, request):
        self.applied = request
        return HistoricalClientPaymentReceipt(
            "historical-client-payment:event:1",
            CASE_NO,
            ("client-obligation:api:1",),
            1200,
            8,
            FINGERPRINT,
        )

    def readback(self, case_no):
        assert case_no == CASE_NO
        facts = HistoricalClientPaymentFacts(case_no, 8, 41, True, (), (_obligation(),))
        projections = (HistoricalClientPaymentProjection("client-obligation:api:1", 1200, 3),)
        return HistoricalClientPaymentReadback(facts, projections, True)


def _client(application: _Application) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_admin] = lambda: AdminPrincipal(
        7, "finance-admin", "Finance Admin", "system_admin"
    )
    app.dependency_overrides[get_historical_client_payment_workflow] = lambda: application
    return TestClient(app)


def test_client_finance_historical_contract_exposes_query_preview_apply_and_fresh_readback() -> None:
    application = _Application()
    client = _client(application)
    intent = {
        "case_no": CASE_NO,
        "direction": "receivable_from_client",
        "confirmation_kind": "paid",
        "obligation_identities": ["client-obligation:api:1"],
        "payment_date": "2025-01-08",
        "payment_date_unknown_reason": None,
        "source_availability": "missing",
        "evidence_reference": "ledger-reference:12",
    }

    query = client.get(f"/api/v1/client-payments/historical-payments/{CASE_NO}")
    preview = client.post("/api/v1/client-payments/historical-payments/preview", json=intent)
    apply = client.post(
        "/api/v1/client-payments/historical-payments/apply",
        headers={"Idempotency-Key": "historical-client:api:1", "X-Correlation-ID": "corr-client-api"},
        json={
            **intent,
            "expected_account_version": 7,
            "expected_adoption_receipt_id": 41,
            "preview_fingerprint": FINGERPRINT.value,
            "reason": "Confirm adopted pre-system payment.",
        },
    )
    readback = client.get(
        f"/api/v1/client-payments/historical-payments/{CASE_NO}/readback"
    )

    assert [response.status_code for response in (query, preview, apply, readback)] == [200, 200, 200, 200]
    assert query.json()["data"]["account_version"] == 7
    assert preview.json()["data"]["preview_fingerprint"] == FINGERPRINT.value
    assert apply.json()["data"]["resulting_account_version"] == 8
    assert readback.json()["data"]["owner_terminal"] is True
    assert application.applied.actor.actor_id == "finance-admin"


def test_client_finance_historical_contract_requires_authenticated_internal_principal() -> None:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_admin] = lambda: (_ for _ in ()).throw(
        HTTPException(status_code=401, detail="authentication_required")
    )

    response = TestClient(app).get(
        f"/api/v1/client-payments/historical-payments/{CASE_NO}"
    )

    assert response.status_code == 401


def test_client_finance_historical_stale_is_a_closed_typed_conflict() -> None:
    class StaleApplication(_Application):
        def apply(self, request):
            raise HistoricalClientPaymentError(
                TypedError(
                    ErrorCategory.CONFLICT,
                    "historical_client_payment_candidate_stale",
                    "Historical Client Finance payment could not be applied.",
                    CorrelationId("corr-client-api"),
                    current_version=ExpectedVersion(8),
                )
            )

    response = _client(StaleApplication()).post(
        "/api/v1/client-payments/historical-payments/apply",
        headers={"Idempotency-Key": "historical-client:api:1", "X-Correlation-ID": "corr-client-api"},
        json={
            "case_no": CASE_NO,
            "direction": "receivable_from_client",
            "confirmation_kind": "paid",
            "obligation_identities": ["client-obligation:api:1"],
            "payment_date": "2025-01-08",
            "payment_date_unknown_reason": None,
            "source_availability": "missing",
            "evidence_reference": "ledger-reference:12",
            "expected_account_version": 7,
            "expected_adoption_receipt_id": 41,
            "preview_fingerprint": FINGERPRINT.value,
            "reason": "Confirm adopted pre-system payment.",
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"]["error"]["code"] == "historical_client_payment_candidate_stale"
    assert response.json()["detail"]["error"]["current_version"] == 8
