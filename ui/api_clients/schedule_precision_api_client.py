"""Typed Streamlit client for the Scheduling attendance precision query."""

from __future__ import annotations

from collections.abc import Mapping

import requests
from pydantic import ValidationError

from api.schemas.base import BaseResponse
from api.schemas.orders import ScheduleCalculationRequest
from api.schemas.schedule_precision import SchedulePrecisionResultView


class SchedulePrecisionApiError(RuntimeError):
    """Raised before an invalid transport or projection reaches rendering."""


class SchedulePrecisionApiClient:
    def __init__(
        self,
        *,
        base_url: str,
        headers: Mapping[str, str],
        timeout: float = 10.0,
        session: requests.Session | None = None,
    ) -> None:
        if not isinstance(base_url, str) or not base_url.strip():
            raise ValueError("base_url is required")
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        self._base_url = base_url.rstrip("/")
        self._headers = {str(key): str(value) for key, value in headers.items()}
        self._timeout = float(timeout)
        self._session = session or requests.Session()

    def preview(self, payload: Mapping[str, object]) -> SchedulePrecisionResultView:
        try:
            request = ScheduleCalculationRequest.model_validate(dict(payload))
            response = self._session.post(
                f"{self._base_url}/api/v1/orders/calculate-schedule",
                headers=self._headers,
                json=request.model_dump(mode="json", exclude_none=True),
                timeout=self._timeout,
            )
            response.raise_for_status()
            envelope = BaseResponse[SchedulePrecisionResultView].model_validate(
                response.json()
            )
        except (requests.RequestException, ValidationError, ValueError, TypeError) as error:
            raise SchedulePrecisionApiError(
                "出勤天數精算 Preview 回應格式不正確或暫時無法取得。"
            ) from error
        if not envelope.success or envelope.data is None:
            raise SchedulePrecisionApiError("出勤天數精算 Preview 回應狀態不正確。")
        return envelope.data


__all__ = ["SchedulePrecisionApiClient", "SchedulePrecisionApiError"]
