"""
File: anomaly_recovery.py
Description: 提供異常根事實、事件歷程與修復動作的封閉唯讀 FastAPI 投影。
"""

from __future__ import annotations

from dataclasses import fields, is_dataclass
from datetime import date, datetime, time
from enum import Enum

from fastapi import APIRouter, Depends, Header, HTTPException, Path

from api.dependencies.admin_auth import require_system_admin
from api.dependencies.anomaly_recovery import (
    get_anomaly_maintenance_application,
    get_anomaly_recovery_application,
)
from api.schemas.anomaly_recovery import (
    AnomalyRootFactSnapshotView,
    AnomalyRecoveryContextView,
    FinanceOccurrenceView,
    RecoveryActionView,
    RetryAnomalyProjectorBody,
    RetryAnomalyProjectorResultView,
    ScanAnomalyDefinitionBody,
    ScanAnomalyDefinitionResultView,
)
from api.schemas.anomaly_registry import (
    AnomalyDisplaySnapshotView,
    AnomalySourceBindingView,
    AnomalyTimelineEventView,
)
from api.schemas.base import BaseResponse
from domains.anomalies.maintenance import (
    RetryAnomalyProjectorRequest,
    ScanAnomalyDefinitionRequest,
)
from subsystems.access.authentication_session import AdminPrincipal
from shared_kernel.errors import ErrorCategory
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.identities import CorrelationId, ExpectedVersion
from subsystems.anomalies.maintenance_workflow import (
    AnomalyMaintenanceApplication,
    AnomalyMaintenanceError,
)
from subsystems.anomalies.root_fact_projection_workflow import (
    RootFactProjectionApplication,
    RootFactProjectionError,
)

router = APIRouter(prefix="/api/v1/anomaly-recovery", tags=["Anomalies"])


# The typed HTTP signature remains explicit so FastAPI documents every boundary.
@router.post(
    "/definitions/{definition_code}/scan",
    response_model=BaseResponse[ScanAnomalyDefinitionResultView],
)
def scan_anomaly_definition(
    body: ScanAnomalyDefinitionBody,
    definition_code: str = Path(..., min_length=1, max_length=191),
    correlation_header: str | None = Header(
        default=None,
        alias="X-Correlation-ID",
    ),
    principal: AdminPrincipal = Depends(require_system_admin),
    application: AnomalyMaintenanceApplication = Depends(
        get_anomaly_maintenance_application
    ),
):
    del principal
    correlation_id = _correlation_id(
        correlation_header,
        f"anomaly-scan:{definition_code}",
    )
    request = ScanAnomalyDefinitionRequest(
        definition_code,
        body.maximum_items,
        body.after_source_id,
    )
    return _call_maintenance(
        lambda: _scan_result_payload(
            application.scan_definition(request, correlation_id)
        ),
        "完成異常根事實分頁重掃描",
    )


# The typed HTTP signature remains explicit so FastAPI documents every boundary.
@router.post(
    "/projector/retry",
    response_model=BaseResponse[RetryAnomalyProjectorResultView],
)
def retry_anomaly_projector(
    body: RetryAnomalyProjectorBody,
    correlation_header: str | None = Header(
        default=None,
        alias="X-Correlation-ID",
    ),
    principal: AdminPrincipal = Depends(require_system_admin),
    application: AnomalyMaintenanceApplication = Depends(
        get_anomaly_maintenance_application
    ),
):
    del principal
    correlation_id = _correlation_id(
        correlation_header,
        "anomaly-projector-retry",
    )
    request = RetryAnomalyProjectorRequest(body.maximum_events)
    return _call_maintenance(
        lambda: _retry_result_payload(
            application.retry_projector(request, correlation_id)
        ),
        "已重新排入失敗的異常 projector 事件",
    )


@router.get(
    "/{fingerprint}",
    response_model=BaseResponse[AnomalyRecoveryContextView],
)
def query_recovery_context(
    fingerprint: str = Path(..., pattern=r"^[0-9a-f]{64}$"),
    principal: AdminPrincipal = Depends(require_system_admin),
    application: RootFactProjectionApplication = Depends(
        get_anomaly_recovery_application
    ),
):
    del principal
    correlation_id = CorrelationId(f"anomaly-recovery:{fingerprint}")
    return _call(
        lambda: _context_payload(
            application.query_recovery(
                PreviewFingerprint(fingerprint),
                correlation_id,
            )
        ),
        "成功取得異常修復資訊",
        correlation_id,
    )


