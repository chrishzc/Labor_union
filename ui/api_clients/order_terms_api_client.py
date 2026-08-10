"""Framework-neutral client for the canonical Orders Terms API."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, TypeVar

import requests
from pydantic import BaseModel, ValidationError

from api.schemas.base import BaseResponse
from api.schemas.order_terms import (
    OrderTermsPreviewView,
    OrderTermsQueryView,
    OrderTermsReceiptView,
    OrderTermsTypedErrorView,
)


T = TypeVar("T", bound=BaseModel)


@dataclass(slots=True)
class OrderTermsApiError(RuntimeError):
    status_code: int | None
    error: OrderTermsTypedErrorView

    def __str__(self) -> str:
        return self.error.message


class OrderTermsApiClient:
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

    def query(self, case_no: str) -> OrderTermsQueryView:
        return self._request("GET", _path(case_no), response_type=OrderTermsQueryView)

    def preview(self, case_no: str, proposed_terms: Mapping[str, Any], *, correlation_id: str) -> OrderTermsPreviewView:
        return self._request(
            "POST",
            f"{_path(case_no)}/preview",
            payload={"proposed_terms": dict(proposed_terms)},
            command_headers={"X-Correlation-ID": _required_text(correlation_id, "correlation_id")},
            response_type=OrderTermsPreviewView,
        )

    def apply(self, case_no: str, proposed_terms: Mapping[str, Any], preview: OrderTermsPreviewView, *, reason: str, idempotency_key: str, correlation_id: str) -> OrderTermsReceiptView:
        return self._request(
            "POST",
            f"{_path(case_no)}/apply",
            payload=_apply_payload(proposed_terms, preview, reason),
            command_headers={
                "Idempotency-Key": _required_text(idempotency_key, "idempotency_key"),
                "X-Correlation-ID": _required_text(correlation_id, "correlation_id"),
            },
            response_type=OrderTermsReceiptView,
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
            raise _client_error(None, "unavailable", "order_terms_transport_error", "無法連線至正式條款 API。", retryable=True) from error


def _path(case_no: object) -> str:
    return f"/api/v1/orders/{_required_text(case_no, 'case_no')}/terms"


def _apply_payload(proposed_terms, preview, reason):
    return {
        "proposed_terms": dict(proposed_terms),
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
        raise _client_error(response.status_code, "internal", "order_terms_invalid_response", "正式條款 API 回傳格式不正確。") from error
    if not envelope.success or envelope.data is None:
        raise _client_error(response.status_code, "internal", "order_terms_invalid_response", "正式條款 API 回傳格式不正確。")
    return envelope.data


def _http_error(response):
    try:
        detail = response.json().get("detail")
        error = OrderTermsTypedErrorView.model_validate(detail["error"])
        return OrderTermsApiError(response.status_code, error)
    except (AttributeError, KeyError, TypeError, ValueError, ValidationError):
        retryable = response.status_code in {502, 503, 504}
        return _client_error(response.status_code, "unavailable" if retryable else "internal", "order_terms_request_failed", "正式條款 API 請求失敗。", retryable=retryable)


def _client_error(status_code, category, code, message, *, retryable=False):
    return OrderTermsApiError(status_code, OrderTermsTypedErrorView(category=category, code=code, message=message, correlation_id="client", retryable=retryable))


def _required_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} is required")
    return value.strip()


__all__ = ["OrderTermsApiClient", "OrderTermsApiError"]
