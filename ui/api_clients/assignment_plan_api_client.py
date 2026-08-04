"""Framework-neutral client for the authoritative Assignment Plan API."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, TypeVar

import requests
from pydantic import BaseModel, ValidationError

from api.schemas.assignment_plan import (
    AssignmentPlanPreviewView,
    AssignmentPlanQueryView,
    AssignmentPlanReceiptView,
    AssignmentPlanTypedErrorView,
)
from api.schemas.base import BaseResponse
from api.schemas.jobs import JobAcceptedResponse, JobResponse

T = TypeVar("T", bound=BaseModel)


@dataclass(slots=True)
class AssignmentPlanApiError(RuntimeError):
    status_code: int | None
    error: AssignmentPlanTypedErrorView

    def __str__(self) -> str:
        return self.error.message


class AssignmentPlanApiClient:
    def __init__(
        self,
        *,
        base_url: str,
        headers: Mapping[str, str],
        timeout: float = 15.0,
        session: requests.Session | None = None,
    ) -> None:
        self._base_url = _canonical_text(base_url, "base_url").rstrip("/")
        self._headers = {str(key): str(value) for key, value in headers.items()}
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        self._timeout = float(timeout)
        self._session = session or requests.Session()

    def query(self, case_no: str) -> AssignmentPlanQueryView:
        return self._request(
            "GET",
            f"/api/v1/orders/{_case_no(case_no)}/assignment-plan",
            response_type=AssignmentPlanQueryView,
        )

    def preview(
        self,
        case_no: str,
        segments: list[dict[str, Any]],
        correlation_id: str,
    ) -> AssignmentPlanPreviewView:
        return self._request(
            "POST",
            f"/api/v1/orders/{_case_no(case_no)}/assignment-plan/preview",
            payload={"segments": segments},
            command_headers={"X-Correlation-ID": correlation_id},
            response_type=AssignmentPlanPreviewView,
        )

    def apply(
        self,
        case_no: str,
        segments: list[dict[str, Any]],
        preview: AssignmentPlanPreviewView,
        *,
        reason: str,
        idempotency_key: str,
        correlation_id: str,
    ) -> JobAcceptedResponse:
        headers = {
            "Idempotency-Key": idempotency_key,
            "X-Correlation-ID": correlation_id,
        }
        return self._request(
            "POST",
            f"/api/v1/orders/{_case_no(case_no)}/assignment-plan/apply",
            payload=_apply_payload(segments, preview, reason),
            command_headers=headers,
            response_type=JobAcceptedResponse,
        )

    def get_job_status(self, job_id: str) -> JobResponse:
        return self._request(
            "GET",
            f"/api/v1/jobs/{job_id}",
            response_type=JobResponse,
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
        headers = {**self._headers, **dict(command_headers or {})}
        try:
            return self._session.request(
                method,
                f"{self._base_url}{path}",
                headers=headers,
                json=dict(payload) if payload is not None else None,
                timeout=self._timeout,
            )
        except requests.RequestException as error:
            raise _client_error(
                None,
                "unavailable",
                "assignment_plan_transport_error",
                "無法連線至正式人力配置 API。",
                retryable=True,
            ) from error


def _apply_payload(segments, preview, reason):
    return {
        "segments": segments,
        "expected_order_version": preview.order_version,
        "expected_scheduling_version": preview.scheduling_version,
        "expected_client_finance_version": preview.client_finance_version,
        "expected_payroll_version": preview.payroll_version,
        "preview_fingerprint": preview.preview_fingerprint,
        "reason": _canonical_text(reason, "reason"),
    }


def _validated_data(response, response_type):
    try:
        envelope = BaseResponse[response_type].model_validate(response.json())
    except (ValueError, ValidationError, TypeError) as error:
        raise _client_error(
            response.status_code,
            "internal",
            "assignment_plan_invalid_response",
            "正式人力配置 API 回傳格式不正確。",
        ) from error
    if not envelope.success or envelope.data is None:
        raise _client_error(
            response.status_code,
            "internal",
            "assignment_plan_invalid_response",
            "正式人力配置 API 回傳格式不正確。",
        )
    return envelope.data


def _http_error(response):
    try:
        body = response.json()
        detail = body.get("detail") if isinstance(body, dict) else None
        candidate = detail.get("error") if isinstance(detail, dict) else None
        error = AssignmentPlanTypedErrorView.model_validate(candidate)
        return AssignmentPlanApiError(response.status_code, error)
    except (ValueError, ValidationError, TypeError, AttributeError):
        retryable = response.status_code in {502, 503, 504}
        return _client_error(
            response.status_code,
            "unavailable" if retryable else "internal",
            "assignment_plan_request_failed",
            "正式人力配置 API 請求失敗。",
            retryable=retryable,
        )


def _client_error(status_code, category, code, message, *, retryable=False):
    return AssignmentPlanApiError(
        status_code,
        AssignmentPlanTypedErrorView(
            category=category,
            code=code,
            message=message,
            correlation_id="client",
            retryable=retryable,
        ),
    )


def _case_no(value: object) -> str:
    return _canonical_text(value, "case_no")


def _canonical_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} is required")
    return value.strip()


__all__ = ["AssignmentPlanApiClient", "AssignmentPlanApiError"]
