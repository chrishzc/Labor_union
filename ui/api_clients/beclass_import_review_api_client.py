"""Framework-neutral API client for BeClass import review."""

from __future__ import annotations

import json
from collections.abc import Mapping
from uuid import uuid4
from typing import Any

import requests
from pydantic import ValidationError

from api.schemas.beclass_import_review import (
    BeClassImportReviewApplyBody,
    BeClassImportReviewIntentBody,
    BeClassImportReviewPreviewView,
    BeClassImportReviewQueryView,
    BeClassImportReviewReceiptView,
    BeClassImportReviewTypedErrorView,
)
from api.schemas.base import BaseResponse


class BeClassImportReviewApiError(RuntimeError):
    def __init__(
        self,
        status_code: int | None,
        error: BeClassImportReviewTypedErrorView,
    ) -> None:
        super().__init__(error.message)
        self.status_code = status_code
        self.error = error

    def __str__(self) -> str:
        return self.error.message


class BeClassImportReviewApiClient:
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

    def query_review(self, review_identity: str) -> BeClassImportReviewQueryView:
        return self._request(
            "GET",
            f"/api/v1/beclass-import-reviews/{_canonical_text(review_identity, 'review_identity')}",
            response_type=BeClassImportReviewQueryView,
        )

    def preview_review(
        self,
        review_identity: str,
        *,
        corrected_fields: Mapping[str, Any],
        resolved_issue_codes: list[str],
        correlation_id: str | None = None,
    ) -> BeClassImportReviewPreviewView:
        body = BeClassImportReviewIntentBody(
            review_identity=_canonical_text(review_identity, "review_identity"),
            corrected_fields=dict(corrected_fields),
            resolved_issue_codes=list(_string_items(resolved_issue_codes)),
        )
        return self._request(
            "POST",
            "/api/v1/beclass-import-reviews/preview",
            payload=body.model_dump(),
            command_headers={"X-Correlation-ID": _canonical_text(correlation_id or str(uuid4()), "correlation_id")},
            response_type=BeClassImportReviewPreviewView,
        )

    def apply_review(
        self,
        review_identity: str,
        preview: BeClassImportReviewPreviewView,
        *,
        corrected_fields: Mapping[str, Any],
        resolved_issue_codes: list[str],
        reason: str,
        idempotency_key: str | None = None,
        correlation_id: str | None = None,
    ) -> BeClassImportReviewReceiptView:
        body = BeClassImportReviewApplyBody(
            review_identity=_canonical_text(review_identity, "review_identity"),
            corrected_fields=dict(corrected_fields),
            resolved_issue_codes=list(_string_items(resolved_issue_codes)),
            expected_version=int(preview.expected_version),
            preview_fingerprint=_canonical_text(preview.preview_fingerprint, "preview_fingerprint"),
            reason=_canonical_text(reason, "reason"),
        )
        return self._request(
            "POST",
            "/api/v1/beclass-import-reviews/apply",
            payload=body.model_dump(),
            command_headers={
                "Idempotency-Key": _canonical_text(idempotency_key or str(uuid4()), "idempotency_key"),
                "X-Correlation-ID": _canonical_text(correlation_id or str(uuid4()), "correlation_id"),
            },
            response_type=BeClassImportReviewReceiptView,
        )

    def _request(
        self,
        method: str,
        path: str,
        *,
        payload: Mapping[str, Any] | None = None,
        command_headers: Mapping[str, str] | None = None,
        response_type=BeClassImportReviewQueryView,
    ):
        response = self._send(method, path, payload, command_headers)
        if not response.ok:
            raise _http_error(response)
        return _validated_data(response, response_type)

    def _send(self, method: str, path: str, payload: Mapping[str, Any] | None, command_headers: Mapping[str, str] | None):
        headers = {**self._headers, **dict(command_headers or {})}
        try:
            return self._session.request(
                method,
                f"{self._base_url}{path}",
                headers=headers,
                json=dict(payload) if payload is not None else None,
                timeout=self._timeout,
            )
        except requests.RequestException as error:
            raise _client_error(
                None,
                "unavailable",
                "beclass_import_review_transport_error",
                "無法連線到 BeClass 匯入修正 API。",
                retryable=True,
            ) from error


def _validated_data(response, response_type):
    try:
        envelope = BaseResponse[response_type].model_validate(response.json())
    except (ValueError, TypeError, ValidationError) as error:
        raise _client_error(
            response.status_code,
            "internal",
            "beclass_import_review_invalid_response",
            "BeClass 匯入修正 API 回傳格式不正確。",
        ) from error
    if not envelope.success or envelope.data is None:
        raise _client_error(
            response.status_code,
            "internal",
            "beclass_import_review_invalid_response",
            "BeClass 匯入修正 API 回傳格式不正確。",
        )
    return envelope.data


def _http_error(response):
    try:
        body = response.json()
        detail = body.get("detail") if isinstance(body, dict) else None
        candidate = detail.get("error") if isinstance(detail, dict) else None
        error = BeClassImportReviewTypedErrorView.model_validate(candidate)
        return BeClassImportReviewApiError(response.status_code, error)
    except (ValueError, TypeError, ValidationError, AttributeError):
        retryable = response.status_code in {502, 503, 504}
        return _client_error(
            response.status_code,
            "unavailable" if retryable else "internal",
            "beclass_import_review_request_failed",
            "BeClass 匯入修正 API 請求失敗。",
            retryable=retryable,
        )


def _client_error(
    status_code: int | None,
    category: str,
    code: str,
    message: str,
    *,
    retryable: bool = False,
) -> BeClassImportReviewApiError:
    return BeClassImportReviewApiError(
        status_code,
        BeClassImportReviewTypedErrorView(
            category=category,
            code=code,
            message=message,
            correlation_id="client",
            retryable=retryable,
        ),
    )


def _string_items(values) -> list[str]:
    return [item.strip() for item in values if str(item).strip()]


def _canonical_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} is required")
    return value.strip()


__all__ = [
    "BeClassImportReviewApiClient",
    "BeClassImportReviewApiError",
]
