"""Typed HTTP client for authenticated private runtime operations."""

from __future__ import annotations

import os
import random
import time
from datetime import datetime, timezone
from socket import gethostname
from typing import Any, Callable

import requests
from google.auth import jwt
from google.auth.exceptions import DefaultCredentialsError, TransportError
from google.auth.transport.requests import Request as GoogleAuthRequest
from google.oauth2.id_token import fetch_id_token


DATABASE_CREDENTIAL_VARIABLES = (
    "DB_HOST",
    "DB_PORT",
    "DB_USER",
    "DB_PASSWORD",
    "DB_DATABASE",
    "MYSQL_HOST",
    "MYSQL_PORT",
    "MYSQL_USER",
    "MYSQL_PASSWORD",
    "MYSQL_DATABASE",
)


def discard_database_credentials() -> None:
    """Ensure a worker process cannot retain DB credentials inherited from its parent."""
    for variable_name in DATABASE_CREDENTIAL_VARIABLES:
        os.environ.pop(variable_name, None)


class PrivateOperationError(RuntimeError):
    def __init__(self, message: str, *, retryable: bool, code: str = "") -> None:
        super().__init__(message)
        self.retryable = retryable
        self.code = code


class GoogleOidcTokenProvider:
    def __init__(self) -> None:
        self._token = ""
        self._refresh_at_epoch = 0.0

    def __call__(self, audience: str) -> str:
        now = time.time()
        if self._token and now < self._refresh_at_epoch:
            return self._token
        token = fetch_id_token(GoogleAuthRequest(), audience)
        claims = jwt.decode(token, verify=False)
        expires_at = float(claims.get("exp", now + 60))
        self._token = token
        self._refresh_at_epoch = max(now, expires_at - 300)
        return token


