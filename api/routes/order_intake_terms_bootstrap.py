"""Typed Preview/Apply boundaries for pending Orders intake repair."""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Path
from pydantic import BaseModel, Field
from pymysql.err import OperationalError

from api.dependencies.admin_auth import require_persisted_admin
from api.dependencies.order_intake_terms_bootstrap import (
    get_order_intake_terms_bootstrap_application,
)
from api.error_contracts import internal_query_error, typed_http_error
from api.schemas.base import BaseResponse
from api.schemas.orders import (
    ClientNameApplyRequest,
    ClientNamePreviewRequest,
    ClientNamePreviewView,
    ClientNameReceiptView,
)
from infrastructure.mysql.admin_command_repository import AdminCommandRepository
from infrastructure.mysql.mysql_adapter import get_connection
from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.orders import client_name_maintenance
from subsystems.orders.order_intake_terms_bootstrap import (
    OrderIntakeTermsBootstrapApplication,
    OrderIntakeTermsBootstrapError,
)


router = APIRouter(tags=["Orders"])
_CorrelationHeader = Annotated[
    str,
    Header(alias="X-Correlation-ID", min_length=1, max_length=191),
]
_IdempotencyHeader = Annotated[
    str,
    Header(alias="Idempotency-Key", min_length=1, max_length=191),
]


class OrderIntakeTermsBootstrapIntent(BaseModel):
    proposed_start_date: date
    proposed_service_days: int = Field(gt=0)


class OrderIntakeTermsBootstrapApplyBody(OrderIntakeTermsBootstrapIntent):
    expected_lifecycle_version: int = Field(ge=0)
    preview_fingerprint: str = Field(
        min_length=64,
        max_length=64,
        pattern=r"^[0-9a-f]{64}$",
    )
    reason: str = Field(min_length=1, max_length=500)


class OrderIntakeTermsBootstrapPreviewView(BaseModel):
    case_no: str
    lifecycle_version: int
    before_start_date: date | None
    before_service_days: int | None
    after_start_date: date
    after_service_days: int
    changed_fields: list[str]
    blockers: list[str]
    apply_allowed: bool
    preview_fingerprint: str


class OrderIntakeTermsBootstrapReceiptView(BaseModel):
    receipt_key: str
    case_no: str
    lifecycle_version: int
    start_date: date
    service_days: int
    changed_fields: list[str]
    preview_fingerprint: str
    replayed: bool


class OrderIntakeCompletionPreviewView(BaseModel):
    case_no: str
    lifecycle_version: int
    current_status: str
    target_status: str
    missing_fields: list[str]
    blockers: list[str]
    apply_allowed: bool
    preview_fingerprint: str


class OrderIntakeCompletionApplyBody(BaseModel):
    expected_lifecycle_version: int = Field(ge=0)
    preview_fingerprint: str = Field(
        min_length=64,
        max_length=64,
        pattern=r"^[0-9a-f]{64}$",
    )
    reason: str = Field(min_length=1, max_length=500)


class OrderIntakeCompletionReceiptView(BaseModel):
    receipt_key: str
    case_no: str
    lifecycle_version: int
    status: str
    preview_fingerprint: str
    replayed: bool


@router.post(
    "/{case_no}/intake-terms-bootstrap/preview",
    response_model=BaseResponse[OrderIntakeTermsBootstrapPreviewView],
)
def preview_order_intake_terms_bootstrap(
    body: OrderIntakeTermsBootstrapIntent,
    case_no: str = Path(..., min_length=1, max_length=50),
    correlation_id: _CorrelationHeader = "order-intake-terms-bootstrap-preview",
    principal: AdminPrincipal = Depends(require_persisted_admin),
    application: OrderIntakeTermsBootstrapApplication = Depends(
        get_order_intake_terms_bootstrap_application
    ),
):
    del principal
    try:
        result = application.preview(
            case_no.strip(),
            body.proposed_start_date,
            body.proposed_service_days,
        )
        return BaseResponse(
            data=_preview_payload(result),
            message="已產生待補件訂單條款補齊預覽",
        )
    except OrderIntakeTermsBootstrapError as error:
        raise _workflow_http_error(error, correlation_id) from error
    except OperationalError as error:
        raise _database_http_error(error, correlation_id) from error
    except Exception as error:
        raise internal_query_error(
            "order_intake_terms_bootstrap_preview_failed",
            "待補件訂單條款補齊預覽失敗。",
            correlation_id,
        ) from error


