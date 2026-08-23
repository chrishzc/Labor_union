"""
File: scheduling_eligibility_collision.py
Description: 提供 Scheduling 月嫂資格、衝突與覆蓋的 authenticated GET-only API。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pymysql.err import OperationalError, ProgrammingError

from api.dependencies.admin_auth import require_admin
from api.schemas.base import BaseResponse
from api.schemas.errors import GlobalTypedErrorResponseView
from api.schemas.scheduling_eligibility_collision import (
    SchedulingEligibilityCollisionProjectionView,
)
from infrastructure.mysql.mysql_adapter import get_connection
from shared_kernel.clock import SystemBusinessClock
from shared_kernel.errors import ErrorCategory, TypedError
from shared_kernel.identities import CorrelationId
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.scheduling.eligibility_collision_query import (
    CollisionResult,
    EligibilityCollisionProjection,
    EligibilityCollisionQueryError,
    QualificationCheckResult,
    SchedulingEligibilityCollisionQuery,
    SchedulingEligibilityCollisionQueryWorkflow,
)

router = APIRouter(
    prefix="/api/v1/scheduling",
    tags=["Scheduling Eligibility Collision"],
)
_RETRYABLE_MYSQL_CODES = frozenset({1205, 1213})
_SCHEMA_NOT_READY_MYSQL_CODES = frozenset({1054, 1146})


@dataclass(slots=True)
class SchedulingEligibilityCollisionApplication:
    workflow: SchedulingEligibilityCollisionQueryWorkflow

    def query(self, request: SchedulingEligibilityCollisionQuery):
        return self.workflow.query(request)


def get_scheduling_eligibility_collision_application():
    from infrastructure.mysql.scheduling_eligibility_collision_repository import (
        MySqlSchedulingEligibilityCollisionRepository,
    )

    connection = get_connection()
    workflow = SchedulingEligibilityCollisionQueryWorkflow(
        MySqlSchedulingEligibilityCollisionRepository(connection),
        SystemBusinessClock(),
    )
    try:
        yield SchedulingEligibilityCollisionApplication(workflow)
    finally:
        connection.close()


@router.get(
    "/eligibility-collisions",
    response_model=BaseResponse[SchedulingEligibilityCollisionProjectionView],
    responses={
        401: {"model": GlobalTypedErrorResponseView, "description": "需要有效的管理員驗證"},
        403: {"model": GlobalTypedErrorResponseView, "description": "目前身分無權查詢排班資格"},
        404: {"model": GlobalTypedErrorResponseView, "description": "訂單或月嫂不存在"},
        409: {"model": GlobalTypedErrorResponseView, "description": "排班資格根事實不一致"},
        422: {"model": GlobalTypedErrorResponseView, "description": "查詢條件不符合公開契約"},
        500: {"model": GlobalTypedErrorResponseView, "description": "排班資格查詢失敗"},
        503: {"model": GlobalTypedErrorResponseView, "description": "排班資格資料暫時無法使用"},
    },
)
def query_scheduling_eligibility_collisions(
    case_no: str = Query(..., min_length=1, max_length=50),
    as_of: date = Query(...),
    staff_id: int = Query(..., gt=0),
    correlation_id: Annotated[
        str | None,
        Header(alias="X-Correlation-ID", min_length=1, max_length=191),
    ] = None,
    principal: AdminPrincipal = Depends(require_admin),
    application: SchedulingEligibilityCollisionApplication = Depends(
        get_scheduling_eligibility_collision_application
    ),
):
    del principal
    correlation = CorrelationId(correlation_id or uuid4().hex)
    try:
        request = SchedulingEligibilityCollisionQuery(case_no, as_of, staff_id)
    except (TypeError, ValueError) as error:
        _raise_validation_error(error, correlation)
    return _call_query(application, request, correlation)


def _call_query(application, request, correlation):
    try:
        projection = application.query(request)
        return BaseResponse(
            data=_projection_payload(projection),
            message="成功取得月嫂資格、檔期衝突與服務日期覆蓋",
        )
    except EligibilityCollisionQueryError as error:
        _raise_query_error(error, correlation)
    except (OperationalError, ProgrammingError) as error:
        _raise_mysql_error(error, correlation)
    except (TypeError, ValueError) as error:
        _raise_validation_error(error, correlation)
    except HTTPException:
        raise
    except Exception as error:
        raise _http_error(
            500,
            TypedError(
                ErrorCategory.INTERNAL,
                "scheduling_eligibility_collision_internal_error",
                "月嫂資格與檔期查詢失敗。",
                correlation,
            ),
        ) from error


def _projection_payload(projection: EligibilityCollisionProjection) -> dict:
    return {
        "case_no": projection.case_no,
        "case_status": projection.case_status,
        "as_of": projection.as_of,
        "evaluated_at": projection.evaluated_at,
        "scheduling_version": projection.scheduling_version,
        "staff": [
            {
                "staff_id": item.staff_id,
                "eligibility": item.eligibility,
                "availability": item.availability,
                "qualification_checks": [
                    _qualification_payload(check)
                    for check in item.qualification_checks
                ],
                "collisions": [_collision_payload(collision) for collision in item.collisions],
                "coverage": {
                    "start_date": item.coverage.start_date,
                    "end_date": item.coverage.end_date,
                    "required_day_count": item.coverage.required_day_count,
                    "available_day_count": item.coverage.available_day_count,
                    "missing_dates": list(item.coverage.missing_dates),
                    "review_dates": list(item.coverage.review_dates),
                    "status": item.coverage.status,
                },
                "partial_data": list(item.partial_data),
            }
            for item in projection.staff
        ],
        "partial_data": list(projection.partial_data),
    }


def _qualification_payload(check: QualificationCheckResult) -> dict:
    return {
        "code": check.code,
        "status": check.status,
        "owner": check.owner,
        "source_identity": check.source_identity,
        "source_version": check.source_version,
        "detail": check.detail,
    }


def _collision_payload(collision: CollisionResult) -> dict:
    return {
        "kind": collision.kind,
        "severity": collision.severity,
        "staff_id": collision.staff_id,
        "case_no": collision.case_no,
        "assignment_id": collision.assignment_id,
        "source_id": collision.source_id,
        "collision_date": collision.collision_date,
        "start_date": collision.start_date,
        "end_date": collision.end_date,
        "owner": collision.owner,
        "source_identity": collision.source_identity,
        "detail": collision.detail,
    }


def _raise_query_error(error: EligibilityCollisionQueryError, correlation):
    if error.code in {"case_not_found", "staff_not_found"}:
        category = ErrorCategory.NOT_FOUND
        status_code = 404
    else:
        category = ErrorCategory.CONFLICT
        status_code = 409
    typed = TypedError(category, error.code, "排班資格查詢缺少必要根事實。", correlation)
    raise _http_error(status_code, typed) from error


def _raise_validation_error(error: Exception, correlation):
    typed = TypedError(
        ErrorCategory.VALIDATION,
        "scheduling_eligibility_collision_invalid_query",
        "月嫂資格與檔期查詢輸入無效。",
        correlation,
    )
    raise _http_error(422, typed) from error


def _raise_mysql_error(error: Exception, correlation):
    mysql_code = int(error.args[0]) if error.args else 0
    if mysql_code in _SCHEMA_NOT_READY_MYSQL_CODES:
        typed = TypedError(
            ErrorCategory.UNAVAILABLE,
            "scheduling_eligibility_collision_schema_not_ready",
            "候選資料庫尚未完成排班資格查詢所需架構。",
            correlation,
        )
        raise _http_error(503, typed) from error
    retryable = mysql_code in _RETRYABLE_MYSQL_CODES
    typed = TypedError(
        ErrorCategory.UNAVAILABLE if retryable else ErrorCategory.INTERNAL,
        (
            "scheduling_eligibility_collision_temporarily_unavailable"
            if retryable
            else "scheduling_eligibility_collision_database_error"
        ),
        "目前排班資格查詢資料庫暫時無法使用。",
        correlation,
        retryable=retryable,
    )
    raise _http_error(503 if retryable else 500, typed) from error


def _http_error(status_code: int, error: TypedError):
    return HTTPException(
        status_code=status_code,
        detail={"error": _typed_error_payload(error)},
        headers={"Retry-After": "1"} if error.retryable else None,
    )


def _typed_error_payload(error: TypedError) -> dict:
    return {
        "category": error.category.value,
        "code": error.code,
        "message": error.message,
        "correlation_id": error.correlation_id.value,
        "field_errors": [
            {"field": item.field, "code": item.code, "message": item.message}
            for item in error.field_errors
        ],
        "domain_blockers": list(error.domain_blockers),
        "retryable": error.retryable,
        "current_version": error.current_version.value if error.current_version else None,
    }


__all__ = [
    "SchedulingEligibilityCollisionApplication",
    "get_scheduling_eligibility_collision_application",
    "query_scheduling_eligibility_collisions",
    "router",
]
