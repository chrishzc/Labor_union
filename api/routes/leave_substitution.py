"""
File: leave_substitution.py
Description: 提供正式請假代班assignment query、預覽、套用與已受理待辦收據。"""

from __future__ import annotations

from dataclasses import fields, is_dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Path
from pymysql.err import OperationalError

from api.dependencies.admin_auth import require_system_admin
from api.dependencies.leave_substitution import (
    LeaveSubstitutionApplication,
    get_leave_substitution_application,
)
from api.schemas.base import BaseResponse
from api.schemas.leave_substitution import (
    LeaveAssignmentSummaryView,
    LeaveSubstitutionApplyBody,
    LeaveSubstitutionPreviewBody,
    LeaveSubstitutionPreviewView,
    LeaveSubstitutionReceiptView,
    SubstitutionPayablesLineageView,
)
from subsystems.access.authentication_session import AdminPrincipal
from shared_kernel.errors import ErrorCategory, TypedError
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.identities import (
    ActorContext,
    CorrelationId,
    ExpectedVersion,
    IdempotencyKey,
)
from subsystems.scheduling.leave_substitution_workflow import (
    LeaveSubstitutionApplyRequest,
    LinkedLeaveRequestIntent,
    LeaveSubstitutionPreviewRequest,
    LeaveSubstitutionWorkflowError,
)


router = APIRouter(prefix="/api/v1/orders", tags=["Leave Substitution"])
_RETRYABLE_MYSQL_CODES = frozenset({1205, 1213})


@router.get(
    "/{case_no}/leave-substitution/assignments",
    response_model=BaseResponse[list[LeaveAssignmentSummaryView]],
)
def list_leave_assignments(
    case_no: str = Path(..., min_length=1, max_length=50),
    principal: AdminPrincipal = Depends(require_system_admin),
    application: LeaveSubstitutionApplication = Depends(
        get_leave_substitution_application
    ),
):
    del principal
    assignments = application.list_effective_assignments(case_no)
    return BaseResponse(
        data=[
            {
                "assignment_id": row["id"],
                "staff_id": row["staff_id"],
                "assigned_start_date": row["assigned_start_date"],
                "assigned_end_date": row["assigned_end_date"],
                "official_schedules": [
                    {
                        "schedule_id": schedule["schedule_id"],
                        "work_date": schedule["work_date"],
                    }
                    for schedule in row["official_schedules"]
                ],
            }
            for row in assignments
        ],
        message="成功取得請假與代班正式服務指派",
    )


@router.get(
    "/{case_no}/leave-substitution/{batch_key}/payables-lineage",
    response_model=BaseResponse[SubstitutionPayablesLineageView],
)
def query_substitution_payables_lineage(
    case_no: str = Path(..., min_length=1, max_length=50),
    batch_key: str = Path(..., min_length=1, max_length=191),
    principal: AdminPrincipal = Depends(require_system_admin),
    application: LeaveSubstitutionApplication = Depends(
        get_leave_substitution_application
    ),
):
    del principal
    # Keep the transport correlation within the shared 191-character identity bound;
    # case/batch are already carried as validated route parameters and SQL bindings.
    correlation = CorrelationId("leave-substitution-payables-lineage")
    return _call_endpoint(
        lambda: _materialize(application.query_payables_lineage(case_no, batch_key)),
        "成功取得代班至薪資與應付款的版本化血緣",
        correlation,
    )


@router.post(
    "/{case_no}/leave-substitution/preview",
    response_model=BaseResponse[LeaveSubstitutionPreviewView],
)
def preview_leave_substitution(
    body: LeaveSubstitutionPreviewBody,
    case_no: str = Path(..., min_length=1, max_length=50),
    correlation_id: Annotated[
        str,
        Header(alias="X-Correlation-ID", min_length=1, max_length=191),
    ] = "leave-substitution-preview",
    principal: AdminPrincipal = Depends(require_system_admin),
    application: LeaveSubstitutionApplication = Depends(
        get_leave_substitution_application
    ),
):
    del principal
    identity = CorrelationId(correlation_id)
    return _call_endpoint(
        lambda: _preview_command(application, case_no, body, identity),
        "成功產生請假與代班預覽",
        identity,
    )


