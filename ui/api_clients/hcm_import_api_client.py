"""
File: hcm_import_api_client.py
Description: 呼叫 HCM workbook upload API 並驗證 strict typed receipt。
"""

from collections.abc import Mapping

import requests
from pydantic import ValidationError

from api.schemas.base import BaseResponse
from api.schemas.hcm_import import HcmWorkbookReceiptView


class HcmImportApiError(RuntimeError):
    def __init__(self, status_code: int, code: str) -> None:
        super().__init__(code)
        self.status_code = status_code
        self.code = code


class HcmImportApiClient:
    def __init__(self, *, base_url: str, headers: Mapping[str, str], session=None) -> None:
        self._base_url = str(base_url).rstrip("/")
        self._headers = dict(headers)
        self._session = session or requests.Session()

    def ingest_workbook(self, filename: str, content: bytes, *, idempotency_key: str, correlation_id: str) -> HcmWorkbookReceiptView:
        try:
            response = self._session.request(
                "POST", f"{self._base_url}/api/v1/case-import/hcm/workbooks/ingest",
                headers={**self._headers, "Idempotency-Key": idempotency_key, "X-Correlation-ID": correlation_id},
                files={"workbook": (filename, content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
                timeout=30,
            )
        except requests.RequestException as error:
            raise HcmImportApiError(0, "hcm_import_transport_unavailable") from error
        if not response.ok:
            raise HcmImportApiError(response.status_code, _error_code(response))
        try:
            return BaseResponse[HcmWorkbookReceiptView].model_validate(response.json()).data
        except (ValidationError, ValueError) as error:
            raise HcmImportApiError(response.status_code, "hcm_import_response_invalid") from error


def _error_code(response) -> str:
    try:
        detail = response.json().get("detail")
    except ValueError:
        return "hcm_import_http_error"
    return detail.get("code", "hcm_import_http_error") if isinstance(detail, dict) else "hcm_import_http_error"
