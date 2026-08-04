"""Typed client for one Order's fixed calendar terms."""

from __future__ import annotations

from collections.abc import Mapping

import requests
from pydantic import ValidationError

from api.schemas.base import BaseResponse
from api.schemas.order_calendar_detail import OrderCalendarDetailView


class OrderCalendarDetailApiError(RuntimeError):
    pass


class OrderCalendarDetailApiClient:
    def __init__(self, *, base_url: str, headers: Mapping[str, str], timeout: float = 15.0, session: requests.Session | None = None) -> None:
        if not isinstance(base_url, str) or not base_url.strip():
            raise ValueError("base_url is required")
        self._base_url = base_url.strip().rstrip("/")
        self._headers = {str(key): str(value) for key, value in headers.items()}
        self._timeout = timeout
        self._session = session or requests.Session()

    def query(self, case_no: str) -> OrderCalendarDetailView:
        if not isinstance(case_no, str) or not case_no.strip():
            raise ValueError("case_no is required")
        try:
            response = self._session.get(f"{self._base_url}/api/v1/orders/{case_no.strip()}/calendar-detail", headers=self._headers, timeout=self._timeout)
        except requests.RequestException as error:
            raise OrderCalendarDetailApiError("無法連線至訂單排班條款 API。") from error
        if not response.ok:
            raise OrderCalendarDetailApiError(_error_message(response))
        try:
            envelope = BaseResponse[OrderCalendarDetailView].model_validate(response.json())
        except (TypeError, ValidationError, ValueError) as error:
            raise OrderCalendarDetailApiError("訂單排班條款 API 回傳格式不正確。") from error
        if not envelope.success or envelope.data is None:
            raise OrderCalendarDetailApiError("訂單排班條款 API 回傳格式不正確。")
        return envelope.data


def _error_message(response) -> str:
    try:
        detail = response.json().get("detail")
        error = detail.get("error") if isinstance(detail, dict) else None
        return str(error.get("message")) if isinstance(error, dict) else "訂單排班條款查詢失敗。"
    except (AttributeError, ValueError):
        return "訂單排班條款查詢失敗。"


__all__ = ["OrderCalendarDetailApiClient", "OrderCalendarDetailApiError"]
