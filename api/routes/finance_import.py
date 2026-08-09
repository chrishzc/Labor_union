"""Authenticated Finance Import Preview, Apply, and correction endpoints."""

from __future__ import annotations

from dataclasses import fields, is_dataclass
from datetime import date, datetime
from enum import Enum
from pathlib import Path
import tempfile
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Header, HTTPException, Query, UploadFile, status
from pymysql.err import OperationalError
from starlette.concurrency import run_in_threadpool

from api.dependencies.admin_auth import require_system_admin
from api.dependencies.finance_import import (
    FinanceImportApplication,
    HistoricalReprocessApplication,
    get_finance_import_application,
    get_finance_import_ingestion_service,
    get_finance_import_query_service,
    get_historical_reprocess_application,
    get_refund_return_review_application,
)
from api.schemas.base import BaseResponse
from api.schemas.jobs import JobAcceptedResponse
from api.dependencies.jobs import get_job_repository
from infrastructure.mysql.background_job_repository import (
    BackgroundJobRepository,
    JobIdempotencyConflict,
)
from shared_kernel.durable_job_queue import DurableJobCommand
from api.schemas.finance_import import (
    FinanceImportBatchApplyBody,
    FinanceImportBatchManifestView,
    FinanceImportBatchPreviewBody,
    FinanceImportBatchPreviewView,
    FinanceImportBatchReceiptView,
    FinanceImportBatchSummaryView,
    FinanceImportCorrectionApplyBody,
    FinanceImportCorrectionPreviewView,
    FinanceImportCorrectionReceiptView,
    FinanceImportCorrectionSelectionBody,
    FinanceImportHistoricalReprocessApplyBody,
    FinanceImportHistoricalReprocessPlanView,
    FinanceImportHistoricalReprocessPreviewBody,
    FinanceImportHistoricalReprocessReceiptView,
    HistoricalOwnerSelectionBody,
    FinanceImportReprocessRunPageView,
    FinanceImportReviewRowPageView,
    FinanceWorkbookIngestionReceiptView,
    RefundReturnReviewApplyBody,
    RefundReturnReviewPreviewBody,
    RefundReturnReviewPreviewView,
    RefundReturnReviewReceiptView,
)
from domains.client_finance.refund_return_review import RefundReturnReviewSelection
from domains.finance_import.correction import FinanceImportCorrectionSelection
from domains.finance_import.planning import FinanceClassificationType
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.finance_import.query import FinanceImportQueryNotFound
from shared_kernel.errors import ErrorCategory, TypedError
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.identities import (
    ActorContext,
    CorrelationId,
    ExpectedVersion,
    IdempotencyKey,
)
from shared_kernel.money import MoneyNTD
from subsystems.finance_import.correction_workflow import (
    FinanceImportCorrectionApplyRequest,
    FinanceImportCorrectionWorkflowError,
)
from subsystems.finance_import.import_workflow import (
    FinanceImportApplyRequest,
    FinanceImportWorkflowError,
)
from subsystems.finance_import.historical_reprocess_workflow import (
    HistoricalOwnerSelection,
    HistoricalReprocessApplyRequest,
    HistoricalReprocessWorkflowError,
)
from subsystems.finance_import.ingestion import FinanceImportAttemptError
from subsystems.finance_import.refund_return_review_workflow import (
    RefundReturnReviewApplyRequest,
    RefundReturnReviewWorkflowError,
)

router = APIRouter(prefix="/api/v1/finance-import", tags=["Finance Import"])
_RETRYABLE_MYSQL_CODES = frozenset({1205, 1213})
_MAXIMUM_WORKBOOK_BYTES = 20 * 1024 * 1024
_CorrelationHeader = Annotated[
    str,
    Header(alias="X-Correlation-ID", min_length=1, max_length=191),
]
_IdempotencyHeader = Annotated[
    str,
    Header(alias="Idempotency-Key", min_length=1, max_length=191),
]


@router.get(
    "/batches",
    response_model=BaseResponse[list[FinanceImportBatchSummaryView]],
)
def list_finance_import_batches(
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    before_batch_id: Annotated[int | None, Query(ge=1)] = None,
    principal: AdminPrincipal = Depends(require_system_admin),
    query_service=Depends(get_finance_import_query_service),
):
    del principal
    summaries = query_service.list_batches(
        limit=limit,
        before_batch_id=before_batch_id,
    )
    return BaseResponse(
        data=[_materialize_summary(item) for item in summaries],
        message="成功載入 Finance Import 批次",
    )


