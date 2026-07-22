"""Read-only case-to-assignment selection endpoint for multi-caregiver scheduling."""

from typing import Any

from fastapi import APIRouter, HTTPException, Path

from api.schemas.base import BaseResponse
from services.multi_caregiver_schedule_read import (
    list_case_schedule_assignments as list_case_schedule_assignments_service,
)


router = APIRouter(prefix="/api/v1/cases", tags=["Multi-caregiver schedules"])


@router.get("/{case_no}/assignment-schedules", response_model=BaseResponse[dict[str, Any]])
def list_case_schedule_assignments(
    case_no: str = Path(..., min_length=1),
) -> BaseResponse[dict[str, Any]]:
    """Return selectable formal assignments for one explicitly chosen case."""

    try:
        return BaseResponse(
            data=list_case_schedule_assignments_service(case_no),
            message="Case assignments retrieved",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Failed to retrieve case assignments") from exc
