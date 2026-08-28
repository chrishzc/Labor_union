"""File: test_order_cancellation_receipt_route.py
Description: 驗證訂單取消 receipt 唯讀查詢、認證、嚴格回應與不洩漏 404。
"""

from datetime import date

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.dependencies.admin_auth import require_system_admin
from api.dependencies.order_cancellation import (
    OrderCancellationApplication,
    get_order_cancellation_application,
)
from api.routes.order_cancellation import router
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.identities import IdempotencyKey
from domains.orders.lifecycle import OrderLifecycleStatus
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.orders.cancellation_workflow import (
    OrderCancellationReceipt,
    StoredCancellationReceipt,
)


class _Repository:
    def __init__(self):
        self.receipts = {
            "cancel-key-1": StoredCancellationReceipt(
                PreviewFingerprint("b" * 64),
                OrderCancellationReceipt(
                    "CASE-1",
                    5,
                    3,
                    2,
                    6,
                    4,
                    OrderLifecycleStatus.CANCELLED,
                    date(2026, 8, 2),
                    1,
                    8,
                    (11,),
                    ("CASE-1:g2:a1",),
                    PreviewFingerprint("a" * 64),
                ),
            )
        }
        self.calls = []

    def find_receipt(self, key: IdempotencyKey, *, for_update: bool):
        self.calls.append((key.value, for_update))
        return self.receipts.get(key.value)


def _client(repository: _Repository) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_system_admin] = lambda: AdminPrincipal(
        id=1,
        username="admin",
        display_name="Administrator",
        role="system_admin",
    )
    app.dependency_overrides[get_order_cancellation_application] = lambda: (
        OrderCancellationApplication(repository, object())
    )
    return TestClient(app)


def test_receipt_query_is_authenticated_read_only_and_strict():
    repository = _Repository()
    response = _client(repository).get(
        "/api/v1/orders/CASE-1/cancellation/receipt",
        headers={"Idempotency-Key": "cancel-key-1"},
    )

    assert response.status_code == 200
    assert response.json()["data"] == {
        "case_no": "CASE-1",
        "order_version": 5,
        "scheduling_version": 3,
        "scheduling_generation": 2,
        "client_finance_version": 6,
        "payroll_version": 4,
        "lifecycle_status": OrderLifecycleStatus.CANCELLED.value,
        "actual_end_date": "2026-08-02",
        "official_service_day_count": 1,
        "official_service_hours": 8,
        "cancelled_assignment_ids": [11],
        "created_assignment_keys": ["CASE-1:g2:a1"],
        "preview_fingerprint": "a" * 64,
    }
    assert repository.calls == [("cancel-key-1", False)]


def test_receipt_query_returns_same_not_found_for_unknown_and_cross_case():
    repository = _Repository()
    client = _client(repository)

    unknown = client.get(
        "/api/v1/orders/CASE-1/cancellation/receipt",
        headers={"Idempotency-Key": "unknown-key"},
    )
    cross_case = client.get(
        "/api/v1/orders/CASE-OTHER/cancellation/receipt",
        headers={"Idempotency-Key": "cancel-key-1"},
    )

    assert unknown.status_code == cross_case.status_code == 404
    assert unknown.json()["detail"]["error"]["code"] == (
        "order_cancellation_receipt_not_found"
    )
    assert cross_case.json()["detail"]["error"]["code"] == (
        "order_cancellation_receipt_not_found"
    )
    assert "CASE-1" not in cross_case.text


def test_receipt_query_requires_idempotency_key():
    response = _client(_Repository()).get(
        "/api/v1/orders/CASE-1/cancellation/receipt"
    )

    assert response.status_code == 422