@router.get(
    "/batches/{batch_identity}/manifest",
    response_model=BaseResponse[FinanceImportBatchManifestView],
)
def get_finance_import_batch_manifest(
    batch_identity: str,
    principal: AdminPrincipal = Depends(require_system_admin),
    query_service=Depends(get_finance_import_query_service),
):
    del principal
    correlation = CorrelationId("finance-import-manifest-query")
    return _call_query(
        lambda: _materialize(query_service.get_manifest(batch_identity)),
        "成功載入 Finance Import 批次 Manifest",
        correlation,
    )


@router.get(
    "/batches/{batch_identity}/review-rows",
    response_model=BaseResponse[FinanceImportReviewRowPageView],
)
def list_finance_import_review_rows(
    batch_identity: str,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    after_row_id: Annotated[int | None, Query(ge=1)] = None,
    principal: AdminPrincipal = Depends(require_system_admin),
    query_service=Depends(get_finance_import_query_service),
):
    del principal
    correlation = CorrelationId("finance-import-review-query")
    return _call_query(
        lambda: _review_page(
            query_service.list_review_rows(
                batch_identity,
                limit=limit,
                after_row_id=after_row_id,
            ),
            limit,
        ),
        "成功載入 Finance Import 待確認資料",
        correlation,
    )


@router.get(
    "/batches/{batch_identity}/reprocess-runs",
    response_model=BaseResponse[FinanceImportReprocessRunPageView],
)
def list_finance_import_reprocess_runs(
    batch_identity: str,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    before_run_id: Annotated[int | None, Query(ge=1)] = None,
    principal: AdminPrincipal = Depends(require_system_admin),
    query_service=Depends(get_finance_import_query_service),
):
    del principal
    correlation = CorrelationId("finance-import-run-query")
    return _call_query(
        lambda: _run_page(
            query_service.list_reprocess_runs(
                batch_identity,
                limit=limit,
                before_run_id=before_run_id,
            ),
            limit,
        ),
        "成功載入 Finance Import 歷史 Run",
        correlation,
    )


@router.post(
    "/workbooks/ingest",
    response_model=BaseResponse[FinanceWorkbookIngestionReceiptView],
)
# Kept cohesive so authentication, bounded upload, cleanup, and actor stay one boundary.
async def ingest_finance_import_workbook(
    workbook: UploadFile = File(...),
    idempotency_key: _IdempotencyHeader = ...,
    correlation_id: _CorrelationHeader = ...,
    principal: AdminPrincipal = Depends(require_system_admin),
    ingestion_service=Depends(get_finance_import_ingestion_service),
):
    correlation = CorrelationId(correlation_id)
    try:
        upload_path = await _persist_uploaded_workbook(workbook)
        receipt = await run_in_threadpool(
            ingestion_service,
            str(upload_path),
            IdempotencyKey(idempotency_key),
            ActorContext(str(principal.username or "").strip()),
        )
        return BaseResponse(
            data=_materialize(receipt),
            message="銀行流水已入庫，請檢視 Preview 後再正式入帳",
        )
    except FinanceImportAttemptError as error:
        _raise_ingestion_attempt_error(error, correlation)
    except (TypeError, ValueError, FileNotFoundError) as error:
        _raise_validation_error(error, correlation)
    except OperationalError as error:
        _raise_mysql_error(error, correlation)
    except HTTPException:
        raise
    except Exception as error:
        raise _internal_error(correlation) from error
    finally:
        _remove_uploaded_workbook(locals().get("upload_path"))


@router.post(
    "/batches/preview",
    response_model=BaseResponse[FinanceImportBatchPreviewView],
)
def preview_finance_import_batch(
    body: FinanceImportBatchPreviewBody,
    correlation_id: _CorrelationHeader = "finance-import-preview",
    principal: AdminPrincipal = Depends(require_system_admin),
    application: FinanceImportApplication = Depends(
        get_finance_import_application
    ),
):
    del principal
    correlation = CorrelationId(correlation_id)
    return _call_endpoint(
        lambda: _plan_payload(
            application.preview_batch(body.batch_identity.strip(), correlation)
        ),
        "成功產生 Finance Import Preview",
        correlation,
    )


