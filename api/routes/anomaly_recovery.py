"""
File: anomaly_recovery.py
Description: 提供去敏異常根事實查詢與重掃描 API。
"""

from __future__ import annotations

from dataclasses import fields, is_dataclass
from datetime import date, datetime, time, timezone
from enum import Enum

from fastapi import APIRouter, Depends, Header, HTTPException, Path, Query

from api.dependencies.admin_auth import require_system_admin
from api.dependencies.anomaly_recovery import get_current_anomaly_issue_repository
from api.schemas.anomaly_recovery import (
    AnomalyRecoveryContextView,
    CurrentAnomalyRecoveryContextView,
    RecoveryActionView,
)
from api.schemas.anomaly_registry import (
    AnomalyDisplaySnapshotView,
    AnomalySourceBindingView,
)
from api.routes.anomaly_registry import _evidence_payload
from api.schemas.base import BaseResponse
from subsystems.access.authentication_session import AdminPrincipal
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.identities import (
    CorrelationId,
    ExpectedVersion,
)

router = APIRouter(prefix="/api/v1/anomaly-recovery", tags=["Anomalies"])
_PROJECTOR_PATTERN = (
    r"^(government_overpayment|client_over_refund_recovery|"
    r"staff_overpayment_recovery)$"
)
_CURRENT_DEFINITION_CODE = "LINE-006"


# The typed HTTP signature remains explicit so FastAPI documents every boundary.
@router.post(
    "/definitions/{definition_code}/scan",
    response_model=None,
)
def scan_anomaly_definition(
    definition_code: str = Path(..., min_length=1, max_length=191),
    principal: AdminPrincipal = Depends(require_system_admin),
):
    del principal, definition_code
    _raise_legacy_maintenance_retired(
        "anomaly_definition_scan_retired",
        "POST /api/v1/anomaly-recovery/definitions/{definition_code}/scan",
        "Global durable anomaly.recheck job with an owner-composed bounded detector",
    )


# The typed HTTP signature remains explicit so FastAPI documents every boundary.
@router.post(
    "/projector/retry",
    response_model=None,
)
def retry_anomaly_projector(
    principal: AdminPrincipal = Depends(require_system_admin),
):
    del principal
    _raise_legacy_maintenance_retired(
        "anomaly_projector_retry_retired",
        "POST /api/v1/anomaly-recovery/projector/retry",
        "Global durable-job retry/supersede mechanism",
    )


@router.get("/projector/dead-letters", include_in_schema=False)
def query_projector_dead_letters(
    maximum_items: int = Query(default=50, ge=1, le=100),
    principal: AdminPrincipal = Depends(require_system_admin),
):
    del maximum_items, principal
    _raise_projector_dead_letter_retired("projector-dead-letter-query")


@router.post(
    "/projector/dead-letters/{projector_identity}/{event_id}/retry/preview",
    include_in_schema=False,
)
def preview_projector_dead_letter_retry(
    projector_identity: str = Path(..., pattern=_PROJECTOR_PATTERN),
    event_id: int = Path(..., gt=0),
    principal: AdminPrincipal = Depends(require_system_admin),
):
    del principal
    _raise_projector_dead_letter_retired(
        f"projector-dead-letter-preview:{projector_identity}:{event_id}"
    )


@router.post(
    "/projector/dead-letters/{projector_identity}/{event_id}/retry/apply",
    include_in_schema=False,
)
def apply_projector_dead_letter_retry(
    projector_identity: str = Path(..., pattern=_PROJECTOR_PATTERN),
    event_id: int = Path(..., gt=0),
    correlation_header: str | None = Header(default=None, alias="X-Correlation-ID"),
    principal: AdminPrincipal = Depends(require_system_admin),
):
    correlation = _correlation_id(
        correlation_header if isinstance(correlation_header, str) else None,
        f"projector-dead-letter-retry:{projector_identity}:{event_id}",
    )
    del principal
    _raise_projector_dead_letter_retired(correlation.value)


@router.post(
    "/projector/dead-letters/{projector_identity}/{event_id}/supersede/preview",
    include_in_schema=False,
)
def preview_projector_dead_letter_supersede(
    projector_identity: str = Path(..., pattern=_PROJECTOR_PATTERN),
    event_id: int = Path(..., gt=0),
    principal: AdminPrincipal = Depends(require_system_admin),
):
    del principal
    _raise_projector_dead_letter_retired(
        f"projector-dead-letter-supersede-preview:{projector_identity}:{event_id}"
    )


