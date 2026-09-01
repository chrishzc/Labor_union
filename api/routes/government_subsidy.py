"""
File: government_subsidy.py
Description: 提供 Government Subsidy typed Query／Preview，並以 Durable Job Bridge 接受 Apply。
"""

from __future__ import annotations

from dataclasses import fields, is_dataclass
from datetime import date
from enum import Enum
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Path, Query, status
from api.schemas.jobs import JobAcceptedResponse
from api.dependencies.jobs import (
    durable_job_conflict_http_error,
    get_durable_job_application,
    immutable_admin_job_actor,
)
from shared_kernel.durable_job_queue import DurableJobCommand
from subsystems.jobs.command_application import DurableJobCommandApplication
from subsystems.jobs.contracts import DurableJobCommandConflict
import uuid

from pydantic import BaseModel, ConfigDict, Field
from pymysql.err import OperationalError

from api.dependencies.admin_auth import require_capability, require_system_admin
from api.dependencies.government_subsidy import (
    GovernmentSubsidyApplication,
    get_government_subsidy_application,
)
from api.dependencies.government_subsidy_payer_master import (
    get_government_payer_master_workflow,
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
    GovernmentPayerAccountApplyBody,
    GovernmentPayerAccountPreviewBody,
    GovernmentPayerAccountPreviewView,
    GovernmentPayerAccountReceiptView,
    GovernmentPayerMasterView,
    GovernmentSubsidyOverageReceiptPreviewBody,
    GovernmentSubsidyOverageReceiptApplyBody,
    GovernmentSubsidyOverpaymentOffsetApplyBody,
    GovernmentSubsidyOverpaymentOffsetPreviewBody,
    GovernmentSubsidyOverpaymentReturnApplyBody,
    GovernmentSubsidyOverpaymentReturnPreviewBody,
    GovernmentSubsidyOverpaymentDispositionApplyBody,
    GovernmentSubsidyOverpaymentDispositionPreviewBody,
    GovernmentOverpaymentReturnReconciliationApplyBody,
    GovernmentOverpaymentReturnReconciliationPreviewBody,
    GovernmentOverpaymentReturnReconciliationWithExcessPreviewView,
    GovernmentSubsidyOverpaymentQueryView,
)
from domains.government_subsidy.payer_master import GovernmentRefundAccount
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
from subsystems.government_subsidy.payer_master_workflow import (
    GovernmentPayerMasterWorkflow,
    GovernmentPayerMasterWorkflowError,
    GovernmentRefundAccountApplyRequest,
)
from subsystems.government_subsidy.overpayment_workflow import (
    OffsetApplyRequest,
    ReceiptWithOverageApplyRequest,
    ReturnApplyRequest,
    ReturnReconciliationApplyRequest,
    ReturnReconciliationWithExcessApplyRequest,
)
from domains.government_subsidy.overpayment import GovernmentSubsidyOffsetIntent
from subsystems.government_subsidy.overpayment_query import (
    GovernmentSubsidyOverpaymentQueryError,
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
):
    del principal
    correlation = CorrelationId(f"government-subsidy-query:{batch_id}")
    return _call_endpoint(
        lambda: _batch_payload(application.query_batch(batch_id)),
        "成功取得政府補助批次",
        correlation,
    )


