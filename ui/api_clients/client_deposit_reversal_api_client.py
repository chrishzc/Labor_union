"""Typed HTTP client for canonical Client Finance deposit reversal."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date

import requests
from pydantic import ValidationError

from api.schemas.base import BaseResponse
from api.schemas.client_deposit_reversal import (
    DepositReversalApplyBody,
    DepositReversalPreviewBody,
    DepositReversalPreviewView,
    DepositReversalReceiptView,
)


@dataclass(frozen=True, slots=True)
class DepositReversalApiError(RuntimeError):
    status_code: int | None
    code: str
    message: str
    retryable: bool = False

    def __str__(self) -> str:
        return self.message


class ClientDepositReversalApiClient:
    def __init__(
        self,
        *,
        base_url: str,
        headers: Mapping[str, str],
        timeout: float = 15.0,
        session: requests.Session | None = None,
    ) -> None:
        self._base_url = _required_text(base_url, "base_url").rstrip("/")
        self._headers = {str(key): str(value) for key, value in headers.items()}
        self._timeout = _positive_timeout(timeout)
        self._session = session or requests.Session()

    def preview(
        self,
        case_no: str,
        original_ledger_entry_id: int,
        reversal_occurred_on: date,
        *,
        correlation_id: str,
    ) -> DepositReversalPreviewView:
        body = DepositReversalPreviewBody(
            original_ledger_entry_id=original_ledger_entry_id,
            reversal_occurred_on=reversal_occurred_on,
        )
        return self._post(
            case_no,
            "/preview",
            body,
            DepositReversalPreviewView,
            {"X-Correlation-ID": _required_text(correlation_id, "correlation_id")},
        )

    def apply(
        self,
        case_no: str,
        original_ledger_entry_id: int,
        reversal_occurred_on: date,
        preview: DepositReversalPreviewView,
        *,
        reason: str,
        idempotency_key: str,
        correlation_id: str,
    ) -> DepositReversalReceiptView:
        body = DepositReversalApplyBody(
            original_ledger_entry_id=original_ledger_entry_id,
            reversal_occurred_on=reversal_occurred_on,
            expected_account_version=preview.account_version,
            preview_fingerprint=preview.preview_fingerprint,
            reason=_required_text(reason, "reason"),
        )
        return self._post(
            case_no,
            "/apply",
            body,
            DepositReversalReceiptView,
            {
                "Idempotency-Key": _required_text(idempotency_key, "idempotency_key"),
                "X-Correlation-ID": _required_text(correlation_id, "correlation_id"),
            },
        )

    def _post(self, case_no, suffix, body, response_type, command_headers):
        try:
            response = self._session.post(
                f"{self._path(case_no)}{suffix}",
                json=body.model_dump(mode="json"),
                headers={**self._headers, **command_headers},
                timeout=self._timeout,
            )
        except requests.RequestException as error:
            raise DepositReversalApiError(
                None,
                "deposit_reversal_transport_error",
                "無法連線至訂金沖正 API。",
                True,
            ) from error
        if not response.ok:
            raise _http_error(response)
        return _validated_data(response, response_type)

    def _path(self, case_no: object) -> str:
        return (
            f"{self._base_url}/api/v1/orders/"
            f"{_required_text(case_no, 'case_no')}/client-finance/deposit-reversal"
        )


def _validated_data(response, response_type):
    try:
        envelope = BaseResponse[response_type].model_validate(response.json())
    except (TypeError, ValidationError, ValueError) as error:
        raise DepositReversalApiError(
            response.status_code,
            "deposit_reversal_invalid_response",
            "訂金沖正 API 回傳格式不正確。",
        ) from error
    if not envelope.success or envelope.data is None:
        raise DepositReversalApiError(
            response.status_code,
            "deposit_reversal_invalid_response",
            "訂金沖正 API 回傳格式不正確。",
        )
    return envelope.data


def _http_error(response) -> DepositReversalApiError:
    try:
        error = response.json()["detail"]["error"]
        return DepositReversalApiError(
            response.status_code,
            str(error["code"]),
            str(error["message"]),
            bool(error.get("retryable", False)),
        )
    except (KeyError, TypeError, ValueError):
        retryable = response.status_code in {502, 503, 504}
        return DepositReversalApiError(
            response.status_code,
            "deposit_reversal_request_failed",
            "訂金沖正 API 請求失敗。",
            retryable,
        )


def _positive_timeout(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        raise ValueError("timeout must be positive")
    return float(value)


def _required_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} is required")
    return value.strip()


__all__ = ["ClientDepositReversalApiClient", "DepositReversalApiError"]
