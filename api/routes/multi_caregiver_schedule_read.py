"""Authenticated, typed read endpoint for formal assignment schedules."""

from fastapi import APIRouter, Depends, HTTPException, Path

from api.dependencies.admin_auth import require_admin
from api.dependencies.multi_caregiver_schedule import (
    get_multi_caregiver_schedule_query_application,
)
from api.schemas.base import BaseResponse
from api.schemas.multi_caregiver_schedule import (
    AssignmentScheduleAssignmentView,
    AssignmentScheduleDayView,
    AssignmentScheduleGuardView,
    AssignmentScheduleView,
)
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.scheduling.multi_caregiver_schedule_query import (
    AssignmentScheduleQuery,
    MultiCaregiverScheduleQueryApplication,
)


router = APIRouter(
    prefix="/api/v1/assignment-schedules",
    tags=["Multi-caregiver schedules"],
)


@router.get("/{assignment_id}", response_model=BaseResponse[AssignmentScheduleView])
def get_assignment_schedule(
    assignment_id: int = Path(..., ge=1),
    principal: AdminPrincipal = Depends(require_admin),
    application: MultiCaregiverScheduleQueryApplication = Depends(
        get_multi_caregiver_schedule_query_application
    ),
) -> BaseResponse[AssignmentScheduleView]:
    """Return one explicit assignment and only its owned schedule days."""
    del principal
    try:
        return BaseResponse(
            data=_assignment_schedule_view(application.get_assignment_schedule(assignment_id)),
            message="Assignment schedule retrieved",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Failed to retrieve assignment schedule") from exc


def _assignment_schedule_view(result: AssignmentScheduleQuery) -> AssignmentScheduleView:
    assignment = result.assignment
    guard = result.adjustment_guard
    return AssignmentScheduleView(
        assignment=AssignmentScheduleAssignmentView(
            id=assignment.id,
            case_no=assignment.case_no,
            staff_id=assignment.staff_id,
            status=assignment.status,
            assigned_start_date=assignment.assigned_start_date,
            assigned_end_date=assignment.assigned_end_date,
            planned_hours=assignment.planned_hours,
            actual_hours=assignment.actual_hours,
            service_hours_per_day=assignment.service_hours_per_day,
            staff_name=assignment.staff_name,
            client_name=assignment.client_name,
        ),
        schedule_days=[
            AssignmentScheduleDayView(
                id=item.id,
                case_no=item.case_no,
                staff_id=item.staff_id,
                assignment_id=item.assignment_id,
                work_date=item.work_date,
                is_work_day=item.is_work_day,
                is_double_pay=item.is_double_pay,
                notes=item.notes,
                is_historical=item.is_historical,
            )
            for item in result.schedule_days
        ],
        database_current_date=result.database_current_date,
        adjustment_guard=AssignmentScheduleGuardView(
            is_cancelled=guard.is_cancelled,
            has_actual_hours_adjustments=guard.has_actual_hours_adjustments,
            has_active_staff_payment=guard.has_active_staff_payment,
            reasons=list(guard.reasons),
        ),
    )