@router.get(
    "/{fingerprint}/actions/{action_key}",
    response_model=BaseResponse[RecoveryActionView],
)
def query_recovery_preview_link(
    fingerprint: str = Path(..., pattern=r"^[0-9a-f]{64}$"),
    action_key: str = Path(..., min_length=1, max_length=191),
    principal: AdminPrincipal = Depends(require_system_admin),
    application: RootFactProjectionApplication = Depends(
        get_anomaly_recovery_application
    ),
):
    del principal
    correlation_id = CorrelationId(f"recovery-action:{fingerprint}")
    return _call(
        lambda: _recovery_action_payload(
            application.query_recovery_preview_link(
                PreviewFingerprint(fingerprint),
                action_key,
                correlation_id,
            )
        ),
        "成功取得 owning Domain Preview 入口",
        correlation_id,
    )


def _context_payload(context):
    projection = context.projection
    return {
        "fingerprint": projection.fingerprint.value,
        "definition_code": projection.definition_code,
        "source_domain": context.source_domain,
        "source_identity": projection.source_identity,
        "source_version": projection.source_version,
        "severity": context.severity,
        "predicate_active": projection.predicate_active,
        "workflow_status": projection.workflow_status.value,
        "workflow_version": projection.workflow_version,
        "domain_blocker_active": context.domain_blocker_active,
        "projection_freshness": context.projection_freshness,
        "root_fact_snapshot": _root_snapshot_payload(context.root_fact_snapshot),
        "occurrence_timeline": [
            _occurrence_payload(item) for item in context.occurrence_timeline
        ],
        "workflow_timeline": [
            _recovery_timeline_payload(item) for item in context.workflow_timeline
        ],
        "available_actions": [
            _recovery_action_payload(item) for item in context.available_actions
        ],
    }


def _call(query, message, correlation):
    try:
        return BaseResponse(data=query(), message=message)
    except RootFactProjectionError as error:
        raise _http_error(error) from error
    except (TypeError, ValueError, KeyError) as error:
        raise _contract_error(correlation) from error


def _call_maintenance(command, message):
    try:
        return BaseResponse(data=command(), message=message)
    except (AnomalyMaintenanceError, RootFactProjectionError) as error:
        raise _http_error(error) from error


_TIMELINE_ACTIONS = {"claim", "resolve", "reopen", "auto_resolve"}


def _root_snapshot_payload(snapshot) -> AnomalyRootFactSnapshotView:
    if not isinstance(snapshot, dict):
        raise ValueError("root snapshot must be an object")
    required = {
        "occurred_at",
        "source_version",
        "finance_import_row_id",
        "finance_import_batch_id",
        "amount_delta_ntd",
        "root_condition_active",
        "integrity_blocker_active",
        "affected_order_identities",
        "affected_obligation_identities",
        "domain_blockers",
        "reason_codes",
    }
    redacted_internal = {"definition_code", "recovery_bindings"}
    optional_public = {"original_refund_ledger_entry_id"}
    if not required.issubset(snapshot) or set(snapshot) - (required | redacted_internal | optional_public):
        raise ValueError("root snapshot fields are not public")
    order_ids = snapshot["affected_order_identities"]
    obligation_ids = snapshot["affected_obligation_identities"]
    blockers = snapshot["domain_blockers"]
    reasons = snapshot["reason_codes"]
    if not isinstance(order_ids, list) or not isinstance(obligation_ids, list):
        raise ValueError("root snapshot identity collections are invalid")
    if not all(_safe_identity(item) for item in order_ids + obligation_ids):
        raise ValueError("root snapshot identities are invalid")
    if not isinstance(blockers, list) or not isinstance(reasons, list):
        raise ValueError("root snapshot code collections are invalid")
    if not all(_safe_code(item) for item in blockers + reasons):
        raise ValueError("root snapshot codes are invalid")
    return AnomalyRootFactSnapshotView(
        occurred_at=snapshot["occurred_at"],
        source_version=snapshot["source_version"],
        finance_import_row_identity=_identity_value(snapshot["finance_import_row_id"]),
        finance_import_batch_identity=_identity_value(snapshot["finance_import_batch_id"]),
        original_refund_ledger_entry_identity=(
            None
            if snapshot.get("original_refund_ledger_entry_id") is None
            else _identity_value(snapshot["original_refund_ledger_entry_id"])
        ),
        amount_delta_ntd=snapshot["amount_delta_ntd"],
        root_condition_active=snapshot["root_condition_active"],
        integrity_blocker_active=snapshot["integrity_blocker_active"],
        affected_order_identities=list(order_ids),
        affected_obligation_identities=list(obligation_ids),
        domain_blockers=list(blockers),
        reason_codes=list(reasons),
    )


