"""
File: test_anomaly_registry_router.py
Description: 驗證異常清單 HTTP 查詢、封閉摘要投影、認證邊界與零寫入契約。
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
import pytest
from pymysql.err import OperationalError

from api.dependencies.admin_auth import require_system_admin
from api.dependencies.anomaly_registry import get_anomaly_application
from api.routes.anomaly_registry import _summary_payload, router
from api.schemas.anomaly_registry import (
    AnomalySummaryView,
    AnomalyWorkflowReceiptView,
    StaffCalendarNavigationView,
)
from api.schemas.base import BaseResponse
from domains.anomalies.registry import (
    AlertWorkflowStatus,
    AnomalySeverity,
    default_anomaly_registry,
)
from infrastructure.mysql.anomaly_registry_repository import AnomalyRepositoryUnavailable
from shared_kernel.fingerprints import PreviewFingerprint
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.anomalies.alert_workflow import (
    AnomalyApplication,
    AnomalyDetail,
    AnomalySummary,
)


@dataclass(frozen=True, slots=True)
class _FakeProjection:
    fingerprint: PreviewFingerprint
    definition_code: str
    source_identity: str
    source_version: int
    predicate_active: bool
    workflow_status: AlertWorkflowStatus
    workflow_version: int


class _FakeAnomalyApplication:
    def __init__(self, summaries: list[AnomalySummary] | None = None) -> None:
        self.summaries = summaries if summaries is not None else _default_summaries()
        self.last_query_params: dict[str, Any] | None = None
        self.mutation_invoked = False
        self.fail_with_error: Exception | None = None

    def query_summaries(
        self,
        *,
        active_only: bool = True,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[AnomalySummary, ...]:
        if self.fail_with_error is not None:
            raise self.fail_with_error
        self.last_query_params = {
            "active_only": active_only,
            "limit": limit,
            "offset": offset,
        }
        summaries = [
            summary
            if summary.display_fields
            else replace(
                summary,
                display_fields=tuple(
                    sorted(
                        key
                        for key in summary.display_snapshot
                        if key != "assignment_a"
                    )
                ),
            )
            for summary in self.summaries
        ]
        filtered = [
            s for s in summaries
            if not active_only or s.projection.predicate_active
        ]
        return tuple(filtered[offset : offset + limit])

    def query_detail(self, fingerprint: PreviewFingerprint):
        if self.fail_with_error is not None:
            raise self.fail_with_error
        raise NotImplementedError("out of scope")

    def claim(self, request):
        self.mutation_invoked = True
        raise NotImplementedError("mutation out of scope")

    def resolve(self, request):
        self.mutation_invoked = True
        raise NotImplementedError("mutation out of scope")

    def project(self, request):
        self.mutation_invoked = True
        raise NotImplementedError("mutation out of scope")


class _RepositoryShapedSummary:
    def __init__(self, summary: AnomalySummary) -> None:
        self.summary = summary

    def query_summaries(self, **_):
        return (self.summary,)

    def query_detail(self, _fingerprint):
        return AnomalyDetail(self.summary, (), ())


def _default_summaries() -> list[AnomalySummary]:
    p1 = _FakeProjection(
        fingerprint=PreviewFingerprint("8f48483d980d2105151522a36a7f05ee461e78a63574a3f1244d2d6c66cf17f8"),
        definition_code="SCHEDULE-001",
        source_identity="assignment:102",
        source_version=2,
        predicate_active=True,
        workflow_status=AlertWorkflowStatus.OPEN,
        workflow_version=0,
    )
    s1 = AnomalySummary(
        projection=p1,
        source_domain="scheduling",
        severity=AnomalySeverity.BLOCKING.value,
        display_snapshot={"staff_id": 14, "holiday_date": "2026-08-20"},
    )

    p2 = _FakeProjection(
        fingerprint=PreviewFingerprint("a" * 64),
        definition_code="SCHEDULE-003",
        source_identity="assignment:103",
        source_version=1,
        predicate_active=True,
        workflow_status=AlertWorkflowStatus.CLAIMED,
        workflow_version=1,
    )
    s2 = AnomalySummary(
        projection=p2,
        source_domain="scheduling",
        severity=AnomalySeverity.WARNING.value,
        display_snapshot={"staff_id": 15, "assignment_a": {"start": "2026-08-21"}},
    )

    p3 = _FakeProjection(
        fingerprint=PreviewFingerprint("b" * 64),
        definition_code="SCHEDULE-005",
        source_identity="assignment:104",
        source_version=3,
        predicate_active=False,
        workflow_status=AlertWorkflowStatus.RESOLVED,
        workflow_version=2,
    )
    s3 = AnomalySummary(
        projection=p3,
        source_domain="scheduling",
        severity=AnomalySeverity.WARNING.value,
        display_snapshot={"staff_id": 16, "work_date": "2026-08-22"},
    )

    p4 = _FakeProjection(
        fingerprint=PreviewFingerprint("c" * 64),
        definition_code="RECEIVABLE-001",
        source_identity="receivable:201",
        source_version=1,
        predicate_active=True,
        workflow_status=AlertWorkflowStatus.OPEN,
        workflow_version=0,
    )
    s4 = AnomalySummary(
        projection=p4,
        source_domain="client_receivable",
        severity=AnomalySeverity.WARNING.value,
        display_snapshot={
            "action": "review_receivable",
            "case_no": "CASE-201",
            "overdue_obligations": ["obligation:201"],
        },
    )

    return [s1, s2, s3, s4]


def _create_app(application: _FakeAnomalyApplication, authenticate: bool = True) -> FastAPI:
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
    app.dependency_overrides[get_anomaly_application] = lambda: application
    return app


def test_query_anomalies_default_snapshot_false_contract_structure() -> None:
    app_state = _FakeAnomalyApplication()
    client = TestClient(_create_app(app_state))

    response = client.get("/api/v1/anomalies")
    assert response.status_code == 200

    payload = response.json()
    assert payload["success"] is True
    assert payload["message"] == "成功取得異常摘要"
    assert payload["error"] is None
    assert isinstance(payload["data"], list)
    assert len(payload["data"]) == 3  # active_only=True by default

    for item in payload["data"]:
        # Strict schema validation using Pydantic model
        view = AnomalySummaryView.model_validate(item)
        assert len(view.fingerprint) == 64
        assert view.source_version >= 0
        assert view.workflow_version >= 0
        assert view.severity in {"warning", "blocking"}
        assert view.workflow_status in {"open", "claimed", "resolved"}
        # include_snapshot=false: display_snapshot MUST be None (null)
        assert view.display_snapshot is None
        assert item["display_snapshot"] is None

    # First item verification (SCHEDULE-001)
    item0 = payload["data"][0]
    assert item0["fingerprint"] == "8f48483d980d2105151522a36a7f05ee461e78a63574a3f1244d2d6c66cf17f8"
    assert item0["definition_code"] == "SCHEDULE-001"
    assert item0["source_domain"] == "scheduling"
    assert item0["source_identity"] == "assignment:102"
    assert item0["source_version"] == 2
    assert item0["severity"] == "blocking"
    assert item0["predicate_active"] is True
    assert item0["workflow_status"] == "open"
    assert item0["workflow_version"] == 0
    assert item0["staff_calendar_navigation"] == {"staff_id": 14, "target_date": "2026-08-20"}

    # Second item verification (SCHEDULE-003)
    item1 = payload["data"][1]
    assert item1["definition_code"] == "SCHEDULE-003"
    assert item1["severity"] == "warning"
    assert item1["workflow_status"] == "claimed"
    assert item1["staff_calendar_navigation"] == {"staff_id": 15, "target_date": "2026-08-21"}

    # Third item verification (current Registry definition without navigation)
    item2 = payload["data"][2]
    assert item2["definition_code"] == "RECEIVABLE-001"
    assert item2["source_domain"] == "client_receivable"
    assert item2["staff_calendar_navigation"] is None


def test_finance_manual_review_list_omits_snapshot_without_validating_detail_fields() -> None:
    summary = AnomalySummary(
        projection=_FakeProjection(
            fingerprint=PreviewFingerprint("d" * 64),
            definition_code="finance_import_manual_review",
            source_identity="finance-import-row:94",
            source_version=1,
            predicate_active=True,
            workflow_status=AlertWorkflowStatus.OPEN,
            workflow_version=0,
        ),
        source_domain="finance_import",
        severity=AnomalySeverity.WARNING,
        display_snapshot={"untyped_legacy_field": "must stay out of list"},
        display_fields=("finance_import_row_id",),
    )

    payload = _summary_payload(summary, include_snapshot=False)

    assert payload["display_snapshot"] is None


def test_query_anomalies_explicit_include_snapshot_false_and_true() -> None:
    app_state = _FakeAnomalyApplication()
    client = TestClient(_create_app(app_state))

    # Explicit include_snapshot=false
    res_false = client.get("/api/v1/anomalies?include_snapshot=false")
    assert res_false.status_code == 200
    for item in res_false.json()["data"]:
        assert item["display_snapshot"] is None

    # Explicit include_snapshot=true
    res_true = client.get("/api/v1/anomalies?include_snapshot=true")
    assert res_true.status_code == 200
    data_true = res_true.json()["data"]
    assert data_true[0]["display_snapshot"] == {
        "redaction_version": "anomaly-safe.v1",
        "definition_code": "SCHEDULE-001",
        "fields": [
            {"kind": "date", "key": "holiday_date", "value": "2026-08-20"},
            {"kind": "identity", "key": "staff_id", "value": "14"},
        ],
    }
    assert data_true[1]["display_snapshot"] == {
        "redaction_version": "anomaly-safe.v1",
        "definition_code": "SCHEDULE-003",
        "fields": [
            {"kind": "identity", "key": "staff_id", "value": "15"},
        ],
    }
    assert "assignment_a" not in str(data_true[1]["display_snapshot"])
    assert data_true[2]["display_snapshot"] == {
        "redaction_version": "anomaly-safe.v1",
        "definition_code": "RECEIVABLE-001",
        "fields": [
            {"kind": "code", "key": "action", "value": "review_receivable"},
            {"kind": "identity", "key": "case_no", "value": "CASE-201"},
            {
                "kind": "identity_list",
                "key": "overdue_obligations",
                "value": ["obligation:201"],
            },
        ],
    }


def test_query_anomalies_query_parameters_forwarding_and_filtering() -> None:
    app_state = _FakeAnomalyApplication()
    client = TestClient(_create_app(app_state))

    # Query with active_only=false, limit=2, offset=1
    response = client.get("/api/v1/anomalies?active_only=false&limit=2&offset=1")
    assert response.status_code == 200
    assert app_state.last_query_params == {
        "active_only": False,
        "limit": 2,
        "offset": 1,
    }

    data = response.json()["data"]
    assert len(data) == 2
    # Offset 1 on total 4 items -> returns index 1 (SCHEDULE-003) and index 2 (SCHEDULE-005 resolved)
    assert data[0]["definition_code"] == "SCHEDULE-003"
    assert data[1]["definition_code"] == "SCHEDULE-005"
    assert data[1]["predicate_active"] is False
    assert data[1]["workflow_status"] == "resolved"


def test_query_anomalies_query_parameter_validation_boundaries() -> None:
    app_state = _FakeAnomalyApplication()
    client = TestClient(_create_app(app_state))

    # limit boundary: ge=1, le=200
    assert client.get("/api/v1/anomalies?limit=1").status_code == 200
    assert client.get("/api/v1/anomalies?limit=200").status_code == 200

    # limit violations
    assert client.get("/api/v1/anomalies?limit=0").status_code == 422
    assert client.get("/api/v1/anomalies?limit=-1").status_code == 422
    assert client.get("/api/v1/anomalies?limit=201").status_code == 422
    assert client.get("/api/v1/anomalies?limit=not_an_int").status_code == 422

    # offset boundary: ge=0
    assert client.get("/api/v1/anomalies?offset=0").status_code == 200
    assert client.get("/api/v1/anomalies?offset=50").status_code == 200
    assert client.get("/api/v1/anomalies?offset=-1").status_code == 422
    assert client.get("/api/v1/anomalies?offset=not_an_int").status_code == 422

    # active_only boolean validation
    assert client.get("/api/v1/anomalies?active_only=true").status_code == 200
    assert client.get("/api/v1/anomalies?active_only=false").status_code == 200
    assert client.get("/api/v1/anomalies?active_only=not_a_bool").status_code == 422


def test_query_anomalies_staff_calendar_navigation_for_valid_projection() -> None:
    # Test SCHEDULE-005 navigation
    p_valid = _FakeProjection(
        fingerprint=PreviewFingerprint("d" * 64),
        definition_code="SCHEDULE-005",
        source_identity="assignment:105",
        source_version=1,
        predicate_active=True,
        workflow_status=AlertWorkflowStatus.OPEN,
        workflow_version=0,
    )
    s_valid = AnomalySummary(
        projection=p_valid,
        source_domain="scheduling",
        severity=AnomalySeverity.WARNING.value,
        display_snapshot={"staff_id": 99, "work_date": "2026-09-01"},
    )

    app_state = _FakeAnomalyApplication([s_valid])
    client = TestClient(_create_app(app_state))

    response = client.get("/api/v1/anomalies")
    assert response.status_code == 200
    assert response.json()["data"][0]["staff_calendar_navigation"] == {
        "staff_id": 99,
        "target_date": "2026-09-01",
    }


def test_query_anomalies_malformed_calendar_evidence_fails_closed() -> None:
    p_invalid_staff = _FakeProjection(
        fingerprint=PreviewFingerprint("e" * 64),
        definition_code="SCHEDULE-001",
        source_identity="assignment:106",
        source_version=1,
        predicate_active=True,
        workflow_status=AlertWorkflowStatus.OPEN,
        workflow_version=0,
    )
    s_invalid_staff = AnomalySummary(
        projection=p_invalid_staff,
        source_domain="scheduling",
        severity=AnomalySeverity.WARNING.value,
        display_snapshot={"staff_id": 0, "holiday_date": "2026-09-01"},
    )

    # Test invalid date string
    p_invalid_date = _FakeProjection(
        fingerprint=PreviewFingerprint("f" * 64),
        definition_code="SCHEDULE-001",
        source_identity="assignment:107",
        source_version=1,
        predicate_active=True,
        workflow_status=AlertWorkflowStatus.OPEN,
        workflow_version=0,
    )
    s_invalid_date = AnomalySummary(
        projection=p_invalid_date,
        source_domain="scheduling",
        severity=AnomalySeverity.WARNING.value,
        display_snapshot={"staff_id": 10, "holiday_date": "not-a-date"},
    )

    for summary in (s_invalid_staff, s_invalid_date):
        client = TestClient(_create_app(_FakeAnomalyApplication([summary])))
        response = client.get("/api/v1/anomalies?include_snapshot=true")
        assert response.status_code == 422
        assert (
            response.json()["detail"]["error"]["code"]
            == "anomaly_projection_data_integrity_violation"
        )


def test_query_anomalies_requires_system_admin_authentication() -> None:
    app_state = _FakeAnomalyApplication()
    app = _create_app(app_state, authenticate=False)
    client = TestClient(app)

    response = client.get("/api/v1/anomalies")
    assert response.status_code in {401, 403}


def test_query_anomalies_zero_mutation_guarantee() -> None:
    app_state = _FakeAnomalyApplication()
    client = TestClient(_create_app(app_state))

    # Initial state
    assert app_state.mutation_invoked is False

    # Execute multiple GET requests
    res1 = client.get("/api/v1/anomalies")
    res2 = client.get("/api/v1/anomalies?active_only=false")
    res3 = client.get("/api/v1/anomalies?limit=10&offset=0")

    assert res1.status_code == 200
    assert res2.status_code == 200
    assert res3.status_code == 200

    # Ensure zero mutations were triggered
    assert app_state.mutation_invoked is False
    assert len(app_state.summaries) == 4


def test_query_anomalies_mysql_retryable_error_handling() -> None:
    app_state = _FakeAnomalyApplication()
    app_state.fail_with_error = OperationalError(1205, "Lock wait timeout exceeded")
    client = TestClient(_create_app(app_state))

    response = client.get("/api/v1/anomalies")
    assert response.status_code == 503
    assert response.headers.get("Retry-After") == "1"

    error = response.json()["detail"]["error"]
    assert error["category"] == "unavailable"
    assert error["code"] == "transaction_failed"
    assert error["retryable"] is True


def test_query_anomalies_repository_unavailable_error_handling() -> None:
    app_state = _FakeAnomalyApplication()
    app_state.fail_with_error = AnomalyRepositoryUnavailable("Projector is busy")
    client = TestClient(_create_app(app_state))

    response = client.get("/api/v1/anomalies")
    assert response.status_code == 503
    assert response.headers.get("Retry-After") == "1"

    error = response.json()["detail"]["error"]
    assert error["category"] == "unavailable"
    assert error["code"] == "projector_unavailable"
    assert error["retryable"] is True


def test_query_anomalies_empty_dataset() -> None:
    app_state = _FakeAnomalyApplication([])
    client = TestClient(_create_app(app_state))

    response = client.get("/api/v1/anomalies")
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["data"] == []
    assert payload["error"] is None


def test_application_enriches_repository_summary_from_canonical_registry() -> None:
    repository_summary = _default_summaries()[0]
    repository_summary = AnomalySummary(
        projection=repository_summary.projection,
        source_domain=repository_summary.source_domain,
        severity="",
        display_snapshot=repository_summary.display_snapshot,
    )
    application = AnomalyApplication(
        default_anomaly_registry(),
        _RepositoryShapedSummary(repository_summary),
        lambda: None,
    )

    listed = application.query_summaries()[0]
    detailed = application.query_detail(repository_summary.projection.fingerprint)

    assert listed.severity is AnomalySeverity.WARNING
    assert detailed.summary.severity is AnomalySeverity.WARNING


def test_application_rejects_repository_source_domain_drift() -> None:
    repository_summary = _default_summaries()[0]
    repository_summary = AnomalySummary(
        projection=repository_summary.projection,
        source_domain="client_finance",
        severity="",
        display_snapshot=repository_summary.display_snapshot,
    )
    application = AnomalyApplication(
        default_anomaly_registry(),
        _RepositoryShapedSummary(repository_summary),
        lambda: None,
    )

    with pytest.raises(ValueError, match="anomaly_projection_data_integrity_violation"):
        application.query_summaries()


def test_query_route_returns_typed_error_for_repository_source_domain_drift() -> None:
    repository_summary = _default_summaries()[0]
    drifted = AnomalySummary(
        projection=repository_summary.projection,
        source_domain="client_finance",
        severity="",
        display_snapshot=repository_summary.display_snapshot,
    )
    application = AnomalyApplication(
        default_anomaly_registry(),
        _RepositoryShapedSummary(drifted),
        lambda: None,
    )
    client = TestClient(_create_app(application))

    response = client.get("/api/v1/anomalies")

    assert response.status_code == 422
    error = response.json()["detail"]["error"]
    assert error["code"] == "anomaly_projection_data_integrity_violation"
    assert error["retryable"] is False


def test_application_rejects_unknown_repository_workflow_status() -> None:
    repository_summary = _default_summaries()[0]
    unknown_projection = _FakeProjection(
        fingerprint=repository_summary.projection.fingerprint,
        definition_code=repository_summary.projection.definition_code,
        source_identity=repository_summary.projection.source_identity,
        source_version=repository_summary.projection.source_version,
        predicate_active=True,
        workflow_status="unknown",  # type: ignore[arg-type]
        workflow_version=repository_summary.projection.workflow_version,
    )
    application = AnomalyApplication(
        default_anomaly_registry(),
        _RepositoryShapedSummary(
            AnomalySummary(
                projection=unknown_projection,
                source_domain="scheduling",
                severity="",
                display_snapshot=repository_summary.display_snapshot,
            )
        ),
        lambda: None,
    )

    with pytest.raises(ValueError, match="anomaly_projection_data_integrity_violation"):
        application.query_summaries()


def test_query_route_returns_typed_error_for_unknown_definition() -> None:
    repository_summary = _default_summaries()[0]
    unknown_projection = _FakeProjection(
        fingerprint=repository_summary.projection.fingerprint,
        definition_code="UNKNOWN-999",
        source_identity=repository_summary.projection.source_identity,
        source_version=repository_summary.projection.source_version,
        predicate_active=True,
        workflow_status=AlertWorkflowStatus.OPEN,
        workflow_version=repository_summary.projection.workflow_version,
    )
    application = AnomalyApplication(
        default_anomaly_registry(),
        _RepositoryShapedSummary(
            AnomalySummary(
                projection=unknown_projection,
                source_domain="scheduling",
                severity="",
                display_snapshot=repository_summary.display_snapshot,
            )
        ),
        lambda: None,
    )
    client = TestClient(_create_app(application))

    response = client.get("/api/v1/anomalies")

    assert response.status_code == 422
    error = response.json()["detail"]["error"]
    assert error["code"] == "anomaly_definition_not_found"
    assert error["retryable"] is False


@pytest.mark.parametrize(
    ("field", "value"),
    (("severity", ""), ("severity", "critical"), ("workflow_status", "unknown")),
)
def test_anomaly_summary_public_contract_rejects_unknown_enums(
    field: str,
    value: str,
) -> None:
    payload = {
        "fingerprint": "a" * 64,
        "definition_code": "SCHEDULE-001",
        "source_domain": "scheduling",
        "source_identity": "assignment:1",
        "source_version": 1,
        "severity": "warning",
        "predicate_active": True,
        "workflow_status": "open",
        "workflow_version": 1,
    }
    payload[field] = value

    with pytest.raises(ValueError):
        AnomalySummaryView.model_validate(payload)


def test_anomaly_public_json_schema_exposes_closed_enums() -> None:
    summary_schema = AnomalySummaryView.model_json_schema()
    receipt_schema = AnomalyWorkflowReceiptView.model_json_schema()

    assert summary_schema["$defs"]["AnomalySeverity"]["enum"] == [
        "warning",
        "blocking",
    ]
    assert summary_schema["$defs"]["AlertWorkflowStatus"]["enum"] == [
        "open",
        "claimed",
        "resolved",
    ]
    assert receipt_schema["$defs"]["AlertWorkflowStatus"]["enum"] == [
        "open",
        "claimed",
        "resolved",
    ]
