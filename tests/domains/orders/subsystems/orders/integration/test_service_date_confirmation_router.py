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
    get_historical_restart_arrangement_workflow,
    get_service_date_confirmation_workflow,
)
from api.routes.service_date_confirmation import router
from domains.orders.service_date_confirmation import ConfirmedServiceDateCandidate
from shared_kernel.fingerprints import PreviewFingerprint
from subsystems.orders.historical_restart_arrangement import (
    HistoricalRestartArrangementPreview,
    HistoricalRestartArrangementReceipt,
    _arrangement_candidate,
)
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.orders.service_date_confirmation_workflow import (
    RestartSchedulingAssignmentFacts,
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
        self.receipts: dict[str, tuple[str, str, str, ServiceDateConfirmationReceipt]] = {}
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

    def replay(
        self,
        idempotency_key: str,
        command_fingerprint: str,
        *,
        actor: str,
        reason: str,
        for_update: bool = False,
    ) -> ServiceDateConfirmationReceipt | None:
        if idempotency_key in self.receipts:
            saved_fp, saved_actor, saved_reason, receipt = self.receipts[idempotency_key]
            if (saved_fp, saved_actor, saved_reason) != (command_fingerprint, actor, reason):
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
        self.receipts[idempotency_key] = (command_fingerprint, actor, reason, receipt)
        self.next_version += 1
        return receipt


class InMemorySchedulingSnapshotInvalidationPort:
    def __init__(self) -> None:
        self.invalidated_case_nos: list[str] = []

    def invalidate_current_snapshot(self, case_no: str) -> None:
        self.invalidated_case_nos.append(case_no)



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


def _create_app(
    repo: InMemoryServiceDateConfirmationRepository,
    snapshot_invalidation: InMemorySchedulingSnapshotInvalidationPort,
    authenticate: bool = True,
    principal: AdminPrincipal | None = None,
):
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
        app.dependency_overrides[require_system_admin] = lambda: principal or AdminPrincipal(
            id=1, username="admin_tester", display_name="Admin Tester", role="system_admin"
        )
    app.dependency_overrides[get_service_date_confirmation_workflow] = (
        lambda: ServiceDateConfirmationWorkflow(
            repo,
            lambda: _UnitOfWork(repo),
            snapshot_invalidation,
        )
    )
    return app


def test_query_service_dates_success():
    repo = InMemoryServiceDateConfirmationRepository()
    client = TestClient(_create_app(repo, InMemorySchedulingSnapshotInvalidationPort()))

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
    assert data["bound_staff"] == []
    assert data["arrangement_pending"] is False


def test_query_service_dates_preserves_historical_bound_staff():
    facts = ServiceDateConfirmationFacts(
        case_no="HIST-SD-001",
        order_version=2,
        scheduling_version=3,
        contracted_service_days=3,
        suggested_dates=(),
        selectable_dates=(date(2026, 8, 1), date(2026, 8, 2), date(2026, 8, 3)),
        current_version=None,
        current_dates=(),
        restart_generation_number=4,
        restart_assignments=(RestartSchedulingAssignmentFacts(91, 12, 1, 3, "王月嫂"),),
    )
    client = TestClient(_create_app(
        InMemoryServiceDateConfirmationRepository(facts),
        InMemorySchedulingSnapshotInvalidationPort(),
    ))

    response = client.get("/api/v1/orders/HIST-SD-001/service-dates")

    assert response.status_code == 200
    assert response.json()["data"]["bound_staff"] == [
        {"staff_id": 12, "staff_name": "王月嫂"}
    ]
    assert response.json()["data"]["arrangement_pending"] is False


def test_historical_arrangement_http_is_separate_from_date_confirmation():
    facts = ServiceDateConfirmationFacts(
        case_no="HIST-SD-ARRANGE", order_version=2, scheduling_version=3,
        contracted_service_days=2,
        suggested_dates=(),
        selectable_dates=(date(2026, 8, 1), date(2026, 8, 2), date(2026, 8, 3)),
        current_version=1,
        current_dates=(date(2026, 8, 2), date(2026, 8, 3)),
        restart_generation_number=4,
        restart_assignments=(RestartSchedulingAssignmentFacts(None, 12, 1, 0, "王月嫂"),),
        service_hours_per_day=8,
    )
    app = _create_app(
        InMemoryServiceDateConfirmationRepository(facts),
        InMemorySchedulingSnapshotInvalidationPort(),
    )
    calls = []

    class Arrangement:
        def preview(self, case_no, segments):
            calls.append(("preview", case_no, segments))
            return HistoricalRestartArrangementPreview(
                _arrangement_candidate(facts, segments), 2, 1,
                PreviewFingerprint("a" * 64),
            )

        def apply(self, case_no, segments, **kwargs):
            calls.append(("apply", case_no, segments, kwargs))
            return HistoricalRestartArrangementReceipt(
                case_no, 4, 5, (101,), PreviewFingerprint("a" * 64),
            )

    app.dependency_overrides[get_historical_restart_arrangement_workflow] = Arrangement
    client = TestClient(app)
    query = client.get("/api/v1/orders/HIST-SD-ARRANGE/service-dates")
    assert query.json()["data"]["arrangement_pending"] is True
    body = {"segments": [{
        "staff_id": 12,
        "service_dates": ["2026-08-02", "2026-08-03"],
    }]}
    preview = client.post(
        "/api/v1/orders/HIST-SD-ARRANGE/service-dates/arrangement/preview",
        json=body,
    )
    assert preview.status_code == 200
    assert preview.json()["data"]["segments"][0]["assigned_start_date"] == "2026-08-01"
    applied = client.post(
        "/api/v1/orders/HIST-SD-ARRANGE/service-dates/arrangement/apply",
        headers={"Idempotency-Key": "arrange-1", "X-Correlation-ID": "arrange-correlation"},
        json={**body, "expected_order_version": 2, "expected_scheduling_version": 3,
              "expected_confirmed_version": 1, "preview_fingerprint": "a" * 64,
              "reason": "核對既定月嫂"},
    )
    assert applied.status_code == 200
    assert applied.json()["data"]["assignment_ids"] == [101]
    assert calls[1][3]["expected_confirmed_version"] == 1


def test_query_service_dates_case_not_found():
    repo = InMemoryServiceDateConfirmationRepository()
    client = TestClient(_create_app(repo, InMemorySchedulingSnapshotInvalidationPort()))

    response = client.get("/api/v1/orders/NON-EXISTENT/service-dates")
    assert response.status_code == 404
    error = response.json()["detail"]["error"]
    assert error["category"] == "not_found"
    assert error["code"] == "service_date_confirmation_case_not_found"
    assert "CASE-SD-001" not in error["code"]


def test_preview_service_dates_success():
    repo = InMemoryServiceDateConfirmationRepository()
    client = TestClient(_create_app(repo, InMemorySchedulingSnapshotInvalidationPort()))

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
    client = TestClient(_create_app(repo, InMemorySchedulingSnapshotInvalidationPort()))

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
    snapshot_invalidation = InMemorySchedulingSnapshotInvalidationPort()
    client = TestClient(_create_app(repo, snapshot_invalidation))

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
    assert snapshot_invalidation.invalidated_case_nos == ["CASE-SD-001"]


def test_apply_service_dates_reason_validation():
    repo = InMemoryServiceDateConfirmationRepository()
    client = TestClient(_create_app(repo, InMemorySchedulingSnapshotInvalidationPort()))

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
    client = TestClient(_create_app(repo, InMemorySchedulingSnapshotInvalidationPort()))

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


@pytest.mark.parametrize(
    "stale_field",
    ("expected_order_version", "expected_scheduling_version"),
)
def test_apply_service_dates_stale_versions(stale_field):
    repo = InMemoryServiceDateConfirmationRepository()
    client = TestClient(_create_app(repo, InMemorySchedulingSnapshotInvalidationPort()))

    preview_res = client.post(
        "/api/v1/orders/CASE-SD-001/service-dates/preview",
        json={"service_dates": ["2026-08-03", "2026-08-04", "2026-08-05"]},
    )
    fingerprint = preview_res.json()["data"]["preview_fingerprint"]

    # Each owning version must independently reject stale commands.
    res_stale = client.post(
        "/api/v1/orders/CASE-SD-001/service-dates/apply",
        headers={"Idempotency-Key": "key-stale-1", "X-Correlation-ID": "corr-stale"},
        json={
            "service_dates": ["2026-08-03", "2026-08-04", "2026-08-05"],
            "expected_order_version": 2,
            "expected_scheduling_version": 3,
            stale_field: 99,
            "preview_fingerprint": fingerprint,
            "reason": "版本過期測試",
        },
    )
    assert res_stale.status_code == 409
    error = res_stale.json()["detail"]["error"]
    assert error["category"] == "conflict"
    assert error["code"] == "service_date_confirmation_stale_version"
    assert repo.receipts == {}
    assert repo.committed is False


def test_service_dates_mysql_retryable_error():
    repo = InMemoryServiceDateConfirmationRepository()
    repo.fail_with_mysql_code = 1205  # Lock wait timeout
    client = TestClient(_create_app(repo, InMemorySchedulingSnapshotInvalidationPort()))

    res = client.get("/api/v1/orders/CASE-SD-001/service-dates")
    assert res.status_code == 503
    assert res.headers.get("Retry-After") == "1"
    error = res.json()["detail"]["error"]
    assert error["category"] == "unavailable"
    assert error["retryable"] is True


def test_historical_arrangement_missing_policy_reports_the_arrangement_blocker():
    class MissingPolicyWorkflow:
        def preview(self, _case_no, _segments):
            raise ValueError("historical_arrangement_case_policy_missing_blocked")

    app = _create_app(
        InMemoryServiceDateConfirmationRepository(),
        InMemorySchedulingSnapshotInvalidationPort(),
    )
    app.dependency_overrides[get_historical_restart_arrangement_workflow] = (
        lambda: MissingPolicyWorkflow()
    )
    response = TestClient(app).post(
        "/api/v1/orders/HIST-001/service-dates/arrangement/preview",
        json={"segments": [{"staff_id": 1, "service_dates": ["2026-09-03"]}]},
    )

    assert response.status_code == 409
    error = response.json()["detail"]["error"]
    assert error["category"] == "domain_blocked"
    assert error["code"] == "historical_arrangement_case_policy_missing_blocked"
    assert error["message"] == (
        "本案缺少已核定的月嫂費率政策，無法建立正式安排；已確認的服務日期不受影響。"
    )


def test_service_dates_requires_auth():
    repo = InMemoryServiceDateConfirmationRepository()
    app = _create_app(
        repo,
        InMemorySchedulingSnapshotInvalidationPort(),
        authenticate=False,
    )
    client = TestClient(app)

    res = client.get("/api/v1/orders/CASE-SD-001/service-dates")
    assert res.status_code in {401, 403}