@router.get(
    "/overpayments/{overpayment_identity}",
    response_model=BaseResponse[GovernmentSubsidyOverpaymentQueryView],
)
def query_government_subsidy_overpayment(
    overpayment_identity: str = Path(..., min_length=1, max_length=191),
    principal: AdminPrincipal = Depends(require_system_admin),
    application: GovernmentSubsidyApplication = Depends(
        get_government_subsidy_application
    ),
):
    del principal
    correlation = CorrelationId(
        f"government-overpayment-query:{overpayment_identity}"
    )
    return _call_endpoint(
        lambda: _overpayment_query_payload(
            application.query_overpayment(overpayment_identity.strip(), correlation)
        ),
        "成功取得政府補助溢撥現況",
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
    idempotency_key: Annotated[
        str,
        Header(alias="Idempotency-Key", min_length=1, max_length=191),
    ] = ...,
    correlation_id: Annotated[
        str,
        Header(alias="X-Correlation-ID", min_length=1, max_length=191),
    ] = ...,
    principal: AdminPrincipal = Depends(require_system_admin),
    job_application: DurableJobCommandApplication = Depends(get_durable_job_application),
):
    request = ClaimPlanningApplyRequest(
        _planning_intent(body),
        ExpectedVersion(body.expected_batch_version),
        PreviewFingerprint(body.preview_fingerprint),
        IdempotencyKey(idempotency_key),
        _actor(principal, correlation_id),
        body.reason,
        CorrelationId(correlation_id),
    )
    return _enqueue_apply(_government_subsidy_command("claim_plan", body.intent.model_dump(), request), job_application)


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
    job_application: DurableJobCommandApplication = Depends(get_durable_job_application),
):
    request = ClaimSubmissionApplyRequest(
        ClaimSubmissionIntent(batch_id),
        ExpectedVersion(body.expected_batch_version),
        PreviewFingerprint(body.preview_fingerprint),
        IdempotencyKey(idempotency_key),
        _actor(principal, correlation_id),
        body.reason,
        CorrelationId(correlation_id),
    )
    return _enqueue_apply(_government_subsidy_command("claim_submission", {"batch_id": batch_id}, request), job_application)


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
    job_application: DurableJobCommandApplication = Depends(get_durable_job_application),
):
    request = ClaimApprovalApplyRequest(
        _approval_intent(batch_id, body.item_approvals),
        ExpectedVersion(body.expected_batch_version),
        PreviewFingerprint(body.preview_fingerprint),
        IdempotencyKey(idempotency_key),
        _actor(principal, correlation_id),
        body.reason,
        CorrelationId(correlation_id),
    )
    return _enqueue_apply(_government_subsidy_command("claim_approval", {"batch_id": batch_id, "item_approvals": [item.model_dump() for item in body.item_approvals]}, request), job_application)


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
    idempotency_key: Annotated[
        str,
        Header(alias="Idempotency-Key", min_length=1, max_length=191),
    ] = ...,
    correlation_id: Annotated[
        str,
        Header(alias="X-Correlation-ID", min_length=1, max_length=191),
    ] = ...,
    principal: AdminPrincipal = Depends(require_system_admin),
    job_application: DurableJobCommandApplication = Depends(get_durable_job_application),
):
    request = GovernmentSubsidyReceiptApplyRequest(
        _receipt_intent(body.intent),
        ExpectedVersion(body.expected_batch_version),
        PreviewFingerprint(body.preview_fingerprint),
        IdempotencyKey(idempotency_key),
        _actor(principal, correlation_id),
        body.reason,
        CorrelationId(correlation_id),
    )
    return _enqueue_apply(_government_subsidy_command("receipt", body.intent.model_dump(), request), job_application)


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
    idempotency_key: Annotated[
        str,
        Header(alias="Idempotency-Key", min_length=1, max_length=191),
    ] = ...,
    correlation_id: Annotated[
        str,
        Header(alias="X-Correlation-ID", min_length=1, max_length=191),
    ] = ...,
    principal: AdminPrincipal = Depends(require_system_admin),
    job_application: DurableJobCommandApplication = Depends(get_durable_job_application),
):
    request = GovernmentSubsidyReversalApplyRequest(
        _reversal_intent(body.intent),
        ExpectedVersion(body.expected_batch_version),
        PreviewFingerprint(body.preview_fingerprint),
        IdempotencyKey(idempotency_key),
        _actor(principal, correlation_id),
        body.reason,
        CorrelationId(correlation_id),
    )
    return _enqueue_apply(_government_subsidy_command("reversal", body.intent.model_dump(), request), job_application)


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


