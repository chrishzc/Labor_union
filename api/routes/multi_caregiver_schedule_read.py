"""Read-only endpoints for formal multi-caregiver assignment schedules."""

from typing import Any

from fastapi import APIRouter, HTTPException, Path

from api.schemas.base import BaseResponse
from services.multi_caregiver_schedule_read import (
    get_assignment_schedule as get_assignment_schedule_service,
)


router = APIRouter(
    prefix="/api/v1/assignment-schedules",
    tags=["Multi-caregiver schedules"],
)


@router.get("/{assignment_id}", response_model=BaseResponse[dict[str, Any]])
def get_assignment_schedule(
    assignment_id: int = Path(..., ge=1),
) -> BaseResponse[dict[str, Any]]:
    """Return one explicit assignment and only its owned schedule days."""

    try:
        return BaseResponse(
            data=get_assignment_schedule_service(assignment_id),
            message="Assignment schedule retrieved",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Failed to retrieve assignment schedule") from exc