@router.post(
    "/projector/dead-letters/{projector_identity}/{event_id}/supersede/apply",
    include_in_schema=False,
)
def apply_projector_dead_letter_supersede(
    projector_identity: str = Path(..., pattern=_PROJECTOR_PATTERN),
    event_id: int = Path(..., gt=0),
    correlation_header: str | None = Header(default=None, alias="X-Correlation-ID"),
    principal: AdminPrincipal = Depends(require_system_admin),
):
    correlation = _correlation_id(
        correlation_header if isinstance(correlation_header, str) else None,
        f"projector-dead-letter-supersede:{projector_identity}:{event_id}",
    )
    del principal
    _raise_projector_dead_letter_retired(correlation.value)


@router.get(
    "/{issue_key}",
    response_model=BaseResponse[CurrentAnomalyRecoveryContextView],
    include_in_schema=False,
)
def query_recovery_context(
    issue_key: str = Path(..., pattern=r"^(?:ci_[0-9a-f]{64}|[0-9a-f]{64})$"),
    principal: AdminPrincipal = Depends(require_system_admin),
    repository = Depends(
        get_current_anomaly_issue_repository
    ),
):
    del principal
    correlation_id = CorrelationId(f"anomaly-recovery:{issue_key}")
    _reject_legacy_fingerprint(issue_key, correlation_id)
    return _call_current(
        lambda: _current_context_payload(repository.query_current(issue_key)),
        "成功取得目前異常資訊",
        correlation_id,
    )


@router.get(
    "/{issue_key}/actions/{action_key}",
    response_model=BaseResponse[RecoveryActionView],
)
def query_recovery_preview_link(
    issue_key: str = Path(..., pattern=r"^(?:ci_[0-9a-f]{64}|[0-9a-f]{64})$"),
    action_key: str = Path(..., min_length=1, max_length=191),
    principal: AdminPrincipal = Depends(require_system_admin),
    repository = Depends(
        get_current_anomaly_issue_repository
    ),
):
    del principal
    correlation_id = CorrelationId(f"recovery-action:{issue_key}")
    _reject_legacy_fingerprint(issue_key, correlation_id)
    def _query_action():
        context = _current_context_payload(repository.query_current(issue_key))
        for action in context["available_actions"]:
            if action["action_key"] == action_key:
                return action
        raise ValueError("recovery_action_not_available")
    return _call_current(
        _query_action,
        "成功取得 owning Domain Preview 入口",
        correlation_id,
    )


def _current_context_payload(projection):
    if projection is None:
        raise ValueError("anomaly_not_found")
    candidate = projection.candidate
    if candidate.definition_code != _CURRENT_DEFINITION_CODE:
        raise ValueError("anomaly_not_found")
    details = dict(candidate.details)
    if not isinstance(details, dict):
        raise ValueError("anomaly_projection_data_integrity_violation")
    raw_actions = details.pop("available_actions", ()) if isinstance(details, dict) else ()
    if not isinstance(raw_actions, (tuple, list)):
        raise ValueError("anomaly_projection_data_integrity_violation")
    # Never expose the persisted JSON mapping.  Only the closed, redacted
    # display projection crosses the HTTP boundary.
    detail_snapshot = _current_display_snapshot(candidate.definition_code, details)
    subject_snapshot = _current_display_snapshot(
        candidate.definition_code,
        candidate.subject_identity,
    )
    return {
        "issue_key": candidate.issue_key,
        "definition_code": candidate.definition_code,
        "owner_domain": candidate.owner_domain,
        "owner_root_type": candidate.owner_root_type,
        "subject": subject_snapshot,
        "owner_snapshot_token": projection.owner_snapshot_token,
        "owner_version": candidate.owner_version,
        "severity": candidate.severity,
        "blocking": candidate.blocking,
        "details_version": projection.details_version,
        "details": detail_snapshot,
        "episode_started_at": projection.episode_started_at,
        "last_verified_at": projection.last_verified_at,
        "available_actions": [_recovery_action_payload(item) for item in raw_actions],
    }


def _current_display_snapshot(definition_code, values):
    if values is None:
        raise ValueError("anomaly_projection_data_integrity_violation")
    if not isinstance(values, dict):
        raise ValueError("anomaly_projection_data_integrity_violation")
    return AnomalyDisplaySnapshotView(
        redaction_version="anomaly-safe.v1",
        definition_code=definition_code,
        fields=[_current_evidence_payload(key, values[key]) for key in sorted(values)],
    )