def _actor(principal, correlation_id):
    return ActorContext(immutable_admin_job_actor(principal, correlation_id))


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



def _enqueue_apply(command, job_application):
    durable_command = command(str(uuid.uuid4()))
    try:
        acceptance = job_application.enqueue(durable_command)
    except DurableJobCommandConflict as error:
        raise durable_job_conflict_http_error(
            error,
            durable_command.correlation_id,
        ) from error

    return BaseResponse(
        data=JobAcceptedResponse(
            job_id=acceptance.job_id,
            status_url=f"/api/v1/jobs/{acceptance.job_id}",
        ),
        message="202 Accepted",
    )


def _government_subsidy_command(action, intent, request):
    payload = {
            "action": action,
            "intent": intent,
            "expected_batch_version": request.expected_batch_version.value,
            "preview_fingerprint": request.preview_fingerprint.value,
            "idempotency_key": request.idempotency_key.value,
            "actor": request.actor.actor_id,
            "reason": request.reason,
            "correlation_id": request.correlation_id.value,
    }
    return lambda job_id: DurableJobCommand(
        job_id,
        request.idempotency_key.value,
        "government_subsidy_apply",
        1,
        payload,
        request.actor.actor_id,
        request.correlation_id.value,
    )

def _call_endpoint(command, message, correlation_id):
    try:
        return BaseResponse(data=command(), message=message)
    except GovernmentSubsidyWorkflowError as error:
        _raise_typed_error(error.error)
    except GovernmentSubsidyClaimWorkflowError as error:
        _raise_typed_error(error.error)
    except GovernmentSubsidyOverpaymentQueryError as error:
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


@router.get(
    "/payer-master",
    response_model=BaseResponse[GovernmentPayerMasterView],
)
def query_government_payer_master(
    principal: AdminPrincipal = Depends(require_system_admin),
    workflow: GovernmentPayerMasterWorkflow = Depends(get_government_payer_master_workflow),
):
    del principal
    master = workflow.query()
    return BaseResponse(data=_payer_master_payload(master, workflow), message="成功取得政府付款方主檔")


@router.post(
    "/payer-master/refund-accounts/preview",
    response_model=BaseResponse[GovernmentPayerAccountPreviewView],
)
def preview_government_refund_account(
    body: GovernmentPayerAccountPreviewBody,
    correlation_id: Annotated[str, Header(alias="X-Correlation-ID", min_length=1, max_length=191)] = "government-payer-account-preview",
    principal: AdminPrincipal = Depends(require_system_admin),
    workflow: GovernmentPayerMasterWorkflow = Depends(get_government_payer_master_workflow),
):
    del principal
    return _call_payer_endpoint(
        lambda: BaseResponse(data=_payer_preview_payload(workflow.preview(_payer_account(body.account)), workflow), message="成功產生政府退款帳戶預覽"),
        CorrelationId(correlation_id),
    )


@router.post(
    "/payer-master/refund-accounts/apply",
    response_model=BaseResponse[GovernmentPayerAccountReceiptView],
)
def apply_government_refund_account(
    body: GovernmentPayerAccountApplyBody,
    correlation_id: Annotated[str, Header(alias="X-Correlation-ID", min_length=1, max_length=191)] = ...,
    principal: AdminPrincipal = Depends(require_system_admin),
    workflow: GovernmentPayerMasterWorkflow = Depends(get_government_payer_master_workflow),
):
    request = GovernmentRefundAccountApplyRequest(
        _payer_account(body.account), PreviewFingerprint(body.preview_fingerprint),
        _actor(principal), CorrelationId(correlation_id),
    )
    return _call_payer_endpoint(
        lambda: BaseResponse(data=_payer_receipt_payload(workflow.apply(request)), message="成功新增政府退款帳戶版本"),
        request.correlation_id,
    )


