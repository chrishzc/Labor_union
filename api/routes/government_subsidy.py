"""Typed Government Subsidy Query, Preview, and Apply endpoints."""

from __future__ import annotations

from dataclasses import fields, is_dataclass
from enum import Enum
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Path, Query, status
from api.schemas.jobs import JobAcceptedResponse
from api.dependencies.jobs import get_job_repository
from infrastructure.mysql.background_job_repository import (
    BackgroundJobRepository,
    JobIdempotencyConflict,
)
import uuid

from pydantic import BaseModel, ConfigDict, Field
from pymysql.err import OperationalError

from api.dependencies.admin_auth import require_system_admin
from api.dependencies.government_subsidy import (
    GovernmentSubsidyApplication,
    get_government_subsidy_application,
)
from api.schemas.base import BaseResponse
from api.schemas.government_subsidy import (
    GovernmentSubsidyClaimApprovalApplyBody,
    GovernmentSubsidyClaimApprovalPreviewBody,
    GovernmentSubsidyClaimBatchPageView,
    GovernmentSubsidyClaimPlanningApplyBody,
    GovernmentSubsidyClaimPlanningPreviewBody,
    GovernmentSubsidyClaimPreviewView,
    GovernmentSubsidyClaimReceiptView,
    GovernmentSubsidyClaimSubmissionApplyBody,
    GovernmentSubsidyClaimSubmissionPreviewBody,
    GovernmentSubsidyBatchView,
    GovernmentSubsidyPreviewView,
    GovernmentSubsidyReceiptIntentView,
    GovernmentSubsidyReceiptView,
    GovernmentSubsidyReversalIntentView,
)
from domains.government_subsidy.claims import (
    ClaimApprovalCandidate,
    ClaimApprovalIntent,
    ClaimPlanningCandidate,
    ClaimPlanningIntent,
)
from domains.government_subsidy.ledger import (
    AllocationIntent,
    ClaimBatchIdentity,
    GovernmentSubsidyDomainError,
    ReceiptIntent,
    ReversalIntent,
    reduce_batch_status,
)
from subsystems.access.authentication_session import AdminPrincipal
from shared_kernel.errors import ErrorCategory, TypedError
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.identities import (
    ActorContext,
    CorrelationId,
    ExpectedVersion,
    IdempotencyKey,
)
from shared_kernel.money import MoneyNTD
from subsystems.government_subsidy.ledger_workflow import (
    GovernmentSubsidyReceiptApplyRequest,
    GovernmentSubsidyReversalApplyRequest,
    GovernmentSubsidyWorkflowError,
)
from subsystems.government_subsidy.claim_workflow import (
    ClaimApprovalApplyRequest,
    ClaimPlanningApplyRequest,
    ClaimSubmissionApplyRequest,
    ClaimSubmissionIntent,
    GovernmentSubsidyClaimWorkflowError,
)

router = APIRouter(
    prefix="/api/v1/government-subsidy",
    tags=["Government Subsidy"],
)
_RETRYABLE_MYSQL_CODES = frozenset({1205, 1213})


@router.get(
    "/claim-batches",
    response_model=BaseResponse[GovernmentSubsidyClaimBatchPageView],
)
def list_government_subsidy_batches(
    cursor: int | None = Query(default=None, gt=0),
    limit: int = Query(default=20, ge=1, le=100),
    principal: AdminPrincipal = Depends(require_system_admin),
    application: GovernmentSubsidyApplication = Depends(
        get_government_subsidy_application
    ),
    job_repository: BackgroundJobRepository = Depends(get_job_repository),
):
    del principal
    correlation = CorrelationId("government-subsidy-batch-list")
    return _call_endpoint(
        lambda: _batch_page_payload(application.list_batches(cursor, limit)),
        "成功取得政府補助批次清單",
        correlation,
    )


class GovernmentSubsidyReceiptPreviewBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent: GovernmentSubsidyReceiptIntentView


class GovernmentSubsidyReceiptApplyBody(
    GovernmentSubsidyReceiptPreviewBody
):
    expected_batch_version: int = Field(ge=0)
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    reason: str = Field(min_length=1, max_length=500)


class GovernmentSubsidyReversalPreviewBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent: GovernmentSubsidyReversalIntentView


class GovernmentSubsidyReversalApplyBody(
    GovernmentSubsidyReversalPreviewBody
):
    expected_batch_version: int = Field(ge=0)
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    reason: str = Field(min_length=1, max_length=500)


@router.get(
    "/claim-batches/{batch_id}",
    response_model=BaseResponse[GovernmentSubsidyBatchView],
)
def query_government_subsidy_batch(
    batch_id: int = Path(..., gt=0),
    principal: AdminPrincipal = Depends(require_system_admin),
    application: GovernmentSubsidyApplication = Depends(
        get_government_subsidy_application
    ),
    job_repository: BackgroundJobRepository = Depends(get_job_repository),
):
    del principal
    correlation = CorrelationId(f"government-subsidy-query:{batch_id}")
    return _call_endpoint(
        lambda: _batch_payload(application.query_batch(batch_id)),
        "成功取得政府補助批次",
        correlation,
    )


@router.post(
    "/claim-batches/preview",
    response_model=BaseResponse[GovernmentSubsidyClaimPreviewView],
)
def preview_government_subsidy_claim_plan(
    body: GovernmentSubsidyClaimPlanningPreviewBody,
    correlation_id: Annotated[
        str,
        Header(alias="X-Correlation-ID", min_length=1, max_length=191),
    ] = "government-subsidy-claim-preview",
    principal: AdminPrincipal = Depends(require_system_admin),
    application: GovernmentSubsidyApplication = Depends(
        get_government_subsidy_application
    ),
    job_repository: BackgroundJobRepository = Depends(get_job_repository),
):
    del principal
    correlation = CorrelationId(correlation_id)
    intent = _planning_intent(body)
    return _call_endpoint(
        lambda: _claim_preview_payload(
            application.preview_claim_plan(intent)
        ),
        "成功產生政府補助申請批次預覽",
        correlation,
    )


@router.post(
    "/claim-batches/apply",
    response_model=BaseResponse[JobAcceptedResponse],
    status_code=status.HTTP_202_ACCEPTED,
)
def apply_government_subsidy_claim_plan(
    body: GovernmentSubsidyClaimPlanningApplyBody,
    background_tasks: BackgroundTasks,
    idempotency_key: Annotated[
        str,
        Header(alias="Idempotency-Key", min_length=1, max_length=191),
    ] = ...,
    correlation_id: Annotated[
        str,
        Header(alias="X-Correlation-ID", min_length=1, max_length=191),
    ] = ...,
    principal: AdminPrincipal = Depends(require_system_admin),
    application: GovernmentSubsidyApplication = Depends(
        get_government_subsidy_application
    ),
    job_repository: BackgroundJobRepository = Depends(get_job_repository),
):
    request = ClaimPlanningApplyRequest(
        _planning_intent(body),
        ExpectedVersion(body.expected_batch_version),
        PreviewFingerprint(body.preview_fingerprint),
        IdempotencyKey(idempotency_key),
        _actor(principal),
        body.reason,
        CorrelationId(correlation_id),
    )
    return _call_apply_async(
        lambda: _materialize(application.apply_claim_plan(request)),
        "成功建立政府補助申請批次",
        request.correlation_id,
        request.idempotency_key,
        background_tasks,
        job_repository,
    )


@router.post(
    "/claim-batches/{batch_id}/submit/preview",
    response_model=BaseResponse[GovernmentSubsidyClaimPreviewView],
)
def preview_government_subsidy_claim_submission(
    body: GovernmentSubsidyClaimSubmissionPreviewBody,
    batch_id: int = Path(..., gt=0),
    correlation_id: Annotated[
        str,
        Header(alias="X-Correlation-ID", min_length=1, max_length=191),
    ] = "government-subsidy-submit-preview",
    principal: AdminPrincipal = Depends(require_system_admin),
    application: GovernmentSubsidyApplication = Depends(
        get_government_subsidy_application
    ),
    job_repository: BackgroundJobRepository = Depends(get_job_repository),
):
    del body, principal
    correlation = CorrelationId(correlation_id)
    intent = ClaimSubmissionIntent(batch_id)
    return _call_endpoint(
        lambda: _claim_preview_payload(
            application.preview_claim_submission(intent)
        ),
        "成功產生政府補助送件預覽",
        correlation,
    )


