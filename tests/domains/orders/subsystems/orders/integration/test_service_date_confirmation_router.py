"""
File: test_service_date_confirmation_router.py
Description: 驗證服務日期確認 HTTP Query、Preview 與 Apply 端點行為、理由驗證與型別化錯誤。
"""

from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
from pymysql.err import OperationalError

from api.dependencies.admin_auth import require_system_admin
from api.dependencies.service_date_confirmation import (
    get_service_date_confirmation_workflow,
)
from api.routes.service_date_confirmation import router
from domains.orders.service_date_confirmation import ConfirmedServiceDateCandidate
from shared_kernel.fingerprints import PreviewFingerprint
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.orders.service_date_confirmation_workflow import (
    ServiceDateConfirmationFacts,
    ServiceDateConfirmationReceipt,
    ServiceDateConfirmationWorkflow,
)


class InMemoryServiceDateConfirmationRepository:
    def __init__(self, facts: ServiceDateConfirmationFacts | None = None) -> None:
        self.facts = facts or ServiceDateConfirmationFacts(
            case_no="CASE-SD-001",
            order_version=2,
            scheduling_version=3,
            contracted_service_days=3,
            suggested_dates=(date(2026, 8, 3), date(2026, 8, 4), date(2026, 8, 5)),
            selectable_dates=tuple(
                date(2026, 8, d) for d in range(1, 20)
            ),
            current_version=1,
            current_dates=(date(2026, 8, 1), date(2026, 8, 2), date(2026, 8, 3)),
        )
        self.receipts: dict[str, tuple[str, ServiceDateConfirmationReceipt]] = {}
        self.next_version = 2
        self.committed = False
        self.rolled_back = False
        self.fail_with_mysql_code: int | None = None

    def load(self, case_no: str, *, lock: bool = False) -> ServiceDateConfirmationFacts:
        if self.fail_with_mysql_code is not None:
            raise OperationalError(self.fail_with_mysql_code, "database error")
        if self.facts is None or self.facts.case_no != case_no:
            raise ValueError("service_date_confirmation_case_not_found")
        return self.facts

    def replay(self, idempotency_key: str, command_fingerprint: str) -> ServiceDateConfirmationReceipt | None:
        if idempotency_key in self.receipts:
            saved_fp, receipt = self.receipts[idempotency_key]
            if saved_fp != command_fingerprint:
                raise ValueError("service_date_confirmation_idempotency_conflict")
            return receipt
        return None

    def save(
        self,
        candidate: ConfirmedServiceDateCandidate,
        *,
        actor: str,
        reason: str,
        idempotency_key: str,
        command_fingerprint: str,
    ) -> ServiceDateConfirmationReceipt:
        if self.fail_with_mysql_code is not None:
            raise OperationalError(self.fail_with_mysql_code, "database error")
        receipt = ServiceDateConfirmationReceipt(
            case_no=candidate.case_no,
            confirmed_version=self.next_version,
            order_version=candidate.order_version,
            scheduling_version=candidate.scheduling_version,
            service_dates=candidate.service_dates,
            fingerprint=candidate.fingerprint,
        )
        self.receipts[idempotency_key] = (command_fingerprint, receipt)
        self.next_version += 1
        return receipt



class _UnitOfWork:
    def __init__(self, repository: InMemoryServiceDateConfirmationRepository) -> None:
        self._repository = repository
        self._committed = False

    def __enter__(self):
        return self

    def __exit__(self, exception_type, exception, traceback):
        if exception_type is not None or not self._committed:
            self._repository.rolled_back = True
        return False

    def commit(self) -> None:
        self._repository.committed = True
        self._committed = True


from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


def _create_app(repo: InMemoryServiceDateConfirmationRepository, authenticate: bool = True):
    app = FastAPI()
    app.include_router(router)

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request, exc: RequestValidationError):
        errors = []
        for err in exc.errors():
            clean_err = dict(err)
            if clean_err.get("input") is Ellipsis:
                clean_err["input"] = None
            if "ctx" in clean_err and isinstance(clean_err["ctx"], dict):
                clean_err["ctx"] = {
                    k: str(v) if isinstance(v, Exception) else v
                    for k, v in clean_err["ctx"].items()
                }
            errors.append(clean_err)
        return JSONResponse(status_code=422, content={"detail": errors})

    if authenticate:
        app.dependency_overrides[require_system_admin] = lambda: AdminPrincipal(
            id=1, username="admin_tester", display_name="Admin Tester", role="system_admin"
        )
    app.dependency_overrides[get_service_date_confirmation_workflow] = (
        lambda: ServiceDateConfirmationWorkflow(repo, lambda: _UnitOfWork(repo))
    )
    return app


def test_query_service_dates_success():
    repo = InMemoryServiceDateConfirmationRepository()
    client = TestClient(_create_app(repo))

    response = client.get("/api/v1/orders/CASE-SD-001/service-dates")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["case_no"] == "CASE-SD-001"
    assert data["order_version"] == 2
    assert data["scheduling_version"] == 3
    assert data["contracted_service_days"] == 3
    assert data["suggested_dates"] == ["2026-08-03", "2026-08-04", "2026-08-05"]
    assert len(data["selectable_dates"]) == 19
    assert data["current_version"] == 1
    assert data["current_dates"] == ["2026-08-01", "2026-08-02", "2026-08-03"]


