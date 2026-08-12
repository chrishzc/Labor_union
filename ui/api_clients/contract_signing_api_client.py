"""Typed UI read client for the contract-signing workflow state."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import BinaryIO
from uuid import uuid4

import requests
from pydantic import BaseModel, Field, ValidationError

from api.schemas.base import BaseResponse


class ContractSigningSegmentView(BaseModel):
    segment_id: int
    staff_id: int
    sent: bool
    signed_received: bool


class ContractDocumentView(BaseModel):
    document_version_id: int
    scope: str
    role: str
    target_key: str
    version_number: int
    template_key: str | None
    template_sha256: str | None
    mapping_sha256: str | None
    archive_sha256: str
    mime_type: str
    file_size: int


class ContractSigningView(BaseModel):
    case_no: str
    staff_segments: list[ContractSigningSegmentView]
    commitment_id: int | None
    client_document_sent: bool
    client_signed_received: bool
    contract_identity: str | None
    documents: list[ContractDocumentView] = Field(default_factory=list)


class ContractSigningCommandReceipt(BaseModel):
    document_version_id: int
    signing_event_id: int
    line_delivery_task_id: int | None
    commitment_id: int | None
    contract_identity: str | None


@dataclass(slots=True)
class ContractSigningApiError(RuntimeError):
    status_code: int | None
    message: str
    code: str | None = None

    def __str__(self) -> str:
        return self.message


class ContractSigningApiClient:
    def __init__(self, *, base_url: str, headers: Mapping[str, str], timeout: float = 10.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._headers = dict(headers)
        self._timeout = timeout

    def query(self, case_no: str) -> ContractSigningView:
        try:
            response = requests.get(
                f"{self._base_url}/api/v1/orders/{case_no}/contract-signing",
                headers=self._headers,
                timeout=self._timeout,
            )
        except requests.RequestException as error:
            raise ContractSigningApiError(None, "無法連線至契約簽署 API。") from error
        if not response.ok:
            raise _api_error(response)
        try:
            envelope = BaseResponse[ContractSigningView].model_validate(response.json())
        except (TypeError, ValueError, ValidationError) as error:
            raise ContractSigningApiError(response.status_code, "契約簽署 API 回傳格式不正確。") from error
        if not envelope.success or envelope.data is None:
            raise ContractSigningApiError(response.status_code, "契約簽署 API 回傳格式不正確。")
        return envelope.data

    def send_staff_contract(self, case_no: str, segment_id: int, download_url: str) -> ContractSigningCommandReceipt:
        return self._command(
            "post",
            f"/api/v1/orders/{case_no}/contract-signing/staff-segments/{segment_id}/send",
            json={"download_url": download_url},
        )

    def download_document(self, case_no: str, document_version_id: int) -> bytes:
        try:
            response = requests.get(
                f"{self._base_url}/api/v1/orders/{case_no}/contract-signing/documents/{document_version_id}/download",
                headers=self._headers, timeout=self._timeout,
            )
        except requests.RequestException as error:
            raise ContractSigningApiError(None, "無法下載契約文件。") from error
        if not response.ok:
            raise _api_error(response)
        return response.content

    def record_staff_signed_return(self, case_no: str, segment_id: int, document: BinaryIO, filename: str, mime_type: str, expected_document_version_id: int, *, idempotency_key: str | None = None) -> ContractSigningCommandReceipt:
        return self._command(
            "post",
            f"/api/v1/orders/{case_no}/contract-signing/staff-segments/{segment_id}/signed-return",
            files={"document": (filename, document, mime_type)},
            data={"expected_document_version_id": str(expected_document_version_id)},
            idempotency_key=idempotency_key,
        )

    def send_client_contract(self, case_no: str, download_url: str) -> ContractSigningCommandReceipt:
        return self._command(
            "post",
            f"/api/v1/orders/{case_no}/contract-signing/client/send",
            json={"download_url": download_url},
        )

    def record_client_signed_return(self, case_no: str, document: BinaryIO, filename: str, mime_type: str, expected_document_version_id: int, *, idempotency_key: str | None = None) -> ContractSigningCommandReceipt:
        return self._command(
            "post",
            f"/api/v1/orders/{case_no}/contract-signing/client/signed-return",
            files={"document": (filename, document, mime_type)},
            data={"expected_document_version_id": str(expected_document_version_id)},
            idempotency_key=idempotency_key,
        )

    def _command(self, method: str, path: str, *, idempotency_key: str | None = None, **request_kwargs) -> ContractSigningCommandReceipt:
        headers = {
            **self._headers,
            "Idempotency-Key": idempotency_key or f"ui-contract-{uuid4().hex}",
            "X-Correlation-ID": f"ui-contract-{uuid4().hex}",
        }
        try:
            response = requests.request(
                method,
                f"{self._base_url}{path}",
                headers=headers,
                timeout=self._timeout,
                **request_kwargs,
            )
        except requests.RequestException as error:
            raise ContractSigningApiError(None, "無法連線至契約簽署 API。") from error
        if not response.ok:
            raise _api_error(response)
        try:
            envelope = BaseResponse[ContractSigningCommandReceipt].model_validate(response.json())
        except (TypeError, ValueError, ValidationError) as error:
            raise ContractSigningApiError(response.status_code, "契約簽署命令回傳格式不正確。") from error
        if not envelope.success or envelope.data is None:
            raise ContractSigningApiError(response.status_code, "契約簽署命令回傳格式不正確。")
        return envelope.data


def _api_error(response) -> ContractSigningApiError:
    try:
        error = response.json()["detail"]["error"]
        return ContractSigningApiError(response.status_code, str(error["message"]), str(error["code"]))
    except (KeyError, TypeError, ValueError):
        return _request_validation_error(response)


def _request_validation_error(response) -> ContractSigningApiError:
    try:
        detail = response.json()["detail"]
        first_error = detail[0]
        field = str(first_error["loc"][-1])
        message = str(first_error["msg"])
    except (IndexError, KeyError, TypeError, ValueError):
        return ContractSigningApiError(
            response.status_code,
            f"契約簽署 API 請求失敗 (HTTP {response.status_code})。",
        )
    return ContractSigningApiError(
        response.status_code,
        f"契約簽署命令欄位 {field} 無效：{message}",
        "contract_signing_request_validation_error",
    )
