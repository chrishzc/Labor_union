"""
File: jobs.py
Description: 提供 Durable Job canonical closed outcome 查詢與 outer-UoW 安全取消入口。
"""

from fastapi import APIRouter, Depends
from pydantic import ValidationError

from api.dependencies.admin_auth import require_system_admin, AdminPrincipal
from api.dependencies.jobs import get_durable_job_cancellation, get_job_repository
from api.error_contracts import typed_http_error
from api.schemas.base import BaseResponse
from api.schemas.jobs import (
    JobFailureOutcomeView,
    JobObservationView,
    JobResponse,
    JobSuccessOutcomeView,
)
from infrastructure.mysql.background_job_repository import BackgroundJobRepository
from shared_kernel.durable_job_queue import DurableJobStateConflict
from subsystems.jobs.command_application import DurableJobCancellationApplication

router = APIRouter(prefix="/api/v1/jobs", tags=["Jobs"])

_OBSERVED_COMMAND_TYPES = frozenset(
    {
        "assignment_plan_apply",
        "finance_import_historical_reprocess_apply",
        "finance_import_batch_apply",
        "finance_import_correction_apply",
        "orders_auto_completion_apply",
        "government_subsidy_apply",
        "payroll_rebuild_apply",
        "staff_payout_apply",
    }
)


@router.get(
    "/{job_id}/observation",
    response_model=BaseResponse[JobObservationView],
)
def get_job_observation(
    job_id: str,
    principal: AdminPrincipal = Depends(require_system_admin),
    repository: BackgroundJobRepository = Depends(get_job_repository),
) -> BaseResponse[JobObservationView]:
    """Return a safe job execution-state view without terminal payloads."""
    del principal
    job = repository.get_job(job_id)
    if not job:
        raise typed_http_error(
            404,
            "not_found",
            "job_not_found",
            "Job was not found.",
            f"job-observation:{job_id}",
        )
    if job.command_type not in _OBSERVED_COMMAND_TYPES:
        raise typed_http_error(
            503,
            "unavailable",
            "job_observation_unavailable",
            "此背景工作類型尚未開放安全查詢投影。",
            f"job-observation:{job_id}",
            retryable=False,
        )
    return BaseResponse(
        data=JobObservationView(
            job_id=job.job_id,
            command_type=job.command_type,
            status=job.status,
            attempt_count=job.attempt_count,
            max_attempts=job.max_attempts,
        ),
        message="成功取得背景工作執行狀態",
    )

@router.get("/{job_id}", response_model=BaseResponse[JobResponse])
def get_job_status(
    job_id: str,
    principal: AdminPrincipal = Depends(require_system_admin),
    repository: BackgroundJobRepository = Depends(get_job_repository),
) -> BaseResponse[JobResponse]:
    job = repository.get_job(job_id)
    if not job:
        raise typed_http_error(
            404,
            "not_found",
            "job_not_found",
            "Job was not found.",
            f"job-status:{job_id}",
        )
        
    return BaseResponse(data=_job_response(job, f"job-status:{job_id}"))


@router.post("/{job_id}/cancel", response_model=BaseResponse[JobResponse])
def cancel_queued_job(
    job_id: str,
    principal: AdminPrincipal = Depends(require_system_admin),
    repository: BackgroundJobRepository = Depends(get_job_repository),
    cancellation: DurableJobCancellationApplication = Depends(
        get_durable_job_cancellation
    ),
) -> BaseResponse[JobResponse]:
    del principal
    job = repository.get_job(job_id)
    if job is None:
        raise typed_http_error(404, "not_found", "job_not_found", "Job was not found.", f"job-cancel:{job_id}")
    try:
        cancellation.cancel_queued(job_id)
    except DurableJobStateConflict as error:
        raise typed_http_error(409, "conflict", "job_state_conflict", "Only an unclaimed queued job can be cancelled.", f"job-cancel:{job_id}") from error
    return BaseResponse(
        data=_job_response(job, f"job-cancel:{job_id}", status_override="cancelled")
    )


def _job_response(
    job,
    correlation_id: str,
    *,
    status_override: str | None = None,
) -> JobResponse:
    try:
        public_status = job.status if status_override is None else status_override
        outcome = None
        if public_status == "succeeded":
            outcome = JobSuccessOutcomeView.model_validate(job.receipt_payload)
        elif public_status == "failed":
            outcome = JobFailureOutcomeView.model_validate(job.error_payload)
        return JobResponse(
            job_id=job.job_id,
            status=public_status,
            command_type=job.command_type,
            attempt_count=job.attempt_count,
            max_attempts=job.max_attempts,
            outcome=outcome,
        )
    except ValidationError as error:
        raise typed_http_error(
            503,
            "unavailable",
            "job_outcome_contract_unavailable",
            "Durable Job outcome is not available through the closed public contract.",
            correlation_id,
        ) from error
