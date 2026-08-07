"""Framework-neutral client for anomaly registry and workflow endpoints."""

from __future__ import annotations

from collections.abc import Mapping
import requests
from typing import Any
from pydantic import ValidationError

from api.schemas.anomaly_registry import (
    AnomalyDetailView,
    AnomalySummaryView,
    AnomalyTypedErrorView,
    AnomalyWorkflowReceiptView,
    ClaimAnomalyBody,
    ResolveAnomalyBody,
)
from api.schemas.base import BaseResponse


class AnomalyRegistryApiError(RuntimeError):
    def __init__(self, status_code: int | None, error: AnomalyTypedErrorView) -> None:
        super().__init__(error.message)
        self.status_code = status_code
        self.error = error

    def __str__(self) -> str:
        return self.error.message


class AnomalyRegistryApiClient:
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

    def query_anomalies(
        self,
        *,
        active_only: bool = True,
        limit: int = 100,
        offset: int = 0,
        include_snapshot: bool = False,
    ) -> tuple[AnomalySummaryView, ...]:
        return self._request(
            "GET",
            "/api/v1/anomalies",
            params={
                "active_only": "true" if active_only else "false",
                "limit": int(limit),
                "offset": int(offset),
                "include_snapshot": "true" if include_snapshot else "false",
            },
            response_type=list[AnomalySummaryView],
        )

    def query_anomaly_detail(self, fingerprint: str) -> AnomalyDetailView:
        return self._request(
            "GET",
            f"/api/v1/anomalies/{_canonical_text(fingerprint, 'fingerprint')}",
            response_type=AnomalyDetailView,
        )

    def claim_anomaly(
        self,
        fingerprint: str,
        *,
        expected_workflow_version: int,
        idempotency_key: str,
        correlation_id: str,
    ) -> AnomalyWorkflowReceiptView:
        payload = ClaimAnomalyBody(
            expected_workflow_version=_nonnegative_int(
                expected_workflow_version,
                "expected_workflow_version",
            ),
        )
        headers = {
            "Idempotency-Key": _canonical_text(idempotency_key, "idempotency_key"),
            "X-Correlation-ID": _canonical_text(correlation_id, "correlation_id"),
        }
        return self._request(
            "POST",
            f"/api/v1/anomalies/{_canonical_text(fingerprint, 'fingerprint')}/claim",
            payload=payload.model_dump(),
            command_headers=headers,
            response_type=AnomalyWorkflowReceiptView,
        )

    def resolve_anomaly(
        self,
        fingerprint: str,
        *,
        expected_workflow_version: int,
        reason: str,
        idempotency_key: str,
        correlation_id: str,
    ) -> AnomalyWorkflowReceiptView:
        payload = ResolveAnomalyBody(
            expected_workflow_version=_nonnegative_int(
                expected_workflow_version,
                "expected_workflow_version",
            ),
            reason=_canonical_text(reason, "reason"),
        )
        headers = {
            "Idempotency-Key": _canonical_text(idempotency_key, "idempotency_key"),
            "X-Correlation-ID": _canonical_text(correlation_id, "correlation_id"),
        }
        return self._request(
            "POST",
            f"/api/v1/anomalies/{_canonical_text(fingerprint, 'fingerprint')}/resolve",
            payload=payload.model_dump(),
            command_headers=headers,
            response_type=AnomalyWorkflowReceiptView,
        )

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        payload: Mapping[str, Any] | None = None,
        command_headers: Mapping[str, str] | None = None,
        response_type: Any,
    ):
        response = self._send(method, path, params, payload, command_headers)
        if not response.ok:
            raise _http_error(response)
        return _validated_data(response, response_type)

    def _send(
        self,
        method: str,
        path: str,
        params: Mapping[str, Any] | None,
        payload: Mapping[str, Any] | None,
        command_headers: Mapping[str, str] | None,
    ):
        headers = {**self._headers, **dict(command_headers or {})}
        try:
            return self._session.request(
                method,
                f"{self._base_url}{path}",
                headers=headers,
                params=dict(params) if params is not None else None,
                json=dict(payload) if payload is not None else None,
                timeout=self._timeout,
            )
        except requests.RequestException as error:
            raise _client_error(
                None,
                "unavailable",
                "anomaly_registry_transport_error",
                "無法連線到異常註冊中心 API。",
                retryable=True,
            ) from error


def _validated_data(response, response_type):
    try:
        envelope = BaseResponse[response_type].model_validate(response.json())
    except (ValueError, TypeError, ValidationError) as error:
        raise _client_error(
            response.status_code,
            "internal",
            "anomaly_registry_invalid_response",
            "異常註冊中心 API 回傳格式不正確。",
        ) from error
    if not envelope.success or envelope.data is None:
        raise _client_error(
            response.status_code,
            "internal",
            "anomaly_registry_invalid_response",
            "異常註冊中心 API 回傳格式不正確。",
        )
    return envelope.data


def _http_error(response):
    try:
        body = response.json()
        detail = body.get("detail") if isinstance(body, dict) else None
        candidate = detail.get("error") if isinstance(detail, dict) else None
        error = AnomalyTypedErrorView.model_validate(candidate)
        return AnomalyRegistryApiError(response.status_code, error)
    except (ValueError, TypeError, ValidationError, AttributeError):
        retryable = response.status_code in {502, 503, 504}
        return _client_error(
            response.status_code,
            "unavailable" if retryable else "internal",
            "anomaly_registry_request_failed",
            "異常註冊中心 API 請求失敗。",
            retryable=retryable,
        )


def _client_error(
    status_code: int | None,
    category: str,
    code: str,
    message: str,
    *,
    retryable: bool = False,
) -> AnomalyRegistryApiError:
    return AnomalyRegistryApiError(
        status_code,
        AnomalyTypedErrorView(
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


def _nonnegative_int(value: int, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field_name} must be nonnegative integer")
    return value


__all__ = [
    "AnomalyRegistryApiClient",
    "AnomalyRegistryApiError",
]
