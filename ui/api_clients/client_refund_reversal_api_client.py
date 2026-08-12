"""Typed HTTP client for canonical Client Finance refund operations."""

from __future__ import annotations

from collections.abc import Mapping

import requests

from api.schemas.base import BaseResponse
from api.schemas.client_refund_reversal import (
    ClientRefundApplyBody,
    ClientRefundPreviewBody,
    ClientRefundReversalPreviewView,
    ClientRefundReversalQueryView,
    ClientRefundReversalReceiptView,
    ClientRefundReturnApplyBody,
    ClientRefundReturnPreviewBody,
    ClientOverRefundRecoveryApplyBody,
    ClientOverRefundRecoveryMatchedApplyBody,
    ClientOverRefundRecoveryMatchedPreviewBody,
    ClientOverRefundRecoveryPreviewBody,
    ClientOverRefundRecoveryPreviewView,
    ClientOverRefundRecoveryReceiptView,
    ClientOverRefundRecoveryAdjustmentApplyBody,
    ClientOverRefundRecoveryAdjustmentPreviewBody,
    ClientOverRefundRecoveryAdjustmentPreviewView,
    ClientOverRefundRecoveryMatchingApplyBody,
    ClientOverRefundRecoveryMatchingPreviewBody,
    ClientOverRefundRecoveryMatchingPreviewView,
    ClientOverRefundRecoveryMatchingReceiptView,
)