def _payer_account(view):
    try:
        effective_from = date.fromisoformat(view.effective_from)
    except ValueError as error:
        raise ValueError("government_payer_account_effective_date_invalid") from error
    return GovernmentRefundAccount(view.bank_code, view.account_number, view.account_name, effective_from, view.reason, view.evidence_reference)


def _payer_master_payload(master, workflow):
    active = master.active_account
    return {
        "payer_identity": master.payer_identity,
        "payer_name": master.payer_name,
        "active_refund_account": None if active is None else {
            "bank_code": active.account.bank_code,
            "account_display": workflow.account_display(active.account.account_number),
            "account_name": active.account.account_name,
            "effective_from": active.account.effective_from.isoformat(),
            "effective_until": active.effective_until.isoformat() if active.effective_until else None,
        },
    }


def _payer_preview_payload(preview, workflow):
    return {
        "payer_identity": preview.payer_identity,
        "effective_from": preview.account.effective_from.isoformat(),
        "previous_effective_from": preview.previous_effective_from.isoformat() if preview.previous_effective_from else None,
        "account_display": workflow.account_display(preview.account.account_number),
        "preview_fingerprint": preview.fingerprint.value,
    }


def _payer_receipt_payload(receipt):
    return {
        "payer_identity": receipt.payer_identity,
        "effective_from": receipt.effective_from,
        "previous_effective_from": None,
        "account_display": receipt.account_display,
        "preview_fingerprint": receipt.preview_fingerprint.value,
        "replayed": receipt.replayed,
    }


def _call_payer_endpoint(command, correlation_id):
    try:
        return command()
    except GovernmentPayerMasterWorkflowError as error:
        _raise_typed_error(error.error)
    except OperationalError as error:
        _raise_mysql_error(error, correlation_id)
    except ValueError as error:
        _raise_value_error(error, correlation_id)
    except HTTPException:
        raise
    except Exception as error:
        raise _internal_error(correlation_id) from error


@router.post("/receipts-with-overage/preview")
def preview_government_subsidy_receipt_with_overage(body: GovernmentSubsidyOverageReceiptPreviewBody, application: GovernmentSubsidyApplication = Depends(get_government_subsidy_application), principal: AdminPrincipal = Depends(require_system_admin)):
    del principal
    candidate = application.preview_receipt_with_overage(body.intent.finance_import_row_id, body.intent.batch_id, _overage_intents(body.intent.allocations))
    return BaseResponse(data={"batch_id":candidate.batch_id,"allocated_amount_ntd":candidate.allocated_amount_ntd.amount,"overpayment_amount_ntd":candidate.overpayment_amount_ntd.amount,"preview_fingerprint":candidate.fingerprint.value}, message="成功產生政府補助溢撥預覽")


@router.post("/receipts-with-overage/apply")
def apply_government_subsidy_receipt_with_overage(body: GovernmentSubsidyOverageReceiptApplyBody, idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=191)] = ..., correlation_id: Annotated[str, Header(alias="X-Correlation-ID", min_length=1, max_length=191)] = ..., application: GovernmentSubsidyApplication = Depends(get_government_subsidy_application), principal: AdminPrincipal = Depends(require_system_admin)):
    request = ReceiptWithOverageApplyRequest(body.intent.finance_import_row_id, body.intent.batch_id, _overage_intents(body.intent.allocations), body.intent.evidence_reference, ExpectedVersion(body.expected_batch_version), PreviewFingerprint(body.preview_fingerprint), IdempotencyKey(idempotency_key), _actor(principal), body.reason, CorrelationId(correlation_id))
    return _call_endpoint(lambda: BaseResponse(data=application.apply_receipt_with_overage(request), message="成功建立政府補助溢撥"), "成功建立政府補助溢撥", request.correlation_id)


def _overage_intents(values):
    return tuple(GovernmentSubsidyOffsetIntent(item.target_identity, MoneyNTD(item.amount_ntd)) for item in values)


