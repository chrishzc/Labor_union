"""
File: staff_service_day_logs.py
Description: 提供已驗證月嫂提交自己正式服務日日誌與餐食照片 reference 的 LIFF API。
"""

from typing import Annotated

from fastapi import APIRouter, Header, HTTPException

from api.routes.line_staff_self_service import _required_staff, _verified_line_user_id
from api.schemas.base import BaseResponse
from api.schemas.line_staff_self_service import StaffServiceDayLogCreate, StaffServiceDayLogResponse
from domains.scheduling.service_day_log import ServiceDayLogIntent
from infrastructure.mysql.line_unit_of_work import open_line_unit_of_work
from infrastructure.mysql.mysql_adapter import get_connection
from infrastructure.mysql.service_day_log_repository import MySqlServiceDayLogRepository
from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
from subsystems.scheduling.service_day_log_workflow import ServiceDayLogWorkflow, SubmitServiceDayLog


router = APIRouter(prefix="/api/v1/line/staff-self-service", tags=["Scheduling Service Day Logs"])


@router.post("/service-day-logs", response_model=BaseResponse[StaffServiceDayLogResponse])
def submit_service_day_log(body: StaffServiceDayLogCreate, idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=191)]):
    line_user_id = _verified_line_user_id(body)
    with open_line_unit_of_work() as line_uow:
        staff = _required_staff(line_uow.customer_service.staff_subject(line_user_id.value))
        line_uow.commit()
    connection = get_connection()
    try:
        with MySqlUnitOfWork(connection) as unit_of_work:
            result = ServiceDayLogWorkflow(MySqlServiceDayLogRepository(connection)).submit(
                SubmitServiceDayLog(int(staff["staff_id"]), line_user_id.value, body.assignment_id, ServiceDayLogIntent(body.service_date, body.baby_log_text, tuple(body.meal_photo_media_ids)), idempotency_key)
            )
            unit_of_work.commit()
    except ValueError as error:
        raise HTTPException(status_code=422, detail={"code": str(error)}) from error
    finally:
        connection.close()
    return BaseResponse(data={"log_id": result.log_id, "case_no": result.case_no, "service_date": result.service_date, "requires_cooking": result.requires_cooking, "outcome": result.outcome})


__all__ = ["router"]
