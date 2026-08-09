"""Framework-neutral client for the canonical case bootstrap API."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, TypeVar

import requests
from pydantic import BaseModel, ValidationError

from api.schemas.base import BaseResponse
from api.schemas.case_architecture_bootstrap import (
    CaseArchitectureBootstrapPreviewView,
    CaseArchitectureBootstrapReceiptView,
    CaseArchitectureBootstrapStatusView,
    CaseArchitectureBootstrapTypedErrorView,
)


T = TypeVar("T", bound=BaseModel)


@dataclass(slots=True)
class CaseArchitectureBootstrapApiError(RuntimeError):
    status_code: int | None
    error: CaseArchitectureBootstrapTypedErrorView

    def __str__(self) -> str:
        return self.error.message


class CaseArchitectureBootstrapApiClient:
    def __init__(
        self,
        *,
        base_url: str,
        headers: Mapping[str, str],
        timeout: float = 15.0,
        session: requests.Session | None = None,
    ) -> None:
        self._base_url = _required_text(base_url, "base_url").rstrip("/")
        self._headers = {str(key): str(value) for key, value in headers.items()}
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        self._timeout = float(timeout)
        self._session = session or requests.Session()

    def status(self, case_no: str) -> CaseArchitectureBootstrapStatusView:
        return self._request(
            "GET",
            f"/api/v1/cases/{_case_no(case_no)}/architecture-bootstrap/status",
            response_type=CaseArchitectureBootstrapStatusView,
        )

    def preview(
        self,
        case_no: str,
        intent: Mapping[str, Any],
        *,
        correlation_id: str,
    ) -> CaseArchitectureBootstrapPreviewView:
        return self._request(
            "POST",
            f"/api/v1/cases/{_case_no(case_no)}/architecture-bootstrap/preview",
            payload=intent,
            command_headers={"X-Correlation-ID": _required_text(correlation_id, "correlation_id")},
            response_type=CaseArchitectureBootstrapPreviewView,
        )

    def apply(
        self,
        case_no: str,
        preview: CaseArchitectureBootstrapPreviewView,
        *,
        reason: str,
        idempotency_key: str,
        correlation_id: str,
    ) -> CaseArchitectureBootstrapReceiptView:
        return self._request(
            "POST",
            f"/api/v1/cases/{_case_no(case_no)}/architecture-bootstrap/apply",
            payload=_apply_payload(preview, reason),
            command_headers={
                "Idempotency-Key": _required_text(idempotency_key, "idempotency_key"),
                "X-Correlation-ID": _required_text(correlation_id, "correlation_id"),
            },
            response_type=CaseArchitectureBootstrapReceiptView,
        )

    def _request(
        self,
        method: str,
        path: str,
        *,
        response_type: type[T],
        payload: Mapping[str, Any] | None = None,
        command_headers: Mapping[str, str] | None = None,
    ) -> T:
        response = self._send(method, path, payload, command_headers)
        if not response.ok:
            raise _http_error(response)
        return _validated_data(response, response_type)

    def _send(self, method, path, payload, command_headers):
        try:
            return self._session.request(
                method,
                f"{self._base_url}{path}",
                headers={**self._headers, **dict(command_headers or {})},
                json=dict(payload) if payload is not None else None,
                timeout=self._timeout,
            )
        except requests.RequestException as error:
            raise _client_error(
                None,
                "unavailable",
                "case_bootstrap_transport_error",
                "無法連線至案件架構初始化 API。",
                retryable=True,
            ) from error


def _apply_payload(preview, reason):
    return {
        "client_payment_policy_version": preview.client_payment_policy_version,
        "client_hourly_rate_ntd": preview.client_hourly_rate_ntd,
        "deposit_service_days": preview.deposit_service_days,
        "deposit_due_date": preview.deposit_due_date.isoformat(),
        "first_payment_due_date": preview.first_payment_due_date.isoformat(),
        "payroll_policy_version": preview.payroll_policy_version,
        "expected_order_version": preview.order_version,
        "preview_fingerprint": preview.preview_fingerprint,
        "reason": _required_text(reason, "reason"),
    }


def _validated_data(response, response_type):
    try:
        envelope = BaseResponse[response_type].model_validate(response.json())
    except (ValueError, ValidationError, TypeError) as error:
        raise _client_error(response.status_code, "internal", "case_bootstrap_invalid_response", "案件架構初始化 API 回傳格式不正確。") from error
    if not envelope.success or envelope.data is None:
        raise _client_error(response.status_code, "internal", "case_bootstrap_invalid_response", "案件架構初始化 API 回傳格式不正確。")
    return envelope.data


def _http_error(response):
    try:
        detail = response.json().get("detail")
        error = CaseArchitectureBootstrapTypedErrorView.model_validate(detail["error"])
        return CaseArchitectureBootstrapApiError(response.status_code, error)
    except (AttributeError, KeyError, TypeError, ValueError, ValidationError):
        retryable = response.status_code in {502, 503, 504}
        return _client_error(response.status_code, "unavailable" if retryable else "internal", "case_bootstrap_request_failed", "案件架構初始化 API 請求失敗。", retryable=retryable)


def _client_error(status_code, category, code, message, *, retryable=False):
    return CaseArchitectureBootstrapApiError(
        status_code,
        CaseArchitectureBootstrapTypedErrorView(
            category=category,
            code=code,
            message=message,
            correlation_id="client",
            retryable=retryable,
        ),
    )


def _case_no(value: object) -> str:
    return _required_text(value, "case_no")


def _required_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} is required")
    return value.strip()


__all__ = ["CaseArchitectureBootstrapApiClient", "CaseArchitectureBootstrapApiError"]
