"""
File: anomaly_registry.py
Description: 提供異常清單、owner remediation 詳情、工作流與canonical 投影。
"""

from __future__ import annotations

from dataclasses import fields, is_dataclass
from datetime import date, datetime, time
from enum import Enum
from typing import Mapping

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request
from pymysql.err import OperationalError

from api.dependencies.admin_auth import require_system_admin
from api.dependencies.anomaly_registry import (
    get_anomaly_application,
    get_current_issue_query_application,
)
from api.dependencies.anomaly_recovery import get_current_anomaly_issue_repository
from api.schemas.anomaly_recovery import CurrentAnomalyRecoveryContextView
from api.schemas.anomaly_registry import (
    AnomalyDisplaySnapshotView,
    AnomalySummaryView,
    AnomalyTimelineEventView,
    CurrentAnomalyPageView,
)
from api.schemas.base import BaseResponse
from infrastructure.mysql.anomaly_registry_repository import (
    AnomalyRepositoryUnavailable,
)
from subsystems.access.authentication_session import AdminPrincipal
from shared_kernel.errors import ErrorCategory, TypedError
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.identities import CorrelationId, IdempotencyKey
from subsystems.anomalies.alert_workflow import (
    AnomalyApplication,
    AnomalyWorkflowError,
)
from subsystems.anomalies.current_issue_query import (
    CurrentIssueListRequest,
    CurrentIssueQueryApplication,
)

router = APIRouter(prefix="/api/v1/anomalies", tags=["Anomalies"])

_CURRENT_QUERY_PARAMETERS = frozenset(
    {"definition_code", "owner_domain", "blocking", "limit", "cursor"}
)
_CURRENT_DEFINITION_CODE = "LINE-006"


@router.get("", response_model=BaseResponse[CurrentAnomalyPageView])
def query_anomalies(
    request: Request,
    definition_code: str | None = Query(default=None, min_length=1, max_length=191),
    owner_domain: str | None = Query(default=None, min_length=1, max_length=191),
    blocking: bool | None = Query(default=None),
    limit: int = Query(50, ge=1, le=100),
    cursor: str | None = Query(default=None, min_length=1, max_length=2048),
    principal: AdminPrincipal = Depends(require_system_admin),
    application: CurrentIssueQueryApplication = Depends(
        get_current_issue_query_application
    ),
):
    del principal
    unsupported = sorted(set(request.query_params) - _CURRENT_QUERY_PARAMETERS)
    if unsupported:
        _raise_current_query_error(
            422,
            "anomaly_query_filter_not_allowed",
            "目前異常清單的查詢篩選條件不在允許範圍。",
        )
    try:
        page = application.query(
            CurrentIssueListRequest(
                definition_code=definition_code,
                owner_domain=owner_domain,
                blocking=blocking,
                limit=limit,
                cursor=cursor,
            )
        )
    except ValueError as error:
        code = str(error)
        if code != "anomaly_cursor_invalid":
            code = "anomaly_query_invalid"
        _raise_current_query_error(422, code, "目前異常清單的查詢條件無效。", cause=error)
    except OperationalError as error:
        _raise_current_query_error(
            503,
            "anomaly_query_temporarily_unavailable",
            "目前異常清單暫時無法查詢。",
            retryable=True,
            cause=error,
        )
    # The persistence table may still contain rows from an older repository
    # revision. Those rows are not current public definitions and must not
    # cross the API boundary while historical cleanup remains governed.
    current_items = [
        item for item in page.items if item.definition_code == _CURRENT_DEFINITION_CODE
    ]
    return BaseResponse(
        success=True,
        message="成功取得目前異常清單",
        data={
            "items": [
                {
                    "issue_key": item.issue_key,
                    "definition_code": item.definition_code,
                    "owner_domain": item.owner_domain,
                    "severity": item.severity,
                    "blocking": item.blocking,
                    "episode_started_at": item.episode_started_at,
                    "last_verified_at": item.last_verified_at,
                }
                for item in current_items
            ],
            "next_cursor": page.next_cursor,
        },
    )


def _raise_current_query_error(
    status_code: int,
    code: str,
    message: str,
    *,
    retryable: bool = False,
    cause: Exception | None = None,
) -> None:
    error = HTTPException(
        status_code=status_code,
        detail={
            "error": {
                "category": "unavailable" if status_code == 503 else "validation",
                "code": code,
                "message": message,
                "correlation_id": "anomaly-current-query",
                "field_errors": [],
                "domain_blockers": [],
                "retryable": retryable,
                "current_version": None,
            }
        },
    )
    if cause is None:
        raise error
    raise error from cause


