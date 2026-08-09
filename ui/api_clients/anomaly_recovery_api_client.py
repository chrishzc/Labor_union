"""Typed recovery helpers for anomaly detail navigation entries."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
import requests
from pydantic import ValidationError

from api.schemas.anomaly_recovery import (
    AnomalyRecoveryContextView,
    AnomalyRecoveryTypedErrorView,
    RecoveryActionView,
)
from api.schemas.base import BaseResponse


class AnomalyRecoveryApiError(RuntimeError):
    def __init__(
        self,
        status_code: int | None,
        error: AnomalyRecoveryTypedErrorView,
    ) -> None:
        super().__init__(error.message)
        self.status_code = status_code
        self.error = error

    def __str__(self) -> str:
        return self.error.message


class AnomalyRecoveryApiClient:
    def __init__(
        self,
        *,
        base_url: str,
        headers: Mapping[str, str],
        timeout: float = 15.0,
        session: requests.Session | None = None,
    ) -> None:
        if not isinstance(base_url, str) or not base_url.strip():
            raise ValueError("base_url is required")
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        self._base_url = base_url.rstrip("/")
        self._headers = {str(key): str(value) for key, value in headers.items()}
        self._timeout = float(timeout)
        self._session = session or requests.Session()

    def query_recovery_context(self, fingerprint: str) -> AnomalyRecoveryContextView:
        return self._request(
            "GET",
            f"/api/v1/anomaly-recovery/{_canonical_text(fingerprint, 'fingerprint')}",
            response_type=AnomalyRecoveryContextView,
        )

    def query_recovery_preview_link(
        self,
        fingerprint: str,
        action_code: str,
    ) -> RecoveryActionView:
        return self._request(
            "GET",
            f"/api/v1/anomaly-recovery/{_canonical_text(fingerprint, 'fingerprint')}/actions/{_canonical_text(action_code, 'action_code')}",
            response_type=RecoveryActionView,
        )

    def _request(
        self,
        method: str,
        path: str,
        *,
        response_type: Any,
    ):
        response = self._send(method, path)
        if not response.ok:
            raise _http_error(response)
        return _validated_data(response, response_type)

    def _send(self, method: str, path: str):
        try:
            return self._session.request(
                method,
                f"{self._base_url}{path}",
                headers=self._headers,
                timeout=self._timeout,
            )
        except requests.RequestException as error:
            raise _client_error(
                None,
                "unavailable",
                "anomaly_recovery_transport_error",
                "無法連線到異常修復入口 API。",
                retryable=True,
            ) from error


def _validated_data(response, response_type):
    try:
        envelope = BaseResponse[response_type].model_validate(response.json())
    except (ValueError, TypeError, ValidationError) as error:
        raise _client_error(
            response.status_code,
            "internal",
            "anomaly_recovery_invalid_response",
            "異常修復 API 回傳格式不正確。",
        ) from error
    if not envelope.success or envelope.data is None:
        raise _client_error(
            response.status_code,
            "internal",
            "anomaly_recovery_invalid_response",
            "異常修復 API 回傳格式不正確。",
        )
    return envelope.data


def _http_error(response):
    try:
        body = response.json()
        detail = body.get("detail") if isinstance(body, dict) else None
        candidate = detail.get("error") if isinstance(detail, dict) else None
        error = AnomalyRecoveryTypedErrorView.model_validate(candidate)
        return AnomalyRecoveryApiError(response.status_code, error)
    except (ValueError, TypeError, ValidationError, AttributeError):
        retryable = response.status_code in {502, 503, 504}
        return _client_error(
            response.status_code,
            "unavailable" if retryable else "internal",
            "anomaly_recovery_request_failed",
            "異常修復 API 請求失敗。",
            retryable=retryable,
        )


def _client_error(
    status_code: int | None,
    category: str,
    code: str,
    message: str,
    *,
    retryable: bool = False,
) -> AnomalyRecoveryApiError:
    return AnomalyRecoveryApiError(
        status_code,
        AnomalyRecoveryTypedErrorView(
            category=category,
            code=code,
            message=message,
            correlation_id="client",
            retryable=retryable,
        ),
    )


def _canonical_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} is required")
    return value.strip()


__all__ = [
    "AnomalyRecoveryApiClient",
    "AnomalyRecoveryApiError",
]