@router.post("/overpayments/disposition/preview")
def preview_government_subsidy_overpayment_disposition(
    body: GovernmentSubsidyOverpaymentDispositionPreviewBody,
    correlation_id: Annotated[str, Header(alias="X-Correlation-ID", min_length=1, max_length=191)] = "government-overpayment-disposition-preview",
    principal: AdminPrincipal = Depends(require_system_admin),
    application: GovernmentSubsidyApplication = Depends(get_government_subsidy_application),
):
    """Keep the finite disposition branch inside Government Subsidy's typed intent."""
    del principal
    correlation = CorrelationId(correlation_id)
    return _call_endpoint(
        lambda: _overpayment_candidate_payload(
            _preview_overpayment_disposition(application, body)
        ),
        "成功產生政府補助溢撥處置預覽",
        correlation,
    )


@router.post("/overpayments/disposition/apply")
def apply_government_subsidy_overpayment_disposition(
    body: GovernmentSubsidyOverpaymentDispositionApplyBody,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=191)] = ...,
    correlation_id: Annotated[str, Header(alias="X-Correlation-ID", min_length=1, max_length=191)] = ...,
    principal: AdminPrincipal = Depends(require_capability("government_subsidy.overpayment.disposition")),
    application: GovernmentSubsidyApplication = Depends(get_government_subsidy_application),
):
    request = _disposition_apply_request(body, idempotency_key, correlation_id, principal)
    return _call_endpoint(
        lambda: _apply_overpayment_disposition(application, body.disposition, request),
        "成功套用政府補助溢撥處置",
        request.correlation_id,
    )


def _preview_overpayment_disposition(application, body):
    if body.disposition == "offset":
        return application.preview_overpayment_offset(
            body.overpayment_identity,
            _overpayment_offset_intents(body.targets),
        )
    _require_iso_date(body.due_date or "")
    return application.preview_overpayment_return(
        body.overpayment_identity,
        body.due_date or "",
        body.evidence_reference,
    )


def _disposition_apply_request(body, idempotency_key, correlation_id, principal):
    common = (
        body.overpayment_identity,
        ExpectedVersion(body.expected_overpayment_version),
        PreviewFingerprint(body.preview_fingerprint),
        IdempotencyKey(idempotency_key),
        _actor(principal),
        body.reason,
        CorrelationId(correlation_id),
    )
    if body.disposition == "offset":
        return OffsetApplyRequest(
            common[0], _overpayment_offset_intents(body.targets), *common[1:6],
            body.evidence_reference, common[6],
        )
    _require_iso_date(body.due_date or "")
    return ReturnApplyRequest(
        common[0], body.due_date or "", body.evidence_reference,
        *common[1:],
    )


def _apply_overpayment_disposition(application, disposition, request):
    if disposition == "offset":
        return application.apply_overpayment_offset(request)
    return application.apply_overpayment_return(request)


@router.post("/overpayments/offset/preview")
def preview_government_subsidy_overpayment_offset(
    body: GovernmentSubsidyOverpaymentOffsetPreviewBody,
    correlation_id: Annotated[str, Header(alias="X-Correlation-ID", min_length=1, max_length=191)] = "government-overpayment-offset-preview",
    principal: AdminPrincipal = Depends(require_system_admin),
    application: GovernmentSubsidyApplication = Depends(get_government_subsidy_application),
):
    del principal
    correlation = CorrelationId(correlation_id)
    return _call_endpoint(
        lambda: _overpayment_candidate_payload(
            application.preview_overpayment_offset(
                body.overpayment_identity, _overpayment_offset_intents(body.targets)
            )
        ),
        "成功產生政府補助溢撥抵扣預覽",
        correlation,
    )