@router.post(
    "/claim-batches/{batch_id}/submit/apply",
    response_model=BaseResponse[JobAcceptedResponse],
    status_code=status.HTTP_202_ACCEPTED,
)
def apply_government_subsidy_claim_submission(
    body: GovernmentSubsidyClaimSubmissionApplyBody,
    background_tasks: BackgroundTasks,
    batch_id: int = Path(..., gt=0),
    idempotency_key: Annotated[
        str,
        Header(alias="Idempotency-Key", min_length=1, max_length=191),
    ] = ...,
    correlation_id: Annotated[
        str,
        Header(alias="X-Correlation-ID", min_length=1, max_length=191),
    ] = ...,
    principal: AdminPrincipal = Depends(require_system_admin),
    application: GovernmentSubsidyApplication = Depends(
        get_government_subsidy_application
    ),
    job_repository: BackgroundJobRepository = Depends(get_job_repository),
):
    request = ClaimSubmissionApplyRequest(
        ClaimSubmissionIntent(batch_id),
        ExpectedVersion(body.expected_batch_version),
        PreviewFingerprint(body.preview_fingerprint),
        IdempotencyKey(idempotency_key),
        _actor(principal),
        body.reason,
        CorrelationId(correlation_id),
    )
    return _call_apply_async(
        lambda: _materialize(application.apply_claim_submission(request)),
        "成功送出政府補助申請批次",
        request.correlation_id,
        request.idempotency_key,
        background_tasks,
        job_repository,
    )


@router.post(
    "/claim-batches/{batch_id}/approval/preview",
    response_model=BaseResponse[GovernmentSubsidyClaimPreviewView],
)
def preview_government_subsidy_claim_approval(
    body: GovernmentSubsidyClaimApprovalPreviewBody,
    batch_id: int = Path(..., gt=0),
    correlation_id: Annotated[
        str,
        Header(alias="X-Correlation-ID", min_length=1, max_length=191),
    ] = "government-subsidy-approval-preview",
    principal: AdminPrincipal = Depends(require_system_admin),
    application: GovernmentSubsidyApplication = Depends(
        get_government_subsidy_application
    ),
    job_repository: BackgroundJobRepository = Depends(get_job_repository),
):
    del principal
    correlation = CorrelationId(correlation_id)
    intent = _approval_intent(batch_id, body.item_approvals)
    return _call_endpoint(
        lambda: _claim_preview_payload(
            application.preview_claim_approval(intent)
        ),
        "成功產生政府補助核准預覽",
        correlation,
    )


@router.post(
    "/claim-batches/{batch_id}/approval/apply",
    response_model=BaseResponse[JobAcceptedResponse],
    status_code=status.HTTP_202_ACCEPTED,
)
def apply_government_subsidy_claim_approval(
    body: GovernmentSubsidyClaimApprovalApplyBody,
    background_tasks: BackgroundTasks,
    batch_id: int = Path(..., gt=0),
    idempotency_key: Annotated[
        str,
        Header(alias="Idempotency-Key", min_length=1, max_length=191),
    ] = ...,
    correlation_id: Annotated[
        str,
        Header(alias="X-Correlation-ID", min_length=1, max_length=191),
    ] = ...,
    principal: AdminPrincipal = Depends(require_system_admin),
    application: GovernmentSubsidyApplication = Depends(
        get_government_subsidy_application
    ),
    job_repository: BackgroundJobRepository = Depends(get_job_repository),
):
    request = ClaimApprovalApplyRequest(
        _approval_intent(batch_id, body.item_approvals),
        ExpectedVersion(body.expected_batch_version),
        PreviewFingerprint(body.preview_fingerprint),
        IdempotencyKey(idempotency_key),
        _actor(principal),
        body.reason,
        CorrelationId(correlation_id),
    )
    return _call_apply_async(
        lambda: _materialize(application.apply_claim_approval(request)),
        "成功記錄政府補助核准",
        request.correlation_id,
        request.idempotency_key,
        background_tasks,
        job_repository,
    )


