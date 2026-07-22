"""Assignment-aware scheduling endpoints for multi-caregiver orders."""

from datetime import date
from typing import Any

from fastapi import APIRouter, HTTPException, Path
from pydantic import BaseModel, ConfigDict, Field

from api.schemas.base import BaseResponse
from services.multi_caregiver_schedule_adjustment_service import (
    adjust_assignment_schedule_day,
)
from services.multi_caregiver_schedule_generation import (
    generate_assignment_schedule as generate_assignment_schedule_service,
)


router = APIRouter(
    prefix="/api/v1/assignment-schedules",
    tags=["Multi-caregiver schedules"],
)


class AssignmentScheduleDayAdjustment(BaseModel):
    """The only client-controlled fields for one assigned schedule day."""

    model_config = ConfigDict(extra="forbid")

    is_work_day: bool = Field(...)
    is_double_pay: bool = Field(...)
    notes: str | None = Field(default=None, max_length=255)


@router.post("/{assignment_id}/generate", response_model=BaseResponse[dict[str, Any]])
def generate_assignment_schedule(
    assignment_id: int = Path(..., ge=1),
) -> BaseResponse[dict[str, Any]]:
    """Generate missing daily rows for one formal caregiver assignment."""

    try:
        return BaseResponse(
            data=generate_assignment_schedule_service(assignment_id),
            message="Assignment schedule generated",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Failed to generate assignment schedule") from exc


@router.put(
    "/{assignment_id}/days/{work_date}",
    response_model=BaseResponse[dict[str, Any]],
)
def adjust_assignment_schedule(
    adjustment: AssignmentScheduleDayAdjustment,
    assignment_id: int = Path(..., ge=1),
    work_date: date = Path(...),
) -> BaseResponse[dict[str, Any]]:
    """Adjust one existing day owned by a formal caregiver assignment."""

    try:
        return BaseResponse(
            data=adjust_assignment_schedule_day(
                assignment_id=assignment_id,
                work_date=work_date,
                is_work_day=adjustment.is_work_day,
                is_double_pay=adjustment.is_double_pay,
                notes=adjustment.notes,
            ),
            message="Assignment schedule day adjusted",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Failed to adjust assignment schedule day") from exc
