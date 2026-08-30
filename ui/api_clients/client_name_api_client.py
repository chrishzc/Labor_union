"""Typed Streamlit client for the Orders-owned client-name workflow."""

from __future__ import annotations

from collections.abc import Mapping

import requests
from pydantic import ValidationError

from api.schemas.base import BaseResponse
from api.schemas.orders import (
    ClientNameApplyRequest,
    ClientNamePreviewRequest,
    ClientNamePreviewView,
    ClientNameReceiptView,
)


class ClientNameApiError(RuntimeError):
    """Raised before an invalid client-name response reaches Streamlit."""


class ClientNameApiClient:
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

    def preview(self, case_no: str, client_name: str) -> ClientNamePreviewView:
        body = ClientNamePreviewRequest(client_name=client_name)
        return self._request(
            case_no,
            "preview",
            body.model_dump(mode="json"),
            ClientNamePreviewView,
        )

    def apply(
        self,
        case_no: str,
        preview: ClientNamePreviewView,
        *,
        reason: str,
        idempotency_key: str,
    ) -> ClientNameReceiptView:
        body = ClientNameApplyRequest(
            client_name=preview.after_client_name,
            preview_fingerprint=preview.preview_fingerprint,
            reason=reason,
        )
        return self._request(
            case_no,
            "apply",
            body.model_dump(mode="json"),
            ClientNameReceiptView,
            idempotency_key=idempotency_key,
        )

    def _request(
        self,
        case_no: str,
        operation: str,
        payload: dict[str, object],
        response_type,
        *,
        idempotency_key: str | None = None,
    ):
        normalized_case_no = _required_text(case_no, "case_no")
        headers = dict(self._headers)
        if idempotency_key is not None:
            headers["Idempotency-Key"] = _required_text(
                idempotency_key,
                "idempotency_key",
            )
        try:
            response = self._session.post(
                f"{self._base_url}/api/v1/orders/{normalized_case_no}/client-name/{operation}",
                headers=headers,
                json=payload,
                timeout=self._timeout,
            )
            response.raise_for_status()
            envelope = BaseResponse[response_type].model_validate(response.json())
        except (requests.RequestException, ValidationError, ValueError, TypeError) as error:
            raise ClientNameApiError(
                "客戶姓名工作流程回應格式不正確或暫時無法取得。"
            ) from error
        if not envelope.success or envelope.data is None:
            raise ClientNameApiError("客戶姓名工作流程回應狀態不正確。")
        return envelope.data


def _required_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} is required")
    return value.strip()


__all__ = ["ClientNameApiClient", "ClientNameApiError"]
