"""Typed Streamlit client for bounded Data Browser source corrections."""

from __future__ import annotations

from collections.abc import Mapping

import requests
from pydantic import ValidationError

from api.schemas.base import BaseResponse
from api.schemas.data_browser import (
    DataBrowserSourceCorrectionApplyRequest,
    DataBrowserSourceCorrectionPreviewRequest,
    DataBrowserSourceCorrectionPreviewView,
    DataBrowserSourceCorrectionReceiptView,
)


class DataBrowserCorrectionApiError(RuntimeError):
    """Raised before invalid source-correction data reaches rendering."""


class DataBrowserCorrectionApiClient:
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
        self._base_url = base_url.rstrip("/")
        self._headers = {str(key): str(value) for key, value in headers.items()}
        self._timeout = float(timeout)
        self._session = session or requests.Session()

    def preview(
        self,
        table: str,
        row_id: int,
        updates: Mapping[str, object],
    ) -> DataBrowserSourceCorrectionPreviewView:
        body = DataBrowserSourceCorrectionPreviewRequest(updates=dict(updates))
        result = self._request(
            table,
            row_id,
            "preview",
            body.model_dump(mode="json"),
            DataBrowserSourceCorrectionPreviewView,
        )
        _require_matching_identity(result, table, row_id)
        return result

    def apply(
        self,
        table: str,
        row_id: int,
        updates: Mapping[str, object],
        preview: DataBrowserSourceCorrectionPreviewView,
        *,
        reason: str,
        idempotency_key: str,
    ) -> DataBrowserSourceCorrectionReceiptView:
        _require_matching_identity(preview, table, row_id)
        body = DataBrowserSourceCorrectionApplyRequest(
            updates=dict(updates),
            preview_fingerprint=preview.preview_fingerprint,
            reason=reason,
        )
        result = self._request(
            table,
            row_id,
            "apply",
            body.model_dump(mode="json"),
            DataBrowserSourceCorrectionReceiptView,
            idempotency_key=idempotency_key,
        )
        _require_matching_identity(result, table, row_id)
        if set(result.changed_fields) != set(updates):
            raise DataBrowserCorrectionApiError("來源資料更正 receipt 與申請欄位不一致。")
        return result

    def _request(
        self,
        table: str,
        row_id: int,
        operation: str,
        payload: dict[str, object],
        response_type,
        *,
        idempotency_key: str | None = None,
    ):
        normalized_table = _required_text(table, "table")
        if not isinstance(row_id, int) or isinstance(row_id, bool) or row_id <= 0:
            raise ValueError("row_id must be a positive integer")
        headers = dict(self._headers)
        if idempotency_key is not None:
            headers["Idempotency-Key"] = _required_text(
                idempotency_key,
                "idempotency_key",
            )
        try:
            response = self._session.post(
                f"{self._base_url}/api/v1/admin/data-browser/{normalized_table}/{row_id}/source-correction/{operation}",
                headers=headers,
                json=payload,
                timeout=self._timeout,
            )
            response.raise_for_status()
            envelope = BaseResponse[response_type].model_validate(response.json())
        except (requests.RequestException, ValidationError, ValueError, TypeError) as error:
            raise DataBrowserCorrectionApiError(
                "來源資料更正回應格式不正確或暫時無法取得。"
            ) from error
        if not envelope.success or envelope.data is None:
            raise DataBrowserCorrectionApiError("來源資料更正回應狀態不正確。")
        return envelope.data


def _require_matching_identity(result, table: str, row_id: int) -> None:
    if result.table != table or result.row_id != row_id:
        raise DataBrowserCorrectionApiError("來源資料更正回應識別不一致。")


def _required_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} is required")
    return value.strip()


__all__ = ["DataBrowserCorrectionApiClient", "DataBrowserCorrectionApiError"]