@router.post(
    "/receipts/preview",
    response_model=BaseResponse[GovernmentSubsidyPreviewView],
)
def preview_government_subsidy_receipt(
    body: GovernmentSubsidyReceiptPreviewBody,
    correlation_id: Annotated[
        str,
        Header(alias="X-Correlation-ID", min_length=1, max_length=191),
    ] = "government-subsidy-receipt-preview",
    principal: AdminPrincipal = Depends(require_system_admin),
    application: GovernmentSubsidyApplication = Depends(
        get_government_subsidy_application
    ),
    job_repository: BackgroundJobRepository = Depends(get_job_repository),
):
    del principal
    correlation = CorrelationId(correlation_id)
    intent = _receipt_intent(body.intent)
    return _call_endpoint(
        lambda: _preview_payload(application.preview_receipt(intent)),
        "成功產生政府補助入款預覽",
        correlation,
    )


@router.post(
    "/receipts/apply",
    response_model=BaseResponse[JobAcceptedResponse],
    status_code=status.HTTP_202_ACCEPTED,
)
# FastAPI needs the full mutation contract on this callable for OpenAPI.
def apply_government_subsidy_receipt(
    body: GovernmentSubsidyReceiptApplyBody,
    background_tasks: BackgroundTasks,
    idempotency_key: Annotated[
        str,
        Header(alias="Idempotency-Key", min_length=1, max_length=191),
    ] = ...,
    correlation_id: Annotated[
        str,
        Header(alias="X-Correlation-ID", min_length=1, max_length=191),
    ] = ...,
    principal: AdminPrincipal = Depends(require_system_admin),
    application: GovernmentSubsidyApplication = Depends(
        get_government_subsidy_application
    ),
    job_repository: BackgroundJobRepository = Depends(get_job_repository),
):
    request = GovernmentSubsidyReceiptApplyRequest(
        _receipt_intent(body.intent),
        ExpectedVersion(body.expected_batch_version),
        PreviewFingerprint(body.preview_fingerprint),
        IdempotencyKey(idempotency_key),
        _actor(principal),
        body.reason,
        CorrelationId(correlation_id),
    )
    return _call_apply_async(
        lambda: _materialize(application.apply_receipt(request)),
        "成功套用政府補助入款",
        request.correlation_id,
        request.idempotency_key,
        background_tasks,
        job_repository,
    )


@router.post(
    "/reversals/preview",
    response_model=BaseResponse[GovernmentSubsidyPreviewView],
)
def preview_government_subsidy_reversal(
    body: GovernmentSubsidyReversalPreviewBody,
    correlation_id: Annotated[
        str,
        Header(alias="X-Correlation-ID", min_length=1, max_length=191),
    ] = "government-subsidy-reversal-preview",
    principal: AdminPrincipal = Depends(require_system_admin),
    application: GovernmentSubsidyApplication = Depends(
        get_government_subsidy_application
    ),
    job_repository: BackgroundJobRepository = Depends(get_job_repository),
):
    del principal
    correlation = CorrelationId(correlation_id)
    intent = _reversal_intent(body.intent)
    return _call_endpoint(
        lambda: _preview_payload(application.preview_reversal(intent)),
        "成功產生政府補助沖正預覽",
        correlation,
    )


