"""
File: hcm_import_api_client.py
Description: 呼叫 HCM workbook Preview／Apply API 並驗證 strict typed result。
"""

from collections.abc import Mapping

import requests
from pydantic import ValidationError

from api.schemas.base import BaseResponse
from api.schemas.hcm_import import HcmWorkbookPreviewView, HcmWorkbookReceiptView


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
        headers = {"Idempotency-Key": idempotency_key, "X-Correlation-ID": correlation_id}
        return self._upload("ingest", filename, content, HcmWorkbookReceiptView, headers)

    def preview_workbook(self, filename: str, content: bytes) -> HcmWorkbookPreviewView:
        return self._upload("preview", filename, content, HcmWorkbookPreviewView, {})

    def apply_workbook(
        self, filename: str, content: bytes, *, preview_fingerprint: str,
        idempotency_key: str, correlation_id: str,
    ) -> HcmWorkbookReceiptView:
        headers = {
            "Idempotency-Key": idempotency_key,
            "X-Correlation-ID": correlation_id,
            "X-Preview-Fingerprint": preview_fingerprint,
        }
        return self._upload("apply", filename, content, HcmWorkbookReceiptView, headers)

    def preview_historical_workbook(self, filename: str, content: bytes) -> HcmWorkbookPreviewView:
        return self._upload("historical-workbooks/preview", filename, content, HcmWorkbookPreviewView, {})

    def apply_historical_workbook(
        self, filename: str, content: bytes, *, preview_fingerprint: str,
        idempotency_key: str, correlation_id: str,
    ) -> HcmWorkbookReceiptView:
        headers = {
            "Idempotency-Key": idempotency_key,
            "X-Correlation-ID": correlation_id,
            "X-Preview-Fingerprint": preview_fingerprint,
        }
        return self._upload("historical-workbooks/apply", filename, content, HcmWorkbookReceiptView, headers)

    def _upload(self, operation, filename, content, view_type, command_headers):
        try:
            response = self._session.request(
                "POST", f"{self._base_url}/api/v1/case-import/hcm/workbooks/{operation}",
                headers={**self._headers, **command_headers},
                files={"workbook": (filename, content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
                timeout=30,
            )
        except requests.RequestException as error:
            raise HcmImportApiError(0, "hcm_import_transport_unavailable") from error
        if not response.ok:
            raise HcmImportApiError(response.status_code, _error_code(response))
        try:
            return BaseResponse[view_type].model_validate(response.json()).data
        except (ValidationError, ValueError) as error:
            raise HcmImportApiError(response.status_code, "hcm_import_response_invalid") from error


def _error_code(response) -> str:
    try:
        detail = response.json().get("detail")
    except ValueError:
        return "hcm_import_http_error"
    return detail.get("code", "hcm_import_http_error") if isinstance(detail, dict) else "hcm_import_http_error"
