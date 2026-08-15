"""
File: client_beclass_import_api_client.py
Description: 呼叫 Client BeClass temporary workbook Preview／Apply 並驗證 typed result。
"""

from collections.abc import Mapping

import requests
from pydantic import ValidationError

from api.schemas.base import BaseResponse
from api.schemas.client_beclass_import import ClientBeClassWorkbookPreviewView, ClientBeClassWorkbookReceiptView


class ClientBeClassImportApiError(RuntimeError):
    def __init__(self, status_code: int, code: str) -> None:
        super().__init__(code)
        self.status_code = status_code
        self.code = code


class ClientBeClassImportApiClient:
    def __init__(self, *, base_url: str, headers: Mapping[str, str], session=None) -> None:
        self._base_url = str(base_url).rstrip("/")
        self._headers = dict(headers)
        self._session = session or requests.Session()

    def preview_workbook(self, filename: str, content: bytes) -> ClientBeClassWorkbookPreviewView:
        return self._upload("preview", filename, content, ClientBeClassWorkbookPreviewView, {}, {})

    def apply_workbook(
        self, filename: str, content: bytes, *, preview_fingerprint: str,
        idempotency_key: str, correlation_id: str,
    ) -> ClientBeClassWorkbookReceiptView:
        headers = {"Idempotency-Key": idempotency_key, "X-Correlation-ID": correlation_id}
        return self._upload(
            "apply", filename, content, ClientBeClassWorkbookReceiptView,
            headers, {"preview_fingerprint": preview_fingerprint},
        )

    def _upload(self, operation, filename, content, view_type, headers, form_data):
        try:
            response = self._session.request(
                "POST", f"{self._base_url}/api/v1/case-import/client-beclass/workbooks/{operation}",
                headers={**self._headers, **headers}, data=form_data,
                files={"workbook": (filename, content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
                timeout=30,
            )
        except requests.RequestException as error:
            raise ClientBeClassImportApiError(0, "client_beclass_import_transport_unavailable") from error
        if not response.ok:
            raise ClientBeClassImportApiError(response.status_code, _error_code(response))
        try:
            return BaseResponse[view_type].model_validate(response.json()).data
        except (ValidationError, ValueError) as error:
            raise ClientBeClassImportApiError(response.status_code, "client_beclass_import_response_invalid") from error


def _error_code(response) -> str:
    try:
        detail = response.json().get("detail")
    except ValueError:
        return "client_beclass_import_http_error"
    return detail.get("code", "client_beclass_import_http_error") if isinstance(detail, dict) else "client_beclass_import_http_error"
