"""
File: test_anomaly_necessity_migration_api.py
Description: 驗證異常必要性移轉 API 只接受 server-owned policy 與持久化管理員。
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError
import pytest

from api.dependencies.admin_auth import (
    require_persisted_admin,
    require_anomaly_necessity_migration_operator,
)
from api.dependencies.anomaly_necessity_migration import (
    AnomalyNecessityMigrationApplication,
    get_anomaly_necessity_migration_application,
)
from api.main import app
from api.routes.anomaly_necessity_migration import (
    _apply_payload,
    _page_payload,
    _preview_payload,
)
from api.schemas.anomaly_necessity_migration import (
    AnomalyNecessityMigrationApplyBody,
    AnomalyNecessityMigrationIntentBody,
    AnomalyNecessityMigrationPageView,
    AnomalyNecessityMigrationPreviewView,
    AnomalyNecessityMigrationReceiptView,
)
from domains.anomalies.maintenance import (
    AnomalyReclassificationAlertIdentity,
    AnomalyReclassificationCursorPageRequest,
    AnomalyReclassificationDisposition,
    AnomalyReclassificationPage,
    AnomalyReclassificationReceipt,
)
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.identities import ActorContext, CorrelationId, IdempotencyKey
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.anomalies.necessity_migration_policy import (
    approved_anomaly_necessity_migration_policy,
)


_ALERT = AnomalyReclassificationAlertIdentity(
    PreviewFingerprint("a" * 64),
    "SCHEDULE-005",
    "schedule-preference:1",
    3,
    4,
)
_ACTOR = ActorContext("admin:9", ("system.administration",))


class _Workflow:
    def __init__(self) -> None:
        self.preview_calls = []
        self.apply_calls = []

    def query_reclassification(self, request, *, eligible_codes):
        assert isinstance(request, AnomalyReclassificationCursorPageRequest)
        assert eligible_codes == ("SCHEDULE-005",)
        return AnomalyReclassificationPage((_ALERT,), None)

    def preview_reclassification(
        self,
        alert,
        disposition,
        target,
        actor,
        reason,
        evidence_reference,
        rulebook_reference,
        release_evidence_reference,
    ):
        self.preview_calls.append(
            (
                alert,
                disposition,
                target,
                actor,
                rulebook_reference,
                release_evidence_reference,
            )
        )
        return approved_anomaly_necessity_migration_policy().build_candidate(
            alert,
            actor=actor,
            reason=reason,
            evidence_reference=evidence_reference,
        )

    def apply_reclassification(self, request):
        self.apply_calls.append(request)
        return AnomalyReclassificationReceipt(
            request.disposition_identity,
            "anomaly-reclassification-receipt:key-1",
            request.disposition,
            request.alert,
            request.preview_fingerprint,
            request.idempotency_key,
            request.correlation_id,
            request.actor,
            datetime(2026, 8, 27, tzinfo=timezone.utc),
            91,
            request.alert.workflow_version + 1,
            PreviewFingerprint("b" * 64),
            PreviewFingerprint("c" * 64),
        )


def _application():
    return AnomalyNecessityMigrationApplication(
        _Workflow(),
        approved_anomaly_necessity_migration_policy(),
    )


def test_policy_is_stable_and_caller_cannot_select_disposition() -> None:
    first = approved_anomaly_necessity_migration_policy()
    second = approved_anomaly_necessity_migration_policy()
    assert first.identity == second.identity
    assert first.fingerprint == second.fingerprint
    candidate = first.build_candidate(
        _ALERT,
        actor=_ACTOR,
        reason="偏好不得形成硬性異常",
        evidence_reference="evidence:schedule-005",
    )
    assert candidate.disposition is (
        AnomalyReclassificationDisposition.RETIRED_FALSE_POSITIVE
    )
    assert candidate.target is None

    with pytest.raises(ValidationError):
        AnomalyNecessityMigrationIntentBody.model_validate(
            {
                "expected_definition_code": "SCHEDULE-005",
                "expected_source_identity": "schedule-preference:1",
                "expected_source_version": 3,
                "expected_workflow_version": 4,
                "reason": "reason",
                "evidence_reference": "evidence",
                "disposition": "reclassified_to_owner_work_item",
            }
        )


def test_policy_rejects_definition_outside_current_approved_slice() -> None:
    other = AnomalyReclassificationAlertIdentity(
        PreviewFingerprint("d" * 64),
        "ORDER-001",
        "order:1",
        1,
        1,
    )
    with pytest.raises(
        ValueError,
        match="anomaly_necessity_migration_definition_not_admitted",
    ):
        approved_anomaly_necessity_migration_policy().build_candidate(
            other,
            actor=_ACTOR,
            reason="reason",
            evidence_reference="evidence",
        )


def test_query_and_preview_payloads_expose_policy_but_not_a_policy_input() -> None:
    application = _application()
    page = AnomalyNecessityMigrationPageView.model_validate(
        _page_payload(application, 100, None, None)
    )
    assert page.items[0].definition_code == "SCHEDULE-005"
    assert page.policy_fingerprint == application.policy.fingerprint.value

    preview = AnomalyNecessityMigrationPreviewView.model_validate(
        _preview_payload(
            application,
            _ALERT,
            _ACTOR,
            "偏好不得形成硬性異常",
            "evidence:schedule-005",
        )
    )
    assert preview.disposition is (
        AnomalyReclassificationDisposition.RETIRED_FALSE_POSITIVE
    )
    assert preview.target is None
    assert application.workflow.preview_calls[0][2] is None


def test_apply_recomputes_server_preview_and_returns_readback_receipt() -> None:
    application = _application()
    candidate = application.policy.build_candidate(
        _ALERT,
        actor=_ACTOR,
        reason="偏好不得形成硬性異常",
        evidence_reference="evidence:schedule-005",
    )
    body = AnomalyNecessityMigrationApplyBody(
        expected_definition_code=_ALERT.definition_code,
        expected_source_identity=_ALERT.source_identity,
        expected_source_version=_ALERT.source_version,
        expected_workflow_version=_ALERT.workflow_version,
        reason=candidate.reason,
        evidence_reference=candidate.evidence_reference,
        preview_fingerprint=candidate.fingerprint.value,
    )
    receipt = AnomalyNecessityMigrationReceiptView.model_validate(
        _apply_payload(
            application,
            _ALERT,
            _ACTOR,
            body,
            IdempotencyKey("key-1"),
            CorrelationId("corr-1"),
        )
    )
    assert receipt.resulting_predicate_active is False
    assert receipt.resulting_workflow_version == 5
    assert application.workflow.preview_calls == []
    assert len(application.workflow.apply_calls) == 1


def test_apply_rejects_stale_preview_before_any_apply() -> None:
    application = _application()
    body = AnomalyNecessityMigrationApplyBody(
        expected_definition_code=_ALERT.definition_code,
        expected_source_identity=_ALERT.source_identity,
        expected_source_version=_ALERT.source_version,
        expected_workflow_version=_ALERT.workflow_version,
        reason="偏好不得形成硬性異常",
        evidence_reference="evidence:schedule-005",
        preview_fingerprint="f" * 64,
    )
    with pytest.raises(ValueError, match="preview_stale"):
        _apply_payload(
            application,
            _ALERT,
            _ACTOR,
            body,
            IdempotencyKey("key-1"),
            CorrelationId("corr-1"),
        )
    assert application.workflow.apply_calls == []


def test_migration_operator_requires_persisted_system_administrator() -> None:
    request = SimpleNamespace(state=SimpleNamespace())
    bypass = AdminPrincipal(
        None,
        "development-bypass",
        "Developer",
        "system_admin",
        capabilities=frozenset({"system.administration"}),
    )
    with pytest.raises(HTTPException) as denied:
        require_anomaly_necessity_migration_operator(request, bypass)
    assert denied.value.status_code == 403

    operator = AdminPrincipal(
        9,
        "migration-operator",
        "Migration Operator",
        "system_admin",
        capabilities=frozenset({"system.administration"}),
    )
    assert (
        require_anomaly_necessity_migration_operator(request, operator)
        is operator
    )
    assert request.state.admin_actor.actor_id == "admin:9"


def test_openapi_declares_dedicated_routes_and_typed_errors() -> None:
    schema = app.openapi()
    paths = schema["paths"]
    prefix = "/api/v1/admin/anomaly-necessity-migration"
    assert f"{prefix}/alerts" in paths
    assert f"{prefix}/alerts/{{alert_fingerprint}}/preview" in paths
    assert f"{prefix}/alerts/{{alert_fingerprint}}/apply" in paths
    for method, path in (
        ("get", f"{prefix}/alerts"),
        ("post", f"{prefix}/alerts/{{alert_fingerprint}}/preview"),
        ("post", f"{prefix}/alerts/{{alert_fingerprint}}/apply"),
    ):
        responses = paths[path][method]["responses"]
        assert {"403", "404", "409", "422", "500", "503"}.issubset(
            responses
        )


def test_route_auth_failure_uses_global_typed_error_envelope() -> None:
    denied = AdminPrincipal(
        8,
        "migration-reader",
        "Migration Reader",
        "migration_observer",
        capabilities=frozenset(),
    )
    app.dependency_overrides[require_persisted_admin] = lambda: denied
    app.dependency_overrides[get_anomaly_necessity_migration_application] = (
        _application
    )
    try:
        response = TestClient(app).get(
            "/api/v1/admin/anomaly-necessity-migration/alerts",
            headers={"X-Correlation-ID": "anm-nm-a-auth-contract"},
        )
    finally:
        app.dependency_overrides.pop(require_persisted_admin, None)
        app.dependency_overrides.pop(
            get_anomaly_necessity_migration_application,
            None,
        )

    assert response.status_code == 403
    assert response.headers["X-Correlation-ID"] == "anm-nm-a-auth-contract"
    error = response.json()["detail"]["error"]
    assert set(error) == {
        "category",
        "code",
        "message",
        "field_errors",
        "domain_blockers",
        "retryable",
        "correlation_id",
        "current_version",
    }
    assert error["category"] == "forbidden"
    assert error["correlation_id"] == "anm-nm-a-auth-contract"
