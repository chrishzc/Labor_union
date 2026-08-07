"""Framework-neutral client for Payroll rebuild and monthly queries."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TypeVar
from urllib.parse import quote

import requests
from pydantic import BaseModel, ValidationError

from api.schemas.base import BaseResponse
from api.schemas.payroll_rebuild import (
    PayrollRebuildPreviewView,
    PayrollRebuildReceiptView,
    PayrollRebuildTypedErrorView,
    StaffMonthlyPayrollSummaryView,
)
from api.schemas.jobs import JobAcceptedResponse, JobResponse

T = TypeVar("T", bound=BaseModel)


class PayrollRebuildApiError(RuntimeError):
    def __init__(self, status_code, error) -> None:
        super().__init__(error.message)
        self.status_code = status_code
        self.error = error


class PayrollRebuildApiClient:
    def __init__(
        self,
        *,
        base_url: str,
        headers: Mapping[str, str],
        timeout: float = 15.0,
        session: requests.Session | None = None,
    ) -> None:
        self._base_url = _text(base_url, "base_url").rstrip("/")
        self._headers = {str(key): str(value) for key, value in headers.items()}
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        self._timeout = float(timeout)
        self._session = session or requests.Session()

    def preview(self, case_no: str) -> PayrollRebuildPreviewView:
        encoded_case_no = quote(_text(case_no, "case_no"), safe="")
        return self._request(
            "POST",
            f"/api/v1/payroll-rebuild/cases/{encoded_case_no}/preview",
            PayrollRebuildPreviewView,
        )

    # Kept cohesive because preview identity and retry headers are one command.
    def apply(
        self,
        case_no: str,
        preview: PayrollRebuildPreviewView,
        *,
        reason: str,
        idempotency_key: str,
        correlation_id: str,
    ) -> JobAcceptedResponse:
        payload = {
            "expected_payroll_version": preview.payroll_version,
            "preview_fingerprint": preview.preview_fingerprint,
            "reason": _text(reason, "reason"),
        }
        headers = {
            "Idempotency-Key": _text(idempotency_key, "idempotency_key"),
            "X-Correlation-ID": _text(correlation_id, "correlation_id"),
        }
        encoded_case_no = quote(_text(case_no, "case_no"), safe="")
        return self._request(
            "POST",
            f"/api/v1/payroll-rebuild/cases/{encoded_case_no}/apply",
            JobAcceptedResponse,
            payload=payload,
            command_headers=headers,
        )

    def get_job_status(self, job_id: str) -> JobResponse:
        encoded_job_id = quote(_text(job_id, "job_id"), safe="")
        return self._request(
            "GET",
            f"/api/v1/jobs/{encoded_job_id}",
            JobResponse,
        )

    def query_staff_month(
        self,
        staff_id: int,
        year: int,
        month: int,
    ) -> StaffMonthlyPayrollSummaryView:
        _positive_integer(staff_id, "staff_id")
        return self._request(
            "GET",
            f"/api/v1/payroll-rebuild/staff/{staff_id}/months/{year}/{month}",
            StaffMonthlyPayrollSummaryView,
        )

    # Kept cohesive because transport and typed envelope validation share one call.
    def _request(
        self,
        method,
        path,
        response_type: type[T],
        *,
        payload=None,
        command_headers=None,
    ) -> T:
        headers = {**self._headers, **dict(command_headers or {})}
        try:
            response = self._session.request(
                method,
                f"{self._base_url}{path}",
                headers=headers,
                json=payload,
                timeout=self._timeout,
            )
        except requests.RequestException as error:
            raise _transport_error() from error
        if not response.ok:
            raise _http_error(response)
        return _validated(response, response_type)


def _validated(response, response_type):
    try:
        envelope = BaseResponse[response_type].model_validate(response.json())
    except (ValueError, ValidationError, TypeError) as error:
        raise _invalid_response(response.status_code) from error
    if not envelope.success or envelope.data is None:
        raise _invalid_response(response.status_code)
    return envelope.data


def _http_error(response):
    try:
        payload = response.json()
        error = PayrollRebuildTypedErrorView.model_validate(
            payload["detail"]["error"]
        )
    except (KeyError, ValueError, ValidationError, TypeError):
        error = _fallback_error("transaction_failed", "Payroll rebuild 請求失敗。")
    return PayrollRebuildApiError(response.status_code, error)


def _transport_error():
    error = _fallback_error(
        "transaction_failed",
        "無法連線至 Payroll rebuild API。",
        retryable=True,
    )
    return PayrollRebuildApiError(None, error)


def _invalid_response(status_code):
    error = _fallback_error(
        "invalid_payroll_facts",
        "Payroll rebuild API 回傳格式不正確。",
    )
    return PayrollRebuildApiError(status_code, error)


def _fallback_error(code, message, *, retryable=False):
    return PayrollRebuildTypedErrorView(
        category="unavailable" if retryable else "internal",
        code=code,
        message=message,
        correlation_id="client",
        retryable=retryable,
    )


def _positive_integer(value, field_name):
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{field_name} must be a positive integer")
    return value


def _text(value, field_name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} is required")
    return value.strip()


__all__ = ["PayrollRebuildApiClient", "PayrollRebuildApiError"]