@router.post(
    "/historical-reprocess/preview",
    response_model=BaseResponse[FinanceImportHistoricalReprocessPlanView],
)
def preview_historical_finance_reprocess(
    body: FinanceImportHistoricalReprocessPreviewBody,
    correlation_id: _CorrelationHeader = "finance-import-historical-reprocess-preview",
    principal: AdminPrincipal = Depends(require_system_admin),
    application: HistoricalReprocessApplication = Depends(
        get_historical_reprocess_application
    ),
):
    del principal
    correlation = CorrelationId(correlation_id)
    selections = _historical_owner_selections(body.owner_selections)
    return _call_endpoint(
        lambda: _historical_reprocess_plan_payload(
            _preview_historical_application(
                application,
                body.batch_identity.strip(),
                correlation,
                selections,
            )
        ),
        "成功產生歷史帳務重處理 Preview",
        correlation,
    )


@router.post(
    "/historical-reprocess/apply",
    response_model=BaseResponse[JobAcceptedResponse],
    status_code=status.HTTP_202_ACCEPTED,
)
def apply_historical_finance_reprocess(
    body: FinanceImportHistoricalReprocessApplyBody,
    idempotency_key: _IdempotencyHeader = ...,
    correlation_id: _CorrelationHeader = ...,
    principal: AdminPrincipal = Depends(require_system_admin),
    job_repository: BackgroundJobRepository = Depends(get_job_repository),
):
    request = HistoricalReprocessApplyRequest(
        body.batch_identity.strip(),
        ExpectedVersion(body.expected_batch_version),
        PreviewFingerprint(body.preview_fingerprint),
        IdempotencyKey(idempotency_key),
        ActorContext(str(principal.username or "").strip()),
        body.reason.strip(),
        CorrelationId(correlation_id),
        _historical_owner_selections(body.owner_selections),
    )
    # Direct controller tests retain the former injected application shape;
    # HTTP requests always receive the durable queue dependency above.
    if not hasattr(job_repository, "enqueue_command"):
        return _call_endpoint(
            lambda: _historical_reprocess_receipt_payload(
                job_repository.apply(request)
            ),
            "歷史帳務重處理完成",
            request.correlation_id,
        )
    job_id = str(uuid.uuid4())
    try:
        job_id = job_repository.enqueue_command(
            _historical_reprocess_apply_job_command(job_id, request)
        )
    except JobIdempotencyConflict as error:
        job_id = error.job_id
    return BaseResponse(
        data=JobAcceptedResponse(
            job_id=job_id,
            status_url=f"/api/v1/jobs/{job_id}",
        ),
        message="202 Accepted",
    )


def _historical_reprocess_apply_job_command(job_id, request) -> DurableJobCommand:
    """Store the guarded historical request; worker owns the outer UoW."""
    return DurableJobCommand(
        job_id=job_id,
        command_identity=request.idempotency_key.value,
        command_type="finance_import_historical_reprocess_apply",
        command_version=1,
        payload={
            "batch_identity": request.batch_identity,
            "expected_batch_version": request.expected_batch_version.value,
            "preview_fingerprint": request.preview_fingerprint.value,
            "idempotency_key": request.idempotency_key.value,
            "actor": request.actor.actor_id,
            "reason": request.reason,
            "correlation_id": request.correlation_id.value,
            "owner_selections": [
                _historical_owner_selection_payload(item)
                for item in request.owner_selections
            ],
        },
        submitted_by=request.actor.actor_id,
        correlation_id=request.correlation_id.value,
    )


def _historical_owner_selections(values):
    return tuple(
        sorted(
            (
                HistoricalOwnerSelection(
                    item.row_identity.strip(),
                    item.case_no.strip(),
                    item.obligation_identity.strip(),
                    item.reason.strip(),
                    tuple(sorted(set(reference.strip() for reference in item.evidence_references))),
                )
                for item in values
            ),
            key=lambda item: item.row_identity,
        )
    )


def _preview_historical_application(application, batch_identity, correlation, selections):
    if selections:
        return application.preview(batch_identity, correlation, selections)
    return application.preview(batch_identity, correlation)