@router.post("/overpayments/offset/apply")
def apply_government_subsidy_overpayment_offset(
    body: GovernmentSubsidyOverpaymentOffsetApplyBody,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=191)] = ...,
    correlation_id: Annotated[str, Header(alias="X-Correlation-ID", min_length=1, max_length=191)] = ...,
    principal: AdminPrincipal = Depends(require_capability("government_subsidy.overpayment.disposition")),
    application: GovernmentSubsidyApplication = Depends(get_government_subsidy_application),
):
    request = OffsetApplyRequest(
        body.overpayment_identity, _overpayment_offset_intents(body.targets),
        ExpectedVersion(body.expected_overpayment_version),
        PreviewFingerprint(body.preview_fingerprint), IdempotencyKey(idempotency_key),
        _actor(principal), body.reason, body.evidence_reference,
        CorrelationId(correlation_id),
    )
    return _call_endpoint(
        lambda: application.apply_overpayment_offset(request),
        "成功套用政府補助溢撥抵扣",
        request.correlation_id,
    )


@router.post("/overpayments/return/preview")
def preview_government_subsidy_overpayment_return(
    body: GovernmentSubsidyOverpaymentReturnPreviewBody,
    correlation_id: Annotated[str, Header(alias="X-Correlation-ID", min_length=1, max_length=191)] = "government-overpayment-return-preview",
    principal: AdminPrincipal = Depends(require_system_admin),
    application: GovernmentSubsidyApplication = Depends(get_government_subsidy_application),
):
    del principal
    _require_iso_date(body.due_date)
    correlation = CorrelationId(correlation_id)
    return _call_endpoint(
        lambda: _overpayment_candidate_payload(
            application.preview_overpayment_return(
                body.overpayment_identity, body.due_date, body.evidence_reference
            )
        ),
        "成功產生政府補助溢撥退還預覽",
        correlation,
    )


@router.post("/overpayments/return/apply")
def apply_government_subsidy_overpayment_return(
    body: GovernmentSubsidyOverpaymentReturnApplyBody,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=191)] = ...,
    correlation_id: Annotated[str, Header(alias="X-Correlation-ID", min_length=1, max_length=191)] = ...,
    principal: AdminPrincipal = Depends(require_capability("government_subsidy.overpayment.disposition")),
    application: GovernmentSubsidyApplication = Depends(get_government_subsidy_application),
):
    _require_iso_date(body.due_date)
    request = ReturnApplyRequest(
        body.overpayment_identity, body.due_date, body.evidence_reference,
        ExpectedVersion(body.expected_overpayment_version),
        PreviewFingerprint(body.preview_fingerprint), IdempotencyKey(idempotency_key),
        _actor(principal), body.reason, CorrelationId(correlation_id),
    )
    return _call_endpoint(
        lambda: application.apply_overpayment_return(request),
        "成功建立政府補助溢撥退還應付",
        request.correlation_id,
    )


def _overpayment_offset_intents(values):
    return tuple(
        GovernmentSubsidyOffsetIntent(item.claim_item_id, MoneyNTD(item.amount_ntd))
        for item in values
    )


def _overpayment_candidate_payload(candidate):
    return {
        "overpayment_identity": candidate.overpayment_identity,
        "overpayment_version": candidate.overpayment_version,
        "remaining_before_ntd": candidate.remaining_before_ntd.amount,
        "disposition_amount_ntd": candidate.disposition_amount_ntd.amount,
        "remaining_after_ntd": candidate.remaining_after_ntd.amount,
        "resulting_status": candidate.resulting_status.value,
        "disposition_kind": candidate.disposition_kind,
        "preview_fingerprint": candidate.fingerprint.value,
    }


