"""
File: test_anomaly_public_detail_recovery_contract.py
Description: 驗證異常 detail 與 recovery 公開投影的封閉、去敏與零寫入契約。
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException
import pytest

from api.routes import anomaly_recovery as recovery_route
from api.routes import anomaly_registry as registry_route
from api.schemas.anomaly_recovery import (
    AnomalyRecoveryContextView,
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
    AnomalySeverity,
    RecoveryActionDescriptor,
)
from domains.anomalies.current_issue import CurrentIssueCandidate, CurrentIssueProjection
from shared_kernel.identities import CorrelationId
from subsystems.access.authentication_session import AdminPrincipal


_NOW = datetime(2026, 8, 22, 9, 30, tzinfo=timezone.utc)


class _ReadOnlyCurrentIssueRepository:
    def __init__(self, projection: CurrentIssueProjection) -> None:
        self.projection = projection
        self.calls: list[str] = []

    def query_current(self, issue_key: str) -> CurrentIssueProjection:
        assert issue_key == self.projection.issue_key
        self.calls.append("query_current")
        return self.projection


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


def _current_projection() -> CurrentIssueProjection:
    candidate = CurrentIssueCandidate(
        issue_key="ci_" + "c" * 64,
        definition_code="GOVSUB-007",
        owner_domain="government_subsidy",
        owner_root_type="overpayment",
        subject_type="payable",
        subject_id="payable:42",
        owner_version=7,
        severity=AnomalySeverity.WARNING.value,
        blocking=True,
        details={
            "amount_delta_ntd": 1200,
            "root_condition_active": True,
            "available_actions": (_action(bound=True),),
        },
        subject_identity={"payable_identity": "payable:42"},
    )
    return CurrentIssueProjection(
        candidate=candidate,
        episode_started_at=_NOW,
        last_verified_at=_NOW,
        owner_snapshot_token="owner-snapshot:7",
        details_version=1,
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


def test_recovery_query_returns_current_issue_owner_details_and_actions() -> None:
    projection = _current_projection()
    application = _ReadOnlyCurrentIssueRepository(projection)
    response = recovery_route.query_recovery_context(
        projection.issue_key,
        AdminPrincipal(id=1, username="system_admin", display_name="Admin", role="system_admin"),
        application,
    )
    view = AnomalyRecoveryContextView.model_validate(response.data)

    assert application.calls == ["query_current"]
    assert view.issue_key == projection.issue_key
    assert view.owner_domain == "government_subsidy"
    assert view.owner_root_type == "overpayment"
    assert [(item.kind, item.key, item.value) for item in view.subject.fields] == [
        ("identity", "payable_identity", "payable:42"),
    ]
    assert [(item.kind, item.key, item.value) for item in view.details.fields] == [
        ("money_ntd", "amount_delta_ntd", 1200),
        ("boolean", "root_condition_active", True),
    ]
    assert view.owner_snapshot_token == "owner-snapshot:7"
    assert view.owner_version == 7
    assert view.blocking is True
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
        (route._call if route is registry_route else route._call_current)(
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
        lambda: recovery_route._current_display_snapshot(
            "GOVSUB-007", {"unexpected": "snapshot"}
        ),
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
        recovery_route._call_current(
            builder,
            "irrelevant",
            CorrelationId("contract-recovery-422"),
        )
    assert recovery_error.value.status_code == 422
    assert recovery_error.value.detail["error"]["code"] == "anomaly_projection_data_integrity_violation"
