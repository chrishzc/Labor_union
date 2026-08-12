"""Read one complete order only after the operator selects its summary."""

from __future__ import annotations

from collections.abc import Mapping

import requests
from pydantic import ValidationError

from api.schemas.base import BaseResponse
from api.schemas.order_detail import OrderDetailView


class OrderDetailApiClient:
    def __init__(self, *, base_url: str, headers: Mapping[str, str]) -> None:
        self._base_url = base_url.rstrip("/")
        self._headers = dict(headers)

    def query(self, case_no: str) -> OrderDetailView:
        try:
            response = requests.get(
                f"{self._base_url}/api/v1/orders/{case_no}",
                headers=self._headers,
                timeout=15,
            )
            response.raise_for_status()
            envelope = BaseResponse[dict[str, object]].model_validate(response.json())
        except (requests.RequestException, ValidationError, ValueError, TypeError) as error:
            raise RuntimeError("無法取得案件完整資料。") from error
        if not envelope.success or envelope.data is None:
            raise RuntimeError("案件完整資料回應狀態不正確。")
        try:
            return OrderDetailView.model_validate(envelope.data)
        except ValidationError as error:
            raise RuntimeError("案件完整資料回應格式不正確。") from error
