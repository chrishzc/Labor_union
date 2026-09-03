"""Preview/Apply boundary for assignment-only historical calendar repair."""

from __future__ import annotations

from pathlib import Path
import tempfile
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile
from pymysql.err import OperationalError

from api.dependencies.admin_auth import require_historical_order_review_remediator
from api.dependencies.historical_calendar_assignment_remediation import (
    get_historical_calendar_assignment_remediation_application,
)
from api.error_contracts import internal_query_error, typed_http_error
from api.schemas.base import BaseResponse
from api.schemas.historical_calendar_assignment_remediation import (
    HistoricalCalendarAssignmentPreviewView,
    HistoricalCalendarAssignmentReceiptView,
)
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.orders.historical_calendar_assignment_remediation import (
    HistoricalCalendarAssignmentRemediationApplication,
    HistoricalCalendarAssignmentRemediationError,
)


router = APIRouter(
    prefix="/api/v1/orders/historical-calendar-assignment-remediations",
    tags=["Orders"],
)
_MAXIMUM_WORKBOOK_BYTES = 20 * 1024 * 1024
_CorrelationHeader = Annotated[
    str,
    Header(alias="X-Correlation-ID", min_length=1, max_length=191),
]
_IdempotencyHeader = Annotated[
    str,
    Header(alias="Idempotency-Key", min_length=1, max_length=191),
]


@router.post(
    "/preview",
    response_model=BaseResponse[HistoricalCalendarAssignmentPreviewView],
)
def preview_historical_calendar_assignment_remediation(
    case_no: Annotated[str, Form(min_length=1, max_length=50)],
    caregiver_ordinal: Annotated[int, Form(ge=1)] = 1,
    workbook: UploadFile = File(...),
    correlation_id: _CorrelationHeader = "historical-calendar-assignment-preview",
    principal: AdminPrincipal = Depends(
        require_historical_order_review_remediator
    ),
    application: HistoricalCalendarAssignmentRemediationApplication = Depends(
        get_historical_calendar_assignment_remediation_application
    ),
):
    del principal
    path = _save_workbook(workbook)
    try:
        result = application.preview(path, case_no.strip(), caregiver_ordinal)
        return BaseResponse(
            data=_preview_payload(result),
            message="已產生歷史月曆 completed assignment 修復預覽",
        )
    except HistoricalCalendarAssignmentRemediationError as error:
        raise _workflow_http_error(error, correlation_id) from error
    except OperationalError as error:
        raise _database_http_error(error, correlation_id) from error
    except (TypeError, ValueError) as error:
        raise typed_http_error(
            422,
            "validation",
            str(error) or "historical_calendar_assignment_workbook_invalid",
            "歷史訂單 workbook 未通過驗證。",
            correlation_id,
        ) from error
    except Exception as error:
        raise internal_query_error(
            "historical_calendar_assignment_preview_failed",
            "歷史月曆 completed assignment 修復預覽失敗。",
            correlation_id,
        ) from error
    finally:
        path.unlink(missing_ok=True)


@router.post(
    "/apply",
    response_model=BaseResponse[HistoricalCalendarAssignmentReceiptView],
)
def apply_historical_calendar_assignment_remediation(
    case_no: Annotated[str, Form(min_length=1, max_length=50)],
    expected_lifecycle_version: Annotated[int, Form(ge=0)],
    preview_fingerprint: Annotated[str, Form(pattern=r"^[0-9a-f]{64}$")],
    reason: Annotated[str, Form(min_length=1, max_length=500)],
    caregiver_ordinal: Annotated[int, Form(ge=1)] = 1,
    workbook: UploadFile = File(...),
    idempotency_key: _IdempotencyHeader = ...,
    correlation_id: _CorrelationHeader = ...,
    principal: AdminPrincipal = Depends(
        require_historical_order_review_remediator
    ),
    application: HistoricalCalendarAssignmentRemediationApplication = Depends(
        get_historical_calendar_assignment_remediation_application
    ),
):
    path = _save_workbook(workbook)
    try:
        result = application.apply(
            path,
            case_no.strip(),
            caregiver_ordinal,
            expected_lifecycle_version,
            preview_fingerprint,
            idempotency_key,
            str(principal.username or "").strip(),
            reason.strip(),
        )
        return BaseResponse(
            data=_receipt_payload(result),
            message="已套用歷史月曆 completed assignment 修復",
        )
    except HistoricalCalendarAssignmentRemediationError as error:
        raise _workflow_http_error(error, correlation_id) from error
    except OperationalError as error:
        raise _database_http_error(error, correlation_id) from error
    except (TypeError, ValueError) as error:
        raise typed_http_error(
            422,
            "validation",
            str(error) or "historical_calendar_assignment_workbook_invalid",
            "歷史訂單 workbook 未通過驗證。",
            correlation_id,
        ) from error
    except Exception as error:
        raise internal_query_error(
            "historical_calendar_assignment_apply_failed",
            "歷史月曆 completed assignment 修復失敗。",
            correlation_id,
        ) from error
    finally:
        path.unlink(missing_ok=True)


