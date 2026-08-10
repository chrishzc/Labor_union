"""Framework-neutral client for Payroll queries and adjustments."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

import requests
from pydantic import BaseModel

from api.schemas.base import BaseResponse
from api.schemas.payroll import (
    CasePayrollQueryView,
    PayrollAdjustmentPreviewView,
    PayrollAdjustmentReceiptView,
    StaffPayrollObligationsQueryView,
)

T = TypeVar("T", bound=BaseModel)

class PayrollApiClient:
    def __init__(
        self,
        *,
        base_url: str,
        headers: Mapping[str, str],
        timeout: float = 15.0,
        session: requests.Session | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._headers = {str(k): str(v) for k, v in headers.items()}
        self._timeout = timeout
        self._session = session or requests.Session()

    def query_case(self, case_no: str) -> CasePayrollQueryView:
        return self._request(
            "GET",
            f"/api/v1/payroll/cases/{case_no}",
            response_type=CasePayrollQueryView,
        )

    def query_staff(self, staff_id: int) -> StaffPayrollObligationsQueryView:
        return self._request(
            "GET",
            f"/api/v1/payroll/staff/{staff_id}/obligations",
            response_type=StaffPayrollObligationsQueryView,
        )

    def preview(self, payload: dict) -> PayrollAdjustmentPreviewView:
        return self._request(
            "POST",
            "/api/v1/payroll/adjustments/preview",
            payload=payload,
            response_type=PayrollAdjustmentPreviewView,
        )

    def apply(self, payload: dict, command_headers: dict) -> PayrollAdjustmentReceiptView:
        return self._request(
            "POST",
            "/api/v1/payroll/adjustments/apply",
            payload=payload,
            command_headers=command_headers,
            response_type=PayrollAdjustmentReceiptView,
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
        headers = {**self._headers, **(command_headers or {})}
        response = self._session.request(
            method,
            f"{self._base_url}{path}",
            headers=headers,
            json=payload,
            timeout=self._timeout,
        )
        response.raise_for_status()
        envelope = BaseResponse[response_type].model_validate(response.json())
        return envelope.data
