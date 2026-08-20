"""
File: typed_errors.py
Description: 統一受控管理端 namespace 的 correlation 與 Global typed error HTTP 邊界。
"""

from __future__ import annotations

import logging
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.exception_handlers import (
    http_exception_handler as default_http_exception_handler,
    request_validation_exception_handler as default_request_validation_handler,
)
from fastapi.exceptions import RequestValidationError, ResponseValidationError
from pydantic import ValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import JSONResponse, PlainTextResponse, Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from api.schemas.errors import (
    GlobalErrorCategory,
    GlobalFieldErrorView,
    GlobalTypedErrorResponseView,
    GlobalTypedErrorView,
)


LOGGER = logging.getLogger("labor_union.api.typed_errors")
CORRELATION_HEADER: Final = "X-Correlation-ID"
CORRELATION_PATTERN: Final = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,190}$")
CONTROLLED_PREFIXES: Final = ("/api/v1", "/internal/v1")


@dataclass(frozen=True, slots=True)
class LegacyErrorSpec:
    category: GlobalErrorCategory
    message: str
    retryable: bool


LEGACY_ERROR_ALLOWLIST: Final[dict[str, LegacyErrorSpec]] = {
    "mfa_enrollment_required": LegacyErrorSpec(
        GlobalErrorCategory.FORBIDDEN, "請完成 MFA 綁定後再登入", False
    ),
    "login_rate_limited": LegacyErrorSpec(
        GlobalErrorCategory.UNAVAILABLE, "登入嘗試過於頻繁，請稍後再試", True
    ),
    "invalid_credentials_or_factor": LegacyErrorSpec(
        GlobalErrorCategory.FORBIDDEN, "帳號、密碼或驗證碼錯誤", False
    ),
    "admin_auth_unavailable": LegacyErrorSpec(
        GlobalErrorCategory.UNAVAILABLE, "管理員驗證服務暫時無法使用", True
    ),
    "admin_session_schema_not_ready": LegacyErrorSpec(
        GlobalErrorCategory.UNAVAILABLE, "管理員驗證服務暫時無法使用", True
    ),
    "admin_session_storage_unavailable": LegacyErrorSpec(
        GlobalErrorCategory.UNAVAILABLE, "管理員驗證服務暫時無法使用", True
    ),
    "admin_mfa_unavailable": LegacyErrorSpec(
        GlobalErrorCategory.UNAVAILABLE, "管理員驗證服務暫時無法使用", True
    ),
    "mfa_secret_unavailable": LegacyErrorSpec(
        GlobalErrorCategory.UNAVAILABLE, "MFA 驗證服務暫時無法使用", True
    ),
    "mfa_challenge_expired": LegacyErrorSpec(
        GlobalErrorCategory.CONFLICT, "MFA 綁定已失效或驗證碼錯誤", False
    ),
    "internal_service_authentication_unavailable": LegacyErrorSpec(
        GlobalErrorCategory.UNAVAILABLE, "Internal service authentication is unavailable.", False
    ),
    "internal_service_authentication_failed": LegacyErrorSpec(
        GlobalErrorCategory.FORBIDDEN, "Internal service authentication failed.", False
    ),
    "internal_service_operation_forbidden": LegacyErrorSpec(
        GlobalErrorCategory.FORBIDDEN, "The authenticated service cannot run this operation.", False
    ),
}

LEGACY_STRING_ALLOWLIST: Final[dict[str, tuple[str, str]]] = {
    "缺少有效的管理員 Session": ("admin_session_required", "缺少有效的管理員 Session"),
    "管理員 Session 已失效或過期": ("admin_session_expired", "管理員 Session 已失效或過期"),
    "管理員 Session 已失效": ("admin_session_expired", "管理員 Session 已失效或過期"),
    "僅 root 帳號可管理帳號中心": ("root_access_required", "僅 root 帳號可管理帳號中心"),
    "找不到登入端點": ("resource_not_found", "找不到要求的資源"),
}


def is_controlled_namespace(path: str) -> bool:
    """只對正式管理端 JSON namespace 套用本邊界。"""
    return any(path == prefix or path.startswith(f"{prefix}/") for prefix in CONTROLLED_PREFIXES)