@router.get("/{issue_key}", response_model=BaseResponse[CurrentAnomalyRecoveryContextView])
def query_anomaly_detail(
    issue_key: str = Path(..., pattern=r"^(?:ci_[0-9a-f]{64}|[0-9a-f]{64})$"),
    principal: AdminPrincipal = Depends(require_system_admin),
    repository=Depends(get_current_anomaly_issue_repository),
):
    del principal
    if not issue_key.startswith("ci_"):
        _raise_legacy_registry_retired(
            "anomaly_fingerprint_detail_retired",
            "GET /api/v1/anomalies/{fingerprint}",
            "GET /api/v1/anomalies/{issue_key}",
        )
    # Lazy import avoids coupling the current payload builder back into the
    # legacy registry helpers imported by the recovery router.
    from api.routes.anomaly_recovery import _call_current, _current_context_payload

    correlation_id = CorrelationId(f"anomaly-detail:{issue_key}")
    return _call_current(
        lambda: _current_context_payload(repository.query_current(issue_key)),
        "成功取得目前異常資訊",
        correlation_id,
    )


@router.post(
    "/{fingerprint}/claim",
    response_model=None,
)
def claim_anomaly(
    fingerprint: str = Path(..., pattern=r"^[0-9a-f]{64}$"),
    principal: AdminPrincipal = Depends(require_system_admin),
):
    del fingerprint, principal
    _raise_legacy_registry_retired(
        "anomaly_claim_retired",
        "POST /api/v1/anomalies/{fingerprint}/claim",
        "Owning Domain typed Query/Preview/Apply action",
    )


@router.post(
    "/{fingerprint}/resolve",
    response_model=None,
)
def resolve_anomaly(
    fingerprint: str = Path(..., pattern=r"^[0-9a-f]{64}$"),
    principal: AdminPrincipal = Depends(require_system_admin),
):
    del fingerprint, principal
    _raise_legacy_registry_retired(
        "anomaly_resolve_retired",
        "POST /api/v1/anomalies/{fingerprint}/resolve",
        "Owning Domain typed Query/Preview/Apply action followed by bounded recheck",
    )


