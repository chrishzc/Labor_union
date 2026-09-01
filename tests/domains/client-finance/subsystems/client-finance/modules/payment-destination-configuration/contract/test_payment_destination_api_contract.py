from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.dependencies.admin_auth import require_admin
from api.dependencies.client_payment_destination import get_client_payment_destination_application
from api.routes.client_payment_destination import router
from domains.client_finance.payment_destination import ClientPaymentDestination
from shared_kernel.fingerprints import PreviewFingerprint
from subsystems.access.authentication_session import AdminPrincipal


class _Application:
    current = ClientPaymentDestination("822-123456789", 3)
    def query(self): return self.current
    def preview(self, account_display, expected_revision):
        return SimpleNamespace(current=self.current, candidate_account_display=account_display, expected_revision=expected_revision, preview_fingerprint=PreviewFingerprint("a" * 64))
    def apply(self, request):
        return SimpleNamespace(account_display=request.account_display, resulting_revision=4, preview_fingerprint=request.preview_fingerprint)


def _client():
    app = FastAPI(); app.include_router(router)
    app.dependency_overrides[require_admin] = lambda: AdminPrincipal(1, "admin", "Admin", "admin")
    app.dependency_overrides[get_client_payment_destination_application] = _Application
    return TestClient(app)


def test_payment_destination_public_contract_is_query_preview_apply():
    client = _client()
    queried = client.get("/api/v1/client-finance/payment-destination")
    assert queried.status_code == 200
    assert queried.json()["data"] == {"configured": True, "account_display": "822-123456789", "revision": 3}

    previewed = client.post("/api/v1/client-finance/payment-destination/preview", json={"account_display": "822-987654321", "expected_revision": 3})
    assert previewed.status_code == 200
    preview = previewed.json()["data"]
    assert preview["candidate_account_display"] == "822-987654321"

    applied = client.post(
        "/api/v1/client-finance/payment-destination/apply",
        headers={"Idempotency-Key": "destination-1", "X-Correlation-ID": "correlation-1"},
        json={"account_display": "822-987654321", "expected_revision": 3, "preview_fingerprint": preview["preview_fingerprint"], "reason": "更新工會帳戶"},
    )
    assert applied.status_code == 200
    assert applied.json()["data"]["resulting_revision"] == 4
