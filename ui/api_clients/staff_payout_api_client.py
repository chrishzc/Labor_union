"""Framework-neutral client for the authoritative Staff Payout workflow."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date
from typing import Any, TypeVar

import requests
from pydantic import BaseModel, ValidationError

from api.schemas.base import BaseResponse
from api.schemas.jobs import JobAcceptedResponse, JobResponse
from api.schemas.staff_payout import (
    StaffPayablesQueryView,
    StaffPayoutPreviewView,
    StaffPayoutDifferenceSourceView,
    StaffPayoutTypedErrorView,
    StaffOverpaymentRecoveryAdjustmentApplyBody,
    StaffOverpaymentRecoveryAdjustmentPreviewBody,
    StaffOverpaymentRecoveryAdjustmentPreviewView,
    StaffOverpaymentRecoveryApplyBody,
    StaffOverpaymentRecoveryMatchedApplyBody,
    StaffOverpaymentRecoveryMatchedPreviewBody,
    StaffOverpaymentRecoveryMatchingApplyBody,
    StaffOverpaymentRecoveryMatchingPreviewBody,
    StaffOverpaymentRecoveryMatchingPreviewView,
    StaffOverpaymentRecoveryMatchingReceiptView,
    StaffOverpaymentRecoveryPreviewBody,
    StaffOverpaymentRecoveryPreviewView,
    StaffOverpaymentRecoveryReceiptView,
)

T = TypeVar("T", bound=BaseModel)


class StaffPayoutApiError(RuntimeError):
    def __init__(
        self,
        status_code: int | None,
        error: StaffPayoutTypedErrorView,
    ) -> None:
        super().__init__(error.message)
        self.status_code = status_code
        self.error = error

    def __str__(self) -> str:
        return self.error.message


class StaffPayoutApiClient:
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

    def query(self, staff_id: int) -> StaffPayablesQueryView:
        return self._request(
            "GET",
            f"/api/v1/staff-payables/{_positive_integer(staff_id, 'staff_id')}",
            response_type=StaffPayablesQueryView,
        )

    def query_payout_difference_source(self, identity: str) -> StaffPayoutDifferenceSourceView:
        return self._request("GET", f"/api/v1/staff-payables/payout-differences/{_canonical_text(identity, 'payout_difference_identity')}", response_type=StaffPayoutDifferenceSourceView)

    def preview_payout_difference(self, finance_import_row_ids: Sequence[int], obligation_identities: Sequence[str], mode: str, correlation_id: str) -> StaffPayoutPreviewView:
        return self._preview("payout-difference", {**_payout_intent(finance_import_row_ids, obligation_identities), "mode": _difference_mode(mode)}, correlation_id)

    def apply_payout_difference(self, finance_import_row_ids: Sequence[int], obligation_identities: Sequence[str], mode: str, preview: StaffPayoutPreviewView, *, reason: str, idempotency_key: str, correlation_id: str) -> JobAcceptedResponse:
        intent = {**_payout_intent(finance_import_row_ids, obligation_identities), "mode": _difference_mode(mode)}
        return self._apply("payout-difference", intent, preview, _command_identity(reason, idempotency_key, correlation_id))

    def preview_payout(
        self,
        finance_import_row_ids: Sequence[int],
        obligation_identities: Sequence[str],
        correlation_id: str,
    ) -> StaffPayoutPreviewView:
        return self._preview(
            "payout",
            _payout_intent(finance_import_row_ids, obligation_identities),
            correlation_id,
        )

    def apply_payout(
        self,
        finance_import_row_ids: Sequence[int],
        obligation_identities: Sequence[str],
        preview: StaffPayoutPreviewView,
        *,
        reason: str,
        idempotency_key: str,
        correlation_id: str,
    ) -> JobAcceptedResponse:
        intent = _payout_intent(finance_import_row_ids, obligation_identities)
        command_identity = _command_identity(
            reason,
            idempotency_key,
            correlation_id,
        )
        return self._apply("payout", intent, preview, command_identity)

    def preview_return(
        self,
        return_finance_import_row_id: int,
        source_payout_event_id: int,
        obligation_identities: Sequence[str],
        correlation_id: str,
    ) -> StaffPayoutPreviewView:
        intent = _return_intent(
            return_finance_import_row_id,
            source_payout_event_id,
            obligation_identities,
        )
        return self._preview("return", intent, correlation_id)

    # Explicit command fields keep actor data impossible to pass from this client.
    def apply_return(
        self,
        return_finance_import_row_id: int,
        source_payout_event_id: int,
        obligation_identities: Sequence[str],
        preview: StaffPayoutPreviewView,
        *,
        reason: str,
        idempotency_key: str,
        correlation_id: str,
    ) -> JobAcceptedResponse:
        intent = _return_intent(
            return_finance_import_row_id,
            source_payout_event_id,
            obligation_identities,
        )
        command_identity = _command_identity(
            reason,
            idempotency_key,
            correlation_id,
        )
        return self._apply("return", intent, preview, command_identity)

    def preview_reversal(
        self,
        source_payout_event_id: int,
        occurred_on: date,
        obligation_identities: Sequence[str],
        correlation_id: str,
    ) -> StaffPayoutPreviewView:
        intent = _reversal_intent(
            source_payout_event_id,
            occurred_on,
            obligation_identities,
        )
        return self._preview("reversal", intent, correlation_id)

    # Explicit command fields keep actor data impossible to pass from this client.
    def apply_reversal(
        self,
        source_payout_event_id: int,
        occurred_on: date,
        obligation_identities: Sequence[str],
        preview: StaffPayoutPreviewView,
        *,
        reason: str,
        idempotency_key: str,
        correlation_id: str,
    ) -> JobAcceptedResponse:
        intent = _reversal_intent(
            source_payout_event_id,
            occurred_on,
            obligation_identities,
        )
        command_identity = _command_identity(
            reason,
            idempotency_key,
            correlation_id,
        )
        return self._apply("reversal", intent, preview, command_identity)

    def preview_overpayment_recovery_collection(
        self,
        body: StaffOverpaymentRecoveryPreviewBody,
        correlation_id: str,
    ) -> StaffOverpaymentRecoveryPreviewView:
        return self._request(
            "POST",
            "/api/v1/staff-payables/overpayment-recoveries/collection/preview",
            payload=body.model_dump(mode="json"),
            command_headers={"X-Correlation-ID": _canonical_text(correlation_id, "correlation_id")},
            response_type=StaffOverpaymentRecoveryPreviewView,
        )

    def preview_matched_overpayment_recovery_collection(self, body: StaffOverpaymentRecoveryMatchedPreviewBody, correlation_id: str) -> StaffOverpaymentRecoveryPreviewView:
        return self._request("POST", "/api/v1/staff-payables/overpayment-recoveries/matched/preview", response_type=StaffOverpaymentRecoveryPreviewView, payload=body.model_dump(mode="json"), command_headers={"X-Correlation-ID": _canonical_text(correlation_id, "correlation_id")})

    def apply_matched_overpayment_recovery_collection(self, body: StaffOverpaymentRecoveryMatchedApplyBody, idempotency_key: str, correlation_id: str) -> StaffOverpaymentRecoveryReceiptView:
        return self._request("POST", "/api/v1/staff-payables/overpayment-recoveries/matched/apply", response_type=StaffOverpaymentRecoveryReceiptView, payload=body.model_dump(mode="json"), command_headers={"Idempotency-Key": _canonical_text(idempotency_key, "idempotency_key"), "X-Correlation-ID": _canonical_text(correlation_id, "correlation_id")})

    def preview_overpayment_recovery_matching(self, body: StaffOverpaymentRecoveryMatchingPreviewBody, correlation_id: str) -> StaffOverpaymentRecoveryMatchingPreviewView:
        return self._request("POST", "/api/v1/staff-payables/overpayment-recoveries/matching/preview", response_type=StaffOverpaymentRecoveryMatchingPreviewView, payload=body.model_dump(mode="json"), command_headers={"X-Correlation-ID": _canonical_text(correlation_id, "correlation_id")})

    def apply_overpayment_recovery_matching(self, body: StaffOverpaymentRecoveryMatchingApplyBody, idempotency_key: str, correlation_id: str) -> StaffOverpaymentRecoveryMatchingReceiptView:
        return self._request("POST", "/api/v1/staff-payables/overpayment-recoveries/matching/apply", response_type=StaffOverpaymentRecoveryMatchingReceiptView, payload=body.model_dump(mode="json"), command_headers={"Idempotency-Key": _canonical_text(idempotency_key, "idempotency_key"), "X-Correlation-ID": _canonical_text(correlation_id, "correlation_id")})

    def apply_overpayment_recovery_collection(
        self,
        body: StaffOverpaymentRecoveryApplyBody,
        idempotency_key: str,
        correlation_id: str,
    ) -> StaffOverpaymentRecoveryReceiptView:
        return self._recovery_apply(
            "collection",
            body,
            idempotency_key,
            correlation_id,
        )

    def preview_overpayment_recovery_adjustment(
        self,
        body: StaffOverpaymentRecoveryAdjustmentPreviewBody,
        correlation_id: str,
    ) -> StaffOverpaymentRecoveryAdjustmentPreviewView:
        return self._request(
            "POST",
            "/api/v1/staff-payables/overpayment-recoveries/adjustment/preview",
            payload=body.model_dump(mode="json"),
            command_headers={"X-Correlation-ID": _canonical_text(correlation_id, "correlation_id")},
            response_type=StaffOverpaymentRecoveryAdjustmentPreviewView,
        )

    def apply_overpayment_recovery_adjustment(
        self,
        body: StaffOverpaymentRecoveryAdjustmentApplyBody,
        idempotency_key: str,
        correlation_id: str,
    ) -> StaffOverpaymentRecoveryReceiptView:
        return self._recovery_apply(
            "adjustment",
            body,
            idempotency_key,
            correlation_id,
        )

    def _preview(self, operation, intent, correlation_id):
        return self._request(
            "POST",
            f"/api/v1/staff-payables/{operation}/preview",
            payload=intent,
            command_headers={
                "X-Correlation-ID": _canonical_text(
                    correlation_id,
                    "correlation_id",
                )
            },
            response_type=StaffPayoutPreviewView,
        )

    def _apply(self, operation, intent, preview, command_identity):
        payload = {
            **intent,
            **_apply_fields(preview, command_identity),
        }
        return self._request(
            "POST",
            f"/api/v1/staff-payables/{operation}/apply",
            payload=payload,
            command_headers=_command_headers(command_identity),
            response_type=JobAcceptedResponse,
        )

    def _recovery_apply(self, operation, body, idempotency_key, correlation_id):
        return self._request(
            "POST",
            f"/api/v1/staff-payables/overpayment-recoveries/{operation}/apply",
            payload=body.model_dump(mode="json"),
            command_headers={
                "Idempotency-Key": _canonical_text(idempotency_key, "idempotency_key"),
                "X-Correlation-ID": _canonical_text(correlation_id, "correlation_id"),
            },
            response_type=StaffOverpaymentRecoveryReceiptView,
        )

    def get_job_status(self, job_id: str) -> JobResponse:
        return self._query(f"/api/v1/jobs/{job_id}", None, JobResponse)

    def _request(
        self,
        method: str,
        path: str,
        *,
        response_type: type[T],
        payload: Mapping[str, Any] | None = None,
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


def _payout_intent(finance_row_ids, obligation_identities):
    return {
        "finance_import_row_ids": _positive_integer_list(
            finance_row_ids,
            "finance_import_row_ids",
        ),
        "obligation_identities": _identity_list(obligation_identities),
    }


def _difference_mode(value):
    if value not in {"underpayment", "overpayment"}:
        raise ValueError("difference mode is invalid")
    return value


def _return_intent(finance_row_id, source_event_id, obligation_identities):
    return {
        "return_finance_import_row_id": _positive_integer(
            finance_row_id,
            "return_finance_import_row_id",
        ),
        "source_payout_event_id": _positive_integer(
            source_event_id,
            "source_payout_event_id",
        ),
        "obligation_identities": _identity_list(obligation_identities),
    }


def _reversal_intent(source_event_id, occurred_on, obligation_identities):
    if not isinstance(occurred_on, date):
        raise ValueError("occurred_on is required")
    return {
        "source_payout_event_id": _positive_integer(
            source_event_id,
            "source_payout_event_id",
        ),
        "occurred_on": occurred_on.isoformat(),
        "obligation_identities": _identity_list(obligation_identities),
    }


def _apply_fields(preview, command_identity):
    return {
        "expected_staff_payables_version": preview.staff_payables_version,
        "expected_bank_facts_version": preview.bank_facts_version,
        "preview_fingerprint": preview.preview_fingerprint,
        "reason": _canonical_text(command_identity.get("reason"), "reason"),
    }


def _command_identity(reason, idempotency_key, correlation_id):
    return {
        "reason": _canonical_text(reason, "reason"),
        "idempotency_key": _canonical_text(idempotency_key, "idempotency_key"),
        "correlation_id": _canonical_text(correlation_id, "correlation_id"),
    }


def _command_headers(command_identity):
    return {
        "Idempotency-Key": _canonical_text(
            command_identity.get("idempotency_key"),
            "idempotency_key",
        ),
        "X-Correlation-ID": _canonical_text(
            command_identity.get("correlation_id"),
            "correlation_id",
        ),
    }


def _validated_data(response, response_type):
    try:
        envelope = BaseResponse[response_type].model_validate(response.json())
    except (ValueError, ValidationError, TypeError) as error:
        raise _invalid_response_error(response.status_code) from error
    if not envelope.success or envelope.data is None:
        raise _invalid_response_error(response.status_code)
    return envelope.data


def _http_error(response):
    try:
        body = response.json()
        detail = body.get("detail") if isinstance(body, dict) else None
        candidate = detail.get("error") if isinstance(detail, dict) else None
        error = StaffPayoutTypedErrorView.model_validate(candidate)
    except (ValueError, ValidationError, TypeError, AttributeError):
        error = _fallback_error(response.status_code)
    return StaffPayoutApiError(response.status_code, error)


def _transport_error():
    return StaffPayoutApiError(
        None,
        StaffPayoutTypedErrorView(
            category="unavailable",
            code="staff_payout_transport_error",
            message="無法連線至月嫂付款核銷 API。",
            correlation_id="client",
            retryable=True,
        ),
    )


def _invalid_response_error(status_code):
    return StaffPayoutApiError(
        status_code,
        StaffPayoutTypedErrorView(
            category="internal",
            code="staff_payout_invalid_response",
            message="月嫂付款核銷 API 回傳格式不正確。",
            correlation_id="client",
        ),
    )


def _fallback_error(status_code):
    retryable = status_code in {502, 503, 504}
    return StaffPayoutTypedErrorView(
        category="unavailable" if retryable else "internal",
        code="staff_payout_request_failed",
        message="月嫂付款核銷 API 請求失敗。",
        correlation_id="client",
        retryable=retryable,
    )


def _positive_integer_list(values, field_name):
    canonical = [
        _positive_integer(value, field_name)
        for value in values
    ]
    if not canonical or len(canonical) != len(set(canonical)):
        raise ValueError(f"{field_name} must be non-empty and unique")
    return sorted(canonical)


def _identity_list(values):
    canonical = [
        _canonical_text(value, "obligation_identity")
        for value in values
    ]
    if not canonical or len(canonical) != len(set(canonical)):
        raise ValueError("obligation_identities must be non-empty and unique")
    return sorted(canonical)


def _positive_integer(value, field_name):
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{field_name} must contain positive integers")
    return value


def _canonical_text(value, field_name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} is required")
    return value.strip()


__all__ = ["StaffPayoutApiClient", "StaffPayoutApiError"]