def _occurrence_payload(occurrence) -> FinanceOccurrenceView:
    snapshot = occurrence.bounded_snapshot
    if not isinstance(snapshot, dict):
        raise ValueError("occurrence snapshot must be an object")
    field_builders = {
        "amount_delta_ntd": _money_field,
        "domain_blockers": _code_list_field,
        "integrity_blocker_active": _boolean_field,
        "reason_codes": _code_list_field,
        "root_condition_active": _boolean_field,
        "affected_order_identities": _identity_list_field,
        "affected_obligation_identities": _identity_list_field,
        "occurred_at": _date_field,
        "source_version": _integer_field,
        "source_identity": _identity_field,
        "finance_import_row_id": _identity_field,
        "finance_import_batch_id": _identity_field,
        "original_refund_ledger_entry_id": _identity_field,
    }
    internal_keys = {"definition_code", "recovery_bindings"}
    unknown_keys = set(snapshot) - set(field_builders) - internal_keys
    if unknown_keys:
        raise ValueError("occurrence snapshot fields are unknown")
    fields = [
        field_builders[key](key, snapshot[key])
        for key in sorted(set(snapshot) - internal_keys)
    ]

    return FinanceOccurrenceView(
        occurrence_fingerprint=occurrence.occurrence_fingerprint.value,
        definition_code=occurrence.definition_code,
        source_event_identity=_identity_value(occurrence.source_event_identity),
        finance_import_row_id=occurrence.finance_import_row_id,
        finance_import_batch_id=occurrence.finance_import_batch_id,
        source_version=occurrence.source_version,
        occurred_at=_materialize(occurrence.occurred_at),
        bounded_snapshot=AnomalyDisplaySnapshotView(
            redaction_version="anomaly-safe.v1",
            definition_code=occurrence.definition_code,
            fields=fields,
        ),
    )


def _recovery_timeline_payload(event) -> AnomalyTimelineEventView:
    raw = _materialize(event)
    if not isinstance(raw, dict) or set(raw) != {
        "action",
        "expected_workflow_version",
        "resulting_workflow_version",
        "actor",
        "reason",
        "correlation_id",
        "created_at",
    }:
        raise ValueError("workflow timeline fields are invalid")
    action = raw["action"]
    if action not in _TIMELINE_ACTIONS:
        raise ValueError("workflow timeline action is unknown")
    actor = str(raw["actor"]).strip()
    if not actor:
        raise ValueError("workflow timeline actor is invalid")
    correlation_id = str(raw["correlation_id"]).strip()
    if not correlation_id or len(correlation_id) > 191:
        raise ValueError("workflow timeline correlation is invalid")
    return AnomalyTimelineEventView(
        action=action,
        expected_workflow_version=raw["expected_workflow_version"],
        resulting_workflow_version=raw["resulting_workflow_version"],
        actor=f"{actor[:1]}***",
        reason=_safe_reason(action),
        correlation_id=correlation_id,
        created_at=raw["created_at"],
    )


def _recovery_action_payload(action) -> RecoveryActionView:
    raw = _materialize(action)
    if not isinstance(raw, dict):
        raise ValueError("recovery action is invalid")
    expected_fields = {
        "action_key",
        "label",
        "owning_domain",
        "form_schema_key",
        "source_binding_keys",
        "source_bindings",
        "required_operator_inputs",
        "preview_operation",
        "apply_operation",
        "required_capability",
        "completion_predicate",
        "action_contract_version",
        "requires_preview",
    }
    if set(raw) != expected_fields:
        raise ValueError("recovery action fields are invalid")
    source_keys = raw.get("source_binding_keys")
    bindings = raw.get("source_bindings")
    if not isinstance(source_keys, (tuple, list)) or not all(
        isinstance(item, str) and item.strip() for item in source_keys
    ):
        raise ValueError("recovery action binding keys are invalid")
    if len(set(source_keys)) != len(source_keys):
        raise ValueError("recovery action binding keys are duplicated")
    if not isinstance(bindings, dict) or set(bindings) != set(source_keys):
        raise ValueError("recovery action bindings are incomplete")
    return RecoveryActionView.model_validate({
        "action_key": raw.get("action_key"),
        "label": raw.get("label"),
        "owning_domain": raw.get("owning_domain"),
        "form_schema_key": raw.get("form_schema_key"),
        "source_binding_keys": list(source_keys),
        "source_bindings": [
            _source_binding_payload(key, bindings[key]) for key in source_keys
        ],
        "required_operator_inputs": list(raw.get("required_operator_inputs", ())),
        "preview_operation": raw.get("preview_operation"),
        "apply_operation": raw.get("apply_operation"),
        "required_capability": raw.get("required_capability"),
        "completion_predicate": raw.get("completion_predicate"),
        "action_contract_version": raw.get("action_contract_version"),
        "requires_preview": raw.get("requires_preview"),
    })