@router.post(
    "/{case_no}/intake-terms-bootstrap/apply",
    response_model=BaseResponse[OrderIntakeTermsBootstrapReceiptView],
)
def apply_order_intake_terms_bootstrap(
    body: OrderIntakeTermsBootstrapApplyBody,
    case_no: str = Path(..., min_length=1, max_length=50),
    idempotency_key: _IdempotencyHeader = ...,
    correlation_id: _CorrelationHeader = ...,
    principal: AdminPrincipal = Depends(require_persisted_admin),
    application: OrderIntakeTermsBootstrapApplication = Depends(
        get_order_intake_terms_bootstrap_application
    ),
):
    try:
        result = application.apply(
            case_no.strip(),
            body.proposed_start_date,
            body.proposed_service_days,
            body.expected_lifecycle_version,
            body.preview_fingerprint,
            idempotency_key,
            str(principal.username or "").strip(),
            body.reason.strip(),
        )
        return BaseResponse(
            data=_receipt_payload(result),
            message="已補齊待補件訂單條款",
        )
    except OrderIntakeTermsBootstrapError as error:
        raise _workflow_http_error(error, correlation_id) from error
    except OperationalError as error:
        raise _database_http_error(error, correlation_id) from error
    except Exception as error:
        raise internal_query_error(
            "order_intake_terms_bootstrap_apply_failed",
            "待補件訂單條款補齊失敗。",
            correlation_id,
        ) from error


@router.post(
    "/{case_no}/intake-completion/client-name/preview",
    response_model=BaseResponse[ClientNamePreviewView],
)
def preview_order_intake_client_name(
    body: ClientNamePreviewRequest,
    case_no: str = Path(..., min_length=1, max_length=50),
    principal: AdminPrincipal = Depends(require_persisted_admin),
):
    del principal
    connection = get_connection()
    try:
        result = client_name_maintenance.preview(
            AdminCommandRepository(connection),
            case_no.strip(),
            body.client_name.strip(),
        )
        return BaseResponse(
            data=ClientNamePreviewView.model_validate(result),
            message="已產生待補件客戶姓名預覽",
        )
    except ValueError as error:
        raise _client_name_http_error(error, "intake-client-name-preview") from error
    except OperationalError as error:
        raise _database_http_error(error, "intake-client-name-preview") from error
    except Exception as error:
        raise internal_query_error(
            "order_intake_client_name_preview_failed",
            "待補件客戶姓名預覽失敗。",
            "intake-client-name-preview",
        ) from error
    finally:
        connection.close()


@router.post(
    "/{case_no}/intake-completion/client-name/apply",
    response_model=BaseResponse[ClientNameReceiptView],
)
def apply_order_intake_client_name(
    body: ClientNameApplyRequest,
    case_no: str = Path(..., min_length=1, max_length=50),
    idempotency_key: _IdempotencyHeader = ...,
    principal: AdminPrincipal = Depends(require_persisted_admin),
):
    connection = get_connection()
    try:
        result = client_name_maintenance.apply(
            AdminCommandRepository(connection),
            lambda: MySqlUnitOfWork(connection),
            case_no.strip(),
            body.client_name.strip(),
            body.preview_fingerprint,
            idempotency_key,
            str(principal.username or "").strip(),
            body.reason.strip(),
        )
        return BaseResponse(
            data=ClientNameReceiptView.model_validate(result),
            message="已補齊待補件客戶姓名",
        )
    except ValueError as error:
        raise _client_name_http_error(error, "intake-client-name-apply") from error
    except OperationalError as error:
        raise _database_http_error(error, "intake-client-name-apply") from error
    except Exception as error:
        raise internal_query_error(
            "order_intake_client_name_apply_failed",
            "待補件客戶姓名補齊失敗。",
            "intake-client-name-apply",
        ) from error
    finally:
        connection.close()


@router.post(
    "/{case_no}/intake-completion/preview",
    response_model=BaseResponse[OrderIntakeCompletionPreviewView],
)
def preview_order_intake_completion(
    case_no: str = Path(..., min_length=1, max_length=50),
    correlation_id: _CorrelationHeader = "order-intake-completion-preview",
    principal: AdminPrincipal = Depends(require_persisted_admin),
    application: OrderIntakeTermsBootstrapApplication = Depends(
        get_order_intake_terms_bootstrap_application
    ),
):
    del principal
    try:
        result = application.preview_completion(case_no.strip())
        return BaseResponse(
            data=_completion_preview_payload(result),
            message="已重新判定待補件訂單完整性",
        )
    except OrderIntakeTermsBootstrapError as error:
        raise _workflow_http_error(error, correlation_id) from error
    except OperationalError as error:
        raise _database_http_error(error, correlation_id) from error
    except Exception as error:
        raise internal_query_error(
            "order_intake_completion_preview_failed",
            "待補件訂單完整性重新判定失敗。",
            correlation_id,
        ) from error


