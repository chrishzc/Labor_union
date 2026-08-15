"""
File: internal_service_auth.py
Description: 驗證 Private API 的本機 shared key 或 Google OIDC caller，所有錯誤皆 fail closed。
"""

from __future__ import annotations

import hmac
import os
import re
from dataclasses import dataclass
from typing import Any

import requests
from cachecontrol import CacheControl
from fastapi import Header, HTTPException, Request, status
from google.auth.transport.requests import Request as GoogleAuthRequest
from google.oauth2 import id_token


LOCAL_ENVIRONMENTS = frozenset({"development", "dev", "local", "test"})
MINIMUM_SHARED_KEY_LENGTH = 32
SERVICE_NAME_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,99}")
SERVICE_ACCOUNT_EMAIL_SUFFIX = ".iam.gserviceaccount.com"
GOOGLE_OIDC_ISSUERS = frozenset({"accounts.google.com", "https://accounts.google.com"})
_GOOGLE_AUTH_REQUEST = GoogleAuthRequest(session=CacheControl(requests.Session()))


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
    """Authenticate a local shared-key caller or a production Google OIDC caller."""
    app_environment = os.getenv("APP_ENV", "").strip().lower()
    service_name = _validated_service_name(x_internal_service_name)
    if app_environment in LOCAL_ENVIRONMENTS:
        principal = _authenticate_local(service_name, x_internal_service_key)
    else:
        principal = _authenticate_google_oidc(service_name, authorization)
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


def _authenticate_google_oidc(
    service_name: str,
    authorization: str | None,
) -> InternalServicePrincipal:
    if os.getenv("INTERNAL_SERVICE_AUTH_MODE", "").strip().lower() != "google_oidc":
        raise _authentication_unavailable()
    audience = os.getenv("INTERNAL_SERVICE_OIDC_AUDIENCE", "").strip()
    expected_email = _allowed_oidc_callers().get(service_name)
    if not audience:
        raise _authentication_unavailable()
    if not expected_email:
        raise _authentication_failed()
    claims = _verified_claims(_bearer_token(authorization), audience)
    if not _claims_match_email(claims, expected_email):
        raise _authentication_failed()
    return InternalServicePrincipal(service_name, "google_oidc")


def _verified_claims(token: str, audience: str) -> dict[str, Any]:
    try:
        return _verify_google_oidc_token(token, audience)
    except Exception as error:
        raise _authentication_failed() from error


def _verify_google_oidc_token(token: str, audience: str) -> dict[str, Any]:
    claims = id_token.verify_oauth2_token(token, _GOOGLE_AUTH_REQUEST, audience)
    if claims.get("iss") not in GOOGLE_OIDC_ISSUERS:
        raise ValueError("Google OIDC issuer is invalid")
    return dict(claims)


def _allowed_oidc_callers() -> dict[str, str]:
    configured = os.getenv("INTERNAL_SERVICE_OIDC_ALLOWED_CALLERS", "").strip()
    callers: dict[str, str] = {}
    for entry in filter(None, (item.strip() for item in configured.split(","))):
        service_name, separator, email = entry.partition("=")
        valid_service = SERVICE_NAME_PATTERN.fullmatch(service_name) is not None
        valid_email = email.endswith(SERVICE_ACCOUNT_EMAIL_SUFFIX)
        if not separator or not valid_service or not valid_email or service_name in callers:
            raise _authentication_unavailable()
        callers[service_name] = email
    return callers


def _bearer_token(authorization: str | None) -> str:
    scheme, separator, token = (authorization or "").strip().partition(" ")
    if not separator or scheme.lower() != "bearer" or not token.strip():
        raise _authentication_failed()
    return token.strip()


def _claims_match_email(claims: dict[str, Any], expected_email: str) -> bool:
    email = str(claims.get("email", ""))
    return claims.get("email_verified") is True and hmac.compare_digest(email, expected_email)


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
