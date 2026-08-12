"""Framework-neutral API client for Government Subsidy."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import TypeVar

import requests
from pydantic import BaseModel, ValidationError

from api.schemas.base import BaseResponse
from api.schemas.jobs import JobAcceptedResponse
from pydantic import BaseModel

class JobStatusResponse(BaseModel):
    job_id: str
    status: str

from api.schemas.government_subsidy import (
    GovernmentSubsidyApprovalItemView,
    GovernmentSubsidyBatchView,
    GovernmentSubsidyClaimBatchPageView,
    GovernmentSubsidyClaimPlanningIntentView,
    GovernmentSubsidyClaimPreviewView,
    GovernmentSubsidyClaimReceiptView,
    GovernmentSubsidyPreviewView,
    GovernmentSubsidyReceiptIntentView,
    GovernmentSubsidyReceiptView,
    GovernmentSubsidyReversalIntentView,
    GovernmentSubsidyTypedErrorView,
    GovernmentPayerAccountApplyBody,
    GovernmentPayerAccountPreviewBody,
    GovernmentPayerAccountPreviewView,
    GovernmentPayerAccountReceiptView,
    GovernmentPayerMasterView,
    GovernmentSubsidyOverpaymentPreviewView,
    GovernmentSubsidyOverpaymentReceiptView,
    GovernmentSubsidyOverpaymentDispositionApplyBody,
    GovernmentSubsidyOverpaymentDispositionPreviewBody,
    GovernmentOverpaymentReturnReconciliationApplyBody,
    GovernmentOverpaymentReturnReconciliationPreviewBody,
    GovernmentOverpaymentReturnReconciliationPreviewView,
)

T = TypeVar("T", bound=BaseModel)


@dataclass(slots=True)
class GovernmentSubsidyApiError(RuntimeError):
    status_code: int | None
    error: GovernmentSubsidyTypedErrorView

    def __str__(self) -> str:
        return self.error.message


class GovernmentSubsidyApiClient:
    def __init__(
        self,
        *,
        base_url: str,
        headers: Mapping[str, str],
        timeout: float = 15.0,
        session: requests.Session | None = None,
    ) -> None:
        self._base_url = _canonical_text(base_url, "base_url").rstrip("/")
        self._headers = {str(key): str(value) for key, value in headers.items()}
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        self._timeout = float(timeout)
        self._session = session or requests.Session()

    def query_batch(self, batch_id: int) -> GovernmentSubsidyBatchView:
        return self._request(
            "GET",
            f"/api/v1/government-subsidy/claim-batches/{batch_id}",
            response_type=GovernmentSubsidyBatchView,
        )

    def query_payer_master(self) -> GovernmentPayerMasterView:
        return self._request("GET", "/api/v1/government-subsidy/payer-master", response_type=GovernmentPayerMasterView)

    def preview_overpayment_offset(self, overpayment_identity: str, targets: list[dict[str, int]], correlation_id: str) -> GovernmentSubsidyOverpaymentPreviewView:
        return self._request("POST", "/api/v1/government-subsidy/overpayments/offset/preview", payload={"overpayment_identity": overpayment_identity, "targets": targets}, command_headers={"X-Correlation-ID": correlation_id}, response_type=GovernmentSubsidyOverpaymentPreviewView)

    def apply_overpayment_offset(self, overpayment_identity: str, targets: list[dict[str, int]], expected_overpayment_version: int, preview: GovernmentSubsidyOverpaymentPreviewView, *, reason: str, evidence_reference: str, idempotency_key: str, correlation_id: str) -> GovernmentSubsidyOverpaymentReceiptView:
        return self._request("POST", "/api/v1/government-subsidy/overpayments/offset/apply", payload={"overpayment_identity": overpayment_identity, "targets": targets, "expected_overpayment_version": expected_overpayment_version, "preview_fingerprint": preview.preview_fingerprint, "reason": _canonical_text(reason, "reason"), "evidence_reference": _canonical_text(evidence_reference, "evidence_reference")}, command_headers={"Idempotency-Key": idempotency_key, "X-Correlation-ID": correlation_id}, response_type=GovernmentSubsidyOverpaymentReceiptView)

    def preview_overpayment_return(self, overpayment_identity: str, due_date: str, evidence_reference: str, correlation_id: str) -> GovernmentSubsidyOverpaymentPreviewView:
        return self._request("POST", "/api/v1/government-subsidy/overpayments/return/preview", payload={"overpayment_identity": overpayment_identity, "due_date": due_date, "evidence_reference": evidence_reference}, command_headers={"X-Correlation-ID": correlation_id}, response_type=GovernmentSubsidyOverpaymentPreviewView)

    def apply_overpayment_return(self, overpayment_identity: str, due_date: str, evidence_reference: str, expected_overpayment_version: int, preview: GovernmentSubsidyOverpaymentPreviewView, *, reason: str, idempotency_key: str, correlation_id: str) -> GovernmentSubsidyOverpaymentReceiptView:
        return self._request("POST", "/api/v1/government-subsidy/overpayments/return/apply", payload={"overpayment_identity": overpayment_identity, "due_date": due_date, "evidence_reference": _canonical_text(evidence_reference, "evidence_reference"), "expected_overpayment_version": expected_overpayment_version, "preview_fingerprint": preview.preview_fingerprint, "reason": _canonical_text(reason, "reason")}, command_headers={"Idempotency-Key": idempotency_key, "X-Correlation-ID": correlation_id}, response_type=GovernmentSubsidyOverpaymentReceiptView)

    def preview_overpayment_disposition(
        self,
        body: GovernmentSubsidyOverpaymentDispositionPreviewBody,
        correlation_id: str,
    ) -> GovernmentSubsidyOverpaymentPreviewView:
        return self._request(
            "POST",
            "/api/v1/government-subsidy/overpayments/disposition/preview",
            payload=body.model_dump(mode="json"),
            command_headers={"X-Correlation-ID": _canonical_text(correlation_id, "correlation_id")},
            response_type=GovernmentSubsidyOverpaymentPreviewView,
        )

    def apply_overpayment_disposition(
        self,
        body: GovernmentSubsidyOverpaymentDispositionApplyBody,
        idempotency_key: str,
        correlation_id: str,
    ) -> GovernmentSubsidyOverpaymentReceiptView:
        return self._request(
            "POST",
            "/api/v1/government-subsidy/overpayments/disposition/apply",
            payload=body.model_dump(mode="json"),
            command_headers={
                "Idempotency-Key": _canonical_text(idempotency_key, "idempotency_key"),
                "X-Correlation-ID": _canonical_text(correlation_id, "correlation_id"),
            },
            response_type=GovernmentSubsidyOverpaymentReceiptView,
        )

    def preview_overpayment_return_reconciliation(
        self, body: GovernmentOverpaymentReturnReconciliationPreviewBody, correlation_id: str
    ) -> GovernmentOverpaymentReturnReconciliationPreviewView:
        return self._request(
            "POST", "/api/v1/government-subsidy/overpayments/return-reconciliation/preview",
            payload=body.model_dump(mode="json"),
            command_headers={"X-Correlation-ID": _canonical_text(correlation_id, "correlation_id")},
            response_type=GovernmentOverpaymentReturnReconciliationPreviewView,
        )

    def apply_overpayment_return_reconciliation(
        self, body: GovernmentOverpaymentReturnReconciliationApplyBody, idempotency_key: str, correlation_id: str
    ) -> GovernmentSubsidyOverpaymentReceiptView:
        return self._request(
            "POST", "/api/v1/government-subsidy/overpayments/return-reconciliation/apply",
            payload=body.model_dump(mode="json"),
            command_headers={"Idempotency-Key": _canonical_text(idempotency_key, "idempotency_key"), "X-Correlation-ID": _canonical_text(correlation_id, "correlation_id")},
            response_type=GovernmentSubsidyOverpaymentReceiptView,
        )

    def preview_refund_account(self, account: GovernmentPayerAccountPreviewBody, correlation_id: str) -> GovernmentPayerAccountPreviewView:
        return self._request(
            "POST", "/api/v1/government-subsidy/payer-master/refund-accounts/preview",
            payload=account.model_dump(mode="json"),
            command_headers={"X-Correlation-ID": correlation_id},
            response_type=GovernmentPayerAccountPreviewView,
        )

    def apply_refund_account(self, body: GovernmentPayerAccountApplyBody, correlation_id: str) -> GovernmentPayerAccountReceiptView:
        return self._request(
            "POST", "/api/v1/government-subsidy/payer-master/refund-accounts/apply",
            payload=body.model_dump(mode="json"),
            command_headers={"X-Correlation-ID": correlation_id},
            response_type=GovernmentPayerAccountReceiptView,
        )

    def list_batches(
        self,
        *,
        cursor: int | None = None,
        limit: int = 20,
    ) -> GovernmentSubsidyClaimBatchPageView:
        suffix = f"?limit={limit}"
        if cursor is not None:
            suffix += f"&cursor={cursor}"
        return self._request(
            "GET",
            f"/api/v1/government-subsidy/claim-batches{suffix}",
            response_type=GovernmentSubsidyClaimBatchPageView,
        )

    def preview_claim_plan(
        self,
        intent: GovernmentSubsidyClaimPlanningIntentView,
        correlation_id: str,
    ) -> GovernmentSubsidyClaimPreviewView:
        return self._claim_preview(
            "/api/v1/government-subsidy/claim-batches/preview",
            {"intent": intent.model_dump(mode="json")},
            correlation_id,
        )

    def apply_claim_plan(
        self,
        intent: GovernmentSubsidyClaimPlanningIntentView,
        preview: GovernmentSubsidyClaimPreviewView,
        **identity: str,
    ) -> JobAcceptedResponse:
        return self._claim_apply(
            "/api/v1/government-subsidy/claim-batches/apply",
            {"intent": intent.model_dump(mode="json")},
            preview,
            identity,
        )

    def preview_claim_submission(
        self,
        batch_id: int,
        correlation_id: str,
    ) -> GovernmentSubsidyClaimPreviewView:
        return self._claim_preview(
            _claim_action_path(batch_id, "submit", "preview"),
            {},
            correlation_id,
        )

    def apply_claim_submission(
        self,
        batch_id: int,
        preview: GovernmentSubsidyClaimPreviewView,
        **identity: str,
    ) -> JobAcceptedResponse:
        return self._claim_apply(
            _claim_action_path(batch_id, "submit", "apply"),
            {},
            preview,
            identity,
        )

    def preview_claim_approval(
        self,
        batch_id: int,
        approvals: list[GovernmentSubsidyApprovalItemView],
        correlation_id: str,
    ) -> GovernmentSubsidyClaimPreviewView:
        return self._claim_preview(
            _claim_action_path(batch_id, "approval", "preview"),
            _approval_payload(approvals),
            correlation_id,
        )

    def apply_claim_approval(
        self,
        batch_id: int,
        approvals: list[GovernmentSubsidyApprovalItemView],
        preview: GovernmentSubsidyClaimPreviewView,
        **identity: str,
    ) -> JobAcceptedResponse:
        return self._claim_apply(
            _claim_action_path(batch_id, "approval", "apply"),
            _approval_payload(approvals),
            preview,
            identity,
        )

    def preview_receipt(
        self,
        intent: GovernmentSubsidyReceiptIntentView,
        correlation_id: str,
    ) -> GovernmentSubsidyPreviewView:
        return self._preview(
            "/api/v1/government-subsidy/receipts/preview",
            intent,
            correlation_id,
        )

    def apply_receipt(
        self,
        intent: GovernmentSubsidyReceiptIntentView,
        preview: GovernmentSubsidyPreviewView,
        **identity: str,
    ) -> JobAcceptedResponse:
        return self._apply(
            "/api/v1/government-subsidy/receipts/apply",
            intent,
            preview,
            identity,
        )

    def preview_reversal(
        self,
        intent: GovernmentSubsidyReversalIntentView,
        correlation_id: str,
    ) -> GovernmentSubsidyPreviewView:
        return self._preview(
            "/api/v1/government-subsidy/reversals/preview",
            intent,
            correlation_id,
        )

    def apply_reversal(
        self,
        intent: GovernmentSubsidyReversalIntentView,
        preview: GovernmentSubsidyPreviewView,
        **identity: str,
    ) -> JobAcceptedResponse:
        return self._apply(
            "/api/v1/government-subsidy/reversals/apply",
            intent,
            preview,
            identity,
        )

    def _preview(self, path, intent, correlation_id):
        return self._request(
            "POST",
            path,
            payload={"intent": intent.model_dump(mode="json")},
            command_headers={"X-Correlation-ID": correlation_id},
            response_type=GovernmentSubsidyPreviewView,
        )

    def _apply(self, path, intent, preview, identity):
        payload = {
            "intent": intent.model_dump(mode="json"),
            "expected_batch_version": preview.batch_version,
            "preview_fingerprint": preview.preview_fingerprint,
            "reason": _canonical_text(identity["reason"], "reason"),
        }
        return self._request(
            "POST",
            path,
            payload=payload,
            command_headers={
                "Idempotency-Key": identity["idempotency_key"],
                "X-Correlation-ID": identity["correlation_id"],
            },
            response_type=JobAcceptedResponse,
        )

    def _claim_preview(self, path, payload, correlation_id):
        return self._request(
            "POST",
            path,
            payload=payload,
            command_headers={"X-Correlation-ID": correlation_id},
            response_type=GovernmentSubsidyClaimPreviewView,
        )

    def _claim_apply(self, path, payload, preview, identity):
        body = {
            **payload,
            "expected_batch_version": preview.batch_version,
            "preview_fingerprint": preview.preview_fingerprint,
            "reason": _canonical_text(identity["reason"], "reason"),
        }
        return self._request(
            "POST",
            path,
            payload=body,
            command_headers=_command_headers(identity),
            response_type=JobAcceptedResponse,
        )


    def get_job_status(self, job_id: str) -> JobStatusResponse:
        return self._request(
            "GET",
            f"/api/v1/jobs/{job_id}",
            response_type=JobStatusResponse,
        )

    def _request(
        self,
        method: str,
        path: str,
        *,
        response_type: type[T],
        payload: Mapping[str, object] | None = None,
        command_headers: Mapping[str, str] | None = None,
    ) -> T:
        response = self._send(method, path, payload, command_headers)
        if not response.ok:
            raise _http_error(response)
        return _validated_data(response, response_type)

    def _send(self, method, path, payload, command_headers):
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
            raise _transport_error() from error


def _validated_data(response, response_type):
    try:
        envelope = BaseResponse[response_type].model_validate(response.json())
    except (ValueError, ValidationError, TypeError) as error:
        raise _invalid_response_error(response.status_code) from error
    if not envelope.success or envelope.data is None:
        raise _invalid_response_error(response.status_code)
    return envelope.data


def _claim_action_path(batch_id, action, phase):
    return (
        f"/api/v1/government-subsidy/claim-batches/{batch_id}"
        f"/{action}/{phase}"
    )


def _approval_payload(approvals):
    return {
        "item_approvals": [
            approval.model_dump(mode="json") for approval in approvals
        ]
    }


def _command_headers(identity):
    return {
        "Idempotency-Key": identity["idempotency_key"],
        "X-Correlation-ID": identity["correlation_id"],
    }


def _http_error(response):
    try:
        body = response.json()
        detail = body.get("detail") if isinstance(body, dict) else None
        candidate = detail.get("error") if isinstance(detail, dict) else None
        error = GovernmentSubsidyTypedErrorView.model_validate(candidate)
    except (ValueError, ValidationError, TypeError, AttributeError):
        error = _fallback_error(response.status_code)
    return GovernmentSubsidyApiError(response.status_code, error)


def _transport_error():
    return GovernmentSubsidyApiError(
        None,
        GovernmentSubsidyTypedErrorView(
            category="unavailable",
            code="government_subsidy_transport_error",
            message="無法連線至政府補助 API。",
            correlation_id="client",
            retryable=True,
        ),
    )


def _invalid_response_error(status_code):
    return GovernmentSubsidyApiError(
        status_code,
        GovernmentSubsidyTypedErrorView(
            category="internal",
            code="government_subsidy_invalid_response",
            message="政府補助 API 回傳格式不正確。",
            correlation_id="client",
        ),
    )


def _fallback_error(status_code):
    retryable = status_code in {502, 503, 504}
    return GovernmentSubsidyTypedErrorView(
        category="unavailable" if retryable else "internal",
        code="government_subsidy_request_failed",
        message="政府補助 API 請求失敗。",
        correlation_id="client",
        retryable=retryable,
    )


def _canonical_text(value, field):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} is required")
    return value.strip()


__all__ = [
    "GovernmentSubsidyApiClient",
    "GovernmentSubsidyApiError",
]
