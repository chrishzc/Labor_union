"""Typed HTTP client for Client Receipt Reconciliation."""

from __future__ import annotations

from collections.abc import Mapping
import requests

from api.schemas.base import BaseResponse
from api.schemas.client_receipt_reconciliation import (
    ClientReceiptApplyBody,
    ClientReceiptPreviewBody,
    ClientReceiptPreviewView,
    ClientReceiptQueryView,
    ClientReceiptReceiptView,
)

class ClientReceiptReconciliationApiClient:
    def __init__(
        self,
        *,
        base_url: str,
        headers: Mapping[str, str],
        timeout: float = 15.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._headers = dict(headers)
        self._timeout = timeout
        self._session = requests.Session()

    def query(self, case_no: str) -> ClientReceiptQueryView:
        response = self._session.get(
            f"{self._base_url}/api/v1/orders/{case_no}/client-finance/receipt-reconciliation",
            headers=self._headers,
            timeout=self._timeout,
        )
        response.raise_for_status()
        envelope = BaseResponse[ClientReceiptQueryView].model_validate(response.json())
        return envelope.data

    def preview(self, case_no: str, body: ClientReceiptPreviewBody) -> ClientReceiptPreviewView:
        headers = dict(self._headers)
        headers["X-Correlation-ID"] = "preview"
        response = self._session.post(
            f"{self._base_url}/api/v1/orders/{case_no}/client-finance/receipt-reconciliation/preview",
            json=body.model_dump(mode="json"),
            headers=headers,
            timeout=self._timeout,
        )
        response.raise_for_status()
        envelope = BaseResponse[ClientReceiptPreviewView].model_validate(response.json())
        return envelope.data

    def apply(
        self, 
        case_no: str, 
        body: ClientReceiptApplyBody,
        idempotency_key: str,
    ) -> ClientReceiptReceiptView:
        headers = dict(self._headers)
        headers["X-Correlation-ID"] = "apply"
        headers["Idempotency-Key"] = idempotency_key
        response = self._session.post(
            f"{self._base_url}/api/v1/orders/{case_no}/client-finance/receipt-reconciliation/apply",
            json=body.model_dump(mode="json"),
            headers=headers,
            timeout=self._timeout,
        )
        response.raise_for_status()
        envelope = BaseResponse[ClientReceiptReceiptView].model_validate(response.json())
        return envelope.data

    def preview_overage(
        self,
        case_no: str,
        body: ClientReceiptPreviewBody,
    ) -> ClientReceiptPreviewView:
        return self._preview_at(case_no, body, "overage/preview")

    def apply_overage(
        self,
        case_no: str,
        body: ClientReceiptApplyBody,
        idempotency_key: str,
    ) -> ClientReceiptReceiptView:
        return self._apply_at(case_no, body, idempotency_key, "overage/apply")

    def _preview_at(
        self,
        case_no: str,
        body: ClientReceiptPreviewBody,
        suffix: str,
    ) -> ClientReceiptPreviewView:
        headers = dict(self._headers)
        headers["X-Correlation-ID"] = "preview"
        response = self._session.post(
            f"{self._base_url}/api/v1/orders/{case_no}/client-finance/receipt-reconciliation/{suffix}",
            json=body.model_dump(mode="json"),
            headers=headers,
            timeout=self._timeout,
        )
        response.raise_for_status()
        return BaseResponse[ClientReceiptPreviewView].model_validate(response.json()).data

    def _apply_at(
        self,
        case_no: str,
        body: ClientReceiptApplyBody,
        idempotency_key: str,
        suffix: str,
    ) -> ClientReceiptReceiptView:
        headers = dict(self._headers)
        headers["X-Correlation-ID"] = "apply"
        headers["Idempotency-Key"] = idempotency_key
        response = self._session.post(
            f"{self._base_url}/api/v1/orders/{case_no}/client-finance/receipt-reconciliation/{suffix}",
            json=body.model_dump(mode="json"),
            headers=headers,
            timeout=self._timeout,
        )
        response.raise_for_status()
        return BaseResponse[ClientReceiptReceiptView].model_validate(response.json()).data
