"""
File: order_lifecycle_control_api_client.py
Description: 驗證並讀取訂單實際開工日重新確認的唯讀生命週期控制投影。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal, TypeVar

import requests
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from api.schemas.base import BaseResponse


class ActualStartReconfirmationControlView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state: Literal["not_required", "active", "cleared"]
    required_date: str | None
    current_actual_start_date: str | None
    blockers: list[str]
    can_reconfirm: bool


class OrderLifecycleControlStateView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_no: str = Field(min_length=1)
    lifecycle_version: int = Field(ge=0)
    canonical_status: str = Field(min_length=1)
    actual_start_reconfirmation: ActualStartReconfirmationControlView


@dataclass(slots=True)
class OrderLifecycleControlApiError(RuntimeError):
    message: str
    status_code: int | None = None

    def __str__(self) -> str:
        return self.message


T = TypeVar("T", bound=BaseModel)


class OrderLifecycleControlApiClient:
    def __init__(
        self,
        *,
        base_url: str,
        headers: Mapping[str, str],
        timeout: float = 15.0,
        session: requests.Session | None = None,
    ) -> None:
        if not isinstance(base_url, str) or not base_url.strip():
            raise ValueError("base_url is required")
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        self._base_url = base_url.strip().rstrip("/")
        self._headers = {str(key): str(value) for key, value in headers.items()}
        self._timeout = float(timeout)
        self._session = session or requests.Session()

    def query(self, case_no: str) -> OrderLifecycleControlStateView:
        if not isinstance(case_no, str) or not case_no.strip():
            raise ValueError("case_no is required")
        try:
            response = self._session.get(
                f"{self._base_url}/api/v1/orders/{case_no.strip()}/lifecycle-control-state",
                headers=self._headers,
                timeout=self._timeout,
            )
        except requests.RequestException as error:
            raise OrderLifecycleControlApiError("無法連線至訂單生命週期控制 API。") from error
        if not response.ok:
            raise OrderLifecycleControlApiError("訂單生命週期控制狀態查詢失敗。", response.status_code)
        return _validated_data(response, OrderLifecycleControlStateView)


def _validated_data(response: object, response_type: type[T]) -> T:
    try:
        payload = response.json()  # type: ignore[attr-defined]
        envelope = BaseResponse[response_type].model_validate(payload)
    except (AttributeError, TypeError, ValidationError, ValueError) as error:
        raise OrderLifecycleControlApiError("訂單生命週期控制 API 回傳格式不正確。") from error
    if not envelope.success or envelope.data is None:
        raise OrderLifecycleControlApiError("訂單生命週期控制 API 回傳格式不正確。")
    return envelope.data


__all__ = [
    "ActualStartReconfirmationControlView",
    "OrderLifecycleControlApiClient",
    "OrderLifecycleControlApiError",
    "OrderLifecycleControlStateView",
]