def _raise_legacy_registry_retired(
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
                "message": "Legacy anomaly fingerprint workflow has been retired.",
                "correlation_id": "anomaly-registry-retired:" + route_identity,
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


def _summary_payload(summary, *, include_snapshot=True):
    projection = summary.projection
    raw_snapshot = summary.display_snapshot
    display_snapshot = (
        _safe_display_snapshot(
            projection.definition_code,
            summary.display_fields,
            raw_snapshot,
        )
        if include_snapshot
        else None
    )
    return {
        "fingerprint": projection.fingerprint.value,
        "definition_code": projection.definition_code,
        "source_domain": summary.source_domain,
        "source_identity": projection.source_identity,
        "source_version": projection.source_version,
        "severity": summary.severity,
        "predicate_active": projection.predicate_active,
        "workflow_status": projection.workflow_status.value,
        "workflow_version": projection.workflow_version,
        "staff_calendar_navigation": _staff_calendar_navigation(
            projection.definition_code,
            raw_snapshot,
        ),
        **(
            {"display_snapshot": display_snapshot}
            if include_snapshot
            else {"display_snapshot": None}
        ),
    }


def _staff_calendar_navigation(code: str, snapshot: object):
    if not isinstance(snapshot, Mapping):
        return None
    date_field_by_code = {
        "SCHEDULE-001": "holiday_date",
        "SCHEDULE-005": "work_date",
    }
    date_field = date_field_by_code.get(code)
    target_date = snapshot.get(date_field) if date_field is not None else None
    if code == "SCHEDULE-003":
        assignment = snapshot.get("assignment_a")
        target_date = assignment.get("start") if isinstance(assignment, Mapping) else None
    staff_id = snapshot.get("staff_id")
    if isinstance(staff_id, bool) or not isinstance(staff_id, int) or staff_id < 1:
        return None
    if not isinstance(target_date, str):
        return None
    try:
        parsed_date = date.fromisoformat(target_date)
    except ValueError:
        return None
    return {"staff_id": staff_id, "target_date": parsed_date.isoformat()}


def _detail_payload(detail):
    return {
        "summary": _summary_payload(detail.summary, include_snapshot=True),
        "timeline": [_timeline_payload(event) for event in detail.timeline],
        "available_actions": [
            _action_payload(action) for action in detail.available_actions
        ],
    }


_IDENTITY_EVIDENCE_FIELDS = frozenset(
    {
        "assignment_id",
        "assignment_id_a",
        "assignment_id_b",
        "bank_fact_identity",
        "batch_id",
        "case_no",
        "claim_item_id",
        "obligation_identity",
        "overpayment_identity",
        "payable_identity",
        "payout_difference_identity",
        "recovery_identity",
        "review_identity",
        "review_item_id",
        "reversal_bank_fact_identity",
        "source_event_identity",
        "source_receipt_id",
        "staff_id",
        "task_id",
        "underpayment_identity",
        "finance_import_batch_id",
        "finance_import_row_id",
        "original_refund_ledger_entry_id",
    }
)
_TEXT_EVIDENCE_FIELDS = frozenset(
    {
        "line_user_id",
        "case_identity",
        "identifier",
        "staff_name",
        "to_user_id",
    }
)
_DATE_EVIDENCE_FIELDS = frozenset(
    {"due_date", "holiday_date", "original_due_date", "work_date"}
)
_MONEY_EVIDENCE_FIELDS = frozenset(
    {
        "after_amount_ntd",
        "amount",
        "amount_delta_ntd",
        "amount_due_ntd",
        "balance_ntd",
        "bank_amount_ntd",
        "before_amount_ntd",
        "excess_amount_ntd",
        "remaining_reversible_ntd",
    }
)
_INTEGER_EVIDENCE_FIELDS = frozenset(
    {"integrity_revision", "source_row", "version"}
)
_CODE_EVIDENCE_FIELDS = frozenset(
    {
        "action",
        "bank_account_issue",
        "entity_kind",
        "notification_reason",
        "resolution_condition",
        "source_sheet",
    }
)
_CODE_LIST_EVIDENCE_FIELDS = frozenset(
    {"domain_blockers", "drift_fields", "error_codes", "integrity_blockers", "issue_codes", "reason_codes"}
)
_BOOLEAN_EVIDENCE_FIELDS = frozenset({"integrity_blocker_active", "root_condition_active"})
_IDENTITY_LIST_EVIDENCE_FIELDS = frozenset(
    {
        "affected_obligation_identities",
        "affected_order_identities",
        "advance_candidates",
        "candidate_batch_ids",
        "item_outstanding",
        "obligation_identities",
    }
)
_DETAIL_LIST_EVIDENCE_FIELDS = frozenset({"overdue_obligations"})
_IDENTITY_ITEM_KEYS = (
    "advance_identity",
    "advance_id",
    "assignment_identity",
    "assignment_id",
    "batch_identity",
    "batch_id",
    "claim_item_identity",
    "claim_item_id",
    "finance_import_row_identity",
    "obligation_identity",
    "obligation_id",
    "payable_identity",
    "recovery_identity",
)


def _safe_display_snapshot(
    definition_code: str,
    display_fields: object,
    snapshot: object,
) -> AnomalyDisplaySnapshotView:
    """Validate one definition-owned display contract and emit no raw mapping."""
    if not isinstance(display_fields, tuple) or any(
        not isinstance(key, str) or not key for key in display_fields
    ):
        raise ValueError("anomaly_projection_data_integrity_violation")
    if display_fields != tuple(sorted(set(display_fields))):
        raise ValueError("anomaly_projection_data_integrity_violation")
    if snapshot is None:
        if display_fields:
            raise ValueError("anomaly_projection_data_integrity_violation")
        snapshot = {}
    if not isinstance(snapshot, Mapping):
        raise ValueError("anomaly_projection_data_integrity_violation")
    public_snapshot = {
        key: value for key, value in snapshot.items() if key in display_fields
    }
    if set(public_snapshot) != set(display_fields):
        raise ValueError("anomaly_projection_data_integrity_violation")
    unknown = set(snapshot) - set(display_fields)
    if unknown - _private_navigation_fields(definition_code):
        raise ValueError("anomaly_projection_data_integrity_violation")
    return AnomalyDisplaySnapshotView(
        redaction_version="canonical.v1",
        definition_code=definition_code,
        fields=[
            _evidence_payload(key, public_snapshot[key]) for key in display_fields
        ],
    )


def _private_navigation_fields(definition_code: str) -> frozenset[str]:
    if definition_code == "SCHEDULE-003":
        return frozenset({"assignment_a"})
    if definition_code == "finance_import_manual_review":
        return frozenset(
            {
                "definition_code",
                "occurred_at",
                "original_refund_ledger_entry_id",
                "recovery_bindings",
                "source_version",
            }
        )
    if definition_code == "CLIENTREFUND-001":
        return frozenset(
            {
                "definition_code",
                "occurred_at",
                "recovery_bindings",
                "source_version",
            }
        )
    if definition_code in {"RECEIVABLE-001", "CLIENTPAYABLE-001", "RETURN-001"}:
        return frozenset({"account_version"})
    if definition_code in {
        "GOVSUB-006",
        "client_over_refund_recovery_open",
        "staff_overpayment_recovery_open",
    }:
        return frozenset(
            {
                "affected_obligation_identities",
                "affected_order_identities",
                "definition_code",
                "finance_import_batch_id",
                "occurred_at",
                "original_refund_ledger_entry_id",
                "recovery_bindings",
                "source_version",
            }
        )
    return frozenset()


def _evidence_payload(key: str, value: object) -> dict[str, object]:
    if key in _IDENTITY_EVIDENCE_FIELDS:
        return {"kind": "identity", "key": key, "value": _identity(value)}
    if key in _TEXT_EVIDENCE_FIELDS:
        return {"kind": "text", "key": key, "value": _canonical_text_evidence(value)}
    if key in _DATE_EVIDENCE_FIELDS:
        return {"kind": "date", "key": key, "value": _date_value(value)}
    if key in _MONEY_EVIDENCE_FIELDS:
        return {"kind": "money_ntd", "key": key, "value": _integer(value)}
    if key in _INTEGER_EVIDENCE_FIELDS:
        return {"kind": "integer", "key": key, "value": _integer(value)}
    if key in _CODE_EVIDENCE_FIELDS:
        return {"kind": "code", "key": key, "value": _text(value)}
    if key in _CODE_LIST_EVIDENCE_FIELDS:
        return {"kind": "code_list", "key": key, "value": _text_list(value)}
    if key in _IDENTITY_LIST_EVIDENCE_FIELDS:
        return {
            "kind": "identity_list",
            "key": key,
            "value": _identity_list(value),
        }
    if key in _DETAIL_LIST_EVIDENCE_FIELDS:
        return {"kind": "detail_list", "key": key, "value": _text_list(value)}
    if key in _BOOLEAN_EVIDENCE_FIELDS:
        if not isinstance(value, bool):
            raise ValueError("anomaly_projection_data_integrity_violation")
        return {"kind": "boolean", "key": key, "value": value}
    raise ValueError("anomaly_projection_data_integrity_violation")


def _identity(value: object) -> str:
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise ValueError("anomaly_projection_data_integrity_violation")
    if isinstance(value, int) and value <= 0:
        raise ValueError("anomaly_projection_data_integrity_violation")
    rendered = str(value).strip()
    if not rendered or len(rendered) > 191:
        raise ValueError("anomaly_projection_data_integrity_violation")
    return rendered


def _canonical_text_evidence(value: object) -> str:
    return str(value or "").strip() or "—"

def _date_value(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("anomaly_projection_data_integrity_violation")
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError as error:
        raise ValueError("anomaly_projection_data_integrity_violation") from error


def _integer(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("anomaly_projection_data_integrity_violation")
    return value


def _text(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("anomaly_projection_data_integrity_violation")
    rendered = value.strip()
    if not rendered or len(rendered) > 191:
        raise ValueError("anomaly_projection_data_integrity_violation")
    return rendered


def _text_list(value: object) -> list[str]:
    if not isinstance(value, (tuple, list)) or len(value) > 100:
        raise ValueError("anomaly_projection_data_integrity_violation")
    return [_text(item) for item in value]


def _identity_list(value: object) -> list[str]:
    if not isinstance(value, (tuple, list)) or len(value) > 100:
        raise ValueError("anomaly_projection_data_integrity_violation")
    return [_identity_item(item) for item in value]


def _identity_item(value: object) -> str:
    if isinstance(value, Mapping):
        candidates = [key for key in _IDENTITY_ITEM_KEYS if key in value]
        if len(candidates) != 1:
            raise ValueError("anomaly_projection_data_integrity_violation")
        return _identity(value[candidates[0]])
    return _identity(value)


def _timeline_payload(event) -> AnomalyTimelineEventView:
    raw = _materialize(event)
    if not isinstance(raw, Mapping):
        raise ValueError("anomaly_projection_data_integrity_violation")
    required = {
        "action",
        "expected_workflow_version",
        "resulting_workflow_version",
        "actor",
        "reason",
        "correlation_id",
        "created_at",
    }
    if set(raw) != required or raw["action"] not in {
        "claim",
        "resolve",
        "reopen",
        "auto_resolve",
    }:
        raise ValueError("anomaly_projection_data_integrity_violation")
    actor = str(raw["actor"]).strip()
    correlation_id = str(raw["correlation_id"]).strip()
    if not actor or not correlation_id:
        raise ValueError("anomaly_projection_data_integrity_violation")
    return AnomalyTimelineEventView(
        action=raw["action"],
        expected_workflow_version=raw["expected_workflow_version"],
        resulting_workflow_version=raw["resulting_workflow_version"],
        actor=actor,
        reason=str(raw["reason"]).strip(),
        correlation_id=correlation_id,
        created_at=raw["created_at"],
    )


def _safe_timeline_reason(action: str) -> str:
    return {
        "claim": "異常已進入人工確認流程。",
        "resolve": "人工處理進度已更新；不代表根事實已修正。",
        "reopen": "根條件仍存在，異常已重新開啟。",
        "auto_resolve": "根條件已由來源投影解除。",
    }[action]


def _action_payload(action):
    raw = _materialize(action)
    if not isinstance(raw, Mapping):
        raise ValueError("anomaly_projection_data_integrity_violation")
    expected_fields = {
        "action_key",
        "apply_operation",
        "action_contract_version",
        "completion_predicate",
        "form_schema_key",
        "label",
        "owning_domain",
        "preview_operation",
        "required_capability",
        "required_operator_inputs",
        "requires_preview",
        "source_binding_keys",
        "source_bindings",
    }
    if set(raw) != expected_fields:
        raise ValueError("anomaly_projection_data_integrity_violation")
    if not all(
        isinstance(raw.get(key), str) and str(raw[key]).strip()
        for key in (
            "action_key",
            "label",
            "owning_domain",
            "form_schema_key",
            "preview_operation",
            "completion_predicate",
        )
    ):
        raise ValueError("anomaly_projection_data_integrity_violation")
    source_keys = raw.get("source_binding_keys")
    if not isinstance(source_keys, (tuple, list)) or not all(
        isinstance(item, str) and item.strip() for item in source_keys
    ):
        raise ValueError("anomaly_projection_data_integrity_violation")
    source_keys = list(source_keys)
    if source_keys != sorted(set(source_keys)):
        raise ValueError("anomaly_projection_data_integrity_violation")
    operator_inputs = raw.get("required_operator_inputs")
    if not isinstance(operator_inputs, (tuple, list)) or not all(
        isinstance(item, str) and item.strip() for item in operator_inputs
    ):
        raise ValueError("anomaly_projection_data_integrity_violation")
    operator_inputs = list(operator_inputs)
    if operator_inputs != sorted(set(operator_inputs)):
        raise ValueError("anomaly_projection_data_integrity_violation")
    if not isinstance(raw.get("requires_preview"), bool):
        raise ValueError("anomaly_projection_data_integrity_violation")
    contract_version = raw.get("action_contract_version")
    if (
        isinstance(contract_version, bool)
        or not isinstance(contract_version, int)
        or contract_version < 1
    ):
        raise ValueError("anomaly_projection_data_integrity_violation")
    for optional_key in ("apply_operation", "required_capability"):
        optional_value = raw.get(optional_key)
        if optional_value is not None and (
            not isinstance(optional_value, str) or not optional_value.strip()
        ):
            raise ValueError("anomaly_projection_data_integrity_violation")
    bindings = _source_bindings(source_keys, raw.get("source_bindings"))
    return {
        "action_key": raw["action_key"],
        "label": raw["label"],
        "owning_domain": raw["owning_domain"],
        "form_schema_key": raw["form_schema_key"],
        "source_binding_keys": source_keys,
        "source_bindings": bindings,
        "required_operator_inputs": operator_inputs,
        "preview_operation": raw["preview_operation"],
        "apply_operation": raw.get("apply_operation"),
        "required_capability": raw.get("required_capability"),
        "completion_predicate": raw["completion_predicate"],
        "action_contract_version": contract_version,
        "requires_preview": raw["requires_preview"],
    }


_IDENTITY_BINDING_KEYS = frozenset(
    {
        "assignment_id",
        "bank_row_identity",
        "batch_id",
        "case_no",
        "finance_import_row_identity",
        "item_id",
        "matching_identity",
        "obligation_identity",
        "overpayment_identity",
        "recovery_identity",
        "staff_id",
    }
)
_VERSION_BINDING_KEYS = frozenset(
    {
        "account_version",
        "matching_version",
        "overpayment_version",
        "recovery_version",
        "source_version",
        "staff_payables_version",
    }
)


def _source_bindings(
    source_keys: list[str],
    bindings: object,
) -> list[dict[str, object]] | None:
    if bindings is None:
        return None
    if not isinstance(bindings, Mapping) or set(bindings) != set(source_keys):
        raise ValueError("anomaly_projection_data_integrity_violation")
    result = []
    for key in source_keys:
        value = bindings[key]
        if key in _IDENTITY_BINDING_KEYS:
            result.append({"kind": "identity", "key": key, "value": _identity(value)})
        elif key in _VERSION_BINDING_KEYS:
            version = _integer(value)
            if version < 0:
                raise ValueError("anomaly_projection_data_integrity_violation")
            result.append({"kind": "version", "key": key, "value": version})
        else:
            raise ValueError("anomaly_projection_data_integrity_violation")
    return result


def _call(command, message, correlation):
    try:
        return BaseResponse(data=command(), message=message)
    except AnomalyWorkflowError as error:
        _raise_typed(error.error)
    except AnomalyRepositoryUnavailable as error:
        _raise_unavailable(error, correlation)
    except OperationalError as error:
        _raise_mysql(error, correlation)
    except ValueError as error:
        _raise_value_error(error, correlation)
    except HTTPException:
        raise
    except Exception as error:
        raise _internal_error(correlation) from error


def _raise_typed(error: TypedError):
    status = {
        ErrorCategory.NOT_FOUND: 404,
        ErrorCategory.CONFLICT: 409,
        ErrorCategory.VALIDATION: 422,
        ErrorCategory.FORBIDDEN: 403,
        ErrorCategory.DOMAIN_BLOCKED: 409,
        ErrorCategory.IDEMPOTENCY_MISMATCH: 409,
        ErrorCategory.UNAVAILABLE: 503,
        ErrorCategory.INTERNAL: 500,
    }[error.category]
    raise _http_error(status, error)


def _raise_unavailable(error, correlation):
    typed = TypedError(
        ErrorCategory.UNAVAILABLE,
        "projector_unavailable",
        "異常投影暫時無法完成，請沿用相同冪等鍵重試。",
        correlation,
        retryable=True,
    )
    raise _http_error(503, typed, {"Retry-After": "1"}) from error


def _raise_mysql(error, correlation):
    retryable = bool(error.args and int(error.args[0]) in {1205, 1213})
    typed = TypedError(
        ErrorCategory.UNAVAILABLE if retryable else ErrorCategory.INTERNAL,
        "transaction_failed",
        "異常工作流資料庫交易失敗。",
        correlation,
        retryable=retryable,
    )
    headers = {"Retry-After": "1"} if retryable else None
    raise _http_error(503 if retryable else 500, typed, headers) from error


def _raise_value_error(error, correlation):
    code = str(error)
    if code not in {
        "anomaly_not_found",
        "anomaly_definition_not_found",
        "anomaly_projection_data_integrity_violation",
        "anomaly_projection_stale",
        "anomaly_source_fact_invalid",
    }:
        code = "anomaly_projection_data_integrity_violation"
    status = 404 if code == "anomaly_not_found" else 422
    category = ErrorCategory.NOT_FOUND if status == 404 else ErrorCategory.VALIDATION
    typed = TypedError(category, code, "異常資料未通過驗證。", correlation)
    raise _http_error(status, typed) from error


def _internal_error(correlation):
    return _http_error(
        500,
        TypedError(
            ErrorCategory.INTERNAL,
            "transaction_failed",
            "異常工作流交易失敗。",
            correlation,
        ),
    )


def _http_error(status, error, headers=None):
    return HTTPException(
        status_code=status,
        detail={"error": _materialize(error)},
        headers=headers,
    )


# Kept recursive so typed query and workflow payloads share one rule.
def _materialize(value):
    if isinstance(
        value,
        (CorrelationId, IdempotencyKey, PreviewFingerprint),
    ):
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
