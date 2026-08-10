"""Typed client for formal schedule reads and leave/substitution commands."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, TypeVar

import requests
from pydantic import BaseModel, ValidationError

from api.schemas.base import BaseResponse
from api.schemas.leave_substitution import (
    LeaveSubstitutionPreviewView,
    LeaveSubstitutionReceiptView,
    LeaveSubstitutionTypedErrorView,
)


T = TypeVar("T", bound=BaseModel)


@dataclass(slots=True)
class LeaveSubstitutionApiError(RuntimeError):
    status_code: int | None
    error: LeaveSubstitutionTypedErrorView

    def __str__(self) -> str:
        return self.error.message


class LeaveSubstitutionApiClient:
    def __init__(self, *, base_url: str, headers: Mapping[str, str], timeout: float = 15.0, session: requests.Session | None = None) -> None:
        if not isinstance(base_url, str) or not base_url.strip():
            raise ValueError("base_url is required")
        self._base_url = base_url.strip().rstrip("/")
        self._headers = {str(key): str(value) for key, value in headers.items()}
        self._timeout = timeout
        self._session = session or requests.Session()

    def assignment_schedule(self, assignment_id: int) -> dict[str, Any]:
        return self._request("GET", f"/api/v1/assignment-schedules/{_positive_id(assignment_id)}")

    def preview(self, case_no: str, payload: dict[str, Any], correlation_id: str) -> LeaveSubstitutionPreviewView:
        return self._request("POST", f"/api/v1/orders/{_case_no(case_no)}/leave-substitution/preview", payload, {"X-Correlation-ID": correlation_id}, LeaveSubstitutionPreviewView)

    def apply(self, case_no: str, payload: dict[str, Any], idempotency_key: str, correlation_id: str) -> LeaveSubstitutionReceiptView:
        return self._request("POST", f"/api/v1/orders/{_case_no(case_no)}/leave-substitution/apply", payload, {"Idempotency-Key": idempotency_key, "X-Correlation-ID": correlation_id}, LeaveSubstitutionReceiptView)

    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None, command_headers: Mapping[str, str] | None = None, response_type: type[T] | None = None):
        try:
            response = self._session.request(method, f"{self._base_url}{path}", headers={**self._headers, **dict(command_headers or {})}, json=payload, timeout=self._timeout)
        except requests.RequestException as error:
            raise _error(None, "leave_substitution_transport_error", "無法連線至請假與代班 API。", True) from error
        if not response.ok:
            raise _http_error(response)
        try:
            if response_type is None:
                envelope = BaseResponse[dict[str, Any]].model_validate(response.json())
            else:
                envelope = BaseResponse[response_type].model_validate(response.json())
        except (TypeError, ValidationError, ValueError) as error:
            raise _error(response.status_code, "leave_substitution_invalid_response", "請假與代班 API 回傳格式不正確。") from error
        if not envelope.success or envelope.data is None:
            raise _error(response.status_code, "leave_substitution_invalid_response", "請假與代班 API 回傳格式不正確。")
        return envelope.data


def _http_error(response) -> LeaveSubstitutionApiError:
    try:
        detail = response.json().get("detail")
        return LeaveSubstitutionApiError(response.status_code, LeaveSubstitutionTypedErrorView.model_validate(detail.get("error")))
    except (AttributeError, TypeError, ValidationError, ValueError):
        return _error(response.status_code, "leave_substitution_request_failed", "請假與代班請求失敗。", response.status_code in {502, 503, 504})


def _error(status_code, code, message, retryable=False) -> LeaveSubstitutionApiError:
    return LeaveSubstitutionApiError(status_code, LeaveSubstitutionTypedErrorView(category="unavailable" if retryable else "internal", code=code, message=message, correlation_id="leave-substitution-ui", retryable=retryable))


def _positive_id(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError("identifier must be a positive integer")
    return value


def _case_no(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("case_no is required")
    return value.strip()


__all__ = ["LeaveSubstitutionApiClient", "LeaveSubstitutionApiError"]
