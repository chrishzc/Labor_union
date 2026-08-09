"""Typed client for Form Management statistics and selected-case context."""

from __future__ import annotations

from collections.abc import Mapping

import requests
from pydantic import ValidationError

from api.schemas.base import BaseResponse
from api.schemas.form_management import (
    FormManagementCaseContextView,
    FormManagementStatisticsView,
)


class FormManagementApiError(RuntimeError):
    pass


class FormManagementApiClient:
    def __init__(self, *, base_url: str, headers: Mapping[str, str], timeout: float = 15.0) -> None:
        if not isinstance(base_url, str) or not base_url.strip():
            raise ValueError("base_url is required")
        self._base_url = base_url.rstrip("/")
        self._headers = {str(key): str(value) for key, value in headers.items()}
        self._timeout = timeout

    def statistics(self) -> FormManagementStatisticsView:
        return self._get("/api/v1/orders/form-management-statistics", FormManagementStatisticsView)

    def case_context(self, case_no: str) -> FormManagementCaseContextView:
        if not isinstance(case_no, str) or not case_no.strip():
            raise ValueError("case_no is required")
        return self._get(f"/api/v1/orders/{case_no}/form-management-context", FormManagementCaseContextView)

    def _get(self, path, view_type):
        try:
            response = requests.get(
                self._base_url + path,
                headers=self._headers,
                timeout=self._timeout,
            )
        except requests.RequestException as error:
            raise FormManagementApiError("無法連線至表單資料 API。") from error
        if not response.ok:
            raise FormManagementApiError("表單資料 API 查詢失敗。")
        try:
            envelope = BaseResponse[view_type].model_validate(response.json())
        except (TypeError, ValueError, ValidationError) as error:
            raise FormManagementApiError("表單資料 API 回傳格式不正確。") from error
        if not envelope.success or envelope.data is None:
            raise FormManagementApiError("表單資料 API 回傳狀態不正確。")
        return envelope.data


__all__ = ["FormManagementApiClient", "FormManagementApiError"]
