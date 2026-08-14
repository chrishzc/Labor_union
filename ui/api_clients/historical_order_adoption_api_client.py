"""
File: historical_order_adoption_api_client.py
Description: 呼叫 Orders historical workbook Preview／Apply API 並驗證 strict typed view。
"""

from collections.abc import Mapping

import requests
from pydantic import ValidationError

from api.schemas.base import BaseResponse
from api.schemas.historical_order_adoption import HistoricalOrderWorkbookPreviewView, HistoricalOrderWorkbookReceiptView


class HistoricalOrderAdoptionApiError(RuntimeError):
    def __init__(self, status_code: int, code: str) -> None:
        super().__init__(code)
        self.status_code = status_code
        self.code = code


class HistoricalOrderAdoptionApiClient:
    def __init__(self, *, base_url: str, headers: Mapping[str, str], session=None) -> None:
        self._base_url = str(base_url).rstrip("/")
        self._headers = dict(headers)
        self._session = session or requests.Session()

    def preview_workbook(self, filename: str, content: bytes) -> HistoricalOrderWorkbookPreviewView:
        return self._request("preview", filename, content, {}, HistoricalOrderWorkbookPreviewView)

    def apply_workbook(
        self, filename: str, content: bytes, *, preview_fingerprint: str, idempotency_key: str, correlation_id: str,
    ) -> HistoricalOrderWorkbookReceiptView:
        headers = {"Idempotency-Key": idempotency_key, "X-Correlation-ID": correlation_id}
        data = {"preview_fingerprint": preview_fingerprint}
        return self._request("apply", filename, content, headers, HistoricalOrderWorkbookReceiptView, data)

    def _request(self, operation, filename, content, command_headers, response_type, data=None):
        try:
            response = self._session.request(
                "POST", f"{self._base_url}/api/v1/orders/historical-adoption/workbooks/{operation}",
                headers={**self._headers, **command_headers}, data=data,
                files={"workbook": (filename, content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
                timeout=30,
            )
        except requests.RequestException as error:
            raise HistoricalOrderAdoptionApiError(0, "historical_order_import_transport_unavailable") from error
        if not response.ok:
            raise HistoricalOrderAdoptionApiError(response.status_code, _error_code(response))
        try:
            return BaseResponse[response_type].model_validate(response.json()).data
        except (ValidationError, ValueError) as error:
            raise HistoricalOrderAdoptionApiError(response.status_code, "historical_order_import_response_invalid") from error


def _error_code(response) -> str:
    try:
        detail = response.json().get("detail")
    except ValueError:
        return "historical_order_import_http_error"
    return detail.get("code", "historical_order_import_http_error") if isinstance(detail, dict) else "historical_order_import_http_error"
