"""Typed bounded query for current Scheduling lifecycle and occupancy."""

from __future__ import annotations

from dataclasses import fields, is_dataclass
from datetime import date
from enum import Enum
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Path, Query
from pymysql.err import OperationalError, ProgrammingError

from api.dependencies.admin_auth import require_system_admin
from api.dependencies.scheduling_current import (
    SchedulingCurrentApplication,
    get_scheduling_current_application,
)
from api.schemas.base import BaseResponse
from api.schemas.scheduling_current import SchedulingCurrentProjectionView
from domains.scheduling.current_projection import (
    SchedulingCurrentDomainError,
    SchedulingCurrentErrorCode,
)
from subsystems.access.authentication_session import AdminPrincipal
from shared_kernel.errors import ErrorCategory, TypedError
from shared_kernel.identities import CorrelationId
from subsystems.scheduling.current_projection_workflow import (
    SchedulingCurrentQuery,
)

router = APIRouter(
    prefix="/api/v1/scheduling",
    tags=["Scheduling Current Projection"],
)
_RETRYABLE_MYSQL_CODES = frozenset({1205, 1213})
_SCHEMA_NOT_READY_MYSQL_CODES = frozenset({1054, 1146})


@router.get(
    "/staff/{staff_id}/current-calendar",
    response_model=BaseResponse[SchedulingCurrentProjectionView],
)
def query_scheduling_current_calendar(
    staff_id: int = Path(..., gt=0),
    range_start: date = Query(...),
    range_end: date = Query(...),
    correlation_id: Annotated[
        str,
        Header(alias="X-Correlation-ID", min_length=1, max_length=191),
    ] = "scheduling-current-query",
    principal: AdminPrincipal = Depends(require_system_admin),
    application: SchedulingCurrentApplication = Depends(
        get_scheduling_current_application
    ),
):
    del principal
    correlation = CorrelationId(correlation_id)
    request = SchedulingCurrentQuery(staff_id, range_start, range_end)
    return _call_query(application, request, correlation)


def _call_query(application, request, correlation):
    try:
        projection = application.query(request)
        return BaseResponse(
            data=_projection_payload(projection),
            message="成功取得目前排班、鎖定與月嫂狀態",
        )
    except SchedulingCurrentDomainError as error:
        _raise_domain_error(error, correlation)
    except (OperationalError, ProgrammingError) as error:
        _raise_mysql_error(error, correlation)
    except ValueError as error:
        _raise_value_error(error, correlation)
    except HTTPException:
        raise
    except Exception as error:
        raise _internal_error(correlation) from error


def _projection_payload(projection):
    return {
        "staff_id": projection.staff_id,
        "range_start": projection.range_start,
        "range_end": projection.range_end,
        "evaluated_at": projection.evaluated_at,
        "assignments": [_materialize(item) for item in projection.assignments],
        "days": [_materialize(item) for item in projection.days],
        "case_versions": [
            {"case_no": case_no, "scheduling_version": version}
            for case_no, version in projection.case_versions
        ],
        "projection_token": projection.projection_token.value,
    }


def _raise_domain_error(error, correlation):
    conflict_codes = {
        SchedulingCurrentErrorCode.DATA_INTEGRITY,
        SchedulingCurrentErrorCode.OCCUPANCY_CONFLICT,
    }
    category = (
        ErrorCategory.CONFLICT
        if error.code in conflict_codes
        else ErrorCategory.VALIDATION
    )
    typed = TypedError(
        category,
        error.code.value,
        "目前排班根事實無法產生一致的讀取投影。",
        correlation,
        domain_blockers=tuple(sorted(set(error.blockers))),
    )
    raise _http_error(409 if category is ErrorCategory.CONFLICT else 422, typed)


def _raise_value_error(error, correlation):
    code = str(error) or "scheduling_data_integrity_violation"
    not_found = code == "staff_not_found"
    typed = TypedError(
        ErrorCategory.NOT_FOUND if not_found else ErrorCategory.CONFLICT,
        code,
        "目前排班查詢缺少必要根事實。",
        correlation,
    )
    raise _http_error(404 if not_found else 409, typed) from error


def _raise_mysql_error(error, correlation):
    mysql_code = int(error.args[0]) if error.args else 0
    if mysql_code in _SCHEMA_NOT_READY_MYSQL_CODES:
        _raise_schema_not_ready(error, correlation)
    retryable = mysql_code in _RETRYABLE_MYSQL_CODES
    typed = TypedError(
        ErrorCategory.UNAVAILABLE if retryable else ErrorCategory.INTERNAL,
        (
            "scheduling_query_temporarily_unavailable"
            if retryable
            else "scheduling_query_database_error"
        ),
        "目前排班查詢暫時無法完成。",
        correlation,
        retryable=retryable,
    )
    headers = {"Retry-After": "1"} if retryable else None
    raise _http_error(503 if retryable else 500, typed, headers) from error


def _raise_schema_not_ready(error, correlation):
    typed = TypedError(
        ErrorCategory.UNAVAILABLE,
        "scheduling_projection_schema_not_ready",
        "候選資料庫尚未完成正式排班架構回填。",
        correlation,
    )
    raise _http_error(503, typed) from error


def _internal_error(correlation):
    return _http_error(
        500,
        TypedError(
            ErrorCategory.INTERNAL,
            "scheduling_current_projection_internal_error",
            "目前排班查詢失敗。",
            correlation,
        ),
    )


def _http_error(status_code, error, headers=None):
    return HTTPException(
        status_code=status_code,
        detail={"error": _materialize(error)},
        headers=headers,
    )


def _materialize(value):
    if isinstance(value, CorrelationId):
        return value.value
    if is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: _materialize(getattr(value, field.name))
            for field in fields(value)
        }
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, tuple):
        return [_materialize(item) for item in value]
    if isinstance(value, list):
        return [_materialize(item) for item in value]
    return value


__all__ = ["router"]
