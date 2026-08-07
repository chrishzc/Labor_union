"""Typed HTTP client for the bounded Orders summary query."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

import requests
from pydantic import ValidationError

from api.schemas.base import BaseResponse
from api.schemas.order_summary import OrderSummaryPageView


@dataclass(frozen=True, slots=True)
class OrderSummaryQueryResult:
    page: OrderSummaryPageView | None
    etag: str
    not_modified: bool


class OrderSummaryApiError(RuntimeError):
    def __init__(self, status_code: int | None, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code


class OrderSummaryApiClient:
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

    def query(
        self,
        *,
        page_size: int = 50,
        after_case_no: str | None = None,
        etag: str | None = None,
    ) -> OrderSummaryQueryResult:
        response = self._send(page_size, after_case_no, etag)
        response_etag = response.headers.get("ETag", etag or "")
        if response.status_code == 304:
            return OrderSummaryQueryResult(None, response_etag, True)
        if not response.ok:
            raise OrderSummaryApiError(
                response.status_code,
                _error_message(response),
            )
        return OrderSummaryQueryResult(
            _validated_page(response),
            response_etag,
            False,
        )

    def _send(self, page_size, after_case_no, etag):
        headers = dict(self._headers)
        if etag:
            headers["If-None-Match"] = etag
        parameters = {"page_size": page_size}
        if after_case_no is not None:
            parameters["after_case_no"] = after_case_no
        try:
            return self._session.get(
                f"{self._base_url}/api/v1/orders/summaries",
                headers=headers,
                params=parameters,
                timeout=self._timeout,
            )
        except requests.RequestException as error:
            raise OrderSummaryApiError(
                None,
                "無法連線至訂單摘要 API。",
            ) from error


def _validated_page(response) -> OrderSummaryPageView:
    try:
        envelope = BaseResponse[OrderSummaryPageView].model_validate(
            response.json()
        )
    except (ValueError, ValidationError, TypeError) as error:
        raise OrderSummaryApiError(
            response.status_code,
            "訂單摘要 API 回傳格式不正確。",
        ) from error
    if not envelope.success or envelope.data is None:
        raise OrderSummaryApiError(
            response.status_code,
            "訂單摘要 API 回傳狀態不正確。",
        )
    return envelope.data


def _error_message(response) -> str:
    try:
        detail = response.json().get("detail", {})
        error = detail.get("error", {})
        message = error.get("message")
        return str(message) if message else "訂單摘要查詢失敗。"
    except (ValueError, AttributeError):
        return "訂單摘要查詢失敗。"


def _required_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} is required")
    return value.strip()


__all__ = [
    "OrderSummaryApiClient",
    "OrderSummaryApiError",
    "OrderSummaryQueryResult",
]
