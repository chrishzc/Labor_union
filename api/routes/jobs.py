from fastapi import APIRouter, Depends

from api.dependencies.admin_auth import require_system_admin, AdminPrincipal
from api.dependencies.jobs import get_job_repository
from api.error_contracts import typed_http_error
from api.schemas.base import BaseResponse
from api.schemas.jobs import JobResponse
from infrastructure.mysql.background_job_repository import BackgroundJobRepository
from shared_kernel.durable_job_queue import DurableJobStateConflict

router = APIRouter(prefix="/api/v1/jobs", tags=["Jobs"])

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
            "NOT_FOUND",
            "job_not_found",
            "Job was not found.",
            f"job-status:{job_id}",
        )
        
    return BaseResponse(data=_job_response(job))


@router.post("/{job_id}/cancel", response_model=BaseResponse[JobResponse])
def cancel_queued_job(
    job_id: str,
    principal: AdminPrincipal = Depends(require_system_admin),
    repository: BackgroundJobRepository = Depends(get_job_repository),
) -> BaseResponse[JobResponse]:
    del principal
    job = repository.get_job(job_id)
    if job is None:
        raise typed_http_error(404, "NOT_FOUND", "job_not_found", "Job was not found.", f"job-cancel:{job_id}")
    try:
        repository.cancel_queued_job(job_id)
    except DurableJobStateConflict as error:
        raise typed_http_error(409, "CONFLICT", "job_state_conflict", "Only an unclaimed queued job can be cancelled.", f"job-cancel:{job_id}") from error
    cancelled = repository.get_job(job_id)
    if cancelled is None:
        raise typed_http_error(503, "UNAVAILABLE", "job_result_unavailable", "Cancelled job status is unavailable.", f"job-cancel:{job_id}")
    return BaseResponse(data=_job_response(cancelled))


def _job_response(job) -> JobResponse:
    return JobResponse(
        job_id=job.job_id,
        status=job.status,
        receipt_payload=job.receipt_payload,
        error_payload=job.error_payload,
        command_type=job.command_type,
        attempt_count=job.attempt_count,
        max_attempts=job.max_attempts,
        result_reference=job.result_reference,
    )