class CorrelationBoundaryMiddleware:
    """在 FastAPI parameter validation 前建立唯一 correlation header。"""

    def __init__(self, app: ASGIApp) -> None:
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not is_controlled_namespace(str(scope.get("path", ""))):
            await self._app(scope, receive, send)
            return

        header_values = [
            value
            for name, value in scope.get("headers", [])
            if name.lower() == b"x-correlation-id"
        ]
        correlation_id, should_reject = _resolve_correlation(header_values)
        state = scope.setdefault("state", {})
        state["correlation_id"] = correlation_id

        async def send_with_correlation(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = [
                    (name, value)
                    for name, value in message.get("headers", [])
                    if name.lower() != b"x-correlation-id"
                ]
                headers.append((b"x-correlation-id", correlation_id.encode("ascii")))
                message = {**message, "headers": headers}
            await send(message)

        # Replace any incoming spelling/duplicates with exactly one canonical
        # header before FastAPI resolves Header parameters.
        scope["headers"] = [
            (name, value)
            for name, value in scope.get("headers", [])
            if name.lower() != b"x-correlation-id"
        ] + [(b"x-correlation-id", correlation_id.encode("ascii"))]

        if should_reject:
            response = _typed_response(
                422,
                _error_view(
                    GlobalErrorCategory.VALIDATION,
                    "invalid_correlation_id",
                    "X-Correlation-ID 格式不符合契約",
                    correlation_id,
                    field_errors=[
                        GlobalFieldErrorView(
                            field="header.x-correlation-id",
                            code="invalid_correlation_id",
                            message="欄位格式不符合契約",
                        )
                    ],
                ),
            )
            await response(scope, receive, send_with_correlation)
            return

        await self._app(scope, receive, send_with_correlation)


def install_typed_error_handlers(app: FastAPI) -> None:
    """註冊受控 namespace 的完整 FastAPI exception matrix。"""
    app.add_exception_handler(HTTPException, _handle_fastapi_http_exception)
    app.add_exception_handler(StarletteHTTPException, _handle_starlette_http_exception)
    app.add_exception_handler(RequestValidationError, _handle_request_validation)
    app.add_exception_handler(ResponseValidationError, _handle_response_validation)
    app.add_exception_handler(Exception, _handle_unexpected_exception)


async def _handle_fastapi_http_exception(request: Request, exc: Exception) -> Response:
    if not isinstance(exc, HTTPException):
        return PlainTextResponse("Internal Server Error", status_code=500)
    if not is_controlled_namespace(request.url.path):
        return await default_http_exception_handler(request, exc)
    return _http_error_response(request, exc)


async def _handle_starlette_http_exception(request: Request, exc: Exception) -> Response:
    if not isinstance(exc, StarletteHTTPException):
        return PlainTextResponse("Internal Server Error", status_code=500)
    if not is_controlled_namespace(request.url.path):
        return await default_http_exception_handler(request, exc)
    return _http_error_response(request, exc)


async def _handle_request_validation(request: Request, exc: Exception) -> Response:
    if not isinstance(exc, RequestValidationError):
        return PlainTextResponse("Internal Server Error", status_code=500)
    if not is_controlled_namespace(request.url.path):
        return await default_request_validation_handler(request, exc)
    field_errors = sorted(
        (_validation_field_error(item) for item in exc.errors()),
        key=lambda item: (item.field, item.code, item.message),
    )
    return _typed_response(
        422,
        _error_view(
            GlobalErrorCategory.VALIDATION,
            "request_validation_error",
            "請求欄位不符合契約",
            _request_correlation(request),
            field_errors=field_errors,
        ),
    )


async def _handle_response_validation(request: Request, exc: Exception) -> Response:
    if not isinstance(exc, ResponseValidationError):
        return PlainTextResponse("Internal Server Error", status_code=500)
    if not is_controlled_namespace(request.url.path):
        return PlainTextResponse("Internal Server Error", status_code=500)
    LOGGER.error("Controlled API response validation failed")
    return _typed_response(
        500,
        _error_view(
            GlobalErrorCategory.INTERNAL,
            "response_contract_mismatch",
            "伺服器回應不符合公開契約",
            _request_correlation(request),
        ),
    )


async def _handle_unexpected_exception(request: Request, exc: Exception) -> Response:
    if not is_controlled_namespace(request.url.path):
        return PlainTextResponse("Internal Server Error", status_code=500)
    LOGGER.error("Unhandled exception at controlled API boundary")
    return _typed_response(
        500,
        _error_view(
            GlobalErrorCategory.INTERNAL,
            "internal_error",
            "伺服器發生未預期錯誤",
            _request_correlation(request),
        ),
    )


def _http_error_response(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    correlation_id = _request_correlation(request)
    typed = _strict_typed_error(exc.detail)
    if typed is not None:
        error = typed.model_copy(update={"correlation_id": correlation_id})
    else:
        error = _legacy_or_fallback_error(exc.status_code, exc.detail, correlation_id, exc.headers)
    return _typed_response(exc.status_code, error, headers=exc.headers)


def _strict_typed_error(detail: object) -> GlobalTypedErrorView | None:
    if not isinstance(detail, Mapping):
        return None
    candidate = detail.get("error")
    try:
        # The model's strict config protects primitive fields.  Pydantic's
        # call-level strict mode would reject JSON enum strings before enum
        # validation, so keep the transport boundary JSON-compatible here.
        return GlobalTypedErrorView.model_validate(candidate)
    except ValidationError:
        return None


def _legacy_or_fallback_error(
    status_code: int,
    detail: object,
    correlation_id: str,
    headers: Mapping[str, str] | None,
) -> GlobalTypedErrorView:
    if isinstance(detail, Mapping):
        code = detail.get("code")
        if not isinstance(code, str):
            nested = detail.get("error")
            if isinstance(nested, Mapping):
                code = nested.get("code")
        if isinstance(code, str) and code in LEGACY_ERROR_ALLOWLIST:
            spec = LEGACY_ERROR_ALLOWLIST[code]
            return _error_view(spec.category, code, spec.message, correlation_id, retryable=spec.retryable)
    if isinstance(detail, str) and detail in LEGACY_STRING_ALLOWLIST:
        code, message = LEGACY_STRING_ALLOWLIST[detail]
        return _error_view(_status_category(status_code), code, message, correlation_id)
    code, message = _status_fallback(status_code)
    retryable = status_code == 429 or (
        status_code in {502, 503, 504}
        and headers is not None
        and any(key.lower() == "retry-after" for key in headers)
    )
    return _error_view(_status_category(status_code), code, message, correlation_id, retryable=retryable)


def _resolve_correlation(header_values: list[bytes]) -> tuple[str, bool]:
    if not header_values:
        return uuid4().hex, False
    if len(header_values) != 1:
        return uuid4().hex, True
    try:
        candidate = header_values[0].decode("ascii")
    except UnicodeDecodeError:
        return uuid4().hex, True
    if CORRELATION_PATTERN.fullmatch(candidate) is None:
        return uuid4().hex, True
    return candidate, False


def _request_correlation(request: Request) -> str:
    value = getattr(request.state, "correlation_id", None)
    if isinstance(value, str) and CORRELATION_PATTERN.fullmatch(value):
        return value
    return uuid4().hex


def _validation_field_error(item: Mapping[str, object]) -> GlobalFieldErrorView:
    raw_location = item.get("loc")
    location = list(raw_location) if isinstance(raw_location, (list, tuple)) else ["body"]
    root = str(location[0]).lower() if location else "body"
    tail = [str(part).lower() for part in location[1:]]
    field = ".".join([root, *tail])
    raw_code = str(item.get("type", "invalid"))
    code = re.sub(r"[^a-z0-9_]+", "_", raw_code.lower()).strip("_") or "invalid"
    return GlobalFieldErrorView(field=field, code=code, message="欄位格式不符合契約")


def _error_view(
    category: GlobalErrorCategory,
    code: str,
    message: str,
    correlation_id: str,
    *,
    field_errors: list[GlobalFieldErrorView] | None = None,
    domain_blockers: list[str] | None = None,
    retryable: bool = False,
    current_version: int | None = None,
) -> GlobalTypedErrorView:
    return GlobalTypedErrorView(
        category=category,
        code=code,
        message=message,
        field_errors=field_errors or [],
        domain_blockers=domain_blockers or [],
        retryable=retryable,
        correlation_id=correlation_id,
        current_version=current_version,
    )


def _typed_response(
    status_code: int,
    error: GlobalTypedErrorView,
    *,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    payload = GlobalTypedErrorResponseView(detail={"error": error})
    return JSONResponse(
        status_code=status_code,
        content=payload.model_dump(mode="json"),
        headers=dict(headers or {}),
    )


def _status_category(status_code: int) -> GlobalErrorCategory:
    if status_code in {400, 405, 422}:
        return GlobalErrorCategory.VALIDATION
    if status_code in {401, 403}:
        return GlobalErrorCategory.FORBIDDEN
    if status_code in {404, 410}:
        return GlobalErrorCategory.NOT_FOUND
    if status_code == 409:
        return GlobalErrorCategory.CONFLICT
    if status_code in {429, 502, 503, 504}:
        return GlobalErrorCategory.UNAVAILABLE
    return GlobalErrorCategory.INTERNAL


def _status_fallback(status_code: int) -> tuple[str, str]:
    fallbacks = {
        400: ("bad_request", "請求格式不正確"),
        401: ("authentication_required", "需要有效的管理員驗證"),
        403: ("access_forbidden", "目前身分無權執行此操作"),
        404: ("resource_not_found", "找不到要求的資源"),
        405: ("method_not_allowed", "此資源不接受指定的HTTP方法"),
        409: ("conflict", "資料版本或目前狀態發生衝突"),
        410: ("resource_retired", "要求的資源已停止提供"),
        422: ("request_validation_error", "請求欄位不符合契約"),
        429: ("rate_limited", "請求過於頻繁，請稍後再試"),
        502: ("upstream_unavailable", "上游服務暫時無法使用"),
        503: ("service_unavailable", "服務暫時無法使用"),
        504: ("upstream_timeout", "上游服務回應逾時"),
    }
    return fallbacks.get(status_code, ("internal_error", "伺服器發生未預期錯誤"))
