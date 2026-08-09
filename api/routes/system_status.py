"""Read-only, non-persistent operational status for system administrators."""

from fastapi import APIRouter, Depends

from api.dependencies.admin_auth import AdminPrincipal, require_system_admin
from api.schemas.base import BaseResponse
from api.schemas.system_status import PerformanceSnapshotResponse
from shared_kernel.performance_snapshot import api_performance_snapshot


router = APIRouter(prefix="/api/v1/system/status", tags=["System Status"])


@router.get("/performance-snapshot", response_model=BaseResponse[PerformanceSnapshotResponse])
def query_performance_snapshot(
    _: AdminPrincipal = Depends(require_system_admin),
) -> BaseResponse[PerformanceSnapshotResponse]:
    snapshot = api_performance_snapshot.snapshot()
    return BaseResponse(
        data=PerformanceSnapshotResponse(
            started_at=snapshot.started_at,
            request_count=snapshot.request_count,
            average_response_time_ms=snapshot.average_response_time_ms,
            p50_response_time_upper_bound_ms=snapshot.p50_response_time_upper_bound_ms,
            p95_response_time_upper_bound_ms=snapshot.p95_response_time_upper_bound_ms,
            maximum_response_time_ms=snapshot.maximum_response_time_ms,
        )
    )
