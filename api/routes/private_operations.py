"""Authenticated private endpoints for independently supervised runtime processes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status

from api.dependencies.internal_service_auth import (
    InternalServicePrincipal,
    require_internal_service,
    require_operation_service,
)
from api.dependencies.private_operations import (
    inspect_react_admin_artifact_health,
    inspect_runtime_readiness,
    record_monitor_cycle,
    run_durable_job_cycle,
    run_knowledge_cycle,
)
from api.dependencies.line_worker_operation import run_line_cycle
from api.dependencies.maintenance_operation import run_incident_maintenance_cycle
from api.schemas.base import BaseResponse
from api.schemas.private_operations import (
    DurableWorkerCycleRequest,
    MonitorCycleRequest,
    MonitorCycleResponse,
    ReactAdminArtifactHealthResponse,
    RuntimeReadinessItem,
    RuntimeReadinessResponse,
    WorkerCycleRequest,
    WorkerCycleResponse,
    WorkerRuntimeIdentity,
)


router = APIRouter(
    prefix="/internal/v1/runtime",
    tags=["Private Runtime Operations"],
    include_in_schema=False,
)


@router.get(
    "/react-admin/artifact-health",
    response_model=BaseResponse[ReactAdminArtifactHealthResponse],
)
def react_admin_artifact_health(
    request: Request,
    _: InternalServicePrincipal = Depends(require_internal_service),
) -> BaseResponse[ReactAdminArtifactHealthResponse]:
    try:
        health = ReactAdminArtifactHealthResponse.model_validate(
            inspect_react_admin_artifact_health(request)
        )
    except Exception as error:
        raise _operation_unavailable(
            "react_admin_artifact_health_unavailable", error
        ) from error
    return BaseResponse(data=health)


@router.post("/check", response_model=BaseResponse[dict[str, str]])
def check_private_runtime(
    principal: InternalServicePrincipal = Depends(require_internal_service),
) -> BaseResponse[dict[str, str]]:
    return BaseResponse(data={"status": "ready", "service": principal.service_name})


@router.post("/readiness", response_model=BaseResponse[RuntimeReadinessResponse])
def check_runtime_dependencies(
    _: InternalServicePrincipal = Depends(require_internal_service),
) -> BaseResponse[RuntimeReadinessResponse]:
    try:
        observations = inspect_runtime_readiness()
    except Exception as error:
        raise _operation_unavailable("runtime_dependencies_unavailable", error) from error
    checks = tuple(
        RuntimeReadinessItem(
            check_name=item.check_name,
            status=item.status.value,
            message=item.message,
        )
        for item in observations
    )
    ready = all(item.status not in {"critical"} for item in checks)
    return BaseResponse(data=RuntimeReadinessResponse(ready=ready, checks=checks))


@router.post("/durable-jobs/run-once", response_model=BaseResponse[WorkerCycleResponse])
def run_durable_job_once(
    request: DurableWorkerCycleRequest,
    principal: InternalServicePrincipal = Depends(require_internal_service),
) -> BaseResponse[WorkerCycleResponse]:
    _require_bound_service(principal, request.runtime_identity, "durable-job-worker")
    try:
        processed = run_durable_job_cycle(
            request.worker_id,
            request.lease_seconds,
            request.retry_delay_seconds,
            request.runtime_identity,
            check_only=request.check_only,
        )
    except Exception as error:
        raise _operation_unavailable("durable_job_cycle_failed", error) from error
    return BaseResponse(data=WorkerCycleResponse(processed=processed, operation="durable_job"))


@router.post("/knowledge/run-once", response_model=BaseResponse[WorkerCycleResponse])
def run_knowledge_once(
    request: WorkerCycleRequest,
    principal: InternalServicePrincipal = Depends(require_internal_service),
) -> BaseResponse[WorkerCycleResponse]:
    _require_bound_service(
        principal,
        request.runtime_identity,
        "knowledge-retrieval-worker",
    )
    try:
        processed = run_knowledge_cycle(request.worker_id, request.runtime_identity)
    except Exception as error:
        raise _operation_unavailable("knowledge_worker_cycle_failed", error) from error
    return BaseResponse(data=WorkerCycleResponse(processed=processed, operation="knowledge"))


@router.post("/line/run-once", response_model=BaseResponse[WorkerCycleResponse])
def run_line_once(
    request: WorkerCycleRequest,
    principal: InternalServicePrincipal = Depends(require_internal_service),
) -> BaseResponse[WorkerCycleResponse]:
    _require_bound_service(principal, request.runtime_identity, "line-worker")
    try:
        processed = run_line_cycle(request.worker_id, request.runtime_identity)
    except Exception as error:
        raise _operation_unavailable("line_worker_cycle_failed", error) from error
    return BaseResponse(data=WorkerCycleResponse(processed=processed, operation="line"))


@router.post("/incident-maintenance/run-once", response_model=BaseResponse[WorkerCycleResponse])
def run_incident_maintenance_once(
    request: WorkerCycleRequest,
    principal: InternalServicePrincipal = Depends(require_internal_service),
) -> BaseResponse[WorkerCycleResponse]:
    _require_bound_service(principal, request.runtime_identity, "incident-worker")
    try:
        processed = run_incident_maintenance_cycle(request.runtime_identity)
    except Exception as error:
        raise _operation_unavailable("incident_maintenance_cycle_failed", error) from error
    return BaseResponse(
        data=WorkerCycleResponse(processed=processed, operation="incident_maintenance")
    )


@router.post("/monitor/record-cycle", response_model=BaseResponse[MonitorCycleResponse])
def persist_monitor_cycle(
    request: MonitorCycleRequest,
    principal: InternalServicePrincipal = Depends(require_internal_service),
) -> BaseResponse[MonitorCycleResponse]:
    _require_bound_service(principal, request.runtime_identity, "runtime-monitor")
    try:
        recorded, projected = record_monitor_cycle(request)
    except Exception as error:
        raise _operation_unavailable("monitor_cycle_failed", error) from error
    return BaseResponse(
        data=MonitorCycleResponse(
            observations_recorded=recorded,
            events_projected=projected,
        )
    )


def _operation_unavailable(code: str, error: Exception) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail={
            "code": code,
            "message": f"Private runtime operation failed: {type(error).__name__}",
            "retryable": True,
        },
    )


def _require_bound_service(
    principal: InternalServicePrincipal,
    identity: WorkerRuntimeIdentity,
    expected_service_name: str,
) -> None:
    require_operation_service(principal, expected_service_name)
    require_operation_service(
        InternalServicePrincipal(identity.service_name, principal.authentication_method),
        expected_service_name,
    )
