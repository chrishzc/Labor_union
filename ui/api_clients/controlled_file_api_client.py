"""
File: controlled_file_api_client.py
Description: 提供 Global controlled-file 管理 API 的 typed UI client 與 fail-closed 回應驗證。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import BinaryIO, TypeVar

import requests
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from api.schemas.base import BaseResponse


class ControlledFileOwner(str, Enum):
    CONTRACT_SIGNING = "contract_signing"
    SCHEDULING = "scheduling"
    ORDERS = "orders"
    STAFF = "staff"
    LINE_INTEGRATION = "line_integration"


class ControlledFilePurpose(str, Enum):
    FINAL_SIGNED_CONTRACT = "final_signed_contract"
    SERVICE_DATE_CONFIRMATION = "service_date_confirmation"
    BABY_LOG_PHOTO = "baby_log_photo"
    MEAL_PHOTO = "meal_photo"
    ORDER_NOTICE = "order_notice"
    STAFF_RESUME = "staff_resume"
    STAFF_CERTIFICATE = "staff_certificate"
    STAFF_HEALTH_EXAM = "staff_health_exam"
    RICH_MENU_BACKGROUND = "rich_menu_background"


class _StrictView(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ControlledFileIntent(_StrictView):
    staging_id: str = Field(pattern=r"^cfs_[0-9a-f]{32}$")
    owner: ControlledFileOwner
    purpose: ControlledFilePurpose
    subject_reference: str = Field(min_length=1, max_length=500)
    object_key: str = Field(min_length=1, max_length=500)
    logical_folder: str = Field(min_length=1, max_length=500)


class ControlledFileStagingView(_StrictView):
    staging_id: str = Field(pattern=r"^cfs_[0-9a-f]{32}$")
    filename: str
    mime_type: str
    size_bytes: int = Field(ge=0)
    sha256_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    expires_at: datetime


class ControlledFileCandidateView(_StrictView):
    staging_id: str = Field(pattern=r"^cfs_[0-9a-f]{32}$")
    staging_version: int = Field(ge=1)
    owner: ControlledFileOwner
    purpose: ControlledFilePurpose
    subject_reference: str
    object_key: str
    logical_folder: str
    filename: str
    mime_type: str
    size_bytes: int = Field(ge=0)
    sha256_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    expires_at: datetime


class ControlledFilePreviewView(_StrictView):
    candidate: ControlledFileCandidateView
    preview_fingerprint: str = Field(min_length=1)
    expected_staging_version: int = Field(ge=1)
    blockers: tuple[str, ...] = ()


class ControlledFileView(_StrictView):
    file_id: str = Field(pattern=r"^cf_[0-9a-f]{32}$")
    owner: ControlledFileOwner
    purpose: ControlledFilePurpose
    subject_reference: str
    filename: str
    logical_folder: str
    mime_type: str
    size_bytes: int = Field(ge=0)
    version: int = Field(ge=1)
    status: str
    applied_at: datetime


class ControlledFileListView(_StrictView):
    items: tuple[ControlledFileView, ...]


class ControlledFileApplyReceiptView(_StrictView):
    receipt_id: str = Field(pattern=r"^cfr_[0-9a-f]{32}$")
    outcome: str = Field(pattern=r"^(created|replayed)$")
    file_id: str = Field(pattern=r"^cf_[0-9a-f]{32}$")
    owner: ControlledFileOwner
    purpose: ControlledFilePurpose
    subject_reference: str
    filename: str
    logical_folder: str
    version: int = Field(ge=1)
    sha256_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    mime_type: str
    size_bytes: int = Field(ge=0)
    status: str
    applied_at: datetime
    receipt_type: str = Field(pattern=r"^controlled_file_apply$")
    schema_version: str = Field(pattern=r"^controlled-file-apply-receipt\.v1$")


class ControlledFileTypedErrorView(_StrictView):
    category: str
    code: str
    message: str
    correlation_id: str
    retryable: bool = False


@dataclass(slots=True)
class ControlledFileApiError(RuntimeError):
    status_code: int | None
    error: ControlledFileTypedErrorView

    def __str__(self) -> str:
        return self.error.message


T = TypeVar("T", bound=BaseModel)


class ControlledFileApiClient:
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

    def stage(
        self,
        document: BinaryIO,
        *,
        filename: str,
        mime_type: str,
        idempotency_key: str,
        correlation_id: str,
        owner: ControlledFileOwner,
        purpose: ControlledFilePurpose,
        subject_reference: str,
        object_key: str,
        logical_folder: str,
    ) -> ControlledFileStagingView:
        return self._request(
            "POST",
            "/api/v1/storage/staging",
            response_type=ControlledFileStagingView,
            files={"document": (_required_text(filename, "filename"), document, _required_text(mime_type, "mime_type"))},
            form_data={
                "owner": owner.value,
                "purpose": purpose.value,
                "subject_reference": _required_text(subject_reference, "subject_reference"),
                "object_key": _required_text(object_key, "object_key"),
                "logical_folder": _required_text(logical_folder, "logical_folder"),
            },
            command_headers=_command_headers(idempotency_key, correlation_id),
        )

    def preview(
        self,
        intent: ControlledFileIntent,
        *,
        correlation_id: str,
    ) -> ControlledFilePreviewView:
        return self._request(
            "POST",
            "/api/v1/storage/files/preview",
            response_type=ControlledFilePreviewView,
            payload=intent.model_dump(mode="json"),
            command_headers={"X-Correlation-ID": _required_text(correlation_id, "correlation_id")},
        )

    def apply(
        self,
        intent: ControlledFileIntent,
        preview: ControlledFilePreviewView,
        *,
        idempotency_key: str,
        correlation_id: str,
    ) -> ControlledFileApplyReceiptView:
        return self._request(
            "POST",
            "/api/v1/storage/files/apply",
            response_type=ControlledFileApplyReceiptView,
            payload={
                **intent.model_dump(mode="json"),
                "expected_staging_version": preview.expected_staging_version,
                "preview_fingerprint": preview.preview_fingerprint,
            },
            command_headers=_command_headers(idempotency_key, correlation_id),
        )

    def list_files(self) -> ControlledFileListView:
        return self._request("GET", "/api/v1/storage/files", response_type=ControlledFileListView)

    def detail(self, file_id: str) -> ControlledFileView:
        return self._request(
            "GET",
            f"/api/v1/storage/files/{_opaque_id(file_id, 'cf_', 'file_id')}",
            response_type=ControlledFileView,
        )

    def receipt(self, receipt_id: str) -> ControlledFileApplyReceiptView:
        return self._request(
            "GET",
            f"/api/v1/storage/receipts/{_opaque_id(receipt_id, 'cfr_', 'receipt_id')}",
            response_type=ControlledFileApplyReceiptView,
        )

    def download(self, file_id: str) -> bytes:
        response = self._send(
            "GET", f"/api/v1/storage/files/{_opaque_id(file_id, 'cf_', 'file_id')}/download"
        )
        if not response.ok:
            raise _http_error(response)
        return bytes(response.content)

    def _request(
        self,
        method: str,
        path: str,
        *,
        response_type: type[T],
        payload: object | None = None,
        files: object | None = None,
        form_data: object | None = None,
        command_headers: Mapping[str, str] | None = None,
    ) -> T:
        response = self._send(method, path, payload, files, form_data, command_headers)
        if not response.ok:
            raise _http_error(response)
        return _validated_data(response, response_type)

    def _send(
        self,
        method: str,
        path: str,
        payload: object | None = None,
        files: object | None = None,
        form_data: object | None = None,
        command_headers: Mapping[str, str] | None = None,
    ):
        try:
            return self._session.request(
                method,
                f"{self._base_url}{path}",
                headers={**self._headers, **dict(command_headers or {})},
                json=payload,
                data=form_data,
                files=files,
                timeout=self._timeout,
            )
        except requests.RequestException as error:
            raise _client_error(
                None,
                "unavailable",
                "controlled_file_transport_error",
                "無法連線至檔案庫 API。",
                retryable=True,
            ) from error


def _validated_data(response, response_type: type[T]) -> T:
    try:
        envelope = BaseResponse[response_type].model_validate(response.json())
    except (ValueError, TypeError, ValidationError) as error:
        raise _client_error(
            response.status_code,
            "internal",
            "controlled_file_invalid_response",
            "檔案庫 API 回傳格式不正確。",
        ) from error
    if not envelope.success or envelope.data is None:
        raise _client_error(
            response.status_code,
            "internal",
            "controlled_file_invalid_response",
            "檔案庫 API 回傳格式不正確。",
        )
    return envelope.data


def _http_error(response) -> ControlledFileApiError:
    try:
        body = response.json()
        detail = body.get("detail") if isinstance(body, dict) else None
        candidate = detail.get("error") if isinstance(detail, dict) else None
        error = ControlledFileTypedErrorView.model_validate(candidate)
        return ControlledFileApiError(response.status_code, error)
    except (ValueError, TypeError, ValidationError, AttributeError):
        retryable = response.status_code in {502, 503, 504}
        return _client_error(
            response.status_code,
            "unavailable" if retryable else "internal",
            "controlled_file_request_failed",
            "檔案庫 API 請求失敗。",
            retryable=retryable,
        )


def _client_error(
    status_code: int | None,
    category: str,
    code: str,
    message: str,
    *,
    retryable: bool = False,
) -> ControlledFileApiError:
    return ControlledFileApiError(
        status_code,
        ControlledFileTypedErrorView(
            category=category,
            code=code,
            message=message,
            correlation_id="client",
            retryable=retryable,
        ),
    )


def _required_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} is required")
    return value.strip()


def _command_headers(idempotency_key: str, correlation_id: str) -> dict[str, str]:
    return {
        "Idempotency-Key": _required_text(idempotency_key, "idempotency_key"),
        "X-Correlation-ID": _required_text(correlation_id, "correlation_id"),
    }


def _opaque_id(value: object, prefix: str, field_name: str) -> str:
    text = _required_text(value, field_name)
    if len(text) != len(prefix) + 32 or not text.startswith(prefix):
        raise ValueError(f"{field_name} is invalid")
    suffix = text[len(prefix) :]
    if any(character not in "0123456789abcdef" for character in suffix):
        raise ValueError(f"{field_name} is invalid")
    return text


__all__ = [
    "ControlledFileApiClient",
    "ControlledFileApiError",
    "ControlledFileApplyReceiptView",
    "ControlledFileCandidateView",
    "ControlledFileIntent",
    "ControlledFileListView",
    "ControlledFileOwner",
    "ControlledFilePreviewView",
    "ControlledFilePurpose",
    "ControlledFileStagingView",
    "ControlledFileTypedErrorView",
    "ControlledFileView",
]
