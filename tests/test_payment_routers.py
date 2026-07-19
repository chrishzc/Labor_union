from api.main import app
from fastapi.testclient import TestClient


client = TestClient(app)


def test_payment_routers_in_openapi():
    openapi = app.openapi()
    assert "/api/v1/client-payments" in openapi["paths"]
    assert "/api/v1/client-payments/{case_no}" in openapi["paths"]
    assert "/api/v1/client-payments/transaction" in openapi["paths"]
    
    assert "/api/v1/staff-payments" in openapi["paths"]
    assert "/api/v1/staff-payments/{case_no}" in openapi["paths"]
    assert "/api/v1/staff-payments/transaction" in openapi["paths"]


def test_client_transaction_requires_non_blank_reason_before_database_access():
    payload = {
        "case_no": "115000001",
        "stage": "deposit",
        "transaction_type": "receipt",
        "amount": 1000,
        "occurred_at": "2026-07-15",
        "external_reference": "MANUAL-001",
    }

    missing_reason = client.post("/api/v1/client-payments/transaction", json=payload)
    assert missing_reason.status_code == 422

    blank_reason = client.post(
        "/api/v1/client-payments/transaction",
        json={**payload, "notes": "   "},
    )
    assert blank_reason.status_code == 422


def test_client_transaction_schema_excludes_cancellation_refund_stage():
    schema = app.openapi()["components"]["schemas"]["ClientTransactionCreate"]
    stage_schema = schema["properties"]["stage"]
    assert stage_schema["enum"] == ["deposit", "first_payment", "second_payment"]


def test_staff_transaction_requires_non_blank_reason_before_database_access():
    payload = {
        "staff_payment_id": 1,
        "amount": 1000,
        "occurred_at": "2026-07-15",
        "external_reference": "MANUAL-STAFF-001",
    }

    missing_reason = client.post("/api/v1/staff-payments/transaction", json=payload)
    assert missing_reason.status_code == 422

    blank_reason = client.post(
        "/api/v1/staff-payments/transaction",
        json={**payload, "notes": "   "},
    )
    assert blank_reason.status_code == 422
