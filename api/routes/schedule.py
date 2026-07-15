from fastapi import APIRouter, HTTPException
from services import db_service
from api.schemas.base import BaseResponse
from api.schemas.schedule import SaveScheduleRequest

router = APIRouter(prefix="/api/v1/schedule", tags=["Schedule 行事曆與排班"])

@router.post("/save", response_model=BaseResponse[bool])
def save_schedule(req: SaveScheduleRequest):
    """保存月嫂排班與動態休假順延明細至 staff_schedule 資料表"""
    try:
        for item in req.schedule_dates:
            db_service.update_schedule_day(
                case_no=req.case_no,
                staff_id=req.staff_id,
                work_date=item.work_date,
                is_work_day=item.is_work_day,
                is_double_pay=item.is_double_pay,
                notes=item.notes,
            )
        return BaseResponse(data=True, message="成功儲存月嫂排班與放假順延記錄！")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