def _overpayment_query_payload(value):
    return {
        "overpayment_identity": value.overpayment_identity,
        "payer_identity": value.payer_identity,
        "remaining_amount_ntd": value.remaining_amount_ntd,
        "status": value.status,
        "overpayment_version": value.overpayment_version,
        "source_bank_fact_reference": value.source_bank_fact_reference,
        "source_transaction_reference": value.source_transaction_reference,
        "offset_targets": [
            {
                "claim_item_id": target.claim_item_id,
                "claim_batch_id": target.claim_batch_id,
                "batch_version": target.batch_version,
                "outstanding_amount_ntd": target.outstanding_amount_ntd,
                "payer_identity": target.payer_identity,
            }
            for target in value.offset_targets
        ],
        "return_recipient": {
            "ready": value.return_recipient.ready,
            "blockers": list(value.return_recipient.blockers),
            "agency_identity": value.return_recipient.agency_identity,
            "agency_name": value.return_recipient.agency_name,
            "bank_code": value.return_recipient.bank_code,
            "account_display": value.return_recipient.account_display,
            "account_fingerprint": value.return_recipient.account_fingerprint,
            "effective_date": value.return_recipient.effective_date,
        },
        "blockers": list(value.blockers),
        "available_actions": list(value.available_actions),
        "return_excess_recovery": (
            {
                "recovery_identity": value.return_excess_recovery.recovery_identity,
                "source_bank_fact_reference": value.return_excess_recovery.source_bank_fact_reference,
                "source_payout_reference": value.return_excess_recovery.source_payout_reference,
                "original_amount_ntd": value.return_excess_recovery.original_amount_ntd,
                "remaining_amount_ntd": value.return_excess_recovery.remaining_amount_ntd,
                "status": value.return_excess_recovery.status,
                "recovery_version": value.return_excess_recovery.recovery_version,
            }
            if value.return_excess_recovery is not None
            else None
        ),
    }


def _require_iso_date(value):
    try:
        date.fromisoformat(value)
    except ValueError as error:
        raise ValueError("government_subsidy_return_due_date_invalid") from error


@router.post("/overpayments/return-reconciliation/preview")
def preview_government_overpayment_return_reconciliation(
    body: GovernmentOverpaymentReturnReconciliationPreviewBody,
    correlation_id: Annotated[str, Header(alias="X-Correlation-ID", min_length=1, max_length=191)] = "government-overpayment-return-reconciliation-preview",
    principal: AdminPrincipal = Depends(require_system_admin),
    application: GovernmentSubsidyApplication = Depends(get_government_subsidy_application),
):
    del principal
    correlation = CorrelationId(correlation_id)
    return _call_endpoint(
        lambda: _return_reconciliation_candidate_payload(
            application.preview_overpayment_return_reconciliation(
                body.overpayment_identity, body.finance_import_row_id
            )
        ),
        "成功產生政府退款單銀行對帳預覽",
        correlation,
    )


@router.post("/overpayments/return-reconciliation/apply")
def apply_government_overpayment_return_reconciliation(
    body: GovernmentOverpaymentReturnReconciliationApplyBody,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=191)] = ...,
    correlation_id: Annotated[str, Header(alias="X-Correlation-ID", min_length=1, max_length=191)] = ...,
    principal: AdminPrincipal = Depends(require_capability("government_subsidy.overpayment.disposition")),
    application: GovernmentSubsidyApplication = Depends(get_government_subsidy_application),
):
    request = ReturnReconciliationApplyRequest(
        body.overpayment_identity, body.finance_import_row_id,
        ExpectedVersion(body.expected_overpayment_version),
        PreviewFingerprint(body.preview_fingerprint), IdempotencyKey(idempotency_key),
        _actor(principal), body.reason, body.evidence_reference,
        CorrelationId(correlation_id),
    )
    return _call_endpoint(
        lambda: application.apply_overpayment_return_reconciliation(request),
        "成功記錄政府退款單銀行對帳",
        request.correlation_id,
    )


def _return_reconciliation_candidate_payload(candidate):
    return {
        "overpayment_identity": candidate.overpayment_identity,
        "payable_identity": candidate.payable_identity,
        "bank_fact_identity": candidate.bank_fact_identity,
        "amount_ntd": candidate.amount_ntd.amount,
        "remaining_after_ntd": candidate.remaining_after_ntd.amount,
        "resulting_status": candidate.resulting_status.value,
        "preview_fingerprint": candidate.fingerprint.value,
    }


