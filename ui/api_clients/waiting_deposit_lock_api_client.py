"""Typed client for the canonical waiting-deposit lock workflow."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, TypeVar

import requests
from pydantic import BaseModel, ValidationError

from api.schemas.base import BaseResponse
from api.schemas.waiting_deposit_lock import (
    WaitingDepositLockPreviewView,
    WaitingDepositLockReceiptView,
    WaitingDepositLockReleasePreviewView,
    WaitingDepositLockReleaseReceiptView,
)


T = TypeVar("T", bound=BaseModel)


@dataclass(frozen=True, slots=True)
class WaitingDepositLockErrorDetail:
    code: str
    message: str
    retryable: bool = False


@dataclass(slots=True)
class WaitingDepositLockApiError(RuntimeError):
    status_code: int | None
    error: WaitingDepositLockErrorDetail

    def __str__(self) -> str:
        return self.error.message


class WaitingDepositLockApiClient:
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
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        self._timeout = float(timeout)
        self._session = session or requests.Session()

    def preview_acquisition(
        self, case_no: str, plan_id: int
    ) -> WaitingDepositLockPreviewView:
        return self._request(
            "POST",
            _acquire_path(case_no, plan_id, "preview"),
            response_type=WaitingDepositLockPreviewView,
        )

    def apply_acquisition(
        self,
        case_no: str,
        plan_id: int,
        preview_fingerprint: str,
        *,
        idempotency_key: str,
        correlation_id: str,
    ) -> WaitingDepositLockReceiptView:
        return self._request(
            "POST",
            _acquire_path(case_no, plan_id, "apply"),
            payload={"preview_fingerprint": preview_fingerprint},
            command_headers=_command_headers(idempotency_key, correlation_id),
            response_type=WaitingDepositLockReceiptView,
        )

    def preview_release(
        self, case_no: str, plan_id: int, lock_id: int
    ) -> WaitingDepositLockReleasePreviewView:
        return self._request(
            "POST",
            _release_path(case_no, plan_id, lock_id, "preview"),
            response_type=WaitingDepositLockReleasePreviewView,
        )

    def apply_release(
        self,
        case_no: str,
        plan_id: int,
        lock_id: int,
        preview_fingerprint: str,
        *,
        reason: str,
        idempotency_key: str,
        correlation_id: str,
    ) -> WaitingDepositLockReleaseReceiptView:
        return self._request(
            "POST",
            _release_path(case_no, plan_id, lock_id, "apply"),
            payload={
                "preview_fingerprint": preview_fingerprint,
                "reason": _required_text(reason, "reason"),
            },
            command_headers=_command_headers(idempotency_key, correlation_id),
            response_type=WaitingDepositLockReleaseReceiptView,
        )

    def _request(
        self,
        method: str,
        path: str,
        *,
        response_type: type[T],
        payload: Mapping[str, Any] | None = None,
        command_headers: Mapping[str, str] | None = None,
    ) -> T:
        try:
            response = self._session.request(
                method,
                f"{self._base_url}{path}",
                headers={**self._headers, **dict(command_headers or {})},
                json=dict(payload) if payload is not None else None,
                timeout=self._timeout,
            )
        except requests.RequestException as error:
            raise WaitingDepositLockApiError(
                None,
                WaitingDepositLockErrorDetail(
                    "waiting_deposit_lock_transport_error",
                    "無法連線至等待訂金檔期鎖 API。",
                    retryable=True,
                ),
            ) from error
        if not response.ok:
            raise _http_error(response)
        return _validated_data(response, response_type)


def _validated_data(response, response_type: type[T]) -> T:
    try:
        envelope = BaseResponse[response_type].model_validate(response.json())
    except (TypeError, ValidationError, ValueError) as error:
        raise WaitingDepositLockApiError(
            response.status_code,
            WaitingDepositLockErrorDetail(
                "waiting_deposit_lock_invalid_response",
                "等待訂金檔期鎖 API 回傳格式不正確。",
            ),
        ) from error
    if not envelope.success or envelope.data is None:
        raise WaitingDepositLockApiError(
            response.status_code,
            WaitingDepositLockErrorDetail(
                "waiting_deposit_lock_invalid_response",
                "等待訂金檔期鎖 API 回傳格式不正確。",
            ),
        )
    return envelope.data


def _http_error(response) -> WaitingDepositLockApiError:
    try:
        detail = response.json().get("detail")
        error = detail.get("error") if isinstance(detail, dict) else None
        if isinstance(error, dict):
            return WaitingDepositLockApiError(
                response.status_code,
                WaitingDepositLockErrorDetail(
                    str(error.get("code") or "waiting_deposit_lock_request_failed"),
                    str(error.get("message") or "等待訂金檔期鎖請求失敗。"),
                    bool(error.get("retryable")),
                ),
            )
    except (TypeError, ValueError):
        pass
    retryable = response.status_code in {502, 503, 504}
    return WaitingDepositLockApiError(
        response.status_code,
        WaitingDepositLockErrorDetail(
            "waiting_deposit_lock_request_failed",
            "等待訂金檔期鎖請求失敗。",
            retryable,
        ),
    )


def _acquire_path(case_no: str, plan_id: int, action: str) -> str:
    return (
        f"/api/v1/orders/{_case_no(case_no)}/matching-plans/{_positive_id(plan_id)}/"
        f"waiting-deposit-lock/acquire/{action}"
    )


def _release_path(case_no: str, plan_id: int, lock_id: int, action: str) -> str:
    return (
        f"/api/v1/orders/{_case_no(case_no)}/matching-plans/{_positive_id(plan_id)}/"
        f"waiting-deposit-locks/{_positive_id(lock_id)}/release/{action}"
    )


def _command_headers(idempotency_key: str, correlation_id: str) -> dict[str, str]:
    return {
        "Idempotency-Key": _required_text(idempotency_key, "idempotency_key"),
        "X-Correlation-ID": _required_text(correlation_id, "correlation_id"),
    }


def _case_no(value: str) -> str:
    return _required_text(value, "case_no")


def _positive_id(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError("identifier must be a positive integer")
    return value


def _required_text(value: str, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} is required")
    return value.strip()


__all__ = [
    "WaitingDepositLockApiClient",
    "WaitingDepositLockApiError",
    "WaitingDepositLockErrorDetail",
]