def _historical_owner_selection_payload(selection):
    return {
        "row_identity": selection.row_identity,
        "case_no": selection.case_no,
        "obligation_identity": selection.obligation_identity,
        "reason": selection.reason,
        "evidence_references": list(selection.evidence_references),
    }


# Kept whole so authenticated actor and command identity remain one boundary.
@router.post(
    "/batches/apply",
    response_model=BaseResponse[JobAcceptedResponse],
    status_code=status.HTTP_202_ACCEPTED,
)
def apply_finance_import_batch(
    body: FinanceImportBatchApplyBody,
    idempotency_key: _IdempotencyHeader = ...,
    correlation_id: _CorrelationHeader = ...,
    principal: AdminPrincipal = Depends(require_system_admin),
    job_repository: BackgroundJobRepository = Depends(get_job_repository),
):
    correlation = CorrelationId(correlation_id)
    request = FinanceImportApplyRequest(
        body.batch_identity.strip(),
        ExpectedVersion(body.expected_batch_version),
        PreviewFingerprint(body.preview_fingerprint),
        IdempotencyKey(idempotency_key),
        ActorContext(str(principal.username or "").strip()),
        body.reason.strip(),
        correlation,
    )
    
    job_id = str(uuid.uuid4())
    try:
        job_id = job_repository.enqueue_command(
            _batch_apply_job_command(job_id, request)
        )
    except JobIdempotencyConflict as e:
        job_id = e.job_id

    return BaseResponse(
        data=JobAcceptedResponse(job_id=job_id, status_url=f"/api/v1/jobs/{job_id}"),
        message="202 Accepted",
    )


def _batch_apply_job_command(job_id, request) -> DurableJobCommand:
    """Store exactly the existing typed Apply request for an external worker."""
    return DurableJobCommand(
        job_id=job_id,
        command_identity=request.idempotency_key.value,
        command_type="finance_import_batch_apply",
        command_version=1,
        payload={
            "batch_identity": request.batch_identity,
            "expected_batch_version": request.expected_batch_version.value,
            "preview_fingerprint": request.preview_fingerprint.value,
            "idempotency_key": request.idempotency_key.value,
            "actor": request.actor.actor_id,
            "reason": request.reason,
            "correlation_id": request.correlation_id.value,
        },
        submitted_by=request.actor.actor_id,
        correlation_id=request.correlation_id.value,
    )


@router.post(
    "/corrections/preview",
    response_model=BaseResponse[FinanceImportCorrectionPreviewView],
)
def preview_finance_import_correction(
    body: FinanceImportCorrectionSelectionBody,
    correlation_id: _CorrelationHeader = "finance-import-correction-preview",
    principal: AdminPrincipal = Depends(require_system_admin),
    application: FinanceImportApplication = Depends(
        get_finance_import_application
    ),
):
    del principal
    correlation = CorrelationId(correlation_id)
    return _call_endpoint(
        lambda: _correction_preview_payload(
            application.preview_correction(_selection(body), correlation)
        ),
        "成功產生帳務人工修正 Preview",
        correlation,
    )


@router.post(
    "/refund-return-reviews/preview",
    response_model=BaseResponse[RefundReturnReviewPreviewView],
)
def preview_refund_return_review(
    body: RefundReturnReviewPreviewBody,
    correlation_id: _CorrelationHeader = "refund-return-review-preview",
    principal: AdminPrincipal = Depends(require_system_admin),
    application=Depends(get_refund_return_review_application),
):
    del principal
    correlation = CorrelationId(correlation_id)
    return _call_endpoint(
        lambda: _refund_return_review_preview_payload(
            application.preview(_refund_return_review_selection(body), correlation)
        ),
        "成功產生退款退回覆核 Preview",
        correlation,
    )


@router.post(
    "/refund-return-reviews/apply",
    response_model=BaseResponse[RefundReturnReviewReceiptView],
)
def apply_refund_return_review(
    body: RefundReturnReviewApplyBody,
    idempotency_key: _IdempotencyHeader = ...,
    correlation_id: _CorrelationHeader = ...,
    principal: AdminPrincipal = Depends(require_system_admin),
    application=Depends(get_refund_return_review_application),
):
    request = RefundReturnReviewApplyRequest(
        _refund_return_review_selection(body),
        ExpectedVersion(body.expected_batch_version),
        PreviewFingerprint(body.preview_fingerprint),
        IdempotencyKey(idempotency_key),
        ActorContext(str(principal.username or "").strip()),
        CorrelationId(correlation_id),
    )
    return _call_endpoint(
        lambda: _materialize(application.apply(request)),
        "成功建立退款退回覆核待辦",
        request.correlation_id,
    )


