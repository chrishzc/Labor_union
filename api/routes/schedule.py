from fastapi import APIRouter, HTTPException
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from datetime import date
from services import db_service
from api.schemas.base import BaseResponse

router = APIRouter(prefix="/api/v1/schedule", tags=["Schedule 行事曆與排班"])

class SaveScheduleRequest(BaseModel):
    order_id: int = Field(..., description="訂單 ID")
    staff_id: int = Field(..., description="服務人員 ID")
    schedule_dates: List[Dict[str, Any]] = Field(..., description="每日排班列表 [{'work_date': 'YYYY-MM-DD', 'is_work_day': bool, 'is_double_pay': bool, 'notes': str}]")

@router.post("/save", response_model=BaseResponse[bool])
def save_schedule(req: SaveScheduleRequest):
    """保存月嫂排班與動態休假順延明細至 staff_schedule 資料表"""
    try:
        conn = db_service.get_connection()
        try:
            with conn.cursor() as cursor:
                for item in req.schedule_dates:
                    cursor.execute("""
                        INSERT INTO staff_schedule (order_id, staff_id, work_date, is_work_day, is_double_pay, notes)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        ON DUPLICATE KEY UPDATE
                            is_work_day = VALUES(is_work_day),
                            is_double_pay = VALUES(is_double_pay),
                            notes = VALUES(notes)
                    """, (
                        req.order_id,
                        req.staff_id,
                        item.get('work_date'),
                        item.get('is_work_day', True),
                        item.get('is_double_pay', False),
                        item.get('notes')
                    ))
                conn.commit()
            return BaseResponse(data=True, message="成功儲存月嫂排班與放假順延記錄！")
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
