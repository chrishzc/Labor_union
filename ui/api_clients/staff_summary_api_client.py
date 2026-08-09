"""Typed HTTP client for the bounded staff directory query."""

from __future__ import annotations

from collections.abc import Mapping

import requests
from pydantic import ValidationError

from api.schemas.base import BaseResponse
from api.schemas.staff_summary import StaffSummaryPageView


class StaffSummaryApiClient:
    def __init__(self, *, base_url: str, headers: Mapping[str, str]) -> None:
        self._base_url = base_url.rstrip("/")
        self._headers = dict(headers)

    def query(self, *, page_size: int = 200, after_id: int | None = None) -> StaffSummaryPageView:
        parameters = {"page_size": page_size}
        if after_id is not None:
            parameters["after_id"] = after_id
        try:
            response = requests.get(
                f"{self._base_url}/api/v1/staff/summaries",
                headers=self._headers,
                params=parameters,
                timeout=15,
            )
            response.raise_for_status()
            envelope = BaseResponse[StaffSummaryPageView].model_validate(response.json())
        except (requests.RequestException, ValidationError, ValueError, TypeError) as error:
            raise RuntimeError("無法取得月嫂摘要清單。") from error
        if not envelope.success or envelope.data is None:
            raise RuntimeError("月嫂摘要清單回應狀態不正確。")
        return envelope.data
