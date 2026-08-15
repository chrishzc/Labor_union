"""File: leave_substitution.py
Description: 提供正式請假代班預覽、套用與已受理待辦的收據結案。"""

from __future__ import annotations

from dataclasses import fields, is_dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from enum import Enum
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Path
from pydantic import BaseModel, ConfigDict, Field
from pymysql.err import OperationalError

from api.dependencies.admin_auth import require_system_admin
from api.dependencies.leave_substitution import (
    LeaveSubstitutionApplication,
    get_leave_substitution_application,
)
from api.schemas.base import BaseResponse
from api.schemas.leave_substitution import (
    LeaveAssignmentSummaryView,
    LeaveSubstitutionPreviewView,
    LeaveSubstitutionReceiptView,
)
from domains.line.canonical_payload import canonical_line_payload_json
from domains.line.delivery import LineDeliveryRequest, LineMessageKind, LineRecipient, LineRecipientType
from domains.line.identities import LineUserId
from domains.scheduling.leave_substitution import (
    LeaveResolutionType,
    LeaveSubstitutionBatchIntent,
    LeaveSubstitutionItem,
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
    LeaveSubstitutionPreviewRequest,
    LeaveSubstitutionWorkflowError,
)
from subsystems.scheduling.staff_leave_intake_workflow import (
    ResolveStaffLeaveRequest,
    StaffLeaveIntakeWorkflow,
    StaffLeaveIntakeWorkflowError,
)
from infrastructure.mysql.line_delivery_task_repository import MySqlLineDeliveryTaskRepository
from infrastructure.mysql.staff_leave_intake_repository import MySqlStaffLeaveIntakeRepository
from infrastructure.mysql.unit_of_work import MySqlUnitOfWork


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
            }
            for row in assignments
        ],
        message="成功取得請假與代班正式服務指派",
    )


class LeaveSubstitutionItemInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    original_schedule_id: int = Field(gt=0)
    work_date: date
    resolution_type: LeaveResolutionType
    substitute_staff_id: int | None = Field(default=None, gt=0)
    is_double_pay: bool = False

    def to_domain(self) -> LeaveSubstitutionItem:
        return LeaveSubstitutionItem(
            self.original_schedule_id,
            self.work_date,
            self.resolution_type,
            self.substitute_staff_id,
            self.is_double_pay,
        )


class LeaveSubstitutionPreviewBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    original_assignment_id: int = Field(gt=0)
    items: tuple[LeaveSubstitutionItemInput, ...] = ()

    def to_intent(self) -> LeaveSubstitutionBatchIntent:
        return LeaveSubstitutionBatchIntent(
            self.original_assignment_id,
            tuple(item.to_domain() for item in self.items),
        )


class LeaveSubstitutionApplyBody(LeaveSubstitutionPreviewBody):
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
    leave_request_id: int | None = Field(default=None, gt=0)
    expected_leave_request_version: int | None = Field(default=None, ge=1)


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
    receipt = application.apply(request)
    if body.leave_request_id is not None:
        if body.expected_leave_request_version is None:
            raise HTTPException(status_code=422, detail={"code": "leave_request_expected_version_required"})
        _resolve_linked_leave_request(application.connection, body, receipt, key, correlation_id)
    return _materialize(receipt)


def _resolve_linked_leave_request(connection, body, receipt, key, correlation_id):
    resolution_key = _resolution_key(key, body.leave_request_id, receipt.batch_key)
    with MySqlUnitOfWork(connection) as unit_of_work:
        result = StaffLeaveIntakeWorkflow(MySqlStaffLeaveIntakeRepository(connection)).resolve(
            ResolveStaffLeaveRequest(
                body.leave_request_id,
                body.expected_leave_request_version,
                receipt.batch_key,
                resolution_key,
            )
        )
        MySqlLineDeliveryTaskRepository(connection).enqueue(
            _completion_notification(result, correlation_id, resolution_key)
        )
        unit_of_work.commit()


def _resolution_key(key: str, request_id: int, receipt_key: str) -> str:
    return "staff-leave-resolve:" + fingerprint_payload({
        "apply_key": key, "request_id": request_id, "receipt_key": receipt_key,
    }).value


def _completion_notification(snapshot, correlation_id, resolution_key: str) -> LineDeliveryRequest:
    return LineDeliveryRequest(
        LineRecipient(LineRecipientType.USER, LineUserId(snapshot.line_user_id)),
        LineMessageKind.TEXT,
        canonical_line_payload_json({"type": "text", "text": "您的請假申請已完成正式排班處理。"}),
        datetime.now(UTC),
        IdempotencyKey("staff-leave-notify:" + fingerprint_payload({"resolution_key": resolution_key}).value),
        correlation_id,
        "scheduling_staff_leave_request",
        str(snapshot.request_id),
    )


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
        "client_finance_impact": _materialize(preview.client_finance_impact),
        "payroll_impact": _materialize(preview.payroll_impact),
        "orders_impact": _materialize(preview.orders_impact),
        "calendar_candidate": _materialize(preview.calendar_candidate),
        "apply_readiness": _materialize(preview.apply_readiness),
        "preview_fingerprint": preview.fingerprint.value,
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
    except StaffLeaveIntakeWorkflowError as error:
        raise HTTPException(status_code=409, detail={"code": str(error)}) from error
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
