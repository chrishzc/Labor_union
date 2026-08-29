"""
File: test_anomaly_public_detail_recovery_contract.py
Description: 驗證異常 detail 與 recovery 公開投影的封閉、去敏與零寫入契約。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from fastapi import HTTPException
import pytest

from api.routes import anomaly_recovery as recovery_route
from api.routes import anomaly_registry as registry_route
from api.schemas.anomaly_recovery import (
    AnomalyRecoveryContextView,
    AnomalyRootFactSnapshotView,
    FinanceOccurrenceView,
    RecoveryActionView,
)
from api.schemas.anomaly_registry import (
    AnomalyDetailView,
    AnomalyDisplaySnapshotView,
    AnomalySummaryView,
    AnomalyTimelineEventView,
    DomainActionView,
)
from domains.anomalies.registry import (
    AlertWorkflowStatus,
    AnomalySeverity,
    CurrentAlertProjection,
    RecoveryActionDescriptor,
)
from domains.anomalies.root_fact_projection import (
    FinanceAnomalyOccurrence,
    RecoveryContext,
)
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.identities import CorrelationId
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.anomalies.alert_workflow import AnomalyDetail, AnomalySummary


_FINGERPRINT = "a" * 64
_NOW = datetime(2026, 8, 22, 9, 30, tzinfo=timezone.utc)


@dataclass(frozen=True, slots=True)
class _TimelineEvent:
    action: str
    expected_workflow_version: int
    resulting_workflow_version: int
    actor: str
    reason: str
    correlation_id: str
    created_at: datetime


class _ReadOnlyAnomalyQuery:
    def __init__(self, detail: AnomalyDetail) -> None:
        self.detail = detail
        self.calls: list[str] = []

    def query_detail(self, fingerprint: PreviewFingerprint) -> AnomalyDetail:
        assert fingerprint.value == _FINGERPRINT
        self.calls.append("query_detail")
        return self.detail

    def commit(self) -> None:
        raise AssertionError("detail query must not commit")

    def repair(self) -> None:
        raise AssertionError("detail query must not repair")

    def append_outbox(self) -> None:
        raise AssertionError("detail query must not append outbox")


class _ReadOnlyRecoveryQuery:
    def __init__(self, context: RecoveryContext) -> None:
        self.context = context
        self.calls: list[str] = []

    def query_recovery(
        self,
        fingerprint: PreviewFingerprint,
        correlation_id: CorrelationId,
    ) -> RecoveryContext:
        assert fingerprint.value == _FINGERPRINT
        assert correlation_id.value.startswith("anomaly-recovery:")
        self.calls.append("query_recovery")
        return self.context

    def commit(self) -> None:
        raise AssertionError("recovery query must not commit")

    def repair(self) -> None:
        raise AssertionError("recovery query must not repair")

    def append_outbox(self) -> None:
        raise AssertionError("recovery query must not append outbox")


def _projection(definition_code: str = "IMPORT-004") -> CurrentAlertProjection:
    return CurrentAlertProjection(
        fingerprint=PreviewFingerprint(_FINGERPRINT),
        definition_code=definition_code,
        source_identity="opaque-subject:42",
        source_version=7,
        predicate_active=True,
        workflow_status=AlertWorkflowStatus.OPEN,
        workflow_version=3,
    )


def _action(*, bound: bool) -> RecoveryActionDescriptor:
    return RecoveryActionDescriptor(
        action_key="review_safe_projection",
        label="Review safe projection",
        owning_domain="finance_import",
        form_schema_key="finance_import.review.v1",
        source_binding_keys=("finance_import_row_identity", "source_version"),
        source_bindings=(
            {
                "finance_import_row_identity": "finance-row:42",
                "source_version": 7,
            }
            if bound
            else None
        ),
        required_operator_inputs=("evidence", "reason"),
        preview_operation="PreviewSafeProjection",
        apply_operation="ApplySafeProjection",
        required_capability="finance_import.review",
        completion_predicate="source_predicate_cleared",
        action_contract_version=1,
        requires_preview=True,
    )


def _detail() -> AnomalyDetail:
    summary = AnomalySummary(
        projection=_projection(),
        source_domain="case_import",
        severity=AnomalySeverity.WARNING,
        display_snapshot={"case_no": "CASE-42"},
        display_fields=("case_no",),
    )
    return AnomalyDetail(
        summary=summary,
        timeline=(
            _TimelineEvent(
                action="resolve",
                expected_workflow_version=2,
                resulting_workflow_version=3,
                actor="Private Operator Name",
                reason="raw operator note must not cross the public boundary",
                correlation_id="corr-detail-42",
                created_at=_NOW,
            ),
        ),
        available_actions=(_action(bound=False),),
    )


def _recovery_context() -> RecoveryContext:
    occurrence = FinanceAnomalyOccurrence(
        occurrence_fingerprint=PreviewFingerprint("b" * 64),
        definition_code="finance_import_manual_review",
        source_event_identity="event:42",
        finance_import_row_id=42,
        finance_import_batch_id=9,
        source_version=7,
        occurred_at=_NOW,
        bounded_snapshot={
            "amount_delta_ntd": 1200,
            "case_no": "CASE-42",
            "domain_blockers": ["manual_review"],
            "reason_codes": ["AMOUNT_MISMATCH"],
            "recovery_identity": "recovery:42",
            "root_condition_active": True,
            "integrity_blocker_active": False,
        },
    )
    return RecoveryContext(
        projection=_projection("finance_import_manual_review"),
        source_domain="finance_import",
        severity=AnomalySeverity.WARNING.value,
        root_fact_snapshot={
            "occurred_at": _NOW,
            "source_version": 7,
            "amount_delta_ntd": 1200,
            "root_condition_active": True,
            "integrity_blocker_active": False,
            "affected_order_identities": ["order:17"],
            "affected_obligation_identities": ["obligation:19"],
            "domain_blockers": ["manual_review"],
            "reason_codes": ["AMOUNT_MISMATCH"],
            "finance_import_row_id": 42,
            "finance_import_batch_id": 9,
            "case_no": "CASE-42",
            "recovery_identity": "recovery:42",
            "recovery_bindings": {
                "finance_import_row_identity": "finance-row:42",
                "source_version": 7,
            },
        },
        domain_blocker_active=True,
        projection_freshness="fresh",
        occurrence_timeline=(occurrence,),
        workflow_timeline=(
            _TimelineEvent(
                action="resolve",
                expected_workflow_version=2,
                resulting_workflow_version=3,
                actor="Private Operator Name",
                reason="raw root repair claim",
                correlation_id="corr-recovery-42",
                created_at=_NOW,
            ),
        ),
        available_actions=(_action(bound=True),),
    )


def _assert_closed_object_schemas(schema: object) -> None:
    if isinstance(schema, dict):
        if schema.get("type") == "object":
            assert schema.get("additionalProperties") is False
        assert schema.get("additionalProperties") not in ({}, True)
        for value in schema.values():
            _assert_closed_object_schemas(value)
    elif isinstance(schema, list):
        for value in schema:
            _assert_closed_object_schemas(value)


def test_public_detail_and_recovery_models_have_no_raw_mapping_escape_hatch() -> None:
    public_models = (
        AnomalyDisplaySnapshotView,
        AnomalySummaryView,
        AnomalyTimelineEventView,
        DomainActionView,
        AnomalyDetailView,
        AnomalyRootFactSnapshotView,
        FinanceOccurrenceView,
        RecoveryActionView,
        AnomalyRecoveryContextView,
    )

    for model in public_models:
        schema = model.model_json_schema()
        _assert_closed_object_schemas(schema)
        assert "'additionalProperties': {}" not in str(schema)


@pytest.mark.parametrize(
    ("field", "raw_value", "kind", "expected"),
    (
        ("case_no", "CASE-42", "identity", "CASE-42"),
        ("holiday_date", "2026-08-22", "date", "2026-08-22"),
        ("amount_delta_ntd", 1200, "money_ntd", 1200),
        ("version", 7, "integer", 7),
        ("notification_reason", "missing_document", "code", "missing_document"),
        ("issue_codes", ["missing_document"], "code_list", ["missing_document"]),
        ("overdue_obligations", ["obligation:19"], "detail_list", ["obligation:19"]),
        ("staff_name", "Private Operator Name", "masked_text", "P***"),
    ),
)
def test_registry_display_fields_emit_discriminated_safe_evidence(
    field: str,
    raw_value: object,
    kind: str,
    expected: object,
) -> None:
    snapshot = registry_route._safe_display_snapshot(
        "TEST-ANOMALY-001",
        (field,),
        {field: raw_value},
    )

    assert snapshot.redaction_version == "anomaly-safe.v1"
    assert snapshot.definition_code == "TEST-ANOMALY-001"
    assert len(snapshot.fields) == 1
    evidence = snapshot.fields[0]
    assert evidence.kind == kind
    assert evidence.key == field
    assert evidence.value == expected


def test_detail_query_is_typed_redacted_and_does_not_claim_root_repair() -> None:
    application = _ReadOnlyAnomalyQuery(_detail())
    response = registry_route.query_anomaly_detail(
        _FINGERPRINT,
        AdminPrincipal(id=1, username="system_admin", display_name="Admin", role="system_admin"),
        application,
    )
    view = AnomalyDetailView.model_validate(response.data)

    assert application.calls == ["query_detail"]
    assert view.summary.display_snapshot is not None
    assert view.summary.display_snapshot.fields[0].kind == "identity"
    timeline = view.timeline[0]
    assert timeline.actor == "P***"
    assert "Private Operator Name" not in timeline.actor
    assert "不代表根事實已修正" in timeline.reason
    assert view.available_actions[0].source_bindings is None


def test_recovery_query_preserves_required_identities_and_versions_but_redacts_pii() -> None:
    application = _ReadOnlyRecoveryQuery(_recovery_context())
    response = recovery_route.query_recovery_context(
        _FINGERPRINT,
        AdminPrincipal(id=1, username="system_admin", display_name="Admin", role="system_admin"),
        application,
    )
    view = AnomalyRecoveryContextView.model_validate(response.data)

    assert application.calls == ["query_recovery"]
    assert view.source_identity == "opaque-subject:42"
    assert view.source_version == 7
    assert view.root_fact_snapshot.affected_order_identities == ["order:17"]
    assert view.root_fact_snapshot.affected_obligation_identities == ["obligation:19"]
    assert view.root_fact_snapshot.source_version == 7
    assert view.occurrence_timeline[0].source_version == 7
    assert view.occurrence_timeline[0].bounded_snapshot.definition_code == "finance_import_manual_review"
    assert view.workflow_timeline[0].actor == "P***"
    assert "Private Operator Name" not in view.workflow_timeline[0].actor
    assert "不代表根事實已修正" in view.workflow_timeline[0].reason
    bindings = view.available_actions[0].source_bindings
    assert [(item.kind, item.key, item.value) for item in bindings] == [
        ("identity", "finance_import_row_identity", "finance-row:42"),
        ("version", "source_version", 7),
    ]


def _raise_projection_error(code: str) -> None:
    raise ValueError(code)


@pytest.mark.parametrize(
    ("route", "code"),
    (
        (registry_route, "anomaly_definition_not_found"),
        (recovery_route, "recovery_action_not_available"),
    ),
)
def test_unknown_definition_or_action_fails_closed_as_typed_422(route, code: str) -> None:
    with pytest.raises(HTTPException) as error:
        route._call(
            lambda: _raise_projection_error(code),
            "irrelevant",
            CorrelationId(f"contract-{code}"),
        )

    assert error.value.status_code == 422
    assert error.value.detail["error"]["code"] in {
        code,
        "anomaly_projection_data_integrity_violation",
    }


@pytest.mark.parametrize(
    "builder",
    (
        lambda: registry_route._safe_display_snapshot(
            "TEST-ANOMALY-001", ("case_no",), {"case_no": "CASE-42", "raw_payload": "x"}
        ),
        lambda: registry_route._safe_display_snapshot(
            "TEST-ANOMALY-001", ("case_no", "staff_id"), {"case_no": "CASE-42"}
        ),
        lambda: registry_route._safe_display_snapshot(
            "TEST-ANOMALY-001", ("unknown_field",), {"unknown_field": "x"}
        ),
        lambda: registry_route._action_payload({"action_key": "missing-required-fields"}),
        lambda: registry_route._source_bindings(
            ["unknown_binding"], {"unknown_binding": "CASE-42"}
        ),
        lambda: recovery_route._root_snapshot_payload({"unexpected": "snapshot"}),
        lambda: recovery_route._recovery_action_payload({"action_key": "missing-required-fields"}),
        lambda: recovery_route._source_binding_payload("source_version", True),
    ),
)
def test_malformed_or_unknown_public_projection_fails_closed_as_typed_422(builder) -> None:
    with pytest.raises(HTTPException) as registry_error:
        registry_route._call(
            builder,
            "irrelevant",
            CorrelationId("contract-registry-422"),
        )
    assert registry_error.value.status_code == 422
    assert registry_error.value.detail["error"]["code"] == "anomaly_projection_data_integrity_violation"

    with pytest.raises(HTTPException) as recovery_error:
        recovery_route._call(
            builder,
            "irrelevant",
            CorrelationId("contract-recovery-422"),
        )
    assert recovery_error.value.status_code == 422
    assert recovery_error.value.detail["error"]["code"] == "anomaly_projection_data_integrity_violation"