@router.post(
    "/reversals/apply",
    response_model=BaseResponse[JobAcceptedResponse],
    status_code=status.HTTP_202_ACCEPTED,
)
# FastAPI needs the full mutation contract on this callable for OpenAPI.
def apply_government_subsidy_reversal(
    body: GovernmentSubsidyReversalApplyBody,
    background_tasks: BackgroundTasks,
    idempotency_key: Annotated[
        str,
        Header(alias="Idempotency-Key", min_length=1, max_length=191),
    ] = ...,
    correlation_id: Annotated[
        str,
        Header(alias="X-Correlation-ID", min_length=1, max_length=191),
    ] = ...,
    principal: AdminPrincipal = Depends(require_system_admin),
    application: GovernmentSubsidyApplication = Depends(
        get_government_subsidy_application
    ),
    job_repository: BackgroundJobRepository = Depends(get_job_repository),
):
    request = GovernmentSubsidyReversalApplyRequest(
        _reversal_intent(body.intent),
        ExpectedVersion(body.expected_batch_version),
        PreviewFingerprint(body.preview_fingerprint),
        IdempotencyKey(idempotency_key),
        _actor(principal),
        body.reason,
        CorrelationId(correlation_id),
    )
    return _call_apply_async(
        lambda: _materialize(application.apply_reversal(request)),
        "成功套用政府補助沖正",
        request.correlation_id,
        request.idempotency_key,
        background_tasks,
        job_repository,
    )


def _receipt_intent(view):
    return ReceiptIntent(
        view.finance_import_row_id,
        view.batch_id,
        _allocation_intents(view.allocations),
    )


def _reversal_intent(view):
    return ReversalIntent(
        view.finance_import_row_id,
        view.source_receipt_id,
        _allocation_intents(view.allocations),
    )


def _allocation_intents(views):
    return tuple(
        AllocationIntent(view.target_identity, MoneyNTD(view.amount_ntd))
        for view in views
    )


def _planning_intent(body):
    view = body.intent
    return ClaimPlanningIntent(
        ClaimBatchIdentity(
            view.application_year,
            view.quarter,
            view.revision,
        )
    )


def _approval_intent(batch_id, approvals):
    return ClaimApprovalIntent(
        batch_id,
        tuple(
            AllocationIntent(
                item.item_id,
                MoneyNTD(item.approved_amount_ntd),
            )
            for item in approvals
        ),
    )


def _actor(principal):
    return ActorContext(str(principal.username or "").strip())


def _batch_payload(batch):
    return {
        "batch_id": batch.batch_id,
        "batch_identity": batch.identity.value,
        "batch_version": batch.aggregate_version,
        "status": reduce_batch_status(batch).value,
        "requested_total_ntd": batch.requested_total_ntd.amount,
        "approved_total_ntd": batch.approved_total_ntd.amount,
        "net_allocated_ntd": batch.net_allocated_total_ntd.amount,
        "outstanding_ntd": batch.outstanding_total_ntd.amount,
        "items": [_item_payload(item) for item in batch.items],
    }


def _batch_page_payload(page):
    return {
        "batches": [_batch_payload(batch) for batch in page.batches],
        "next_cursor": page.next_cursor,
    }


def _item_payload(item):
    return {
        "item_id": item.item_id,
        "assignment_id": item.assignment_id,
        "case_no": item.case_no,
        "staff_id": item.staff_id,
        "claimed_hours": item.claimed_hours,
        "unit_price_ntd": item.unit_price_ntd.amount,
        "requested_amount_ntd": item.requested_amount_ntd.amount,
        "approved_amount_ntd": item.approved_amount_ntd.amount,
        "net_allocated_ntd": item.net_allocated_ntd.amount,
        "outstanding_ntd": item.outstanding_amount_ntd.amount,
    }


# Kept cohesive because this is the bounded public projection of one candidate.
def _preview_payload(preview):
    candidate = preview.candidate
    return {
        "kind": candidate.kind.value,
        "bank_fact_identity": candidate.bank_fact.bank_fact_identity,
        "batch_id": candidate.batch_id,
        "batch_version": candidate.expected_batch_version,
        "resulting_batch_version": candidate.resulting_batch_version,
        "source_receipt_id": candidate.source_receipt_id,
        "amount_ntd": candidate.amount_ntd.amount,
        "allocations": [
            {
                "claim_item_id": allocation.claim_item_id,
                "amount_ntd": allocation.amount_ntd.amount,
                "reversal_of_allocation_id": (
                    allocation.reversal_of_allocation_id
                ),
            }
            for allocation in candidate.allocations
        ],
        "before_status": candidate.before_status.value,
        "after_status": candidate.after_status.value,
        "before_net_allocated_ntd": (
            candidate.before_net_allocated_ntd.amount
        ),
        "after_net_allocated_ntd": candidate.after_net_allocated_ntd.amount,
        "outstanding_ntd": candidate.outstanding_ntd.amount,
        "preview_fingerprint": preview.fingerprint.value,
    }