@router.post(
    "/{case_no}/leave-substitution/apply",
    response_model=BaseResponse[LeaveSubstitutionReceiptView],
)
# FastAPI requires the complete command contract here for OpenAPI generation.
def apply_leave_substitution(
    body: LeaveSubstitutionApplyBody,
    case_no: str = Path(..., min_length=1, max_length=50),
    idempotency_key: Annotated[
        str,
        Header(alias="Idempotency-Key", min_length=1, max_length=191),
    ] = ...,
    correlation_id: Annotated[
        str,
        Header(alias="X-Correlation-ID", min_length=1, max_length=191),
    ] = ...,
    principal: AdminPrincipal = Depends(require_system_admin),
    application: LeaveSubstitutionApplication = Depends(
        get_leave_substitution_application
    ),
):
    identity = CorrelationId(correlation_id)
    return _call_endpoint(
        lambda: _apply_command(
            application,
            case_no,
            body,
            idempotency_key,
            identity,
            principal,
        ),
        "成功套用請假與代班處理",
        identity,
    )


def _preview_command(application, case_no, body, correlation_id):
    request = LeaveSubstitutionPreviewRequest(
        case_no,
        body.to_intent(),
        correlation_id,
        _linked_intent(body),
    )
    return _preview_payload(application.preview(request))


def _apply_command(application, case_no, body, key, correlation_id, principal):
    request = _apply_request(
        case_no,
        body,
        key,
        correlation_id,
        principal,
    )
    return _receipt_payload(application.apply(request))


def _apply_request(case_no, body, key, correlation_id, principal):
    return LeaveSubstitutionApplyRequest(
        case_no,
        body.to_intent(),
        ExpectedVersion(body.expected_order_version),
        ExpectedVersion(body.expected_scheduling_version),
        ExpectedVersion(body.expected_client_finance_version),
        ExpectedVersion(body.expected_payroll_version),
        PreviewFingerprint(body.preview_fingerprint),
        IdempotencyKey(key),
        ActorContext(str(principal.username or "").strip()),
        body.reason,
        correlation_id,
        _linked_intent(body),
    )


def _preview_payload(preview):
    scheduling = preview.candidate.scheduling
    return {
        "case_no": scheduling.case_no,
        "order_version": preview.order_version,
        "scheduling_version": preview.scheduling_version,
        "scheduling_generation": scheduling.generation_number,
        "client_finance_version": preview.client_finance_version,
        "payroll_version": preview.payroll_version,
        "cancelled_assignment_ids": scheduling.cancelled_assignment_ids,
        "assignments": [_assignment_payload(item) for item in scheduling.assignments],
        "outcomes": _materialize(preview.candidate.outcomes),
        "client_finance_impact": _impact_payload(preview.client_finance_impact),
        "payroll_impact": _impact_payload(preview.payroll_impact),
        "orders_impact": _impact_payload(preview.orders_impact),
        "calendar_candidate": _materialize(preview.calendar_candidate),
        "apply_readiness": _materialize(preview.apply_readiness),
        "linked_request": _linked_payload(preview.linked_request),
        "preview_fingerprint": preview.fingerprint.value,
    }


def _receipt_payload(receipt):
    return {
        "batch_key": receipt.batch_key,
        "case_no": receipt.case_no,
        "order_version": receipt.order_version,
        "scheduling_generation": receipt.scheduling_generation,
        "scheduling_version": receipt.scheduling_version,
        "client_finance_version": receipt.client_finance_version,
        "payroll_version": receipt.payroll_version,
        "outcome_event_ids": list(receipt.outcome_event_ids),
        "preview_fingerprint": receipt.preview_fingerprint.value,
        "linked_request": _linked_payload(receipt.linked_request),
    }


def _linked_intent(body):
    if body.leave_request_id is None:
        return None
    return LinkedLeaveRequestIntent(
        body.leave_request_id,
        body.expected_leave_request_version,
    )


