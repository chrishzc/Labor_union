"""Typed current-state system-alert endpoints."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Path, Query

from api.schemas.finance_alert_center import (
    AlertActionViewModel,
    AlertCenterResponse,
    AlertDetailViewModel,
    AlertFamily,
    AlertListViewModel,
    AlertStatus,
    ClaimAlertRequest,
    PaginationViewModel,
    ResolveAlertRequest,
    ScanSummaryViewModel,
    TypedErrorCode,
    TypedErrorViewModel,
    action_view_from_result,
    alert_summary_from_record,
    scan_summary_from_result,
    system_alert_detail_from_record,
)
from services.anomaly_alert_detection import run_process_alert_scan
from services.db_service import get_connection
from services.system_alert_service import (
    claim_system_alert,
    get_system_alert,
    list_system_alerts,
    resolve_system_alert,
)


router = APIRouter(prefix="/api/v1/system-alerts", tags=["System Alerts"])
assert router.prefix == "/api/v1/system-alerts"

ClaimSystemAlertRequest = ClaimAlertRequest
ResolveSystemAlertRequest = ResolveAlertRequest


def _typed_http_error(
    status_code: int,
    code: TypedErrorCode,
    message: str,
    *,
    retryable: bool = False,
) -> HTTPException:
    error = TypedErrorViewModel(
        code=code,
        message=message,
        retryable=retryable,
    )
    return HTTPException(status_code=status_code, detail=error.model_dump(mode="json"))


def _workflow_error(exc: ValueError) -> HTTPException:
    message = str(exc)
    if message == "alert_id does not exist":
        return _typed_http_error(
            404, TypedErrorCode.NOT_FOUND, "找不到指定的系統警示"
        )
    return _typed_http_error(
        422, TypedErrorCode.VALIDATION_ERROR, message
    )


@router.get("", response_model=AlertCenterResponse[AlertListViewModel])
def list_alerts(
    status: AlertStatus | None = Query(default=None),
    alert_code: str | None = Query(default=None, min_length=1, max_length=191),
    source_domain: str | None = Query(default=None, min_length=1, max_length=100),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0, le=1_000_000),
):
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            records = list_system_alerts(
                cursor,
                status=(
                    status.value
                    if isinstance(status, AlertStatus)
                    else status
                ),
                alert_code=alert_code,
                source_domain=source_domain,
                limit=limit,
                offset=offset,
            )
        items = [
            alert_summary_from_record(record, AlertFamily.SYSTEM)
            for record in records
        ]
        return AlertCenterResponse(
            data=AlertListViewModel(
                items=items,
                pagination=PaginationViewModel(
                    limit=limit,
                    offset=offset,
                    returned_count=len(items),
                    has_more=len(items) == limit,
                ),
            ),
            message="系統警示讀取完成",
        )
    except ValueError as exc:
        raise _workflow_error(exc) from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise _typed_http_error(
            500,
            TypedErrorCode.INTERNAL_ERROR,
            "無法讀取系統警示",
        ) from exc
    finally:
        connection.close()


@router.post("/scan", response_model=AlertCenterResponse[ScanSummaryViewModel])
def scan_alerts():
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            result = run_process_alert_scan(cursor)
        if "IMPORT-006" not in result:
            raise RuntimeError("scan summary is missing IMPORT-006")
        summary = scan_summary_from_result(result)
        connection.commit()
        return AlertCenterResponse(data=summary, message="異常重新掃描完成")
    except HTTPException:
        connection.rollback()
        raise
    except ValueError as exc:
        connection.rollback()
        raise _workflow_error(exc) from exc
    except Exception as exc:
        connection.rollback()
        raise _typed_http_error(
            500,
            TypedErrorCode.INTERNAL_ERROR,
            "異常重新掃描失敗",
        ) from exc
    finally:
        connection.close()


@router.get(
    "/{alert_id}",
    response_model=AlertCenterResponse[AlertDetailViewModel],
)
def get_alert(alert_id: int = Path(..., ge=1)):
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            record = get_system_alert(cursor, alert_id)
        if record is None:
            raise _typed_http_error(
                404, TypedErrorCode.NOT_FOUND, "找不到指定的系統警示"
            )
        return AlertCenterResponse(
            data=system_alert_detail_from_record(record),
            message="系統警示詳情讀取完成",
        )
    except HTTPException:
        raise
    except ValueError as exc:
        raise _workflow_error(exc) from exc
    except Exception as exc:
        raise _typed_http_error(
            500,
            TypedErrorCode.INTERNAL_ERROR,
            "無法讀取系統警示詳情",
        ) from exc
    finally:
        connection.close()


def _run_action(
    action: Callable[[Any], Mapping[str, Any]],
    *,
    action_name: Literal["claim", "resolve"],
) -> AlertCenterResponse[AlertActionViewModel]:
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            result = action(cursor)
        if result.get("result") == "conflict":
            raise _typed_http_error(
                409,
                TypedErrorCode.CONFLICT,
                "系統警示已由其他人處理或目前狀態不允許此操作",
            )
        view = action_view_from_result(
            result,
            family=AlertFamily.SYSTEM,
            action=action_name,
        )
        connection.commit()
        return AlertCenterResponse(data=view, message=view.message)
    except HTTPException:
        connection.rollback()
        raise
    except ValueError as exc:
        connection.rollback()
        raise _workflow_error(exc) from exc
    except Exception as exc:
        connection.rollback()
        raise _typed_http_error(
            500,
            TypedErrorCode.INTERNAL_ERROR,
            "無法更新系統警示",
        ) from exc
    finally:
        connection.close()


@router.post(
    "/{alert_id}/claim",
    response_model=AlertCenterResponse[AlertActionViewModel],
)
def claim_alert(
    request: ClaimAlertRequest,
    alert_id: int = Path(..., ge=1),
):
    return _run_action(
        lambda cursor: claim_system_alert(
            cursor,
            alert_id=alert_id,
            operator=request.operator,
        ),
        action_name="claim",
    )


@router.post(
    "/{alert_id}/resolve",
    response_model=AlertCenterResponse[AlertActionViewModel],
)
def resolve_alert(
    request: ResolveAlertRequest,
    alert_id: int = Path(..., ge=1),
):
    return _run_action(
        lambda cursor: resolve_system_alert(
            cursor,
            alert_id=alert_id,
            operator=request.operator,
            reason=request.reason,
        ),
        action_name="resolve",
    )
