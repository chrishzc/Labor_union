"""
================================================================================
檔案名稱: api/routes/matches.py
功能說明: 訂單媒合 API，管理月嫂推薦、意願回覆、訂單資訊通知、履歷傳送與定案指派
================================================================================
"""

from fastapi import APIRouter, HTTPException, Path
from typing import Dict, Any
from services import db_service
from api.schemas.base import BaseResponse
from api.schemas.matches import (
    MatchAssignRequest,
    MatchCreateRequest,
    MatchLineTestBindingRequest,
    MatchReplyRequest,
)
from services.line_task_service import enqueue_line_task

router = APIRouter(prefix="/api/v1", tags=["Matches 案件配對與 LINE 訊息推播"])


def _target_line_user_id(value: str | None, fallback: str) -> str:
    cleaned = str(value or "").strip()
    return cleaned or fallback


def _order_staff_match(match_id: int) -> dict | None:
    conn = db_service.get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    m.id AS match_id, m.case_no, m.staff_id,
                    s.name AS staff_name, s.line_user_id AS staff_line_user_id,
                    s.phone AS staff_phone, s.city AS staff_city,
                    s.has_massage_cert, s.care_babies,
                    c.id AS client_id, c.name AS client_name,
                    c.city AS client_city, c.address AS client_address,
                    c.line_user_id AS client_line_user_id,
                    o.start_date, o.end_date, o.service_days,
                    o.service_hours_per_day, o.floor_fee
                FROM matching_records m
                JOIN staff s ON m.staff_id = s.id
                JOIN orders o ON m.case_no = o.case_no
                JOIN clients c ON o.client_id = c.id
                WHERE m.id = %s
                """,
                (match_id,),
            )
            return cursor.fetchone()
    finally:
        conn.close()


def _enqueue_and_commit(to_user_id: str, message: str, *, task_type: str, idempotency_key: str) -> int | None:
    conn = db_service.get_connection()
    try:
        with conn.cursor() as cursor:
            task_id = enqueue_line_task(
                cursor,
                to_user_id=to_user_id,
                message_content=message,
                task_type=task_type,
                idempotency_key=idempotency_key,
            )
        conn.commit()
        return task_id
    finally:
        conn.close()


def _staff_order_message(info: dict, info_type: int) -> str:
    title = "訂單資訊-1（粗篩接案詢問）" if info_type == 1 else "訂單資訊-2（精篩補充資訊）"
    return (
        f"【{title}】\n"
        f"案件編號：{info['case_no']}\n"
        f"客戶：{info.get('client_name') or '未填'}\n"
        f"服務地點：{info.get('client_city') or ''}{info.get('client_address') or ''}\n"
        f"服務期間：{info.get('start_date') or '未定'} 至 {info.get('end_date') or '未定'}\n"
        f"服務天數/時數：{info.get('service_days') or '未填'} 天 / {info.get('service_hours_per_day') or '未填'} 小時\n"
        f"樓層費：{info.get('floor_fee') or 0} 元\n\n"
        "若您願意接案，請直接回覆「同意接案」。\n"
        "若這段時間不方便，請直接回覆「拒絕接案」。"
    )


def _client_resume_message(info: dict) -> str:
    cert = "具備" if info.get("has_massage_cert") else "未填/未具備"
    return (
        "【月嫂履歷推薦】\n"
        f"案件編號：{info['case_no']}\n"
        f"推薦月嫂：{info.get('staff_name') or '月嫂'}\n"
        f"居住地：{info.get('staff_city') or '未填'}\n"
        f"可照護寶寶數：{info.get('care_babies') or '未填'}\n"
        f"按摩證照：{cert}\n\n"
        "此為去識別化履歷摘要。若您同意進一步媒合，工會將安排後續確認與契約流程。\n"
        "若您同意進一步媒合，請直接回覆「同意媒合」。\n"
        "若想重新推薦其他月嫂，請直接回覆「重新媒合」。"
    )

@router.get("/matches/recommend-staff", response_model=BaseResponse[list[dict]])


def recommend_staff(
    case_no: str,
    filter_region: bool = True,
    filter_schedule: bool = True,
    filter_babies: bool = True,
    filter_time: bool = True
):
    """智慧粗篩比對月嫂推薦引擎 API (比對 clients.city/address 與檔期 7 天預留備用期)"""
    try:
        data = db_service.get_recommended_staff_for_order(
            case_no=case_no,
            filter_region=filter_region,
            filter_schedule=filter_schedule,
            filter_babies=filter_babies,
            filter_time=filter_time
        )
        return BaseResponse(data=data, message="成功計算月嫂智慧粗篩推薦名單")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/matches/{match_id}/send-info-1", response_model=BaseResponse[Dict[str, Any]])
def send_info_1(match_id: int = Path(..., description="配對紀錄 ID")):
    """發送訂單資訊-1 (粗篩卡片)。若月嫂綁定 staff.line_user_id，同步進行 LINE 實體推播"""
    try:
        info = _order_staff_match(match_id)
        if not info:
            raise HTTPException(status_code=404, detail="配對紀錄不存在")

        # 1. 寫入發送時間戳記
        db_service.update_matching_info_sent(match_id, 1)

        to_user_id = _target_line_user_id(info.get("staff_line_user_id"), f"mock_staff_{info['staff_id']}")
        task_id = _enqueue_and_commit(
            to_user_id,
            _staff_order_message(info, 1),
            task_type="line_push",
            idempotency_key=f"match-info-1:{match_id}",
        )
        line_msg = f"已建立 LINE 訂單資訊-1 任務給月嫂 {info['staff_name']}"

        return BaseResponse(
            data={"match_id": match_id, "line_pushed": True, "line_task_id": task_id, "info_type": 1},
            message=line_msg
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/matches/{match_id}/send-info-2", response_model=BaseResponse[Dict[str, Any]])
def send_info_2(match_id: int = Path(..., description="配對紀錄 ID")):
    """發送訂單資訊-2 (精篩照護圖譜)。若月嫂綁定 staff.line_user_id，同步進行 LINE 實體推播"""
    try:
        info = _order_staff_match(match_id)
        if not info:
            raise HTTPException(status_code=404, detail="配對紀錄不存在")

        db_service.update_matching_info_sent(match_id, 2)
        to_user_id = _target_line_user_id(info.get("staff_line_user_id"), f"mock_staff_{info['staff_id']}")
        task_id = _enqueue_and_commit(
            to_user_id,
            _staff_order_message(info, 2),
            task_type="line_push",
            idempotency_key=f"match-info-2:{match_id}",
        )
        line_msg = f"已建立 LINE 訂單資訊-2 任務給月嫂 {info['staff_name']}"

        return BaseResponse(
            data={"match_id": match_id, "line_pushed": True, "line_task_id": task_id, "info_type": 2},
            message=line_msg
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/matches/{match_id}/reply", response_model=BaseResponse[bool])
def reply_matching_inquiry(
    req: MatchReplyRequest,
    match_id: int = Path(..., description="配對紀錄 ID")
):
    """更新月嫂意願回覆狀態 (1: 願意, 0: 拒絕, NULL: 待回覆)"""
    try:
        success = db_service.reply_matching_inquiry(match_id, req.accepted)
        return BaseResponse(data=success, message="成功更新月嫂接案意願狀態")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/matches/{match_id}/send-resume", response_model=BaseResponse[Dict[str, Any]])
def send_resume_to_client(match_id: int = Path(..., description="配對紀錄 ID")):
    """傳送去識別化月嫂履歷圖卡給客戶 LINE 帳號"""
    try:
        info = _order_staff_match(match_id)
        if not info:
            raise HTTPException(status_code=404, detail="配對紀錄不存在")
        to_user_id = _target_line_user_id(info.get("client_line_user_id"), f"mock_client_{info['case_no']}")
        task_id = _enqueue_and_commit(
            to_user_id,
            _client_resume_message(info),
            task_type="line_push",
            idempotency_key=f"match-resume:{match_id}",
        )
        return BaseResponse(
            data={"match_id": match_id, "line_pushed": True, "line_task_id": task_id},
            message="已建立去識別化月嫂履歷 LINE 任務給客戶",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/orders/{case_no}/line-bindings", response_model=BaseResponse[Dict[str, Any]])
def apply_line_bindings(
    req: MatchLineTestBindingRequest,
    case_no: str = Path(..., description="案件編號"),
):
    """將 LINE userId 綁到此案件客戶與指定月嫂。"""
    try:
        conn = db_service.get_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT c.id AS client_id
                    FROM orders o
                    JOIN clients c ON c.id=o.client_id
                    WHERE o.case_no=%s
                    """,
                    (case_no,),
                )
                order_row = cursor.fetchone()
                if not order_row:
                    raise HTTPException(status_code=404, detail="訂單不存在")
                cursor.execute("SELECT id FROM staff WHERE id=%s", (req.staff_id,))
                if not cursor.fetchone():
                    raise HTTPException(status_code=404, detail="月嫂不存在")

                cursor.execute(
                    "UPDATE clients SET line_user_id=%s WHERE id=%s",
                    (req.client_line_user_id.strip(), order_row["client_id"]),
                )
                cursor.execute(
                    "UPDATE staff SET line_user_id=%s WHERE id=%s",
                    (req.staff_line_user_id.strip(), req.staff_id),
                )
                cursor.execute(
                    """
                    INSERT INTO line_users (line_user_id, role, status, last_event_at)
                    VALUES (%s,'customer','active',NOW())
                    ON DUPLICATE KEY UPDATE role='customer', status='active', last_event_at=NOW()
                    """,
                    (req.client_line_user_id.strip(),),
                )
                cursor.execute(
                    """
                    INSERT INTO line_users (line_user_id, role, status, last_event_at)
                    VALUES (%s,'staff','active',NOW())
                    ON DUPLICATE KEY UPDATE role='staff', status='active', last_event_at=NOW()
                    """,
                    (req.staff_line_user_id.strip(),),
                )
            conn.commit()
        finally:
            conn.close()
        return BaseResponse(
            data={
                "case_no": case_no,
                "client_line_user_id": req.client_line_user_id.strip(),
                "staff_id": req.staff_id,
                "staff_line_user_id": req.staff_line_user_id.strip(),
            },
            message="已更新 LINE 身分綁定",
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/orders/{case_no}/assign-staff", response_model=BaseResponse[bool])
def assign_staff_to_order(
    req: MatchAssignRequest,
    case_no: str = Path(..., description="案件編號")
):
    """成立訂單並定案指派服務人員/月嫂"""
    try:
        success = db_service.assign_staff_to_order(case_no=case_no, staff_id=req.staff_id)
        return BaseResponse(data=success, message="成功定案指派月嫂，訂單狀態升級為訂單成立！")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