def _source_binding_payload(key: str, value: object) -> AnomalySourceBindingView:
    if isinstance(value, bool):
        raise ValueError("recovery binding value is invalid")
    if key.endswith("_version") or key == "source_version":
        if not isinstance(value, int):
            raise ValueError("recovery binding version is invalid")
        if value < 0:
            raise ValueError("recovery binding version is invalid")
        return {"kind": "version", "key": key, "value": value}
    if isinstance(value, (str, int)):
        normalized = str(value).strip()
        if _safe_identity(normalized):
            return {"kind": "identity", "key": key, "value": normalized}
    raise ValueError("recovery binding identity is invalid")


def _identity_value(value: object) -> str:
    direct_value = getattr(value, "value", value)
    materialized = _materialize(direct_value)
    if isinstance(materialized, bool):
        raise ValueError("identity is invalid")
    if isinstance(materialized, int):
        if materialized <= 0:
            raise ValueError("identity is invalid")
        materialized = str(materialized)
    if not _safe_identity(materialized):
        raise ValueError("identity is invalid")
    return materialized


def _identity_field(key: str, value: object) -> dict[str, object]:
    return {"kind": "identity", "key": key, "value": _identity_value(value)}


def _integer_field(key: str, value: object) -> dict[str, object]:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("integer evidence is invalid")
    return {"kind": "integer", "key": key, "value": value}


def _money_field(key: str, value: object) -> dict[str, object]:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("money evidence is invalid")
    return {"kind": "money_ntd", "key": key, "value": value}


def _boolean_field(key: str, value: object) -> dict[str, object]:
    if not isinstance(value, bool):
        raise ValueError("boolean evidence is invalid")
    return {"kind": "boolean", "key": key, "value": value}


def _date_field(key: str, value: object) -> dict[str, object]:
    materialized = _materialize(value)
    if not isinstance(materialized, str) or not materialized.strip():
        raise ValueError("date evidence is invalid")
    return {"kind": "datetime", "key": key, "value": materialized}


def _code_list_field(key: str, value: object) -> dict[str, object]:
    if not isinstance(value, list) or not all(_safe_code(item) for item in value):
        raise ValueError("code-list evidence is invalid")
    return {"kind": "code_list", "key": key, "value": list(value)}


def _identity_list_field(key: str, value: object) -> dict[str, object]:
    if not isinstance(value, list) or not all(_safe_identity(item) for item in value):
        raise ValueError("identity-list evidence is invalid")
    return {"kind": "identity_list", "key": key, "value": list(value)}


def _safe_identity(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip()) and len(value) <= 191


def _safe_code(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip()) and len(value) <= 191 and all(
        char.isalnum() or char in "_.:-" for char in value
    )


def _safe_reason(action: str) -> str:
    return {
        "claim": "異常已進入人工確認流程。",
        "resolve": "人工處理進度已更新；不代表根事實已修正。",
        "reopen": "根條件仍存在，異常已重新開啟。",
        "auto_resolve": "根條件已由來源投影解除。",
    }[action]


def _contract_error(correlation):
    return HTTPException(
        status_code=422,
        detail={
            "error": {
                "category": "validation",
                "code": "anomaly_projection_data_integrity_violation",
                "message": "異常公開投影未通過驗證。",
                "correlation_id": correlation.value,
                "field_errors": [],
                "domain_blockers": [],
                "retryable": False,
                "current_version": None,
            }
        },
    )


def _scan_result_payload(result):
    return {
        "definition_code": result.definition_code,
        "scanned_count": result.scanned_count,
        "active_count": result.active_count,
        "inactive_count": result.inactive_count,
        "next_after_source_id": result.next_after_source_id,
        "completed": result.completed,
    }


def _retry_result_payload(result):
    return {
        "projector_identity": result.projector_identity,
        "requeued_event_ids": list(result.requeued_event_ids),
        "requeued_count": result.requeued_count,
    }


def _correlation_id(value, fallback):
    return CorrelationId(value.strip() if value and value.strip() else fallback)


def _http_error(error):
    status = {
        ErrorCategory.NOT_FOUND: 404,
        ErrorCategory.VALIDATION: 422,
        ErrorCategory.CONFLICT: 409,
        ErrorCategory.UNAVAILABLE: 503,
    }.get(error.error.category, 500)
    headers = {"Retry-After": "1"} if error.error.retryable else None
    return HTTPException(
        status_code=status,
        detail={"error": _materialize(error.error)},
        headers=headers,
    )


def _materialize(value):
    if isinstance(value, (PreviewFingerprint, CorrelationId)):
        return value.value
    if isinstance(value, ExpectedVersion):
        return value.value
    if is_dataclass(value) and not isinstance(value, type):
        return {
            item.name: _materialize(getattr(value, item.name))
            for item in fields(value)
        }
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (date, datetime, time)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _materialize(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_materialize(item) for item in value]
    return value


__all__ = ["router"]
