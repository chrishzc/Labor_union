"""Typed read client for the Orders contract-completion view."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

import requests
from pydantic import ValidationError

from api.schemas.base import BaseResponse
from api.schemas.order_contract_completion import (
    ContractCompletionQueryView,
    ContractCompletionTypedErrorView,
)


@dataclass(slots=True)
class ContractCompletionApiError(RuntimeError):
    status_code: int | None
    error: ContractCompletionTypedErrorView

    def __str__(self) -> str:
        return self.error.message


class ContractCompletionApiClient:
    def __init__(self, *, base_url: str, headers: Mapping[str, str], timeout: float = 10.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._headers = dict(headers)
        self._timeout = timeout

    def query(self, case_no: str) -> ContractCompletionQueryView:
        try:
            response = requests.get(f"{self._base_url}/api/v1/orders/{case_no}/contract-completion", headers=self._headers, timeout=self._timeout)
        except requests.RequestException as error:
            raise _error(None, "unavailable", "contract_completion_transport_error", "無法連線至合約完成 API。", True) from error
        if not response.ok:
            raise _response_error(response)
        try:
            envelope = BaseResponse[ContractCompletionQueryView].model_validate(response.json())
        except (TypeError, ValueError, ValidationError) as error:
            raise _error(response.status_code, "internal", "contract_completion_invalid_response", "合約完成 API 回傳格式不正確。", False) from error
        if not envelope.success or envelope.data is None:
            raise _error(response.status_code, "internal", "contract_completion_invalid_response", "合約完成 API 回傳格式不正確。", False)
        return envelope.data


def _response_error(response) -> ContractCompletionApiError:
    try:
        return ContractCompletionApiError(response.status_code, ContractCompletionTypedErrorView.model_validate(response.json()["detail"]["error"]))
    except (KeyError, TypeError, ValueError, ValidationError):
        return _error(response.status_code, "internal", "contract_completion_request_failed", "合約完成 API 請求失敗。", response.status_code in {502, 503, 504})


def _error(status_code, category, code, message, retryable) -> ContractCompletionApiError:
    return ContractCompletionApiError(status_code, ContractCompletionTypedErrorView(category=category, code=code, message=message, correlation_id="client", retryable=retryable))