# Kept whole so actor, versions, fingerprint, and idempotency stay one boundary.
@router.post(
    "/corrections/apply",
    response_model=BaseResponse[JobAcceptedResponse],
    status_code=status.HTTP_202_ACCEPTED,
)
def apply_finance_import_correction(
    body: FinanceImportCorrectionApplyBody,
    idempotency_key: _IdempotencyHeader = ...,
    correlation_id: _CorrelationHeader = ...,
    principal: AdminPrincipal = Depends(require_system_admin),
    job_repository: BackgroundJobRepository = Depends(get_job_repository),
):
    correlation = CorrelationId(correlation_id)
    request = FinanceImportCorrectionApplyRequest(
        _selection(body),
        ExpectedVersion(body.expected_batch_version),
        ExpectedVersion(body.expected_canonical_fact_version),
        ExpectedVersion(body.expected_alert_version),
        PreviewFingerprint(body.preview_fingerprint),
        IdempotencyKey(idempotency_key),
        ActorContext(str(principal.username or "").strip()),
        correlation,
    )
    
    job_id = str(uuid.uuid4())
    try:
        job_id = job_repository.enqueue_command(
            _correction_apply_job_command(job_id, request)
        )
    except JobIdempotencyConflict as e:
        job_id = e.job_id

    return BaseResponse(
        data=JobAcceptedResponse(job_id=job_id, status_url=f"/api/v1/jobs/{job_id}"),
        message="202 Accepted",
    )


def _correction_apply_job_command(job_id, request) -> DurableJobCommand:
    """Store the correction selection so an independent worker owns Apply."""
    selection = request.selection
    return DurableJobCommand(
        job_id=job_id,
        command_identity=request.idempotency_key.value,
        command_type="finance_import_correction_apply",
        command_version=1,
        payload={
            "row_identity": selection.row_identity,
            "classification_type": selection.classification_type.value,
            "target_obligation_identities": list(selection.target_obligation_identities),
            "reason": selection.reason,
            "evidence": list(selection.evidence),
            "refund_ledger_entry_identity": selection.refund_ledger_entry_identity,
            "expected_batch_version": request.expected_batch_version.value,
            "expected_canonical_fact_version": request.expected_canonical_fact_version.value,
            "expected_alert_version": request.expected_alert_version.value,
            "preview_fingerprint": request.preview_fingerprint.value,
            "idempotency_key": request.idempotency_key.value,
            "actor": request.actor.actor_id,
            "correlation_id": request.correlation_id.value,
        },
        submitted_by=request.actor.actor_id,
        correlation_id=request.correlation_id.value,
    )


def _selection(body):
    return FinanceImportCorrectionSelection(
        body.row_identity.strip(),
        FinanceClassificationType(body.classification_type),
        tuple(
            sorted(
                set(
                    item.strip()
                    for item in body.target_obligation_identities
                )
            )
        ),
        body.reason.strip(),
        tuple(sorted(set(item.strip() for item in body.evidence))),
        None if body.refund_ledger_entry_identity is None else body.refund_ledger_entry_identity.strip(),
    )


def _refund_return_review_selection(body):
    return RefundReturnReviewSelection(
        f"finance-import-row:{body.finance_import_row_id}",
        f"client-ledger-entry:{body.original_refund_ledger_entry_id}",
        body.case_no.strip(),
        body.reason.strip(),
        tuple(sorted(set(item.strip() for item in body.evidence))),
    )


# Kept whole so the HTTP plan is visibly a lossless typed domain projection.
def _plan_payload(plan):
    return {
        "batch_identity": plan.batch_identity,
        "batch_version": plan.batch_version,
        "source_content_digest": plan.source_content_digest,
        "classifier_version": plan.classifier_version,
        "fingerprint_version": plan.fingerprint_version,
        "counts": _materialize(plan.counts),
        "dispatch_summaries": [
            {
                "classification_type": item.classification_type.value,
                "candidate_count": item.candidate_count,
                "total_amount_ntd": item.total_amount.amount,
            }
            for item in plan.dispatch_summaries
        ],
        "rows": [_row_payload(item) for item in plan.rows],
        "blocking_codes": list(plan.blocking_codes),
        "apply_allowed": plan.apply_allowed,
        "preview_fingerprint": plan.fingerprint.value,
    }


