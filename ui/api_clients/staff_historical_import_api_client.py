"""
File: staff_historical_import_api_client.py
Description: 呼叫 Staff historical-only workbook Preview／Apply 並驗證 typed result。
"""

from collections.abc import Mapping

import requests
from pydantic import ValidationError

from api.schemas.base import BaseResponse
from api.schemas.staff_historical_workbook import StaffHistoricalWorkbookPreviewView, StaffHistoricalWorkbookReceiptView


class StaffHistoricalImportApiError(RuntimeError):
    def __init__(self, status_code: int, code: str) -> None:
        super().__init__(code)
        self.status_code = status_code
        self.code = code


class StaffHistoricalImportApiClient:
    def __init__(self, *, base_url: str, headers: Mapping[str, str], session=None) -> None:
        self._base_url = str(base_url).rstrip("/")
        self._headers = dict(headers)
        self._session = session or requests.Session()

    def preview_workbook(self, filename: str, content: bytes, source_revision: str | None):
        return self._upload("preview", filename, content, StaffHistoricalWorkbookPreviewView, source_revision, {})

    def apply_workbook(
        self, filename: str, content: bytes, *, source_revision: str | None,
        preview_fingerprint: str, idempotency_key: str, correlation_id: str,
    ):
        headers = {
            "Idempotency-Key": idempotency_key,
            "X-Correlation-ID": correlation_id,
            "X-Preview-Fingerprint": preview_fingerprint,
        }
        return self._upload("apply", filename, content, StaffHistoricalWorkbookReceiptView, source_revision, headers)

    def _upload(self, operation, filename, content, view_type, source_revision, headers):
        data = {} if not source_revision else {"source_revision": source_revision}
        try:
            response = self._session.request(
                "POST", f"{self._base_url}/api/v1/case-import/staff-historical/workbooks/{operation}",
                headers={**self._headers, **headers}, data=data,
                files={"workbook": (filename, content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
                timeout=30,
            )
        except requests.RequestException as error:
            raise StaffHistoricalImportApiError(0, "staff_historical_import_transport_unavailable") from error
        if not response.ok:
            raise StaffHistoricalImportApiError(response.status_code, _error_code(response))
        try:
            return BaseResponse[view_type].model_validate(response.json()).data
        except (ValidationError, ValueError) as error:
            raise StaffHistoricalImportApiError(response.status_code, "staff_historical_import_response_invalid") from error


def _error_code(response) -> str:
    try:
        detail = response.json().get("detail")
    except ValueError:
        return "staff_historical_import_http_error"
    return detail.get("code", "staff_historical_import_http_error") if isinstance(detail, dict) else "staff_historical_import_http_error"
