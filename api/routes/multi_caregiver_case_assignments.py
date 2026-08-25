"""
File: multi_caregiver_case_assignments.py
Description: 提供 case 與 staff 維度的正式指派唯讀選擇端點。
"""

from typing import Any

from fastapi import APIRouter, HTTPException, Path

from api.schemas.base import BaseResponse
from api.schemas.staff_assignment_options import StaffAssignmentOptionsView
from subsystems.scheduling.assignment_schedule_query import (
    list_case_schedule_assignments as list_case_schedule_assignments_service,
    list_staff_case_schedule_assignments as list_staff_case_schedule_assignments_service,
)


router = APIRouter(prefix="/api/v1/cases", tags=["Multi-caregiver schedules"])
staff_router = APIRouter(prefix="/api/v1/staff", tags=["Multi-caregiver schedules"])


@staff_router.get("/{staff_id}/assignment-schedules", response_model=BaseResponse[StaffAssignmentOptionsView])
def list_staff_schedule_assignments(
    staff_id: int = Path(..., ge=1),
) -> BaseResponse[StaffAssignmentOptionsView]:
    """Return one staff member's formal assignments for Calendar selection."""

    try:
        return BaseResponse[StaffAssignmentOptionsView](
            data=list_staff_case_schedule_assignments_service(staff_id),
            message="Staff assignments retrieved",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Failed to retrieve staff assignments") from exc


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
