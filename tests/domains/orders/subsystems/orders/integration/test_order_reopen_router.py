"""
File: test_order_reopen_router.py
Description: 驗證訂單受控重開 HTTP Preview 與 Apply 端點行為、三版本校驗、理由驗證與型別化錯誤。
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
from pymysql.err import OperationalError

from api.exception_handlers import CorrelationBoundaryMiddleware, install_typed_error_handlers
from api.dependencies.admin_auth import require_system_admin
from api.dependencies.order_reopen import (
    OrderReopenApplication,
    get_order_reopen_application,
)
from api.routes.order_reopen import router
from domains.orders.lifecycle import OrderLifecycleStatus
from domains.orders.reopen import (
    ReopenFinancialEventFact,
    ReopenFinancialEventKind,
    ReopenOrderFacts,
)
from shared_kernel.clock import FixedBusinessClock
from shared_kernel.identities import (
    ActorContext,
    CorrelationId,
    ExpectedVersion,
    IdempotencyKey,
)
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.orders.reopen_workflow import (
    OrderReopenApplyRequest,
    OrderReopenPreview,
    OrderReopenReceipt,
    OrderReopenWorkflow,
    ReopenOrderPersistenceCommand,
    ReopenReceiptPersistenceCommand,
    ReopenWorkflowFacts,
    StoredReopenReceipt,
)
from subsystems.orders.terms_workflow import CommandClaimState


class InMemoryOrderReopenRepository:
    def __init__(self, facts: ReopenWorkflowFacts | None = None) -> None:
        self.facts = facts or _default_facts()
        self.receipts: dict[str, tuple[str, StoredReopenReceipt]] = {}
        self.saved_receipt_command: ReopenReceiptPersistenceCommand | None = None
        self.saved_order_command: ReopenOrderPersistenceCommand | None = None
        self.fail_with_mysql_code: int | None = None

    def load_for_preview(self, case_no: str) -> ReopenWorkflowFacts:
        if self.fail_with_mysql_code is not None:
            raise OperationalError(self.fail_with_mysql_code, "database error")
        if self.facts is None or self.facts.order.case_no != case_no:
            raise ValueError("order_not_found")
        return self.facts

    def load_for_apply(self, case_no: str) -> ReopenWorkflowFacts:
        if self.fail_with_mysql_code is not None:
            raise OperationalError(self.fail_with_mysql_code, "database error")
        if self.facts is None or self.facts.order.case_no != case_no:
            raise ValueError("order_not_found")
        return self.facts

    def claim_command(
        self, request: OrderReopenApplyRequest, command_fingerprint: Any
    ) -> CommandClaimState:
        if request.idempotency_key.value in self.receipts:
            saved_fp, _ = self.receipts[request.idempotency_key.value]
            if saved_fp == command_fingerprint.value:
                return CommandClaimState.MATCHED
            return CommandClaimState.MISMATCH
        return CommandClaimState.CREATED

    def find_receipt(
        self, key: IdempotencyKey, *, for_update: bool = False
    ) -> StoredReopenReceipt | None:
        if key.value in self.receipts:
            _, stored = self.receipts[key.value]
            return stored
        return None

    def append_reopen_event(
        self, request: OrderReopenApplyRequest, preview: OrderReopenPreview
    ) -> int:
        return 101

    def clear_cancellation_control(
        self, request: OrderReopenApplyRequest, reopen_event_id: int
    ) -> int:
        return 102

    def append_reopen_lifecycle(
        self,
        request: OrderReopenApplyRequest,
        preview: OrderReopenPreview,
        cancellation_control_event_id: int,
        business_date: date,
    ) -> int:
        return 103

    def update_reopened_order(
        self, command: ReopenOrderPersistenceCommand
    ) -> None:
        self.saved_order_command = command

    def save_receipt(self, command: ReopenReceiptPersistenceCommand) -> None:
        self.saved_receipt_command = command
        self.receipts[command.key.value] = (
            command.stored_receipt.command_fingerprint.value,
            command.stored_receipt,
        )


class _UnitOfWork:
    def __init__(self) -> None:
        self.committed = False
        self.rolled_back = False

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True


def _default_facts(
    status: OrderLifecycleStatus = OrderLifecycleStatus.CANCELLED,
    cancellation_effective: bool = True,
    financial_events: tuple[ReopenFinancialEventFact, ...] = (),
) -> ReopenWorkflowFacts:
    order = ReopenOrderFacts(
        case_no="CASE-RO-001",
        order_version=4,
        current_status=status,
        cancellation_event_id=7,
        cancellation_effective=cancellation_effective,
        contract_completed=True,
        deposit_settled=False,
        actual_start_date=None,
        service_started=False,
        actual_start_reconfirmed=False,
        service_data_locked=False,
    )
    return ReopenWorkflowFacts(order, financial_events, client_finance_version=2, payroll_version=3)


def _create_app(repo: InMemoryOrderReopenRepository, authenticate: bool = True):
    app = FastAPI()
    app.include_router(router)
    app.add_middleware(CorrelationBoundaryMiddleware)
    install_typed_error_handlers(app)

    if authenticate:
        app.dependency_overrides[require_system_admin] = lambda: AdminPrincipal(
            id=1, username="admin_tester", display_name="Admin Tester", role="system_admin"
        )
    workflow = OrderReopenWorkflow(
        repo,
        lambda: _UnitOfWork(),
        FixedBusinessClock(datetime(2026, 8, 16, 12, 0).astimezone()),
    )
    app.dependency_overrides[get_order_reopen_application] = lambda: OrderReopenApplication(workflow)
    return app


def test_preview_order_reopen_success():
    repo = InMemoryOrderReopenRepository()
    client = TestClient(_create_app(repo))

    response = client.post(
        "/api/v1/orders/CASE-RO-001/reopen/preview",
        headers={"X-Correlation-ID": "test-reopen-preview-corr"},
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["case_no"] == "CASE-RO-001"
    assert data["order_version"] == 4
    assert data["client_finance_version"] == 2
    assert data["payroll_version"] == 3
    assert data["cancellation_event_id"] == 7
    assert data["before_status"] == OrderLifecycleStatus.CANCELLED.value
    assert data["after_status"] == OrderLifecycleStatus.DISCUSSION.value
    assert data["requires_fresh_scheduling_preview"] is True
    assert data["restored_assignment_ids"] == []
    assert data["restored_schedule_ids"] == []
    assert data["restored_lock_ids"] == []
    assert len(data["preview_fingerprint"]) == 64


def test_preview_order_reopen_blocker_not_cancelled():
    repo = InMemoryOrderReopenRepository(
        facts=_default_facts(status=OrderLifecycleStatus.IN_SERVICE, cancellation_effective=False)
    )
    client = TestClient(_create_app(repo))

    response = client.post(
        "/api/v1/orders/CASE-RO-001/reopen/preview",
        headers={"X-Correlation-ID": "test-reopen-blocked"},
    )
    assert response.status_code == 409
    error = response.json()["detail"]["error"]
    assert error["category"] == "domain_blocked"
    assert error["code"] == "order_reopen_requires_cancelled_order"
    assert "order_reopen_requires_cancelled_order" in error["domain_blockers"]


def test_preview_order_reopen_blocker_financial_history():
    repo = InMemoryOrderReopenRepository(
        facts=_default_facts(
            financial_events=(
                ReopenFinancialEventFact("refund-001", ReopenFinancialEventKind.CLIENT_REFUND),
            )
        )
    )
    client = TestClient(_create_app(repo))

    response = client.post(
        "/api/v1/orders/CASE-RO-001/reopen/preview",
        headers={"X-Correlation-ID": "test-reopen-financial-blocked"},
    )
    assert response.status_code == 409
    error = response.json()["detail"]["error"]
    assert error["category"] == "domain_blocked"
    assert error["code"] == "order_reopen_financial_history_exists"


def test_preview_order_reopen_case_not_found():
    repo = InMemoryOrderReopenRepository()
    client = TestClient(_create_app(repo))

    response = client.post(
        "/api/v1/orders/NON-EXISTENT/reopen/preview",
        headers={"X-Correlation-ID": "test-reopen-not-found"},
    )
    assert response.status_code == 404
    error = response.json()["detail"]["error"]
    assert error["category"] == "not_found"
    assert error["code"] == "order_not_found"


def test_apply_order_reopen_success_and_strict_receipt_invariant():
    repo = InMemoryOrderReopenRepository()
    client = TestClient(_create_app(repo))

    # Obtain preview
    preview_res = client.post(
        "/api/v1/orders/CASE-RO-001/reopen/preview",
        headers={"X-Correlation-ID": "test-reopen-preview-corr"},
    )
    fingerprint = preview_res.json()["data"]["preview_fingerprint"]

    response = client.post(
        "/api/v1/orders/CASE-RO-001/reopen/apply",
        headers={
            "X-Correlation-ID": "test-reopen-apply-corr",
            "Idempotency-Key": "idemp-reopen-001",
        },
        json={
            "expected_order_version": 4,
            "expected_client_finance_version": 2,
            "expected_payroll_version": 3,
            "preview_fingerprint": fingerprint,
            "reason": "客戶恢復簽約服務",
        },
    )
    assert response.status_code == 200
    data = response.json()["data"]

    # Exact expected fields
    assert data["case_no"] == "CASE-RO-001"
    assert data["order_version"] == 5
    assert data["lifecycle_status"] == OrderLifecycleStatus.DISCUSSION.value
    assert data["cancellation_event_id"] == 7
    assert data["requires_fresh_scheduling_preview"] is True
    assert data["preview_fingerprint"] == fingerprint

    # STRICT RECEIPT INVARIANT: Forbidden fields MUST NOT be present
    assert "client_finance_version" not in data
    assert "payroll_version" not in data
    assert "created_at" not in data
    assert "idempotency_key" not in data
    assert set(data.keys()) == {
        "case_no",
        "order_version",
        "lifecycle_status",
        "cancellation_event_id",
        "requires_fresh_scheduling_preview",
        "preview_fingerprint",
    }


def test_apply_order_reopen_reason_validation():
    repo = InMemoryOrderReopenRepository()
    client = TestClient(_create_app(repo))

    preview_res = client.post("/api/v1/orders/CASE-RO-001/reopen/preview")
    fingerprint = preview_res.json()["data"]["preview_fingerprint"]

    headers = {
        "X-Correlation-ID": "test-reopen-reason-corr",
        "Idempotency-Key": "idemp-reopen-reason",
    }
    base_body = {
        "expected_order_version": 4,
        "expected_client_finance_version": 2,
        "expected_payroll_version": 3,
        "preview_fingerprint": fingerprint,
    }

    # Empty reason -> 422
    res_empty = client.post(
        "/api/v1/orders/CASE-RO-001/reopen/apply",
        headers=headers,
        json={**base_body, "reason": ""},
    )
    assert res_empty.status_code == 422

    # Whitespace only reason -> 422
    res_space = client.post(
        "/api/v1/orders/CASE-RO-001/reopen/apply",
        headers=headers,
        json={**base_body, "reason": "    \t \n "},
    )
    assert res_space.status_code == 422

    # Missing reason field -> 422
    res_missing = client.post(
        "/api/v1/orders/CASE-RO-001/reopen/apply",
        headers=headers,
        json=base_body,
    )
    assert res_missing.status_code == 422

    # 1-char reason (valid) -> 200
    res_1 = client.post(
        "/api/v1/orders/CASE-RO-001/reopen/apply",
        headers={"X-Correlation-ID": "c1", "Idempotency-Key": "k1"},
        json={**base_body, "reason": "r"},
    )
    assert res_1.status_code == 200

    # 500-char reason (valid) -> 200
    res_500 = client.post(
        "/api/v1/orders/CASE-RO-001/reopen/apply",
        headers={"X-Correlation-ID": "c2", "Idempotency-Key": "k2"},
        json={**base_body, "reason": "x" * 500},
    )
    assert res_500.status_code == 200

    # > 500-char reason (invalid) -> 422
    res_501 = client.post(
        "/api/v1/orders/CASE-RO-001/reopen/apply",
        headers={"X-Correlation-ID": "c3", "Idempotency-Key": "k3"},
        json={**base_body, "reason": "x" * 501},
    )
    assert res_501.status_code == 422

    # Traditional Chinese reason -> 200
    res_tc = client.post(
        "/api/v1/orders/CASE-RO-001/reopen/apply",
        headers={"X-Correlation-ID": "c4", "Idempotency-Key": "k4"},
        json={**base_body, "reason": "客戶重啟訂單"},
    )
    assert res_tc.status_code == 200


def test_apply_order_reopen_version_conflicts():
    repo = InMemoryOrderReopenRepository()
    client = TestClient(_create_app(repo))

    preview_res = client.post("/api/v1/orders/CASE-RO-001/reopen/preview")
    fingerprint = preview_res.json()["data"]["preview_fingerprint"]

    base_body = {
        "expected_order_version": 4,
        "expected_client_finance_version": 2,
        "expected_payroll_version": 3,
        "preview_fingerprint": fingerprint,
        "reason": "衝突測試",
    }

    # Order version mismatch -> 409 order_version_conflict
    res_order = client.post(
        "/api/v1/orders/CASE-RO-001/reopen/apply",
        headers={"X-Correlation-ID": "c-v1", "Idempotency-Key": "k-v1"},
        json={**base_body, "expected_order_version": 99},
    )
    assert res_order.status_code == 409
    assert res_order.json()["detail"]["error"]["code"] == "order_version_conflict"

    # Client finance version mismatch -> 409 client_finance_candidate_stale
    res_fin = client.post(
        "/api/v1/orders/CASE-RO-001/reopen/apply",
        headers={"X-Correlation-ID": "c-v2", "Idempotency-Key": "k-v2"},
        json={**base_body, "expected_client_finance_version": 99},
    )
    assert res_fin.status_code == 409
    assert res_fin.json()["detail"]["error"]["code"] == "client_finance_candidate_stale"

    # Payroll version mismatch -> 409 payroll_version_conflict
    res_pay = client.post(
        "/api/v1/orders/CASE-RO-001/reopen/apply",
        headers={"X-Correlation-ID": "c-v3", "Idempotency-Key": "k-v3"},
        json={**base_body, "expected_payroll_version": 99},
    )
    assert res_pay.status_code == 409
    assert res_pay.json()["detail"]["error"]["code"] == "payroll_version_conflict"


def test_apply_order_reopen_same_key_replay_and_mismatch():
    repo = InMemoryOrderReopenRepository()
    client = TestClient(_create_app(repo))

    preview_res = client.post("/api/v1/orders/CASE-RO-001/reopen/preview")
    fingerprint = preview_res.json()["data"]["preview_fingerprint"]

    headers = {
        "X-Correlation-ID": "test-replay-corr",
        "Idempotency-Key": "same-key-ro-001",
    }
    body = {
        "expected_order_version": 4,
        "expected_client_finance_version": 2,
        "expected_payroll_version": 3,
        "preview_fingerprint": fingerprint,
        "reason": "初次重開申請",
    }

    # First apply
    res1 = client.post("/api/v1/orders/CASE-RO-001/reopen/apply", headers=headers, json=body)
    assert res1.status_code == 200
    receipt1 = res1.json()["data"]

    # Same-key same-payload replay -> 200 same receipt
    res2 = client.post("/api/v1/orders/CASE-RO-001/reopen/apply", headers=headers, json=body)
    assert res2.status_code == 200
    receipt2 = res2.json()["data"]
    assert receipt1 == receipt2

    # Same-key changed-payload -> 409 idempotency_mismatch
    changed_body = {**body, "reason": "修改後的不同理由"}
    res3 = client.post("/api/v1/orders/CASE-RO-001/reopen/apply", headers=headers, json=changed_body)
    assert res3.status_code == 409
    error = res3.json()["detail"]["error"]
    assert error["category"] == "idempotency_mismatch"
    assert error["code"] == "idempotency_mismatch"


def test_apply_order_reopen_missing_headers():
    repo = InMemoryOrderReopenRepository()
    client = TestClient(_create_app(repo))

    preview_res = client.post("/api/v1/orders/CASE-RO-001/reopen/preview")
    fingerprint = preview_res.json()["data"]["preview_fingerprint"]

    body = {
        "expected_order_version": 4,
        "expected_client_finance_version": 2,
        "expected_payroll_version": 3,
        "preview_fingerprint": fingerprint,
        "reason": "正常理由",
    }

    # Missing Idempotency-Key
    res_no_key = client.post(
        "/api/v1/orders/CASE-RO-001/reopen/apply",
        headers={"X-Correlation-ID": "corr-1"},
        json=body,
    )
    assert res_no_key.status_code == 422

    # Missing X-Correlation-ID is generated and injected by the global boundary.
    res_no_corr = client.post(
        "/api/v1/orders/CASE-RO-001/reopen/apply",
        headers={"Idempotency-Key": "key-1"},
        json=body,
    )
    assert res_no_corr.status_code == 200
    assert res_no_corr.headers.get("X-Correlation-ID")


def test_order_reopen_mysql_retryable_error():
    repo = InMemoryOrderReopenRepository()
    repo.fail_with_mysql_code = 1205
    client = TestClient(_create_app(repo))

    res = client.post(
        "/api/v1/orders/CASE-RO-001/reopen/preview",
        headers={"X-Correlation-ID": "corr-retryable"},
    )
    assert res.status_code == 503
    assert res.headers.get("Retry-After") == "1"
    error = res.json()["detail"]["error"]
    assert error["category"] == "unavailable"
    assert error["retryable"] is True


def test_order_reopen_requires_admin_auth():
    repo = InMemoryOrderReopenRepository()
    app = _create_app(repo, authenticate=False)
    client = TestClient(app)

    res = client.post("/api/v1/orders/CASE-RO-001/reopen/preview")
    assert res.status_code in {401, 403}