@router.post(
    "/overpayments/return-reconciliation-with-excess/preview",
    response_model=BaseResponse[GovernmentOverpaymentReturnReconciliationWithExcessPreviewView],
)
def preview_government_overpayment_return_reconciliation_with_excess(
    body: GovernmentOverpaymentReturnReconciliationPreviewBody,
    correlation_id: Annotated[str, Header(alias="X-Correlation-ID", min_length=1, max_length=191)] = "government-overpayment-return-reconciliation-with-excess-preview",
    principal: AdminPrincipal = Depends(require_system_admin),
    application: GovernmentSubsidyApplication = Depends(get_government_subsidy_application),
):
    del principal
    correlation = CorrelationId(correlation_id)
    return _call_endpoint(
        lambda: _return_reconciliation_with_excess_candidate_payload(
            application.preview_overpayment_return_reconciliation_with_excess(
                body.overpayment_identity, body.finance_import_row_id
            )
        ),
        "成功產生政府退款超額對帳預覽",
        correlation,
    )


@router.post(
    "/overpayments/return-reconciliation-with-excess/apply",
)
def apply_government_overpayment_return_reconciliation_with_excess(
    body: GovernmentOverpaymentReturnReconciliationApplyBody,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=191)] = ...,
    correlation_id: Annotated[str, Header(alias="X-Correlation-ID", min_length=1, max_length=191)] = ...,
    principal: AdminPrincipal = Depends(require_capability("government_subsidy.overpayment.disposition")),
    application: GovernmentSubsidyApplication = Depends(get_government_subsidy_application),
):
    request = ReturnReconciliationWithExcessApplyRequest(
        body.overpayment_identity,
        body.finance_import_row_id,
        ExpectedVersion(body.expected_overpayment_version),
        PreviewFingerprint(body.preview_fingerprint),
        IdempotencyKey(idempotency_key),
        _actor(principal),
        body.reason,
        body.evidence_reference,
        CorrelationId(correlation_id),
    )
    return _call_endpoint(
        lambda: application.apply_overpayment_return_reconciliation_with_excess(request),
        "成功記錄政府退款超額對帳",
        request.correlation_id,
    )


def _return_reconciliation_with_excess_candidate_payload(candidate):
    return {
        "overpayment_identity": candidate.overpayment_identity,
        "overpayment_version": candidate.overpayment_version,
        "payable_identity": candidate.payable_identity,
        "payable_version": candidate.payable_version,
        "bank_fact_identity": candidate.bank_fact_identity,
        "actual_amount_ntd": candidate.actual_amount_ntd.amount,
        "lawful_amount_ntd": candidate.lawful_amount_ntd.amount,
        "excess_amount_ntd": candidate.excess_amount_ntd.amount,
        "payable_remaining_after_ntd": candidate.payable_remaining_after_ntd.amount,
        "overpayment_remaining_after_ntd": candidate.overpayment_remaining_after_ntd.amount,
        "resulting_status": candidate.resulting_status.value,
        "recovery_identity": candidate.recovery_identity,
        "recovery_status": candidate.recovery_status.value,
        "preview_fingerprint": candidate.fingerprint.value,
    }


__all__ = [
    "apply_government_subsidy_claim_approval",
    "apply_government_subsidy_claim_plan",
    "apply_government_subsidy_claim_submission",
    "GovernmentSubsidyReceiptApplyBody",
    "GovernmentSubsidyReceiptPreviewBody",
    "GovernmentSubsidyReversalApplyBody",
    "GovernmentSubsidyReversalPreviewBody",
    "list_government_subsidy_batches",
    "query_government_subsidy_overpayment",
    "preview_government_subsidy_claim_approval",
    "preview_government_subsidy_claim_plan",
    "preview_government_subsidy_claim_submission",
    "router",
]
