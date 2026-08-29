"""Authenticated, typed case and staff assignment read endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Path

from api.dependencies.admin_auth import require_admin
from api.dependencies.multi_caregiver_schedule import (
    get_multi_caregiver_schedule_query_application,
)
from api.schemas.base import BaseResponse
from api.schemas.multi_caregiver_schedule import (
    CaseAssignmentListView,
    CaseAssignmentSummaryView,
    CaseAssignmentView,
)
from api.schemas.staff_assignment_options import (
    StaffAssignmentOptionView,
    StaffAssignmentOptionsView,
)
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.scheduling.multi_caregiver_schedule_query import (
    MultiCaregiverScheduleQueryApplication,
)


router = APIRouter(prefix="/api/v1/cases", tags=["Multi-caregiver schedules"])
staff_router = APIRouter(prefix="/api/v1/staff", tags=["Multi-caregiver schedules"])


@staff_router.get("/{staff_id}/assignment-schedules", response_model=BaseResponse[StaffAssignmentOptionsView])
def list_staff_schedule_assignments(
    staff_id: int = Path(..., ge=1),
    principal: AdminPrincipal = Depends(require_admin),
    application: MultiCaregiverScheduleQueryApplication = Depends(
        get_multi_caregiver_schedule_query_application
    ),
) -> BaseResponse[StaffAssignmentOptionsView]:
    """Return one staff member's formal assignments for Calendar selection."""
    del principal
    try:
        return BaseResponse[StaffAssignmentOptionsView](
            data=StaffAssignmentOptionsView(
                assignments=[
                    StaffAssignmentOptionView(
                        id=item.id,
                        case_no=item.case_no,
                        staff_id=item.staff_id,
                        status=item.status,
                        assigned_start_date=item.assigned_start_date,
                        assigned_end_date=item.assigned_end_date,
                        order_status=item.order_status,
                        actual_start_date=item.actual_start_date,
                        actual_end_date=item.actual_end_date,
                        staff_name=item.staff_name,
                    )
                    for item in application.list_staff_assignments(staff_id)
                ]
            ),
            message="Staff assignments retrieved",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Failed to retrieve staff assignments") from exc


@router.get("/{case_no}/assignment-schedules", response_model=BaseResponse[CaseAssignmentListView])
def list_case_schedule_assignments(
    case_no: str = Path(..., min_length=1, max_length=50),
    principal: AdminPrincipal = Depends(require_admin),
    application: MultiCaregiverScheduleQueryApplication = Depends(
        get_multi_caregiver_schedule_query_application
    ),
) -> BaseResponse[CaseAssignmentListView]:
    """Return selectable formal assignments for one explicitly chosen case."""
    del principal
    try:
        result = application.list_case_assignments(case_no)
        return BaseResponse(
            data=CaseAssignmentListView(
                assignments=[
                    CaseAssignmentView(
                        id=item.id,
                        case_no=item.case_no,
                        staff_id=item.staff_id,
                        status=item.status,
                        assigned_start_date=item.assigned_start_date,
                        assigned_end_date=item.assigned_end_date,
                        original_assigned_start_date=item.original_assigned_start_date,
                        original_assigned_end_date=item.original_assigned_end_date,
                        planned_hours=item.planned_hours,
                        actual_hours=item.actual_hours,
                        service_days=item.service_days,
                        service_hours_per_day=item.service_hours_per_day,
                        staff_name=item.staff_name,
                        actual_service_days=item.actual_service_days,
                        rest_days=item.rest_days,
                        substitute_service_days=item.substitute_service_days,
                        deferred_leave_days=item.deferred_leave_days,
                        leave_resolution_days=item.leave_resolution_days,
                        required_service_days=item.required_service_days,
                        adjusted_assigned_start_date=item.adjusted_assigned_start_date,
                        adjusted_assigned_end_date=item.adjusted_assigned_end_date,
                        original_scheduled_service_days=item.original_scheduled_service_days,
                        makeup_service_days=item.makeup_service_days,
                    )
                    for item in result.assignments
                ],
                summary=(
                    CaseAssignmentSummaryView(
                        required_service_days=result.summary.required_service_days,
                        actual_service_days=result.summary.actual_service_days,
                        actual_hours=result.summary.actual_hours,
                        adjusted_start_date=result.summary.adjusted_start_date,
                        adjusted_end_date=result.summary.adjusted_end_date,
                        target_service_days=result.summary.target_service_days,
                        target_service_hours=result.summary.target_service_hours,
                        has_service_gap=result.summary.has_service_gap,
                        has_service_overlap=result.summary.has_service_overlap,
                        rest_days=result.summary.rest_days,
                        substitute_service_days=result.summary.substitute_service_days,
                        deferred_leave_days=result.summary.deferred_leave_days,
                    )
                    if result.summary is not None
                    else None
                ),
            ),
            message="Case assignments retrieved",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Failed to retrieve case assignments") from exc
