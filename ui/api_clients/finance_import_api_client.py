"""Framework-neutral client for Finance Import server workflows."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, TypeVar
from urllib.parse import quote

import requests
from pydantic import BaseModel, ValidationError

from api.schemas.base import BaseResponse
from api.schemas.finance_import import (
    FinanceImportBatchManifestView,
    FinanceImportBatchPreviewView,
    FinanceImportBatchReceiptView,
    FinanceImportBatchSummaryView,
    FinanceImportCorrectionPreviewView,
    FinanceImportCorrectionReceiptView,
    FinanceImportHistoricalReprocessPlanView,
    FinanceImportReprocessRunPageView,
    FinanceImportReviewRowPageView,
    FinanceImportTypedErrorView,
    FinanceWorkbookIngestionReceiptView,
)
from api.schemas.jobs import JobAcceptedResponse, JobResponse

T = TypeVar("T", bound=BaseModel)


class FinanceImportApiError(RuntimeError):
    def __init__(self, status_code, error) -> None:
        super().__init__(error.message)
        self.status_code = status_code
        self.error = error


class FinanceImportApiClient:
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

    # Kept cohesive because multipart bytes and command identity are one request.
    def ingest_workbook(
        self,
        filename: str,
        content: bytes,
        *,
        idempotency_key: str,
        correlation_id: str,
    ) -> FinanceWorkbookIngestionReceiptView:
        canonical_filename = _canonical_text(filename, "filename")
        if not isinstance(content, bytes) or not content:
            raise ValueError("workbook content is required")
        headers = {
            **self._headers,
            **_command_headers(idempotency_key, correlation_id),
        }
        try:
            response = self._session.request(
                "POST",
                f"{self._base_url}/api/v1/finance-import/workbooks/ingest",
                headers=headers,
                files={
                    "workbook": (
                        canonical_filename,
                        content,
                        "application/vnd.openxmlformats-officedocument."
                        "spreadsheetml.sheet",
                    )
                },
                timeout=self._timeout,
            )
        except requests.RequestException as error:
            raise _transport_error() from error
        if not response.ok:
            raise _http_error(response)
        return _validated_data(response, FinanceWorkbookIngestionReceiptView)

    # Kept whole so the client sends only the batch identity to authoritative Preview.
    def list_batches(
        self,
        *,
        limit: int = 50,
        before_batch_id: int | None = None,
    ):
        params = _page_params(limit, before_batch_id, "before_batch_id")
        response = self._send(
            "GET",
            "/api/v1/finance-import/batches",
            None,
            {},
            params=params,
        )
        if not response.ok:
            raise _http_error(response)
        return _validated_list(response, FinanceImportBatchSummaryView)

    def get_manifest(
        self,
        batch_identity: str,
    ) -> FinanceImportBatchManifestView:
        identity = _batch_path_identity(batch_identity)
        return self._query(
            f"/api/v1/finance-import/batches/{identity}/manifest",
            {},
            FinanceImportBatchManifestView,
        )

    def list_review_rows(
        self,
        batch_identity: str,
        *,
        limit: int = 50,
        after_row_id: int | None = None,
    ) -> FinanceImportReviewRowPageView:
        params = _page_params(limit, after_row_id, "after_row_id")
        identity = _batch_path_identity(batch_identity)
        return self._query(
            f"/api/v1/finance-import/batches/{identity}/review-rows",
            params,
            FinanceImportReviewRowPageView,
        )

    def list_reprocess_runs(
        self,
        batch_identity: str,
        *,
        limit: int = 25,
        before_run_id: int | None = None,
    ) -> FinanceImportReprocessRunPageView:
        params = _page_params(limit, before_run_id, "before_run_id")
        identity = _batch_path_identity(batch_identity)
        return self._query(
            f"/api/v1/finance-import/batches/{identity}/reprocess-runs",
            params,
            FinanceImportReprocessRunPageView,
        )

    # Kept whole so the client sends only the batch identity to authoritative Preview.
    def preview_batch(
        self,
        batch_identity: str,
        correlation_id: str,
    ) -> FinanceImportBatchPreviewView:
        return self._request(
            "POST",
            "/api/v1/finance-import/batches/preview",
            {
                "batch_identity": _canonical_text(
                    batch_identity,
                    "batch_identity",
                )
            },
            {
                "X-Correlation-ID": _canonical_text(
                    correlation_id,
                    "correlation_id",
                )
            },
            FinanceImportBatchPreviewView,
        )

    # Kept whole so Apply can only reuse one server-generated batch Preview.
    def apply_batch(
        self,
        preview: FinanceImportBatchPreviewView,
        *,
        reason: str,
        idempotency_key: str,
        correlation_id: str,
    ) -> JobAcceptedResponse:
        payload = {
            "batch_identity": preview.batch_identity,
            "expected_batch_version": preview.batch_version,
            "preview_fingerprint": preview.preview_fingerprint,
            "reason": _canonical_text(reason, "reason"),
        }
        return self._request(
            "POST",
            "/api/v1/finance-import/batches/apply",
            payload,
            _command_headers(idempotency_key, correlation_id),
            JobAcceptedResponse,
        )

    # Kept whole so manual evidence and target choices cross one typed boundary.
    def preview_correction(
        self,
        row_identity: str,
        classification_type: str,
        target_obligation_identities: Sequence[str],
        reason: str,
        evidence: Sequence[str],
        correlation_id: str,
        refund_ledger_entry_identity: str | None = None,
        allow_partial_refund_recovery: bool = False,
        allow_refund_overage_recovery: bool = False,
        allow_client_receipt_overage: bool = False,
    ) -> FinanceImportCorrectionPreviewView:
        payload = _correction_payload(
            row_identity,
            classification_type,
            target_obligation_identities,
            reason,
            evidence,
            refund_ledger_entry_identity,
            allow_partial_refund_recovery,
            allow_refund_overage_recovery,
            allow_client_receipt_overage,
        )
        return self._request(
            "POST",
            "/api/v1/finance-import/corrections/preview",
            payload,
            {
                "X-Correlation-ID": _canonical_text(
                    correlation_id,
                    "correlation_id",
                )
            },
            FinanceImportCorrectionPreviewView,
        )

    # Kept whole so Apply can only reuse a server-generated correction Preview.
    def apply_correction(
        self,
        preview: FinanceImportCorrectionPreviewView,
        *,
        idempotency_key: str,
        correlation_id: str,
    ) -> JobAcceptedResponse:
        candidate = preview.candidate
        payload = {
            **_correction_payload(
                candidate.row_identity,
                candidate.classification_type,
                [item.obligation_identity for item in candidate.allocations],
                candidate.reason,
                candidate.evidence,
                candidate.refund_ledger_entry_identity,
                candidate.allow_partial_refund_recovery,
                candidate.allow_refund_overage_recovery,
                candidate.allow_client_receipt_overage,
            ),
            "expected_batch_version": preview.batch_version,
            "expected_canonical_fact_version": preview.canonical_fact_version,
            "expected_alert_version": preview.alert_version,
            "preview_fingerprint": preview.preview_fingerprint,
        }
        return self._request(
            "POST",
            "/api/v1/finance-import/corrections/apply",
            payload,
            _command_headers(idempotency_key, correlation_id),
            JobAcceptedResponse,
        )

    def preview_historical_reprocess(
        self,
        batch_identity: str,
        correlation_id: str,
        owner_selections: Sequence[Mapping[str, Any]] = (),
    ) -> FinanceImportHistoricalReprocessPlanView:
        return self._request(
            "POST",
            "/api/v1/finance-import/historical-reprocess/preview",
            {
                "batch_identity": _canonical_text(batch_identity, "batch_identity"),
                "owner_selections": _historical_owner_selections(owner_selections),
            },
            {"X-Correlation-ID": _canonical_text(correlation_id, "correlation_id")},
            FinanceImportHistoricalReprocessPlanView,
        )

    def apply_historical_reprocess(
        self,
        preview: FinanceImportHistoricalReprocessPlanView,
        *,
        reason: str,
        idempotency_key: str,
        correlation_id: str,
    ) -> JobAcceptedResponse:
        return self._request(
            "POST",
            "/api/v1/finance-import/historical-reprocess/apply",
            {
                "batch_identity": preview.batch_identity,
                "expected_batch_version": preview.batch_version,
                "preview_fingerprint": preview.preview_fingerprint,
                "reason": _canonical_text(reason, "reason"),
                "owner_selections": [
                    item.model_dump() for item in preview.owner_selections
                ],
            },
            _command_headers(idempotency_key, correlation_id),
            JobAcceptedResponse,
        )

    def get_job_status(self, job_id: str) -> JobResponse:
        return self._query(f"/api/v1/jobs/{job_id}", None, JobResponse)

    def _request(self, method, path, payload, headers, response_type: type[T]) -> T:
        response = self._send(method, path, payload, headers)
        if not response.ok:
            raise _http_error(response)
        return _validated_data(response, response_type)

    def _query(self, path, params, response_type: type[T]) -> T:
        response = self._send("GET", path, None, {}, params=params)
        if not response.ok:
            raise _http_error(response)
        return _validated_data(response, response_type)

    def _send(self, method, path, payload, command_headers, **request_options):
        headers = {**self._headers, **command_headers}
        if payload is not None:
            request_options["json"] = payload
        try:
            return self._session.request(
                method,
                f"{self._base_url}{path}",
                headers=headers,
                timeout=self._timeout,
                **request_options,
            )
        except requests.RequestException as error:
            raise _transport_error() from error


# Kept whole so the client sends choices and evidence but no derived money.
def _correction_payload(
    row_identity,
    classification_type,
    target_obligation_identities,
    reason,
    evidence,
    refund_ledger_entry_identity=None,
    allow_partial_refund_recovery=False,
    allow_refund_overage_recovery=False,
    allow_client_receipt_overage=False,
):
    targets = _canonical_sorted_text(
        target_obligation_identities,
        "target_obligation_identities",
    )
    evidence_items = _canonical_sorted_text(evidence, "evidence")
    payload = {
        "row_identity": _canonical_text(row_identity, "row_identity"),
        "classification_type": _canonical_text(
            classification_type,
            "classification_type",
        ),
        "target_obligation_identities": targets,
        "reason": _canonical_text(reason, "reason"),
        "evidence": evidence_items,
        "allow_partial_refund_recovery": allow_partial_refund_recovery,
        "allow_refund_overage_recovery": allow_refund_overage_recovery,
        "allow_client_receipt_overage": allow_client_receipt_overage,
    }
    if refund_ledger_entry_identity is not None:
        payload["refund_ledger_entry_identity"] = _canonical_text(
            refund_ledger_entry_identity,
            "refund_ledger_entry_identity",
        )
    return payload


def _command_headers(idempotency_key, correlation_id):
    return {
        "Idempotency-Key": _canonical_text(
            idempotency_key,
            "idempotency_key",
        ),
        "X-Correlation-ID": _canonical_text(
            correlation_id,
            "correlation_id",
        ),
    }


def _historical_owner_selections(values):
    selections = []
    for item in values:
        row_identity = _canonical_text(item["row_identity"], "row_identity")
        selections.append(
            {
                "row_identity": row_identity,
                "case_no": _canonical_text(item["case_no"], "case_no"),
                "obligation_identity": _canonical_text(item["obligation_identity"], "obligation_identity"),
                "reason": _canonical_text(item["reason"], "reason"),
                "evidence_references": _canonical_sorted_text(item["evidence_references"], "evidence_references"),
            }
        )
    return sorted(selections, key=lambda item: item["row_identity"])


def _validated_data(response, response_type):
    try:
        envelope = BaseResponse[response_type].model_validate(response.json())
    except (ValueError, ValidationError, TypeError) as error:
        raise _invalid_response_error(response.status_code) from error
    if not envelope.success or envelope.data is None:
        raise _invalid_response_error(response.status_code)
    return envelope.data


def _validated_list(response, item_type):
    try:
        envelope = BaseResponse[list[item_type]].model_validate(response.json())
    except (ValueError, ValidationError, TypeError) as error:
        raise _invalid_response_error(response.status_code) from error
    if not envelope.success or envelope.data is None:
        raise _invalid_response_error(response.status_code)
    return envelope.data


def _http_error(response):
    try:
        detail = response.json().get("detail")
        candidate = detail.get("error") if isinstance(detail, dict) else None
        error = FinanceImportTypedErrorView.model_validate(candidate)
    except (ValueError, ValidationError, TypeError, AttributeError):
        error = _fallback_error(response.status_code)
    return FinanceImportApiError(response.status_code, error)


def _transport_error():
    return FinanceImportApiError(
        None,
        FinanceImportTypedErrorView(
            category="unavailable",
            code="finance_import_transport_error",
            message="無法連線至 Finance Import API。",
            correlation_id="client",
            retryable=True,
        ),
    )


def _invalid_response_error(status_code):
    return FinanceImportApiError(
        status_code,
        FinanceImportTypedErrorView(
            category="internal",
            code="finance_import_invalid_response",
            message="Finance Import API 回傳格式不正確。",
            correlation_id="client",
        ),
    )


def _fallback_error(status_code):
    retryable = status_code in {502, 503, 504}
    return FinanceImportTypedErrorView(
        category="unavailable" if retryable else "internal",
        code="finance_import_request_failed",
        message="Finance Import API 請求失敗。",
        correlation_id="client",
        retryable=retryable,
    )


def _canonical_sorted_text(values, field_name):
    canonical = sorted({_canonical_text(value, field_name) for value in values})
    if not canonical:
        raise ValueError(f"{field_name} is required")
    return canonical


def _page_params(limit, cursor, cursor_name):
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
        raise ValueError("limit must be an integer between 1 and 100")
    params = {"limit": limit}
    if cursor is not None:
        params[cursor_name] = _positive_cursor(cursor, cursor_name)
    return params


def _positive_cursor(value, field_name):
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{field_name} must be a positive integer")
    return value


def _batch_path_identity(value):
    return quote(_canonical_text(value, "batch_identity"), safe=":")


def _canonical_text(value, field_name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} is required")
    return value.strip()


__all__ = ["FinanceImportApiClient", "FinanceImportApiError"]
