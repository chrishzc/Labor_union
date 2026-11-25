"""
File: internal_service_auth.py
Description: 驗證 Private API 的本機 shared key，所有錯誤皆 fail closed。
"""

from __future__ import annotations

import hmac
import os
import re
from dataclasses import dataclass

from fastapi import Header, HTTPException, Request, status


MINIMUM_SHARED_KEY_LENGTH = 32
SERVICE_NAME_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,99}")


@dataclass(frozen=True, slots=True)
class InternalServicePrincipal:
    service_name: str
    authentication_method: str


def require_internal_service(
    request: Request,
    x_internal_service_key: str | None = Header(default=None),
    x_internal_service_name: str | None = Header(default=None),
) -> InternalServicePrincipal:
    """Bind a verified machine credential to its configured service identity."""
    service_name = _validated_service_name(x_internal_service_name)
    mode = os.getenv("INTERNAL_SERVICE_AUTH_MODE", "").strip().lower()
    if mode not in {"", "local_shared_key"}:
        raise _authentication_unavailable()
    principal = _authenticate_local(service_name, x_internal_service_key)
    request.state.internal_service_principal = principal
    return principal


def require_operation_service(
    principal: InternalServicePrincipal,
    expected_service_name: str,
) -> None:
    if hmac.compare_digest(principal.service_name, expected_service_name):
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={
            "code": "internal_service_operation_forbidden",
            "message": "The authenticated service cannot run this operation.",
            "retryable": False,
        },
    )


def _authenticate_local(
    service_name: str,
    supplied_key: str | None,
) -> InternalServicePrincipal:
    configured_key = os.getenv("INTERNAL_SERVICE_SHARED_KEY", "").strip()
    if len(configured_key) < MINIMUM_SHARED_KEY_LENGTH:
        raise _authentication_unavailable()
    candidate = (supplied_key or "").strip()
    if not candidate or not hmac.compare_digest(configured_key, candidate):
        raise _authentication_failed()
    return InternalServicePrincipal(service_name, "local_shared_key")


def _validated_service_name(value: str | None) -> str:
    service_name = (value or "unknown-internal-service").strip()
    if SERVICE_NAME_PATTERN.fullmatch(service_name) is None:
        return "unknown-internal-service"
    return service_name


def _authentication_unavailable() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail={
            "code": "internal_service_authentication_unavailable",
            "message": "Internal service authentication is not configured for this environment.",
            "retryable": False,
        },
    )


def _authentication_failed() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={
            "code": "internal_service_authentication_failed",
            "message": "Internal service authentication failed.",
            "retryable": False,
        },
    )
