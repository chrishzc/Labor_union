"""
File: assignment_plan.py
Description: 提供 Assignment Plan typed Query、Preview 與 Durable Job Apply API。
"""

from __future__ import annotations

from dataclasses import fields, is_dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Path, status
from pydantic import BaseModel, ConfigDict, Field
from pymysql.err import OperationalError, ProgrammingError

from api.dependencies.admin_auth import require_system_admin
from api.dependencies.assignment_plan import (
    AssignmentPlanApplication,
    get_assignment_plan_application,
)
from api.schemas.assignment_plan import (
    AssignmentPlanPreviewView,
    AssignmentPlanQueryView,
    AssignmentPlanReceiptView,
)
from api.schemas.base import BaseResponse
from api.schemas.jobs import JobAcceptedResponse
from api.dependencies.jobs import (
    durable_job_conflict_http_error,
    get_durable_job_application,
    immutable_admin_job_actor,
)
from shared_kernel.durable_job_queue import DurableJobCommand
from domains.scheduling.assignment_plan import (
    AssignmentPlanIntent,
    AssignmentPlanSegmentIntent,
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
from subsystems.scheduling.assignment_plan_workflow import (
    AssignmentPlanApplyRequest,
    AssignmentPlanPreviewRequest,
    AssignmentPlanWorkflowError,
)
from subsystems.jobs.command_application import DurableJobCommandApplication
from subsystems.jobs.contracts import DurableJobCommandConflict


router = APIRouter(prefix="/api/v1/orders", tags=["Assignment Plan"])
_RETRYABLE_MYSQL_CODES = frozenset({1205, 1213})
_SCHEMA_NOT_READY_MYSQL_CODES = frozenset({1054, 1146})


class AssignmentPlanSegmentInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    staff_id: int = Field(gt=0)
    assigned_start_date: date
    assigned_end_date: date
    official_service_dates: tuple[date, ...] = Field(min_length=1)

    def to_domain(self) -> AssignmentPlanSegmentIntent:
        return AssignmentPlanSegmentIntent(
            self.staff_id,
            self.assigned_start_date,
            self.assigned_end_date,
            self.official_service_dates,
        )


class AssignmentPlanPreviewBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    segments: tuple[AssignmentPlanSegmentInput, ...] = Field(
        min_length=1,
        max_length=4,
    )

    def to_intent(self) -> AssignmentPlanIntent:
        return AssignmentPlanIntent(
            tuple(segment.to_domain() for segment in self.segments)
        )


class AssignmentPlanApplyBody(AssignmentPlanPreviewBody):
    expected_order_version: int = Field(ge=0)
    expected_scheduling_version: int = Field(ge=0)
    expected_client_finance_version: int = Field(ge=0)
    expected_payroll_version: int = Field(ge=0)
    preview_fingerprint: str = Field(
        min_length=64,
        max_length=64,
        pattern=r"^[0-9a-f]{64}$",
    )
    reason: str = Field(min_length=1, max_length=500)


@router.get(
    "/{case_no}/assignment-plan",
    response_model=BaseResponse[AssignmentPlanQueryView],
)
def query_assignment_plan(
    case_no: str = Path(..., min_length=1, max_length=50),
    principal: AdminPrincipal = Depends(require_system_admin),
    application: AssignmentPlanApplication = Depends(
        get_assignment_plan_application
    ),
):
    del principal
    return _call_endpoint(
        lambda: _query_payload(application.query(case_no)),
        "成功取得正式人力配置",
        CorrelationId(f"assignment-plan-query:{case_no}"),
    )


@router.post(
    "/{case_no}/assignment-plan/preview",
    response_model=BaseResponse[AssignmentPlanPreviewView],
)
def preview_assignment_plan(
    body: AssignmentPlanPreviewBody,
    case_no: str = Path(..., min_length=1, max_length=50),
    correlation_id: Annotated[
        str,
        Header(alias="X-Correlation-ID", min_length=1, max_length=191),
    ] = "assignment-plan-preview",
    principal: AdminPrincipal = Depends(require_system_admin),
    application: AssignmentPlanApplication = Depends(
        get_assignment_plan_application
    ),
):
    del principal
    identity = CorrelationId(correlation_id)
    request = AssignmentPlanPreviewRequest(case_no, body.to_intent(), identity)
    return _call_endpoint(
        lambda: _preview_payload(application.preview(request)),
        "成功產生正式人力配置預覽",
        identity,
    )


@router.post(
    "/{case_no}/assignment-plan/apply",
    response_model=BaseResponse[JobAcceptedResponse],
    status_code=status.HTTP_202_ACCEPTED,
)
# FastAPI requires the complete HTTP contract here for OpenAPI generation.
def apply_assignment_plan(
    body: AssignmentPlanApplyBody,
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
    job_application: DurableJobCommandApplication = Depends(get_durable_job_application),
):
    request = _apply_request(
        case_no,
        body,
        idempotency_key,
        correlation_id,
        principal,
    )
    
    try:
        acceptance = job_application.enqueue(
            _assignment_plan_command(str(uuid.uuid4()), request)
        )
    except DurableJobCommandConflict as error:
        raise durable_job_conflict_http_error(error, correlation_id) from error

    return BaseResponse(
        data=JobAcceptedResponse(
            job_id=acceptance.job_id,
            status_url=f"/api/v1/jobs/{acceptance.job_id}",
        ),
        message="202 Accepted",
    )


def _assignment_plan_command(job_id, request):
    return DurableJobCommand(
        job_id,
        request.idempotency_key.value,
        "assignment_plan_apply",
        1,
        _assignment_plan_payload(request),
        request.actor.actor_id,
        request.correlation_id.value,
    )


def _assignment_plan_payload(request):
    return {
        "case_no": request.case_no,
        "segments": [
            {
                "staff_id": segment.staff_id,
                "assigned_start_date": segment.assigned_start_date.isoformat(),
                "assigned_end_date": segment.assigned_end_date.isoformat(),
                "official_service_dates": [item.isoformat() for item in segment.official_service_dates],
            }
            for segment in request.intent.segments
        ],
        "expected_order_version": request.expected_order_version.value,
        "expected_scheduling_version": request.expected_scheduling_version.value,
        "expected_client_finance_version": request.expected_client_finance_version.value,
        "expected_payroll_version": request.expected_payroll_version.value,
        "preview_fingerprint": request.preview_fingerprint.value,
        "idempotency_key": request.idempotency_key.value,
        "actor": request.actor.actor_id,
        "reason": request.reason,
        "correlation_id": request.correlation_id.value,
    }


def _apply_request(case_no, body, key, correlation, principal):
    return AssignmentPlanApplyRequest(
        case_no,
        body.to_intent(),
        ExpectedVersion(body.expected_order_version),
        ExpectedVersion(body.expected_scheduling_version),
        ExpectedVersion(body.expected_client_finance_version),
        ExpectedVersion(body.expected_payroll_version),
        PreviewFingerprint(body.preview_fingerprint),
        IdempotencyKey(key),
        ActorContext(immutable_admin_job_actor(principal, correlation)),
        body.reason,
        CorrelationId(correlation),
    )


def _query_payload(facts) -> dict[str, Any]:
    plan = facts.assignment_plan
    return {
        "case_no": plan.case_no,
        "order_version": plan.order_version,
        "scheduling_version": plan.scheduling_version,
        "scheduling_generation": plan.scheduling_generation,
        "client_finance_version": plan.client_finance_version,
        "payroll_version": plan.payroll_version,
        "contracted_service_days": plan.contracted_service_days,
        "service_hours_per_day": plan.service_hours_per_day,
        "service_started": plan.service_started,
        "assignments": [_query_assignment(item) for item in plan.effective_assignments],
    }


def _query_assignment(assignment) -> dict[str, Any]:
    return {
        "assignment_id": assignment.assignment_id,
        "staff_id": assignment.staff_id,
        "sequence": assignment.sequence,
        "assigned_start_date": assignment.assigned_start_date,
        "assigned_end_date": assignment.assigned_end_date,
        "official_service_dates": assignment.official_service_dates,
        "lineage_source_assignment_ids": [],
    }


def _preview_payload(preview) -> dict[str, Any]:
    scheduling = preview.candidate.scheduling
    return {
        "case_no": scheduling.case_no,
        "order_version": preview.order_version,
        "scheduling_version": preview.scheduling_version,
        "scheduling_generation": scheduling.generation_number,
        "client_finance_version": preview.client_finance_version,
        "payroll_version": preview.payroll_version,
        "cancelled_assignment_ids": scheduling.cancelled_assignment_ids,
        "assignments": [_preview_assignment(item) for item in scheduling.assignments],
        "buffers": _materialize(scheduling.buffers),
        "client_finance_impact": _materialize(preview.client_finance_impact),
        "payroll_impact": _materialize(preview.payroll_impact),
        "orders_impact": _materialize(preview.orders_impact),
        "preview_fingerprint": preview.fingerprint.value,
    }


def _preview_assignment(assignment) -> dict[str, Any]:
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
    except AssignmentPlanWorkflowError as error:
        _raise_typed_error(error.error)
    except (OperationalError, ProgrammingError) as error:
        _raise_mysql_error(error, correlation_id)
    except ValueError as error:
        _raise_value_error(error, correlation_id)
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


def _raise_mysql_error(error, correlation_id) -> None:
    mysql_code = int(error.args[0]) if error.args else 0
    if mysql_code in _SCHEMA_NOT_READY_MYSQL_CODES:
        _raise_schema_not_ready(error, correlation_id)
    if mysql_code in _RETRYABLE_MYSQL_CODES:
        typed = TypedError(
            ErrorCategory.UNAVAILABLE,
            "assignment_plan_transaction_temporarily_unavailable",
            "Retry with the same idempotency key.",
            correlation_id,
            retryable=True,
        )
        raise _http_error(503, typed, headers={"Retry-After": "1"}) from error
    raise _http_error(
        500,
        TypedError(
            ErrorCategory.INTERNAL,
            "assignment_plan_database_error",
            "Assignment Plan persistence failed.",
            correlation_id,
        ),
    ) from error


def _raise_schema_not_ready(error, correlation_id) -> None:
    typed = TypedError(
        ErrorCategory.UNAVAILABLE,
        "assignment_plan_schema_not_ready",
        "候選資料庫尚未完成正式排班架構回填。",
        correlation_id,
    )
    raise _http_error(503, typed) from error


def _raise_value_error(error, correlation_id) -> None:
    code = str(error)
    category = ErrorCategory.CONFLICT if "conflict" in code else ErrorCategory.VALIDATION
    status_code = 409 if category is ErrorCategory.CONFLICT else 422
    raise _http_error(
        status_code,
        TypedError(
            category,
            code,
            "Assignment Plan request was rejected.",
            correlation_id,
        ),
    ) from error


def _internal_error(correlation_id):
    return _http_error(
        500,
        TypedError(
            ErrorCategory.INTERNAL,
            "assignment_plan_internal_error",
            "Assignment Plan processing failed.",
            correlation_id,
        ),
    )


def _http_error(status_code, error, *, headers=None):
    return HTTPException(
        status_code=status_code,
        detail={"error": _materialize(error)},
        headers=headers,
    )


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