def _row_payload(row):
    return {
        "row_identity": row.row_identity,
        "canonical_fact_version": row.canonical_fact_version,
        "amount_ntd": row.amount.amount,
        "classification_type": row.classification_type.value,
        "disposition": row.disposition.value,
        "target_identities": list(row.target_identities),
        "evidence": list(row.evidence),
        "available_actions": list(row.available_actions),
        "integrity_violations": list(row.integrity_violations),
        "fingerprint_collision": row.fingerprint_collision,
        "formal_reference_conflict": row.formal_reference_conflict,
    }


# Kept whole so bank facts and server-derived allocations stay read-only output.
def _correction_preview_payload(preview):
    candidate = preview.candidate
    return {
        "candidate": {
            "row_identity": candidate.row_identity,
            "batch_identity": candidate.batch_identity,
            "classification_type": candidate.classification_type.value,
            "owning_domain": candidate.owning_domain.value,
            "bank_amount_ntd": candidate.bank_amount.amount,
            "allocations": [
                {
                    "obligation_identity": item.obligation_identity,
                    "amount_ntd": item.amount.amount,
                }
                for item in candidate.allocations
            ],
            "reason": candidate.reason,
            "evidence": list(candidate.evidence),
            "refund_ledger_entry_identity": candidate.refund_ledger_entry_identity,
            "candidate_fingerprint": candidate.fingerprint.value,
        },
        "batch_version": preview.batch_version,
        "canonical_fact_version": preview.canonical_fact_version,
        "alert_version": preview.alert_version,
        "preview_fingerprint": preview.fingerprint.value,
    }


def _refund_return_review_preview_payload(preview):
    return {
        "batch_version": preview.batch_version,
        "preview_fingerprint": preview.fingerprint.value,
        "candidate_fingerprint": preview.candidate.fingerprint.value,
        "row_identity": preview.candidate.selection.row_identity,
        "original_refund_ledger_entry_identity": (
            preview.candidate.selection.original_refund_ledger_entry_identity
        ),
    }


def _historical_reprocess_plan_payload(plan):
    payload = {
        "batch_identity": plan.batch_identity,
        "batch_version": plan.batch_version,
        "row_count": len(plan.rows),
        "preview_fingerprint": plan.fingerprint.value,
    }
    selections = [
        _historical_owner_selection_payload(row.owner_selection)
        for row in plan.rows
        if row.owner_selection is not None
    ]
    if selections:
        payload["owner_selections"] = selections
    return payload


def _historical_reprocess_receipt_payload(receipt):
    return {
        "batch_identity": receipt.batch_identity,
        "resulting_batch_version": receipt.resulting_batch_version,
        "reprocess_run_id": receipt.reprocess_run_id,
        "reclassified_count": receipt.reclassified_count,
        "dispatched_count": receipt.dispatched_count,
        "preview_fingerprint": receipt.fingerprint.value,
    }


def _call_endpoint(command, message, correlation_id):
    try:
        return BaseResponse(data=command(), message=message)
    except (
        FinanceImportWorkflowError,
        FinanceImportCorrectionWorkflowError,
        HistoricalReprocessWorkflowError,
        RefundReturnReviewWorkflowError,
    ) as error:
        _raise_typed_error(error.error)
    except OperationalError as error:
        _raise_mysql_error(error, correlation_id)
    except (TypeError, ValueError) as error:
        _raise_validation_error(error, correlation_id)
    except HTTPException:
        raise
    except Exception as error:
        raise _internal_error(correlation_id) from error


def _call_query(query, message, correlation_id):
    try:
        return BaseResponse(data=query(), message=message)
    except FinanceImportQueryNotFound as error:
        typed = TypedError(
            ErrorCategory.NOT_FOUND,
            "finance_import_batch_not_found",
            str(error),
            correlation_id,
        )
        raise _http_error(404, typed)
    except OperationalError as error:
        _raise_mysql_error(error, correlation_id)
    except (TypeError, ValueError) as error:
        _raise_validation_error(error, correlation_id)
    except HTTPException:
        raise
    except Exception as error:
        raise _internal_error(correlation_id) from error