def _current_evidence_payload(key: str, value: object) -> dict[str, object]:
    """Add only current subject/detail scalar types absent from legacy views."""

    if key in {"generation", "integrity_revision"}:
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError("anomaly_projection_data_integrity_violation")
        return {"kind": "integer", "key": key, "value": value}
    if key in {"applicable_source_count", "unresolved_source_count"}:
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError("anomaly_projection_data_integrity_violation")
        return {"kind": "integer", "key": key, "value": value}
    if key == "unresolved_reason_codes":
        if not isinstance(value, (tuple, list)) or any(
            not isinstance(item, str) or not item for item in value
        ):
            raise ValueError("anomaly_projection_data_integrity_violation")
        return {"kind": "code_list", "key": key, "value": list(value)}
    if key == "subject_type":
        if not _safe_code(value):
            raise ValueError("anomaly_projection_data_integrity_violation")
        return {"kind": "code", "key": key, "value": value}
    if key == "code":
        if not _safe_code(value):
            raise ValueError("anomaly_projection_data_integrity_violation")
        return {"kind": "code", "key": key, "value": value}
    return _evidence_payload(key, value)


def _call_current(query, message, correlation):
    try:
        return BaseResponse(data=query(), message=message)
    except ValueError as error:
        if str(error) == "anomaly_not_found":
            raise _current_not_found(correlation) from error
        if str(error) == "recovery_action_not_available":
            raise HTTPException(
                status_code=422,
                detail={
                    "error": {
                        "category": "validation",
                        "code": "recovery_action_not_available",
                        "message": "此 current issue 沒有要求的修復入口。",
                        "correlation_id": correlation.value,
                        "field_errors": [],
                        "domain_blockers": [],
                        "retryable": False,
                        "current_version": None,
                    }
                },
            ) from error
        raise _contract_error(correlation) from error


def _reject_legacy_fingerprint(issue_key: str, correlation: CorrelationId) -> None:
    if issue_key.startswith("ci_"):
        return
    raise HTTPException(
        status_code=410,
        detail={
            "error": {
                "category": "domain_blocked",
                "code": "anomaly_recovery_fingerprint_retired",
                "message": "舊 anomaly fingerprint 已停止 recovery 查詢。",
                "correlation_id": correlation.value,
                "field_errors": [],
                "domain_blockers": [
                    "replacement_identifier:GET /api/v1/anomalies/{issue_key}",
                ],
                "retryable": False,
                "current_version": None,
            }
        },
    )


def _current_not_found(correlation: CorrelationId) -> HTTPException:
    return HTTPException(
        status_code=404,
        detail={
            "error": {
                "category": "not_found",
                "code": "anomaly_not_found",
                "message": "找不到目前仍成立的異常。",
                "correlation_id": correlation.value,
                "field_errors": [],
                "domain_blockers": [],
                "retryable": False,
                "current_version": None,
            }
        },
    )


def _raise_projector_dead_letter_retired(correlation_id: str) -> None:
    """Keep unresolved public legacy URLs fail-closed until the generic replacement exists."""
    raise HTTPException(
        status_code=410,
        detail={
            "error": {
                "category": "domain_blocked",
                "code": "anomaly_projector_dead_letter_endpoint_retired",
                "message": "Projector dead-letter recovery has moved to the Global durable-job contract.",
                "correlation_id": correlation_id,
                "field_errors": [],
                "domain_blockers": [
                    "replacement_identifier:Global durable-job retry/supersede mechanism",
                ],
                "retryable": False,
                "current_version": None,
            }
        },
    )


def _raise_legacy_maintenance_retired(
    code: str,
    route_identity: str,
    replacement: str,
) -> None:
    raise HTTPException(
        status_code=410,
        detail={
            "error": {
                "category": "domain_blocked",
                "code": code,
                "message": "Legacy anomaly maintenance projection has been retired.",
                "correlation_id": "anomaly-maintenance-retired:" + route_identity,
                "field_errors": [],
                "domain_blockers": [
                    f"replacement_identifier:{replacement}",
                    "removal_gate:blocked_external_caller_evidence",
                ],
                "retryable": False,
                "current_version": None,
            }
        },
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


def _safe_identity(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip()) and len(value) <= 191


def _safe_code(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip()) and len(value) <= 191 and all(
        char.isalnum() or char in "_.:-" for char in value
    )


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


def _correlation_id(value, fallback):
    return CorrelationId(value.strip() if value and value.strip() else fallback)


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
