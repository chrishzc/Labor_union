"""Framework-neutral client for the canonical Order Cancellation API."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from typing import TypeVar

import requests
from pydantic import BaseModel, ValidationError

from api.schemas.base import BaseResponse
from api.schemas.order_cancellation import (
    OrderCancellationPreviewView,
    OrderCancellationQueryView,
    OrderCancellationReceiptView,
    OrderCancellationTypedErrorView,
)


T = TypeVar("T", bound=BaseModel)


@dataclass(slots=True)
class OrderCancellationApiError(RuntimeError):
    status_code: int | None
    error: OrderCancellationTypedErrorView

    def __str__(self) -> str:
        return self.error.message


class OrderCancellationApiClient:
    def __init__(self, *, base_url: str, headers: Mapping[str, str], timeout: float = 15.0, session: requests.Session | None = None) -> None:
        self._base_url = _required_text(base_url, "base_url").rstrip("/")
        self._headers = {str(key): str(value) for key, value in headers.items()}
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        self._timeout = float(timeout)
        self._session = session or requests.Session()

    def query(self, case_no: str) -> OrderCancellationQueryView:
        return self._request("GET", _path(case_no), response_type=OrderCancellationQueryView)

    def preview(self, case_no: str, confirmed_service_days: Sequence[Mapping[str, object]], *, correlation_id: str) -> OrderCancellationPreviewView:
        return self._request(
            "POST", f"{_path(case_no)}/preview",
            payload={"confirmed_service_days": _service_day_payloads(confirmed_service_days)},
            command_headers={"X-Correlation-ID": _required_text(correlation_id, "correlation_id")},
            response_type=OrderCancellationPreviewView,
        )

    def apply(self, case_no: str, confirmed_service_days: Sequence[Mapping[str, object]], preview: OrderCancellationPreviewView, *, reason: str, idempotency_key: str, correlation_id: str) -> OrderCancellationReceiptView:
        return self._request(
            "POST", f"{_path(case_no)}/apply",
            payload={
                "confirmed_service_days": _service_day_payloads(confirmed_service_days),
                "expected_order_version": preview.order_version,
                "expected_scheduling_version": preview.scheduling_version,
                "expected_client_finance_version": preview.client_finance_version,
                "expected_payroll_version": preview.payroll_version,
                "preview_fingerprint": preview.preview_fingerprint,
                "reason": _required_text(reason, "reason"),
            },
            command_headers={
                "Idempotency-Key": _required_text(idempotency_key, "idempotency_key"),
                "X-Correlation-ID": _required_text(correlation_id, "correlation_id"),
            },
            response_type=OrderCancellationReceiptView,
        )

    def _request(self, method, path, *, response_type: type[T], payload=None, command_headers=None) -> T:
        response = self._send(method, path, payload, command_headers)
        if not response.ok:
            raise _http_error(response)
        return _validated_data(response, response_type)

    def _send(self, method, path, payload, command_headers):
        try:
            return self._session.request(method, f"{self._base_url}{path}", headers={**self._headers, **dict(command_headers or {})}, json=payload, timeout=self._timeout)
        except requests.RequestException as error:
            raise _client_error(None, "unavailable", "order_cancellation_transport_error", "無法連線至訂單取消 API。", retryable=True) from error


def _path(case_no: object) -> str:
    return f"/api/v1/orders/{_required_text(case_no, 'case_no')}/cancellation"


def _service_day_payloads(days: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    return [_service_day_payload(day) for day in days]


def _service_day_payload(day: Mapping[str, object]) -> dict[str, object]:
    service_date = day.get("service_date")
    staff_id = day.get("staff_id")
    if not isinstance(service_date, date):
        raise ValueError("service_date must be a date")
    if isinstance(staff_id, bool) or not isinstance(staff_id, int) or staff_id <= 0:
        raise ValueError("staff_id must be a positive integer")
    reason = day.get("reason")
    return {
        "service_date": service_date.isoformat(),
        "staff_id": staff_id,
        "reason": _optional_text(reason),
    }


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("service day reason must be text")
    return value.strip() or None


def _validated_data(response, response_type):
    try:
        envelope = BaseResponse[response_type].model_validate(response.json())
    except (ValueError, ValidationError, TypeError) as error:
        raise _client_error(response.status_code, "internal", "order_cancellation_invalid_response", "訂單取消 API 回傳格式不正確。") from error
    if not envelope.success or envelope.data is None:
        raise _client_error(response.status_code, "internal", "order_cancellation_invalid_response", "訂單取消 API 回傳格式不正確。")
    return envelope.data


def _http_error(response):
    try:
        detail = response.json().get("detail")
        error = OrderCancellationTypedErrorView.model_validate(detail["error"])
        return OrderCancellationApiError(response.status_code, error)
    except (AttributeError, KeyError, TypeError, ValueError, ValidationError):
        retryable = response.status_code in {502, 503, 504}
        return _client_error(response.status_code, "unavailable" if retryable else "internal", "order_cancellation_request_failed", "訂單取消 API 請求失敗。", retryable=retryable)


def _client_error(status_code, category, code, message, *, retryable=False):
    return OrderCancellationApiError(status_code, OrderCancellationTypedErrorView(category=category, code=code, message=message, correlation_id="client", retryable=retryable))


def _required_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} is required")
    return value.strip()


__all__ = ["OrderCancellationApiClient", "OrderCancellationApiError"]