class PrivateOperationsClient:
    # Transport, authentication and retry injections stay together as one immutable client policy.
    def __init__(
        self,
        service_name: str,
        *,
        base_url: str | None = None,
        shared_key: str | None = None,
        timeout_seconds: float = 55.0,
        auth_mode: str | None = None,
        oidc_audience: str | None = None,
        token_provider: Callable[[str], str] | None = None,
        max_attempts: int | None = None,
        retry_base_seconds: float = 0.5,
        retry_max_seconds: float = 5.0,
        sleep: Callable[[float], None] = time.sleep,
        random_fraction: Callable[[], float] = random.random,
    ) -> None:
        self._service_name = service_name
        self._base_url = (
            base_url or os.getenv("INTERNAL_API_BASE_URL", "http://127.0.0.1:8000")
        ).rstrip("/")
        self._shared_key = shared_key or os.getenv("INTERNAL_SERVICE_SHARED_KEY", "")
        self._timeout_seconds = timeout_seconds
        self._auth_mode = auth_mode or os.getenv("INTERNAL_SERVICE_AUTH_MODE", "local_shared_key")
        self._oidc_audience = oidc_audience or os.getenv("INTERNAL_SERVICE_OIDC_AUDIENCE", "")
        self._token_provider = token_provider or GoogleOidcTokenProvider()
        self._max_attempts = max_attempts or int(os.getenv("INTERNAL_API_MAX_ATTEMPTS", "3"))
        self._retry_base_seconds = retry_base_seconds
        self._retry_max_seconds = retry_max_seconds
        self._sleep = sleep
        self._random_fraction = random_fraction

    def check(self) -> None:
        self._post("/internal/v1/runtime/check", {})

    def readiness(self) -> dict[str, Any]:
        return self._post("/internal/v1/runtime/readiness", {})

    def run_durable_cycle(self, payload: dict[str, Any]) -> int:
        return int(self._post("/internal/v1/runtime/durable-jobs/run-once", payload)["processed"])

    def run_line_cycle(self, payload: dict[str, Any]) -> int:
        return int(self._post("/internal/v1/runtime/line/run-once", payload)["processed"])

    def run_knowledge_cycle(self, payload: dict[str, Any]) -> int:
        return int(self._post("/internal/v1/runtime/knowledge/run-once", payload)["processed"])

    def run_incident_maintenance_cycle(self, payload: dict[str, Any]) -> int:
        return int(
            self._post("/internal/v1/runtime/incident-maintenance/run-once", payload)["processed"]
        )

    def record_monitor_cycle(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._post("/internal/v1/runtime/monitor/record-cycle", payload)

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        attempts = max(1, self._max_attempts)
        for attempt_index in range(attempts):
            try:
                return self._post_once(path, payload)
            except PrivateOperationError as error:
                if not error.retryable or attempt_index + 1 >= attempts:
                    raise
                self._sleep(self._retry_delay(attempt_index))
        raise AssertionError("retry loop must return or raise")

    # Keep request, typed HTTP failure and response validation in one transport boundary.
    def _post_once(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            response = requests.post(
                self._base_url + path,
                json=payload,
                headers=self._request_headers(),
                timeout=self._timeout_seconds,
            )
        except requests.RequestException as error:
            raise PrivateOperationError(
                f"Private API unavailable: {type(error).__name__}",
                retryable=True,
            ) from error
        try:
            body = response.json()
        except (TypeError, ValueError) as error:
            raise PrivateOperationError(
                "Private API returned invalid JSON.",
                retryable=True,
            ) from error
        if response.status_code >= 400:
            raise _response_error(response.status_code, body)
        data = body.get("data") if isinstance(body, dict) else None
        if not isinstance(data, dict):
            raise PrivateOperationError("Private API returned an invalid response.", retryable=True)
        return data

    def _request_headers(self) -> dict[str, str]:
        headers = {"X-Internal-Service-Name": self._service_name}
        if self._auth_mode == "local_shared_key" and self._shared_key:
            headers["X-Internal-Service-Key"] = self._shared_key
            return headers
        if self._auth_mode == "google_oidc" and self._oidc_audience:
            headers["Authorization"] = f"Bearer {self._oidc_token()}"
            return headers
        raise PrivateOperationError(
            "Private API authentication is not configured.",
            retryable=False,
            code="internal_service_authentication_unavailable",
        )

    def _oidc_token(self) -> str:
        try:
            return self._token_provider(self._oidc_audience)
        except TransportError as error:
            raise PrivateOperationError(
                "Google OIDC token service is temporarily unavailable.",
                retryable=True,
                code="google_oidc_token_temporarily_unavailable",
            ) from error
        except DefaultCredentialsError as error:
            raise PrivateOperationError(
                "Google OIDC credentials are not configured.",
                retryable=False,
                code="google_oidc_credentials_unavailable",
            ) from error
        except Exception as error:
            raise PrivateOperationError(
                "Google OIDC token could not be created.",
                retryable=False,
                code="google_oidc_token_invalid",
            ) from error

    def _retry_delay(self, attempt_index: int) -> float:
        ceiling = min(
            self._retry_max_seconds,
            self._retry_base_seconds * (2 ** attempt_index),
        )
        return max(0.0, ceiling * self._random_fraction())


def runtime_identity(service_name: str, instance_id: str) -> dict[str, object]:
    return {
        "service_name": service_name,
        "instance_id": instance_id,
        "process_id": os.getpid(),
        "hostname": gethostname(),
        "started_at": datetime.now(timezone.utc).isoformat(),
        "release_version": _release_version(),
    }


def _release_version() -> str:
    return (
        os.getenv("APP_RELEASE_VERSION", "").strip()
        or os.getenv("K_REVISION", "").strip()
        or "local-development"
    )


def _response_error(status_code: int, body: object) -> PrivateOperationError:
    detail = body.get("detail") if isinstance(body, dict) else None
    typed = detail if isinstance(detail, dict) else {}
    retryable = typed.get("retryable")
    if not isinstance(retryable, bool):
        retryable = status_code >= 500
    code = str(typed.get("code", "private_api_http_error"))
    return PrivateOperationError(
        f"Private API returned HTTP {status_code} ({code}).",
        retryable=retryable,
        code=code,
    )