@router.post(
    "/{case_no}/intake-completion/apply",
    response_model=BaseResponse[OrderIntakeCompletionReceiptView],
)
def apply_order_intake_completion(
    body: OrderIntakeCompletionApplyBody,
    case_no: str = Path(..., min_length=1, max_length=50),
    idempotency_key: _IdempotencyHeader = ...,
    correlation_id: _CorrelationHeader = ...,
    principal: AdminPrincipal = Depends(require_persisted_admin),
    application: OrderIntakeTermsBootstrapApplication = Depends(
        get_order_intake_terms_bootstrap_application
    ),
):
    try:
        result = application.apply_completion(
            case_no.strip(),
            body.expected_lifecycle_version,
            body.preview_fingerprint,
            idempotency_key,
            str(principal.username or "").strip(),
            body.reason.strip(),
        )
        return BaseResponse(
            data=_completion_receipt_payload(result),
            message="待補件訂單已恢復為洽談中",
        )
    except OrderIntakeTermsBootstrapError as error:
        raise _workflow_http_error(error, correlation_id) from error
    except OperationalError as error:
        raise _database_http_error(error, correlation_id) from error
    except Exception as error:
        raise internal_query_error(
            "order_intake_completion_apply_failed",
            "待補件訂單狀態恢復失敗。",
            correlation_id,
        ) from error


def _preview_payload(result):
    return {
        "case_no": result.case_no,
        "lifecycle_version": result.lifecycle_version,
        "before_start_date": result.before_start_date,
        "before_service_days": result.before_service_days,
        "after_start_date": result.after_start_date,
        "after_service_days": result.after_service_days,
        "changed_fields": list(result.changed_fields),
        "blockers": list(result.blockers),
        "apply_allowed": result.apply_allowed,
        "preview_fingerprint": result.preview_fingerprint,
    }


def _receipt_payload(result):
    return {
        "receipt_key": result.receipt_key,
        "case_no": result.case_no,
        "lifecycle_version": result.lifecycle_version,
        "start_date": result.start_date,
        "service_days": result.service_days,
        "changed_fields": list(result.changed_fields),
        "preview_fingerprint": result.preview_fingerprint,
        "replayed": result.replayed,
    }


def _completion_preview_payload(result):
    return {
        "case_no": result.case_no,
        "lifecycle_version": result.lifecycle_version,
        "current_status": result.current_status.value,
        "target_status": result.target_status.value,
        "missing_fields": list(result.missing_fields),
        "blockers": list(result.blockers),
        "apply_allowed": result.apply_allowed,
        "preview_fingerprint": result.preview_fingerprint,
    }


def _completion_receipt_payload(result):
    return {
        "receipt_key": result.receipt_key,
        "case_no": result.case_no,
        "lifecycle_version": result.lifecycle_version,
        "status": result.status.value,
        "preview_fingerprint": result.preview_fingerprint,
        "replayed": result.replayed,
    }


def _workflow_http_error(error, correlation_id):
    if error.code in {
        "order_intake_terms_bootstrap_case_not_found",
        "order_intake_completion_case_not_found",
    }:
        return typed_http_error(
            404,
            "not_found",
            error.code,
            "找不到指定訂單。",
            correlation_id,
        )
    if error.code in {
        "order_intake_terms_bootstrap_stale_preview",
        "order_intake_terms_bootstrap_idempotency_key_conflict",
        "order_intake_terms_bootstrap_blocked",
        "order_intake_completion_stale_preview",
        "order_intake_completion_idempotency_key_conflict",
        "order_intake_completion_blocked",
    }:
        exc = typed_http_error(
            409,
            "conflict",
            error.code,
            "補件條件已變更、冪等鍵衝突，或目前訂單不可套用。",
            correlation_id,
        )
        if error.blockers:
            exc.detail["error"]["domain_blockers"] = list(error.blockers)
        return exc
    return typed_http_error(
        422,
        "validation",
        error.code,
        "待補件訂單資料未通過驗證。",
        correlation_id,
    )


def _client_name_http_error(error: ValueError, correlation_id: str):
    code = str(error)
    if code == "client_not_found":
        return typed_http_error(
            404,
            "not_found",
            code,
            "找不到指定訂單的客戶資料。",
            correlation_id,
        )
    if code in {"stale_preview", "idempotency_key_conflict"}:
        return typed_http_error(
            409,
            "conflict",
            code,
            "客戶姓名資料已變更，請重新預覽後再補件。",
            correlation_id,
        )
    return typed_http_error(
        422,
        "validation",
        code or "order_intake_client_name_invalid",
        "客戶姓名未通過驗證。",
        correlation_id,
    )


def _database_http_error(error, correlation_id):
    retryable = bool(error.args) and error.args[0] in {1205, 1213}
    return typed_http_error(
        503 if retryable else 500,
        "unavailable" if retryable else "internal",
        (
            "order_intake_terms_bootstrap_database_unavailable"
            if retryable
            else "order_intake_terms_bootstrap_database_failed"
        ),
        (
            "補件資料庫暫時忙碌，請重新 Preview 後再試。"
            if retryable
            else "補件資料庫操作失敗。"
        ),
        correlation_id,
        retryable=retryable,
    )


__all__ = ["router"]