def test_query_service_dates_case_not_found():
    repo = InMemoryServiceDateConfirmationRepository()
    client = TestClient(_create_app(repo))

    response = client.get("/api/v1/orders/NON-EXISTENT/service-dates")
    assert response.status_code == 404
    error = response.json()["detail"]["error"]
    assert error["category"] == "not_found"
    assert error["code"] == "service_date_confirmation_case_not_found"
    assert "CASE-SD-001" not in error["code"]


def test_preview_service_dates_success():
    repo = InMemoryServiceDateConfirmationRepository()
    client = TestClient(_create_app(repo))

    response = client.post(
        "/api/v1/orders/CASE-SD-001/service-dates/preview",
        headers={"X-Correlation-ID": "test-corr-sd-preview"},
        json={"service_dates": ["2026-08-03", "2026-08-04", "2026-08-05"]},
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["case_no"] == "CASE-SD-001"
    assert data["order_version"] == 2
    assert data["scheduling_version"] == 3
    assert data["current_version"] == 1
    assert data["service_dates"] == ["2026-08-03", "2026-08-04", "2026-08-05"]
    assert len(data["weeks"]) >= 1
    assert len(data["preview_fingerprint"]) == 64
    assert repo.committed is False


def test_preview_service_dates_validation_errors():
    repo = InMemoryServiceDateConfirmationRepository()
    client = TestClient(_create_app(repo))

    # Empty service dates (Pydantic min_length=1)
    res_empty = client.post(
        "/api/v1/orders/CASE-SD-001/service-dates/preview",
        json={"service_dates": []},
    )
    assert res_empty.status_code == 422

    # Date count mismatch (2 instead of contracted 3)
    res_count = client.post(
        "/api/v1/orders/CASE-SD-001/service-dates/preview",
        json={"service_dates": ["2026-08-03", "2026-08-04"]},
    )
    assert res_count.status_code == 422
    assert res_count.json()["detail"]["error"]["category"] == "validation"

    # Date outside selectable range
    res_outside = client.post(
        "/api/v1/orders/CASE-SD-001/service-dates/preview",
        json={"service_dates": ["2026-08-03", "2026-08-04", "2026-08-30"]},
    )
    assert res_outside.status_code == 422
    assert res_outside.json()["detail"]["error"]["code"] == "service_date_confirmation_date_outside_selectable_range"


def test_apply_service_dates_success():
    repo = InMemoryServiceDateConfirmationRepository()
    client = TestClient(_create_app(repo))

    # Obtain preview first to get valid fingerprint
    preview_res = client.post(
        "/api/v1/orders/CASE-SD-001/service-dates/preview",
        json={"service_dates": ["2026-08-03", "2026-08-04", "2026-08-05"]},
    )
    fingerprint = preview_res.json()["data"]["preview_fingerprint"]

    response = client.post(
        "/api/v1/orders/CASE-SD-001/service-dates/apply",
        headers={
            "X-Correlation-ID": "test-corr-sd-apply",
            "Idempotency-Key": "idemp-sd-001",
        },
        json={
            "service_dates": ["2026-08-03", "2026-08-04", "2026-08-05"],
            "expected_order_version": 2,
            "expected_scheduling_version": 3,
            "preview_fingerprint": fingerprint,
            "reason": "客戶確認服務日期",
        },
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["case_no"] == "CASE-SD-001"
    assert data["confirmed_version"] == 2
    assert data["order_version"] == 2
    assert data["scheduling_version"] == 3
    assert data["service_dates"] == ["2026-08-03", "2026-08-04", "2026-08-05"]
    assert data["preview_fingerprint"] == fingerprint
    assert repo.committed is True


def test_apply_service_dates_reason_validation():
    repo = InMemoryServiceDateConfirmationRepository()
    client = TestClient(_create_app(repo))

    preview_res = client.post(
        "/api/v1/orders/CASE-SD-001/service-dates/preview",
        json={"service_dates": ["2026-08-03", "2026-08-04", "2026-08-05"]},
    )
    fingerprint = preview_res.json()["data"]["preview_fingerprint"]

    headers = {
        "X-Correlation-ID": "test-corr-sd-reason",
        "Idempotency-Key": "idemp-sd-reason",
    }
    base_body = {
        "service_dates": ["2026-08-03", "2026-08-04", "2026-08-05"],
        "expected_order_version": 2,
        "expected_scheduling_version": 3,
        "preview_fingerprint": fingerprint,
    }

    # Empty reason
    res_empty = client.post(
        "/api/v1/orders/CASE-SD-001/service-dates/apply",
        headers=headers,
        json={**base_body, "reason": ""},
    )
    assert res_empty.status_code == 422

    # Whitespace only reason
    res_space = client.post(
        "/api/v1/orders/CASE-SD-001/service-dates/apply",
        headers=headers,
        json={**base_body, "reason": "     "},
    )
    assert res_space.status_code == 422

    # Missing reason field
    res_missing = client.post(
        "/api/v1/orders/CASE-SD-001/service-dates/apply",
        headers=headers,
        json=base_body,
    )
    assert res_missing.status_code == 422

    # Single character reason (valid)
    res_single = client.post(
        "/api/v1/orders/CASE-SD-001/service-dates/apply",
        headers={"X-Correlation-ID": "c1", "Idempotency-Key": "k1"},
        json={**base_body, "reason": "a"},
    )
    assert res_single.status_code == 200

    # 500-character reason (valid)
    res_500 = client.post(
        "/api/v1/orders/CASE-SD-001/service-dates/apply",
        headers={"X-Correlation-ID": "c2", "Idempotency-Key": "k2"},
        json={**base_body, "reason": "r" * 500},
    )
    assert res_500.status_code == 200

    # >500-character reason (invalid)
    res_501 = client.post(
        "/api/v1/orders/CASE-SD-001/service-dates/apply",
        headers={"X-Correlation-ID": "c3", "Idempotency-Key": "k3"},
        json={**base_body, "reason": "r" * 501},
    )
    assert res_501.status_code == 422


def test_apply_service_dates_idempotency_and_conflict():
    repo = InMemoryServiceDateConfirmationRepository()
    client = TestClient(_create_app(repo))

    preview_res = client.post(
        "/api/v1/orders/CASE-SD-001/service-dates/preview",
        json={"service_dates": ["2026-08-03", "2026-08-04", "2026-08-05"]},
    )
    fingerprint = preview_res.json()["data"]["preview_fingerprint"]

    headers = {
        "X-Correlation-ID": "test-corr-sd-idemp",
        "Idempotency-Key": "same-key-001",
    }
    body = {
        "service_dates": ["2026-08-03", "2026-08-04", "2026-08-05"],
        "expected_order_version": 2,
        "expected_scheduling_version": 3,
        "preview_fingerprint": fingerprint,
        "reason": "第一次套用",
    }

    # Initial apply
    res1 = client.post("/api/v1/orders/CASE-SD-001/service-dates/apply", headers=headers, json=body)
    assert res1.status_code == 200
    receipt1 = res1.json()["data"]

    # Same-key same-payload replay -> same receipt
    res2 = client.post("/api/v1/orders/CASE-SD-001/service-dates/apply", headers=headers, json=body)
    assert res2.status_code == 200
    receipt2 = res2.json()["data"]
    assert receipt1 == receipt2

    # Same-key changed-payload -> 409 idempotency conflict
    changed_body = {
        **body,
        "service_dates": ["2026-08-04", "2026-08-05", "2026-08-06"],
    }
    res3 = client.post("/api/v1/orders/CASE-SD-001/service-dates/apply", headers=headers, json=changed_body)
    assert res3.status_code == 409
    error = res3.json()["detail"]["error"]
    assert error["category"] == "idempotency_mismatch"
    assert error["code"] == "service_date_confirmation_idempotency_conflict"


def test_apply_service_dates_stale_versions():
    repo = InMemoryServiceDateConfirmationRepository()
    client = TestClient(_create_app(repo))

    preview_res = client.post(
        "/api/v1/orders/CASE-SD-001/service-dates/preview",
        json={"service_dates": ["2026-08-03", "2026-08-04", "2026-08-05"]},
    )
    fingerprint = preview_res.json()["data"]["preview_fingerprint"]

    # Stale order version
    res_stale = client.post(
        "/api/v1/orders/CASE-SD-001/service-dates/apply",
        headers={"Idempotency-Key": "key-stale-1", "X-Correlation-ID": "corr-stale"},
        json={
            "service_dates": ["2026-08-03", "2026-08-04", "2026-08-05"],
            "expected_order_version": 99,
            "expected_scheduling_version": 3,
            "preview_fingerprint": fingerprint,
            "reason": "版本過期測試",
        },
    )
    assert res_stale.status_code == 409
    error = res_stale.json()["detail"]["error"]
    assert error["category"] == "conflict"
    assert error["code"] == "service_date_confirmation_stale_version"


def test_service_dates_mysql_retryable_error():
    repo = InMemoryServiceDateConfirmationRepository()
    repo.fail_with_mysql_code = 1205  # Lock wait timeout
    client = TestClient(_create_app(repo))

    res = client.get("/api/v1/orders/CASE-SD-001/service-dates")
    assert res.status_code == 503
    assert res.headers.get("Retry-After") == "1"
    error = res.json()["detail"]["error"]
    assert error["category"] == "unavailable"
    assert error["retryable"] is True


def test_service_dates_requires_auth():
    repo = InMemoryServiceDateConfirmationRepository()
    app = _create_app(repo, authenticate=False)
    client = TestClient(app)

    res = client.get("/api/v1/orders/CASE-SD-001/service-dates")
    assert res.status_code in {401, 403}