def _linked_payload(linked):
    if linked is None:
        return None
    return {
        "request_id": linked.request_id,
        "expected_version": linked.expected_version,
        "resolved_version": linked.resolved_version,
        "status": linked.status,
        "receipt_key": linked.receipt_key,
        "notification_intent": linked.notification_intent,
    }


def _impact_payload(impact):
    return {
        "expected_version": impact.expected_version,
        "resulting_version": impact.resulting_version,
        "fingerprint": impact.fingerprint.value,
        "blockers": list(impact.blockers),
    }


def _assignment_payload(assignment):
    return {
        "candidate_key": assignment.candidate_key,
        "staff_id": assignment.staff_id,
        "sequence": assignment.sequence,
        "assigned_start_date": assignment.assigned_start_date,
        "assigned_end_date": assignment.assigned_end_date,
        "official_service_dates": assignment.service_dates,
        "actual_hours": assignment.actual_hours,
        "lineage_source_assignment_ids": assignment.lineage_source_assignment_ids,
    }


def _call_endpoint(command, message, correlation_id):
    try:
        return BaseResponse(data=command(), message=message)
    except LeaveSubstitutionWorkflowError as error:
        _raise_typed_error(error.error)
    except OperationalError as error:
        _raise_mysql_error(error, correlation_id)
    except (TypeError, ValueError) as error:
        _raise_request_error(error, correlation_id)
    except HTTPException:
        raise
    except Exception as error:
        raise _internal_error(correlation_id) from error


def _raise_typed_error(error: TypedError) -> None:
    status_code = {
        ErrorCategory.VALIDATION: 422,
        ErrorCategory.FORBIDDEN: 403,
        ErrorCategory.NOT_FOUND: 404,
        ErrorCategory.DOMAIN_BLOCKED: 409,
        ErrorCategory.CONFLICT: 409,
        ErrorCategory.IDEMPOTENCY_MISMATCH: 409,
        ErrorCategory.UNAVAILABLE: 503,
        ErrorCategory.INTERNAL: 500,
    }[error.category]
    headers = {"Retry-After": "1"} if error.retryable else None
    raise _http_error(status_code, error, headers=headers)


def _raise_mysql_error(error, correlation_id):
    mysql_code = int(error.args[0]) if error.args else 0
    if mysql_code in _RETRYABLE_MYSQL_CODES:
        typed = TypedError(
            ErrorCategory.UNAVAILABLE,
            "leave_substitution_transaction_temporarily_unavailable",
            "Retry with the same idempotency key.",
            correlation_id,
            retryable=True,
        )
        raise _http_error(503, typed, headers={"Retry-After": "1"}) from error
    raise _http_error(500, _database_error(correlation_id)) from error


def _raise_request_error(error, correlation_id):
    code = str(error)
    category = ErrorCategory.CONFLICT if "conflict" in code else ErrorCategory.VALIDATION
    status_code = 409 if category is ErrorCategory.CONFLICT else 422
    raise _http_error(
        status_code,
        TypedError(
            category,
            code,
            "Leave/substitution request was rejected.",
            correlation_id,
        ),
    ) from error


def _database_error(correlation_id):
    return TypedError(
        ErrorCategory.INTERNAL,
        "leave_substitution_database_error",
        "Leave/substitution persistence failed.",
        correlation_id,
    )


def _internal_error(correlation_id):
    return _http_error(
        500,
        TypedError(
            ErrorCategory.INTERNAL,
            "leave_substitution_internal_error",
            "Leave/substitution processing failed.",
            correlation_id,
        ),
    )


def _http_error(status_code, error, *, headers=None):
    return HTTPException(
        status_code=status_code,
        detail={"error": _materialize(error)},
        headers=headers,
    )


# One recursive transformer keeps typed HTTP payloads deterministic.
def _materialize(value):
    if hasattr(value, "value") and value.__class__.__module__.startswith(
        "shared_kernel"
    ):
        return value.value
    if is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: _materialize(getattr(value, field.name))
            for field in fields(value)
        }
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _materialize(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_materialize(item) for item in value]
    return value