def _claim_preview_payload(preview):
    candidate = preview.candidate
    if isinstance(candidate, ClaimPlanningCandidate):
        return _planning_preview_payload(candidate)
    return _existing_claim_preview_payload(candidate)


def _planning_preview_payload(candidate):
    return {
        "kind": candidate.kind.value,
        "batch_id": None,
        "batch_identity": candidate.identity.value,
        "batch_version": candidate.expected_batch_version,
        "resulting_batch_version": candidate.resulting_batch_version,
        "before_status": None,
        "after_status": "draft",
        "total_ntd": candidate.requested_total_ntd.amount,
        "items": [_planned_item_payload(item) for item in candidate.items],
        "preview_fingerprint": candidate.fingerprint.value,
    }


def _existing_claim_preview_payload(candidate):
    batch = candidate.batch
    approval = isinstance(candidate, ClaimApprovalCandidate)
    return {
        "kind": candidate.kind.value,
        "batch_id": batch.batch_id,
        "batch_identity": batch.identity.value,
        "batch_version": candidate.expected_batch_version,
        "resulting_batch_version": candidate.resulting_batch_version,
        "before_status": candidate.before_status.value,
        "after_status": candidate.after_status.value,
        "total_ntd": (
            candidate.approved_total_ntd.amount
            if approval
            else batch.requested_total_ntd.amount
        ),
        "items": [
            _claim_item_preview_payload(item, candidate)
            for item in batch.items
        ],
        "preview_fingerprint": candidate.fingerprint.value,
    }


def _planned_item_payload(item):
    return {
        "item_id": None,
        "assignment_id": item.assignment_id,
        "case_no": item.case_no,
        "staff_id": item.staff_id,
        "claimed_hours": item.claimed_hours,
        "unit_price_ntd": item.unit_price_ntd.amount,
        "requested_amount_ntd": item.requested_amount_ntd.amount,
        "approved_amount_ntd": 0,
    }


def _claim_item_preview_payload(item, candidate):
    approval_by_item = _approval_amounts(candidate)
    return {
        "item_id": item.item_id,
        "assignment_id": item.assignment_id,
        "case_no": item.case_no,
        "staff_id": item.staff_id,
        "claimed_hours": item.claimed_hours,
        "unit_price_ntd": item.unit_price_ntd.amount,
        "requested_amount_ntd": item.requested_amount_ntd.amount,
        "approved_amount_ntd": approval_by_item.get(
            item.item_id,
            item.approved_amount_ntd.amount,
        ),
    }


def _approval_amounts(candidate):
    if not isinstance(candidate, ClaimApprovalCandidate):
        return {}
    return {
        item.target_identity: item.amount_ntd.amount
        for item in candidate.intent.item_approvals
    }



