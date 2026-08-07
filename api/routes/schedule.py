from fastapi import APIRouter, Depends, HTTPException

from api.dependencies.admin_auth import require_system_admin
from api.schemas.base import BaseResponse
from api.schemas.schedule import SaveScheduleRequest
from subsystems.access.authentication_session import AdminPrincipal

router = APIRouter(prefix="/api/v1/schedule", tags=["Schedule 行事曆與排班"])

@router.post("/save", response_model=BaseResponse[bool])
def save_schedule(
    req: SaveScheduleRequest,
    principal: AdminPrincipal = Depends(require_system_admin),
):
    """Retired daily writer; schedules are assignment-owned projections."""
    del principal
    raise HTTPException(
        status_code=410,
        detail={
            "code": "legacy_daily_schedule_writer_retired",
            "case_no": req.case_no,
            "replacement": "Assignment Plan or Leave/Substitution Preview/Apply",
        },
    )
