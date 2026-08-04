"""Framework-neutral client for the canonical Actual Start API."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from typing import TypeVar

import requests
from pydantic import BaseModel, ValidationError

from api.schemas.base import BaseResponse
from api.schemas.order_actual_start import (
    ActualStartPreviewView,
    ActualStartQueryView,
    ActualStartReceiptView,
    ActualStartTypedErrorView,
)


T = TypeVar("T", bound=BaseModel)


@dataclass(slots=True)
class ActualStartApiError(RuntimeError):
    status_code: int | None
    error: ActualStartTypedErrorView

    def __str__(self) -> str:
        return self.error.message


class ActualStartApiClient:
    def __init__(self, *, base_url: str, headers: Mapping[str, str], timeout: float = 15.0, session: requests.Session | None = None) -> None:
        self._base_url = _required_text(base_url, "base_url").rstrip("/")
        self._headers = {str(key): str(value) for key, value in headers.items()}
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        self._timeout = float(timeout)
        self._session = session or requests.Session()

    def query(self, case_no: str) -> ActualStartQueryView:
        return self._request("GET", _path(case_no), response_type=ActualStartQueryView)

    def preview(self, case_no: str, new_actual_start_date: date, *, correlation_id: str) -> ActualStartPreviewView:
        return self._request(
            "POST", f"{_path(case_no)}/preview",
            payload={"new_actual_start_date": new_actual_start_date.isoformat()},
            command_headers={"X-Correlation-ID": _required_text(correlation_id, "correlation_id")},
            response_type=ActualStartPreviewView,
        )

    def apply(self, case_no: str, preview: ActualStartPreviewView, *, reason: str, idempotency_key: str, correlation_id: str) -> ActualStartReceiptView:
        return self._request(
            "POST", f"{_path(case_no)}/apply",
            payload=_apply_payload(preview, reason),
            command_headers={
                "Idempotency-Key": _required_text(idempotency_key, "idempotency_key"),
                "X-Correlation-ID": _required_text(correlation_id, "correlation_id"),
            },
            response_type=ActualStartReceiptView,
        )

    def _request(self, method, path, *, response_type: type[T], payload=None, command_headers=None) -> T:
        response = self._send(method, path, payload, command_headers)
        if not response.ok:
            raise _http_error(response)
        return _validated_data(response, response_type)

    def _send(self, method, path, payload, command_headers):
        try:
            return self._session.request(
                method, f"{self._base_url}{path}",
                headers={**self._headers, **dict(command_headers or {})},
                json=payload, timeout=self._timeout,
            )
        except requests.RequestException as error:
            raise _client_error(None, "unavailable", "actual_start_transport_error", "無法連線至實際開工 API。", retryable=True) from error


def _path(case_no: object) -> str:
    return f"/api/v1/orders/{_required_text(case_no, 'case_no')}/actual-start"


def _apply_payload(preview, reason):
    return {
        "new_actual_start_date": preview.after_actual_start_date.isoformat(),
        "expected_order_version": preview.order_version,
        "expected_scheduling_version": preview.scheduling_version,
        "expected_client_finance_version": preview.client_finance_version,
        "expected_payroll_version": preview.payroll_version,
        "preview_fingerprint": preview.preview_fingerprint,
        "reason": _required_text(reason, "reason"),
    }


def _validated_data(response, response_type):
    try:
        envelope = BaseResponse[response_type].model_validate(response.json())
    except (ValueError, ValidationError, TypeError) as error:
        raise _client_error(response.status_code, "internal", "actual_start_invalid_response", "實際開工 API 回傳格式不正確。") from error
    if not envelope.success or envelope.data is None:
        raise _client_error(response.status_code, "internal", "actual_start_invalid_response", "實際開工 API 回傳格式不正確。")
    return envelope.data


def _http_error(response):
    try:
        detail = response.json().get("detail")
        error = ActualStartTypedErrorView.model_validate(detail["error"])
        return ActualStartApiError(response.status_code, error)
    except (AttributeError, KeyError, TypeError, ValueError, ValidationError):
        retryable = response.status_code in {502, 503, 504}
        return _client_error(response.status_code, "unavailable" if retryable else "internal", "actual_start_request_failed", "實際開工 API 請求失敗。", retryable=retryable)


def _client_error(status_code, category, code, message, *, retryable=False):
    return ActualStartApiError(status_code, ActualStartTypedErrorView(category=category, code=code, message=message, correlation_id="client", retryable=retryable))


def _required_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} is required")
    return value.strip()


__all__ = ["ActualStartApiClient", "ActualStartApiError"]