def _call_apply_async(command, message, correlation_id, idempotency_key, background_tasks, job_repository):
    job_id = str(uuid.uuid4())
    try:
        job_id = job_repository.enqueue_job(job_id, idempotency_key)
        
        def _background_worker():
            job_repository.mark_running(job_id)
            try:
                receipt = command()
                job_repository.mark_succeeded(job_id, receipt)
            except GovernmentSubsidyWorkflowError as error:
                job_repository.mark_failed(job_id, {"error": _materialize(error.error)})
            except GovernmentSubsidyClaimWorkflowError as error:
                job_repository.mark_failed(job_id, {"error": _materialize(error.error)})
            except GovernmentSubsidyDomainError as error:
                job_repository.mark_failed(job_id, {"error": {"category": "VALIDATION", "code": error.code, "message": str(error)}})
            except OperationalError as error:
                job_repository.mark_failed(job_id, {"error": {"category": "INTERNAL", "code": "database_error", "message": str(error)}})
            except ValueError as error:
                job_repository.mark_failed(job_id, {"error": {"category": "VALIDATION", "code": "invalid_government_subsidy_intent", "message": str(error)}})
            except Exception as error:
                job_repository.mark_failed(job_id, {"error": {"category": "INTERNAL", "code": "internal_error", "message": str(error)}})

        background_tasks.add_task(_background_worker)
        
    except JobIdempotencyConflict as e:
        job_id = e.job_id

    return BaseResponse(
        data=JobAcceptedResponse(job_id=job_id, status_url=f"/api/v1/jobs/{job_id}"),
        message="202 Accepted",
    )

def _call_endpoint(command, message, correlation_id):
    try:
        return BaseResponse(data=command(), message=message)
    except GovernmentSubsidyWorkflowError as error:
        _raise_typed_error(error.error)
    except GovernmentSubsidyClaimWorkflowError as error:
        _raise_typed_error(error.error)
    except GovernmentSubsidyDomainError as error:
        _raise_domain_error(error, correlation_id)
    except OperationalError as error:
        _raise_mysql_error(error, correlation_id)
    except ValueError as error:
        _raise_value_error(error, correlation_id)
    except HTTPException:
        raise
    except Exception as error:
        raise _internal_error(correlation_id) from error


def _raise_domain_error(error, correlation_id):
    category = (
        ErrorCategory.DOMAIN_BLOCKED
        if error.code.value.endswith(("review_required", "stale"))
        else ErrorCategory.VALIDATION
    )
    typed = TypedError(
        category,
        error.code.value,
        "政府補助根事實或分配未通過 Domain 驗證。",
        correlation_id,
        domain_blockers=tuple(sorted(error.blockers)),
    )
    raise _http_error(409 if category is ErrorCategory.DOMAIN_BLOCKED else 422, typed)


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
    if mysql_code in _RETRYABLE_MYSQL_CODES:
        typed = TypedError(
            ErrorCategory.UNAVAILABLE,
            "transaction_temporarily_unavailable",
            "可使用相同冪等鍵重試政府補助交易。",
            correlation_id,
            retryable=True,
        )
        raise _http_error(503, typed, headers={"Retry-After": "1"}) from error
    typed = TypedError(
        ErrorCategory.INTERNAL,
        "government_subsidy_database_error",
        "政府補助交易寫入失敗。",
        correlation_id,
    )
    raise _http_error(500, typed) from error


def _raise_value_error(error, correlation_id):
    code = str(error) or "government_subsidy_claim_facts_invalid"
    not_found = code == "government_subsidy_batch_not_found"
    typed = TypedError(
        ErrorCategory.NOT_FOUND if not_found else ErrorCategory.VALIDATION,
        code,
        "政府補助請求未通過資料驗證。",
        correlation_id,
    )
    raise _http_error(404 if not_found else 422, typed) from error


def _internal_error(correlation_id):
    return _http_error(
        500,
        TypedError(
            ErrorCategory.INTERNAL,
            "government_subsidy_internal_error",
            "政府補助處理失敗。",
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
    return _materialize_collection(value)


def _materialize_collection(value):
    if isinstance(value, dict):
        return {str(key): _materialize(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_materialize(item) for item in value]
    return value


__all__ = [
    "apply_government_subsidy_claim_approval",
    "apply_government_subsidy_claim_plan",
    "apply_government_subsidy_claim_submission",
    "GovernmentSubsidyReceiptApplyBody",
    "GovernmentSubsidyReceiptPreviewBody",
    "GovernmentSubsidyReversalApplyBody",
    "GovernmentSubsidyReversalPreviewBody",
    "list_government_subsidy_batches",
    "preview_government_subsidy_claim_approval",
    "preview_government_subsidy_claim_plan",
    "preview_government_subsidy_claim_submission",
    "router",
]
