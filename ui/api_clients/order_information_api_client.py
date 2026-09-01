"""Typed client for staff order-information Query/Preview."""

from __future__ import annotations

from collections.abc import Mapping

import requests
from pydantic import ValidationError

from api.schemas.base import BaseResponse
from api.schemas.order_information import OrderInformationView


class OrderInformationApiError(RuntimeError):
    pass


class OrderInformationApiClient:
    def __init__(self, *, base_url: str, headers: Mapping[str, str], timeout: float = 15.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._headers = {str(key): str(value) for key, value in headers.items()}
        self._timeout = timeout

    def query(
        self, case_no: str, template_id: str, assignment_id: int | None = None
    ) -> OrderInformationView:
        return self._send("GET", case_no, template_id, assignment_id)

    def preview(
        self, case_no: str, template_id: str, assignment_id: int | None = None
    ) -> OrderInformationView:
        return self._send("POST", case_no, template_id, assignment_id)

    def _send(self, method, case_no, template_id, assignment_id):
        params = {"assignment_id": assignment_id} if assignment_id is not None else None
        try:
            response = requests.request(
                method,
                f"{self._base_url}/api/v1/orders/{case_no}/order-information/{template_id}",
                params=params,
                headers=self._headers,
                timeout=self._timeout,
            ) if method == "GET" else requests.post(
                f"{self._base_url}/api/v1/orders/{case_no}/order-information/{template_id}/preview",
                params=params,
                headers=self._headers,
                timeout=self._timeout,
            )
        except requests.RequestException as error:
            raise OrderInformationApiError("無法連線至訂單資訊 API。") from error
        if not response.ok:
            raise OrderInformationApiError("訂單資訊 API 查詢失敗。")
        try:
            envelope = BaseResponse[OrderInformationView].model_validate(response.json())
            if not envelope.success or envelope.data is None:
                raise ValueError("invalid response envelope")
            return envelope.data
        except (TypeError, ValueError, ValidationError) as error:
            raise OrderInformationApiError("訂單資訊 API 回傳格式不正確。") from error


__all__ = ["OrderInformationApiClient", "OrderInformationApiError"]
