"""
File: import_warning_tracking_api_client.py
Description: 提供匯入警示追蹤 API 的 typed Query、Preview、Apply receipt 與查詢 client。
"""

from collections.abc import Mapping
from typing import Any

import requests
from pydantic import ValidationError

from api.schemas.base import BaseResponse
from api.schemas.import_warning_tracking import ImportWarningTaskView, WarningTransitionBody, WarningTransitionPreviewView, WarningTransitionReceiptView


class ImportWarningTrackingApiError(RuntimeError):
    pass


class ImportWarningTrackingApiClient:
    def __init__(self, *, base_url: str, headers: Mapping[str, str], timeout: float = 20.0, session: requests.Session | None = None) -> None:
        self._base_url = base_url.rstrip("/")
        self._headers = dict(headers)
        self._timeout = timeout
        self._session = session or requests.Session()

    def query_tasks(self, *, active_only: bool = True) -> tuple[ImportWarningTaskView, ...]:
        return tuple(self._request("GET", "/api/v1/import-warning-tracking/tasks", params={"active_only": str(active_only).lower()}, response_type=list[ImportWarningTaskView]))

    def preview(self, occurrence_identity: str, body: WarningTransitionBody, *, idempotency_key: str, correlation_id: str) -> WarningTransitionPreviewView:
        return self._command("preview", occurrence_identity, body, idempotency_key, correlation_id, WarningTransitionPreviewView)

    def apply(self, occurrence_identity: str, body: WarningTransitionBody, *, idempotency_key: str, correlation_id: str) -> WarningTransitionReceiptView:
        return self._command("apply", occurrence_identity, body, idempotency_key, correlation_id, WarningTransitionReceiptView)

    def query_receipt(self, receipt_identity: str) -> WarningTransitionReceiptView:
        return self._request("GET", f"/api/v1/import-warning-tracking/receipts/{receipt_identity}", response_type=WarningTransitionReceiptView)

    def _command(self, operation: str, occurrence_identity: str, body: WarningTransitionBody, idempotency_key: str, correlation_id: str, response_type):
        return self._request("POST", f"/api/v1/import-warning-tracking/tasks/{occurrence_identity}/{operation}", payload=body.model_dump(), headers={"Idempotency-Key": idempotency_key, "X-Correlation-ID": correlation_id}, response_type=response_type)

    def _request(self, method: str, path: str, *, response_type: Any, params=None, payload=None, headers=None):
        try:
            response = self._session.request(method, f"{self._base_url}{path}", headers={**self._headers, **dict(headers or {})}, params=params, json=payload, timeout=self._timeout)
        except requests.RequestException as error:
            raise ImportWarningTrackingApiError("import_warning_tracking_transport_error") from error
        if not response.ok:
            raise ImportWarningTrackingApiError(_error_code(response))
        try:
            envelope = BaseResponse[response_type].model_validate(response.json())
        except (ValueError, TypeError, ValidationError) as error:
            raise ImportWarningTrackingApiError("import_warning_tracking_invalid_response") from error
        if not envelope.success or envelope.data is None:
            raise ImportWarningTrackingApiError("import_warning_tracking_invalid_response")
        return envelope.data


def _error_code(response) -> str:
    try:
        detail = response.json().get("detail", {})
        return str(detail.get("error", {}).get("code") or "import_warning_tracking_request_failed")
    except (ValueError, AttributeError):
        return "import_warning_tracking_request_failed"


__all__ = ["ImportWarningTrackingApiClient", "ImportWarningTrackingApiError"]
