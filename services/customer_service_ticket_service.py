"""Customer service ticket workflow for LINE users and union staff."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

import pymysql

from services.db_service import get_connection
from services.line_task_service import enqueue_line_task


CATEGORIES = {
    "service_flow": "服務流程",
    "payment_subsidy": "收費與補助",
    "service_progress": "查詢服務進度",
    "profile_update": "修改登記資料",
    "contact_union": "聯絡工會人員",
    "other": "其他問題",
}
STATUSES = {"waiting": "等待客服", "handling": "處理中", "resolved": "已完成"}
TAIPEI_TIMEZONE = ZoneInfo("Asia/Taipei")
CLIENT_PROFILE_FIELDS = {
    "name": "姓名",
    "gender": "性別",
    "phone": "行動電話",
    "city": "縣市",
    "address": "地址",
    "service_time": "服務時間",
    "due_month": "預產期月份",
    "service_start_date": "預計服務日期",
    "notes": "其他事項",
    "service_days": "希望服務天數",
    "residence_type": "居住型態",
    "delivery_type": "生產方式",
    "service_type": "服務方式",
    "baby_info": "寶寶資訊",
    "line_id": "LINE ID",
    "admin_notes": "管理者註記",
    "reject_reason": "不符合原因",
}
CLIENT_PROFILE_SELECT_COLUMNS = ", ".join(
    f"c.`{field}` AS `{field}`" for field in CLIENT_PROFILE_FIELDS
)


class CustomerServiceTicketNotFoundError(LookupError):
    pass


class CustomerServiceTicketStateError(RuntimeError):
    pass


def _as_int(value: Any) -> int:
    return int(value or 0)


def _utc_naive(value: datetime | None) -> datetime | None:
    if value is None or value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _mask_line_id(value: str | None) -> str:
    text = (value or "").strip()
    if len(text) <= 8:
        return text or "-"
    return f"{text[:4]}…{text[-4:]}"


def _serialise_client_profile(row: dict[str, Any] | None) -> dict[str, Any]:
    if not row:
        return {}
    return {
        "id": row.get("client_id"),
        "case_no": row.get("client_case_no") or row.get("case_no"),
        "fields": {
            field: row.get(field)
            for field in CLIENT_PROFILE_FIELDS
        },
        "field_labels": CLIENT_PROFILE_FIELDS,
    }


def _latest_client_context(cursor, line_user_id: str) -> dict[str, Any]:
    cursor.execute(
        f"""
        SELECT c.id AS client_id, c.name AS client_name, c.phone AS client_phone,
               c.case_no AS client_case_no,
               {CLIENT_PROFILE_SELECT_COLUMNS},
               o.case_no AS order_case_no, o.status AS order_status,
               o.start_date, o.end_date
        FROM clients c
        LEFT JOIN orders o ON o.client_id=c.id
        WHERE c.line_user_id=%s
        ORDER BY o.created_at DESC, o.case_no DESC
        LIMIT 1
        """,
        (line_user_id,),
    )
    row = cursor.fetchone() or {}
    if not row:
        return {}
    return {
        **row,
        "case_no": row.get("order_case_no") or row.get("client_case_no"),
    }


def create_or_reopen_ticket(
    cursor,
    *,
    line_user_id: str,
    category: str,
    message: str,
    source_event_id: str | None = None,
) -> dict[str, Any]:
    if category not in CATEGORIES:
        raise ValueError("不支援的客服分類")
    line_user_id = line_user_id.strip()
    if not line_user_id:
        raise ValueError("缺少 LINE 使用者")
    message = message.strip() or CATEGORIES[category]
    context = _latest_client_context(cursor, line_user_id)
    cursor.execute(
        """
        SELECT id FROM customer_service_tickets
        WHERE line_user_id=%s AND category=%s AND status IN ('waiting','handling')
        ORDER BY updated_at DESC, id DESC
        LIMIT 1
        """,
        (line_user_id, category),
    )
    existing = cursor.fetchone()
    if existing:
        ticket_id = int(existing["id"])
        cursor.execute(
            """
            UPDATE customer_service_tickets
            SET message=CONCAT(message, '\n\n', %s), updated_at=CURRENT_TIMESTAMP
            WHERE id=%s
            """,
            (message, ticket_id),
        )
        return {"id": ticket_id, "created": False, "context": context}

    cursor.execute(
        """
        INSERT INTO customer_service_tickets (
            line_user_id, client_id, case_no, category, message
        ) VALUES (%s,%s,%s,%s,%s)
        """,
        (
            line_user_id,
            context.get("client_id"),
            context.get("case_no"),
            category,
            message,
        ),
    )
    ticket_id = int(cursor.lastrowid)
    return {"id": ticket_id, "created": True, "context": context}


def get_ticket_summary() -> dict[str, int]:
    taipei_now = datetime.now(TAIPEI_TIMEZONE)
    day_start = taipei_now.replace(hour=0, minute=0, second=0, microsecond=0)
    utc_day_start = day_start.astimezone(timezone.utc).replace(tzinfo=None)
    utc_day_end = (day_start + timedelta(days=1)).astimezone(timezone.utc).replace(tzinfo=None)
    conn = get_connection()
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute(
                """
                SELECT
                    SUM(status='waiting') AS waiting,
                    SUM(status='handling') AS handling,
                    SUM(status='resolved' AND resolved_at >= %s AND resolved_at < %s) AS resolved_today,
                    SUM(created_at >= %s AND created_at < %s) AS created_today
                FROM customer_service_tickets
                """,
                (utc_day_start, utc_day_end, utc_day_start, utc_day_end),
            )
            row = cursor.fetchone() or {}
        return {
            "waiting": _as_int(row.get("waiting")),
            "handling": _as_int(row.get("handling")),
            "resolved_today": _as_int(row.get("resolved_today")),
            "created_today": _as_int(row.get("created_today")),
        }
    finally:
        conn.close()


def list_tickets(
    *,
    status: str | None = "waiting",
    category: str | None = None,
    search: str | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    page: int = 1,
    page_size: int = 25,
) -> dict[str, Any]:
    if status and status not in STATUSES:
        raise ValueError("不支援的處理狀態")
    if category and category not in CATEGORIES:
        raise ValueError("不支援的客服分類")
    clauses = ["1=1"]
    params: list[Any] = []
    if status:
        clauses.append("t.status=%s")
        params.append(status)
    if category:
        clauses.append("t.category=%s")
        params.append(category)
    if search and search.strip():
        keyword = f"%{search.strip()}%"
        clauses.append(
            "(CAST(t.id AS CHAR) LIKE %s OR t.line_user_id LIKE %s OR "
            "t.case_no LIKE %s OR c.name LIKE %s OR c.phone LIKE %s OR t.message LIKE %s)"
        )
        params.extend([keyword] * 6)
    if created_from:
        clauses.append("t.created_at >= %s")
        params.append(_utc_naive(created_from))
    if created_to:
        clauses.append("t.created_at <= %s")
        params.append(_utc_naive(created_to))
    page = max(1, page)
    page_size = max(1, min(page_size, 100))
    offset = (page - 1) * page_size
    where_sql = " AND ".join(clauses)
    order_sql = "t.created_at ASC, t.id ASC" if status in {None, "waiting", "handling"} else "t.updated_at DESC, t.id DESC"
    conn = get_connection()
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute(
                f"""
                SELECT COUNT(*) AS total
                FROM customer_service_tickets t
                LEFT JOIN clients c ON c.id=t.client_id
                WHERE {where_sql}
                """,
                params,
            )
            total = _as_int((cursor.fetchone() or {}).get("total"))
            cursor.execute(
                f"""
                SELECT t.id, t.line_user_id, t.client_id, t.case_no, t.category,
                       t.message, t.status, t.internal_note, t.last_reply,
                       t.created_at, t.updated_at, t.last_replied_at, t.resolved_at,
                       c.name AS client_name, c.phone AS client_phone,
                       o.status AS order_status, o.start_date, o.end_date,
                       a.display_name AS assigned_to_name
                FROM customer_service_tickets t
                LEFT JOIN clients c ON c.id=t.client_id
                LEFT JOIN orders o ON o.case_no=t.case_no
                LEFT JOIN admin_users a ON a.id=t.assigned_to_admin_user_id
                WHERE {where_sql}
                ORDER BY {order_sql}
                LIMIT %s OFFSET %s
                """,
                [*params, page_size, offset],
            )
            rows = list(cursor.fetchall())
        items = []
        for row in rows:
            item = dict(row)
            item["line_user_id_masked"] = _mask_line_id(item.get("line_user_id"))
            item["category_label"] = CATEGORIES.get(item.get("category"), item.get("category"))
            item["status_label"] = STATUSES.get(item.get("status"), item.get("status"))
            items.append(item)
        return {
            "items": items,
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": max(1, (total + page_size - 1) // page_size),
        }
    finally:
        conn.close()


def get_ticket(ticket_id: int) -> dict[str, Any]:
    result = list_tickets(status=None, search=str(ticket_id), page=1, page_size=20)
    for item in result["items"]:
        if int(item["id"]) == int(ticket_id):
            if item.get("client_id"):
                conn = get_connection()
                try:
                    with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                        cursor.execute(
                            f"""
                            SELECT c.id AS client_id, c.case_no AS client_case_no,
                                   {CLIENT_PROFILE_SELECT_COLUMNS}
                            FROM clients c
                            WHERE c.id=%s
                            """,
                            (item["client_id"],),
                        )
                        item["client_profile"] = _serialise_client_profile(cursor.fetchone())
                finally:
                    conn.close()
            else:
                item["client_profile"] = {}
            return item
    raise CustomerServiceTicketNotFoundError(f"找不到客服需求 #{ticket_id}")


def apply_client_profile_field_update(
    ticket_id: int,
    *,
    field: str,
    action: str,
    value: Any,
    note: str | None,
    admin_user_id: int | None,
) -> dict[str, Any]:
    if field not in CLIENT_PROFILE_FIELDS:
        raise ValueError("此欄位不開放在客服流程中修改")
    if action not in {"add", "update", "clear"}:
        raise ValueError("不支援的異動方式")

    new_value = None if action == "clear" else str(value or "").strip()
    if action in {"add", "update"} and not new_value:
        raise ValueError("請輸入要寫入的新內容")
    if field == "service_days" and new_value:
        try:
            service_days = int(new_value)
        except ValueError as exc:
            raise ValueError("希望服務天數必須是數字") from exc
        if service_days < 1:
            raise ValueError("希望服務天數必須大於 0")
        new_value = service_days
    if field == "gender" and new_value and new_value not in {"男", "女"}:
        raise ValueError("性別只能選擇男或女")
    if field in {"delivery_type"} and new_value and new_value not in {"自然產", "剖腹產"}:
        raise ValueError("生產方式只能選擇自然產或剖腹產")
    if field == "service_type" and new_value and new_value not in {"週休2日", "週休1日", "連續服務"}:
        raise ValueError("服務方式只能選擇週休2日、週休1日或連續服務")

    conn = get_connection()
    try:
        conn.begin()
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute("SELECT * FROM customer_service_tickets WHERE id=%s FOR UPDATE", (ticket_id,))
            ticket = cursor.fetchone()
            if not ticket:
                raise CustomerServiceTicketNotFoundError(f"找不到客服需求 #{ticket_id}")
            client_id = ticket.get("client_id")
            if not client_id:
                raise ValueError("此客服需求尚未綁定客戶資料，請先請客戶完成服務登記或帳號綁定")
            cursor.execute(f"SELECT `{field}` FROM clients WHERE id=%s FOR UPDATE", (client_id,))
            client = cursor.fetchone()
            if not client:
                raise ValueError("找不到已綁定的客戶資料")
            old_value = client.get(field)
            if action == "add" and old_value not in {None, ""}:
                raise ValueError("此欄位已有資料，如需變更請選擇「修改」")

            cursor.execute(f"UPDATE clients SET `{field}`=%s WHERE id=%s", (new_value, client_id))
            action_label = {"add": "新增", "update": "修改", "clear": "清空"}[action]
            field_label = CLIENT_PROFILE_FIELDS[field]
            note_lines = [
                f"[客戶資料異動] {action_label}{field_label}",
                f"異動前：{old_value if old_value not in {None, ''} else '空白'}",
                f"異動後：{new_value if new_value not in {None, ''} else '空白'}",
            ]
            if note and note.strip():
                note_lines.append(f"說明：{note.strip()}")
            change_note = "\n".join(note_lines)
            cursor.execute(
                """
                UPDATE customer_service_tickets
                SET status='handling',
                    assigned_to_admin_user_id=COALESCE(%s,assigned_to_admin_user_id),
                    internal_note=CONCAT(COALESCE(internal_note,''), CASE WHEN COALESCE(internal_note,'')='' THEN '' ELSE '\n\n' END, %s),
                    updated_at=CURRENT_TIMESTAMP
                WHERE id=%s
                """,
                (admin_user_id, change_note, ticket_id),
            )
        conn.commit()
        return get_ticket(ticket_id)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def update_ticket(
    ticket_id: int,
    *,
    status: str | None,
    internal_note: str | None,
    admin_user_id: int | None,
) -> dict[str, Any]:
    if status and status not in STATUSES:
        raise ValueError("不支援的處理狀態")
    conn = get_connection()
    try:
        conn.begin()
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute("SELECT id FROM customer_service_tickets WHERE id=%s FOR UPDATE", (ticket_id,))
            if not cursor.fetchone():
                raise CustomerServiceTicketNotFoundError(f"找不到客服需求 #{ticket_id}")
            assignments = []
            params: list[Any] = []
            if status:
                assignments.append("status=%s")
                params.append(status)
                if status == "resolved":
                    assignments.append("resolved_at=COALESCE(resolved_at,UTC_TIMESTAMP())")
                else:
                    assignments.append("resolved_at=NULL")
            if internal_note is not None:
                assignments.append("internal_note=%s")
                params.append(internal_note.strip() or None)
            if admin_user_id:
                assignments.append("assigned_to_admin_user_id=%s")
                params.append(admin_user_id)
            if assignments:
                cursor.execute(
                    f"UPDATE customer_service_tickets SET {', '.join(assignments)} WHERE id=%s",
                    [*params, ticket_id],
                )
        conn.commit()
        return get_ticket(ticket_id)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def reply_ticket(
    ticket_id: int,
    *,
    reply_text: str,
    internal_note: str | None,
    resolve: bool,
    admin_user_id: int | None,
    source_event_id: str | None = None,
) -> dict[str, Any]:
    reply_text = reply_text.strip()
    if not reply_text:
        raise ValueError("回覆內容不可為空")
    conn = get_connection()
    try:
        conn.begin()
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute("SELECT * FROM customer_service_tickets WHERE id=%s FOR UPDATE", (ticket_id,))
            ticket = cursor.fetchone()
            if not ticket:
                raise CustomerServiceTicketNotFoundError(f"找不到客服需求 #{ticket_id}")
            if ticket["status"] == "resolved" and not resolve:
                raise CustomerServiceTicketStateError("已完成的客服需求不可直接回覆，請先改為處理中")
            enqueue_line_task(
                cursor,
                to_user_id=ticket["line_user_id"],
                message_content=reply_text,
                source_event_id=source_event_id,
                idempotency_key=f"customer-service-reply:{ticket_id}:{datetime.now(timezone.utc).timestamp()}",
            )
            cursor.execute(
                """
                UPDATE customer_service_tickets
                SET status=%s, assigned_to_admin_user_id=COALESCE(%s,assigned_to_admin_user_id),
                    internal_note=%s, last_reply=%s, last_replied_at=UTC_TIMESTAMP(),
                    resolved_at=CASE WHEN %s THEN UTC_TIMESTAMP() ELSE NULL END
                WHERE id=%s
                """,
                (
                    "resolved" if resolve else "handling",
                    admin_user_id,
                    internal_note.strip() if internal_note is not None and internal_note.strip() else ticket.get("internal_note"),
                    reply_text,
                    resolve,
                    ticket_id,
                ),
            )
        conn.commit()
        return get_ticket(ticket_id)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
