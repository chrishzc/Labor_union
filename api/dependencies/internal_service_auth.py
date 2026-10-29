"""
File: internal_service_auth.py
Description: 驗證 Private API 的本機 shared key 或 NAS 獨立機器憑證，所有錯誤皆 fail closed。
"""

from __future__ import annotations

import hmac
import hashlib
import os
import re
from dataclasses import dataclass

from fastapi import Header, HTTPException, Request, status
from infrastructure.runtime.worker_credentials import read_verifiers, LINE_MEDIA_SERVICE, LINE_OPERATIONS_SERVICE


LOCAL_ENVIRONMENTS = frozenset({"development", "dev", "local", "test"})
MINIMUM_SHARED_KEY_LENGTH = 32
SERVICE_NAME_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,99}")


@dataclass(frozen=True, slots=True)
class InternalServicePrincipal:
    service_name: str
    authentication_method: str


def require_internal_service(
    request: Request,
    authorization: str | None = Header(default=None),
    x_internal_service_key: str | None = Header(default=None),
    x_internal_service_name: str | None = Header(default=None),
) -> InternalServicePrincipal:
    """Bind a verified machine credential to its configured service identity."""
    app_environment = os.getenv("APP_ENV", "").strip().lower()
    service_name = _validated_service_name(x_internal_service_name)
    mode = os.getenv("INTERNAL_SERVICE_AUTH_MODE", "").strip().lower()
    if mode == "nas_service_token":
        if request.url.scheme != "https":
            raise HTTPException(status_code=426, detail={
                "code": "internal_service_https_required",
                "message": "Private machine operations require HTTPS.", "retryable": False,
            })
        principal = _authenticate_nas(service_name, authorization)
    elif app_environment in LOCAL_ENVIRONMENTS and mode in {"", "local_shared_key"}:
        principal = _authenticate_local(service_name, x_internal_service_key)
    else:
        raise _authentication_unavailable()
    if (principal.service_name == LINE_MEDIA_SERVICE
            and not request.url.path.startswith("/internal/v1/line-media/")):
        raise HTTPException(status_code=403, detail={
            "code": "internal_service_operation_forbidden",
            "message": "The photo credential cannot run other internal operations.",
            "retryable": False,
        })
    if (principal.service_name == LINE_OPERATIONS_SERVICE
            and not request.url.path.startswith("/internal/v1/line-operations/")):
        raise HTTPException(status_code=403, detail={
            "code": "internal_service_operation_forbidden",
            "message": "The LINE operations credential cannot run other internal operations.",
            "retryable": False,
        })
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


def _authenticate_nas(
    service_name: str,
    authorization: str | None,
) -> InternalServicePrincipal:
    operations = service_name == LINE_OPERATIONS_SERVICE
    setting = "LINE_OPERATIONS_CREDENTIALS_FILE" if operations else "INTERNAL_SERVICE_CREDENTIALS_FILE"
    path = os.getenv(setting, "").strip()
    try:
        verifiers = (read_verifiers(path, allowed_services=(LINE_OPERATIONS_SERVICE,))
                     if operations else read_verifiers(path))
    except (OSError, ValueError, TypeError):
        raise _authentication_unavailable() from None
    digest = hashlib.sha256(_bearer_token(authorization).encode("utf-8")).hexdigest()
    # Identity comes from the credential; the caller's header is only a claim.
    for configured_service, expected in verifiers.items():
        if hmac.compare_digest(digest, expected):
            if service_name not in {"unknown-internal-service", configured_service}:
                raise _authentication_failed()
            return InternalServicePrincipal(configured_service, "nas_service_token")
    raise _authentication_failed()


def _bearer_token(authorization: str | None) -> str:
    scheme, separator, token = (authorization or "").strip().partition(" ")
    if not separator or scheme.lower() != "bearer" or not token.strip():
        raise _authentication_failed()
    return token.strip()


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