def _review_page(items, limit):
    return {
        "items": [_materialize(item) for item in items],
        "next_after_row_id": items[-1].row_id if len(items) == limit else None,
    }


def _run_page(items, limit):
    return {
        "items": [_materialize(item) for item in items],
        "next_before_run_id": items[-1].run_id if len(items) == limit else None,
    }


def _raise_typed_error(error):
    status_code = {
        ErrorCategory.VALIDATION: 422,
        ErrorCategory.FORBIDDEN: 403,
        ErrorCategory.NOT_FOUND: 404,
        ErrorCategory.DOMAIN_BLOCKED: 409,
        ErrorCategory.CONFLICT: 409,
        ErrorCategory.IDEMPOTENCY_MISMATCH: 409,
        ErrorCategory.UNAVAILABLE: 503,
        ErrorCategory.INTERNAL: 500,
    }[error.category]
    headers = {"Retry-After": "1"} if error.retryable else None
    raise _http_error(status_code, error, headers=headers)


def _raise_mysql_error(error, correlation_id):
    mysql_code = int(error.args[0]) if error.args else 0
    retryable = mysql_code in _RETRYABLE_MYSQL_CODES
    typed = TypedError(
        ErrorCategory.UNAVAILABLE if retryable else ErrorCategory.INTERNAL,
        "downstream_unavailable" if retryable else "transaction_failed",
        "Finance Import 交易暫時無法完成。" if retryable else "Finance Import 交易失敗。",
        correlation_id,
        retryable=retryable,
    )
    raise _http_error(503 if retryable else 500, typed)


def _raise_validation_error(error, correlation_id):
    typed = TypedError(
        ErrorCategory.VALIDATION,
        "invalid_finance_import_request",
        str(error) or "Finance Import request is invalid.",
        correlation_id,
    )
    raise _http_error(422, typed)


def _raise_ingestion_attempt_error(error, correlation_id):
    validation_codes = {
        "finance_import_source_missing",
        "finance_import_validation_failed",
    }
    category = (
        ErrorCategory.VALIDATION
        if error.attempt.error_code in validation_codes
        else ErrorCategory.INTERNAL
    )
    typed = TypedError(
        category,
        error.attempt.error_code or "finance_import_ingestion_failed",
        "Finance Import 匯入未完成；請使用相同 Idempotency-Key 查看原嘗試紀錄。",
        correlation_id,
    )
    raise HTTPException(
        status_code=422 if category is ErrorCategory.VALIDATION else 500,
        detail={"error": _materialize(typed), "attempt": _materialize(error.attempt)},
    )


def _internal_error(correlation_id):
    return _http_error(
        500,
        TypedError(
            ErrorCategory.INTERNAL,
            "transaction_failed",
            "Finance Import 交易失敗。",
            correlation_id,
        ),
    )


def _http_error(status_code, error, *, headers=None):
    return HTTPException(
        status_code=status_code,
        detail={"error": _materialize(error)},
        headers=headers,
    )


def _materialize(value):
    if isinstance(value, MoneyNTD):
        return value.amount
    if isinstance(
        value,
        (CorrelationId, ExpectedVersion, IdempotencyKey, PreviewFingerprint),
    ):
        return value.value
    if is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: _materialize(getattr(value, field.name))
            for field in fields(value)
        }
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _materialize(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_materialize(item) for item in value]
    return value


def _materialize_summary(summary):
    payload = _materialize(summary)
    payload["created_at"] = summary.created_at.isoformat()
    return payload


async def _persist_uploaded_workbook(workbook):
    filename = str(workbook.filename or "").strip()
    suffix = Path(filename).suffix.lower()
    if suffix not in {".xlsx", ".xls"}:
        raise ValueError("finance workbook must be .xlsx or .xls")
    content = await workbook.read(_MAXIMUM_WORKBOOK_BYTES + 1)
    if not content:
        raise ValueError("finance workbook is empty")
    if len(content) > _MAXIMUM_WORKBOOK_BYTES:
        raise ValueError("finance workbook exceeds 20 MiB")
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as target:
        target.write(content)
        return Path(target.name)


def _remove_uploaded_workbook(upload_path):
    if not isinstance(upload_path, Path):
        return
    upload_path.unlink(missing_ok=True)


__all__ = ["router"]