class ClientRefundReversalApiClient:
    def __init__(self, *, base_url: str, headers: Mapping[str, str], timeout: float = 15.0, session: requests.Session | None = None) -> None:
        self._base_url = base_url.rstrip("/")
        self._headers = dict(headers)
        self._timeout = timeout
        self._session = session or requests.Session()

    def query(self, case_no: str) -> ClientRefundReversalQueryView:
        return self._get(case_no, "/refund-reversal", ClientRefundReversalQueryView)

    def preview_refund(self, case_no: str, body: ClientRefundPreviewBody) -> ClientRefundReversalPreviewView:
        return self._post(case_no, "/refund/preview", body, ClientRefundReversalPreviewView, "client-refund-preview")

    def apply_refund(self, case_no: str, body: ClientRefundApplyBody, idempotency_key: str) -> ClientRefundReversalReceiptView:
        return self._apply(case_no, "/refund/apply", body, idempotency_key, "client-refund-apply")

    def preview_refund_overage(self, case_no: str, body: ClientRefundPreviewBody) -> ClientRefundReversalPreviewView:
        return self._post(case_no, "/refund-overage/preview", body, ClientRefundReversalPreviewView, "client-refund-overage-preview")

    def apply_refund_overage(self, case_no: str, body: ClientRefundApplyBody, idempotency_key: str) -> ClientRefundReversalReceiptView:
        return self._apply(case_no, "/refund-overage/apply", body, idempotency_key, "client-refund-overage-apply")

    def preview_subsidy_return(self, case_no: str, body: ClientRefundPreviewBody) -> ClientRefundReversalPreviewView:
        return self._post(case_no, "/subsidy-return/preview", body, ClientRefundReversalPreviewView, "client-subsidy-return-preview")

    def apply_subsidy_return(self, case_no: str, body: ClientRefundApplyBody, idempotency_key: str) -> ClientRefundReversalReceiptView:
        return self._apply(case_no, "/subsidy-return/apply", body, idempotency_key, "client-subsidy-return-apply")

    def preview_refund_return(self, case_no: str, body: ClientRefundReturnPreviewBody) -> ClientRefundReversalPreviewView:
        return self._post(case_no, "/refund-return/preview", body, ClientRefundReversalPreviewView, "client-refund-return-preview")

    def apply_refund_return(self, case_no: str, body: ClientRefundReturnApplyBody, idempotency_key: str) -> ClientRefundReversalReceiptView:
        return self._apply(case_no, "/refund-return/apply", body, idempotency_key, "client-refund-return-apply")

    def preview_refund_overage_recovery(self, case_no: str, body: ClientOverRefundRecoveryPreviewBody) -> ClientOverRefundRecoveryPreviewView:
        return self._post(case_no, "/refund-overage-recovery/preview", body, ClientOverRefundRecoveryPreviewView, "client-over-refund-recovery-preview")

    def apply_refund_overage_recovery(self, case_no: str, body: ClientOverRefundRecoveryApplyBody, idempotency_key: str) -> ClientOverRefundRecoveryReceiptView:
        return self._apply(case_no, "/refund-overage-recovery/apply", body, idempotency_key, "client-over-refund-recovery-apply", ClientOverRefundRecoveryReceiptView)

    def preview_matched_refund_overage_recovery(self, case_no: str, body: ClientOverRefundRecoveryMatchedPreviewBody) -> ClientOverRefundRecoveryPreviewView:
        return self._post(case_no, "/refund-overage-recovery/matched/preview", body, ClientOverRefundRecoveryPreviewView, "client-over-refund-recovery-matched-preview")

    def apply_matched_refund_overage_recovery(self, case_no: str, body: ClientOverRefundRecoveryMatchedApplyBody, idempotency_key: str) -> ClientOverRefundRecoveryReceiptView:
        return self._apply(case_no, "/refund-overage-recovery/matched/apply", body, idempotency_key, "client-over-refund-recovery-matched-apply", ClientOverRefundRecoveryReceiptView)

    def preview_refund_overage_recovery_adjustment(self, case_no: str, body: ClientOverRefundRecoveryAdjustmentPreviewBody) -> ClientOverRefundRecoveryAdjustmentPreviewView:
        return self._post(case_no, "/refund-overage-recovery/adjustment/preview", body, ClientOverRefundRecoveryAdjustmentPreviewView, "client-over-refund-recovery-adjustment-preview")

    def apply_refund_overage_recovery_adjustment(self, case_no: str, body: ClientOverRefundRecoveryAdjustmentApplyBody, idempotency_key: str) -> ClientOverRefundRecoveryReceiptView:
        return self._apply(case_no, "/refund-overage-recovery/adjustment/apply", body, idempotency_key, "client-over-refund-recovery-adjustment-apply", ClientOverRefundRecoveryReceiptView)

    def preview_refund_overage_recovery_matching(self, case_no: str, body: ClientOverRefundRecoveryMatchingPreviewBody) -> ClientOverRefundRecoveryMatchingPreviewView:
        return self._post(case_no, "/refund-overage-recovery/matching/preview", body, ClientOverRefundRecoveryMatchingPreviewView, "client-over-refund-recovery-matching-preview")

    def apply_refund_overage_recovery_matching(self, case_no: str, body: ClientOverRefundRecoveryMatchingApplyBody, idempotency_key: str) -> ClientOverRefundRecoveryMatchingReceiptView:
        return self._apply(case_no, "/refund-overage-recovery/matching/apply", body, idempotency_key, "client-over-refund-recovery-matching-apply", ClientOverRefundRecoveryMatchingReceiptView)

    def _get(self, case_no: str, suffix: str, response_type):
        response = self._session.get(self._url(case_no, suffix), headers=self._headers, timeout=self._timeout)
        response.raise_for_status()
        return BaseResponse[response_type].model_validate(response.json()).data

    def _post(self, case_no: str, suffix: str, body: object, response_type, correlation_id: str):
        headers = {**self._headers, "X-Correlation-ID": correlation_id}
        response = self._session.post(self._url(case_no, suffix), json=body.model_dump(mode="json"), headers=headers, timeout=self._timeout)
        response.raise_for_status()
        return BaseResponse[response_type].model_validate(response.json()).data

    def _apply(self, case_no: str, suffix: str, body: object, idempotency_key: str, correlation_id: str, response_type=ClientRefundReversalReceiptView):
        headers = {**self._headers, "X-Correlation-ID": correlation_id, "Idempotency-Key": idempotency_key}
        response = self._session.post(self._url(case_no, suffix), json=body.model_dump(mode="json"), headers=headers, timeout=self._timeout)
        response.raise_for_status()
        return BaseResponse[response_type].model_validate(response.json()).data

    def _url(self, case_no: str, suffix: str) -> str:
        return f"{self._base_url}/api/v1/orders/{case_no}/client-finance{suffix}"


__all__ = ["ClientRefundReversalApiClient"]