def _save_workbook(workbook: UploadFile) -> Path:
    filename = (workbook.filename or "").lower()
    if not filename.endswith(".xlsx"):
        raise HTTPException(
            status_code=422,
            detail="historical_calendar_assignment_workbook_must_be_xlsx",
        )
    with tempfile.NamedTemporaryFile(
        prefix="historical-calendar-assignment-",
        suffix=".xlsx",
        delete=False,
    ) as target:
        written = 0
        while chunk := workbook.file.read(1024 * 1024):
            written += len(chunk)
            if written > _MAXIMUM_WORKBOOK_BYTES:
                target.close()
                Path(target.name).unlink(missing_ok=True)
                raise HTTPException(
                    status_code=422,
                    detail="historical_calendar_assignment_workbook_too_large",
                )
            target.write(chunk)
        if written == 0:
            target.close()
            Path(target.name).unlink(missing_ok=True)
            raise HTTPException(
                status_code=422,
                detail="historical_calendar_assignment_workbook_empty",
            )
        return Path(target.name)


def _preview_payload(result):
    return {
        "case_no": result.case_no,
        "caregiver_ordinal": result.caregiver_ordinal,
        "order_status": result.order_status,
        "lifecycle_version": result.lifecycle_version,
        "source_content_digest": result.source_content_digest,
        "source_identity": result.source_identity,
        "source_fingerprint": result.source_fingerprint,
        "staff_id": result.staff_id,
        "staff_name": result.staff_name,
        "start_date": result.start_date,
        "end_date": result.end_date,
        "existing_assignment_id": result.existing_assignment_id,
        "disposition": result.disposition,
        "blockers": list(result.blockers),
        "apply_allowed": result.apply_allowed,
        "preview_fingerprint": result.preview_fingerprint,
    }


def _receipt_payload(result):
    return {
        "receipt_key": result.receipt_key,
        "case_no": result.case_no,
        "caregiver_ordinal": result.caregiver_ordinal,
        "assignment_id": result.assignment_id,
        "created": result.created,
        "lifecycle_version": result.lifecycle_version,
        "source_content_digest": result.source_content_digest,
        "preview_fingerprint": result.preview_fingerprint,
        "replayed": result.replayed,
        "orders_changed": False,
    }


def _workflow_http_error(error, correlation_id):
    if error.code == "historical_calendar_assignment_case_not_found":
        return typed_http_error(
            404,
            "not_found",
            error.code,
            "找不到指定歷史訂單。",
            correlation_id,
        )
    if error.code in {
        "historical_calendar_assignment_stale_preview",
        "historical_calendar_assignment_idempotency_key_conflict",
        "historical_calendar_assignment_blocked",
    }:
        exc = typed_http_error(
            409,
            "conflict",
            error.code,
            "修復條件已變更、重複鍵衝突，或目前資料不可套用。",
            correlation_id,
        )
        if error.blockers:
            exc.detail["error"]["domain_blockers"] = list(error.blockers)
        return exc
    return typed_http_error(
        422,
        "validation",
        error.code,
        "歷史月曆 completed assignment 修復資料未通過驗證。",
        correlation_id,
    )


def _database_http_error(error, correlation_id):
    retryable = bool(error.args) and error.args[0] in {1205, 1213}
    return typed_http_error(
        503 if retryable else 500,
        "unavailable" if retryable else "internal",
        (
            "historical_calendar_assignment_database_unavailable"
            if retryable
            else "historical_calendar_assignment_database_failed"
        ),
        (
            "歷史月曆修復資料庫暫時忙碌，請重新 Preview 後再試。"
            if retryable
            else "歷史月曆修復資料庫操作失敗。"
        ),
        correlation_id,
        retryable=retryable,
    )


__all__ = ["router"]
