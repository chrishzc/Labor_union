"""Customer service ticket workflow for LINE users and union staff."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
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
LIFF_CHANGE_FIELD_TO_CLIENT_FIELD = {
    "name": "name",
    "phone": "phone",
    "expected_date": "due_month",
    "service_days": "service_days",
    "address": "address",
}
PROFILE_CHANGE_STATUSES = {
    "pending": "待審核",
    "approved": "已核准",
    "partially_approved": "部分核准",
    "rejected": "已拒絕",
    "reverted": "已回復",
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
    reviewer_name: str,
    decision: str = "approve",
    rejection_reason: str | None = None,
    admin_user_id: int | None = None,
) -> dict[str, Any]:
    reviewer_name = reviewer_name.strip()
    if not reviewer_name:
        raise ValueError("請選擇審核人員")
    if field not in CLIENT_PROFILE_FIELDS:
        raise ValueError("此欄位不開放在客服流程中修改")
    if action not in {"add", "update", "clear"}:
        raise ValueError("不支援的異動方式")
    if decision not in {"approve", "reject"}:
        raise ValueError("不支援的審核結果")
    reject_reason = (rejection_reason or "").strip()
    if decision == "reject" and not reject_reason:
        raise ValueError("不同意修改時，請填寫退回原因")

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

            action_label = {"add": "新增", "update": "修改", "clear": "清空"}[action]
            field_label = CLIENT_PROFILE_FIELDS[field]
            requested_changes = [
                {
                    "field_id": field,
                    "client_field": field,
                    "label": field_label,
                    "value": new_value,
                    "source": "manual",
                    "action": action,
                }
            ]
            old_values = {field: old_value}
            applied_values = {field: new_value} if decision == "approve" else {}
            if decision == "approve":
                cursor.execute(f"UPDATE clients SET `{field}`=%s WHERE id=%s", (new_value, client_id))
            cursor.execute(
                """
                INSERT INTO client_profile_change_requests (
                    line_user_id, client_id, case_no, ticket_id, status,
                    requested_changes_json, old_values_json, applied_values_json,
                    rejection_reason, reviewed_by_name, reviewed_by_admin_user_id, reviewed_at
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,UTC_TIMESTAMP())
                """,
                (
                    ticket["line_user_id"],
                    client_id,
                    ticket.get("case_no"),
                    ticket_id,
                    "approved" if decision == "approve" else "rejected",
                    json.dumps(requested_changes, ensure_ascii=False, default=_json_default),
                    json.dumps(old_values, ensure_ascii=False, default=_json_default),
                    json.dumps(applied_values, ensure_ascii=False, default=_json_default),
                    reject_reason or None,
                    reviewer_name,
                    admin_user_id,
                ),
            )
            request_id = int(cursor.lastrowid)
            if decision == "reject":
                _enqueue_profile_change_rejection_message(
                    cursor,
                    to_user_id=ticket["line_user_id"],
                    reason=reject_reason,
                    request_id=request_id,
                    rejected_labels=[field_label],
                )
            note_lines = [
                (
                    f"[手動-資料異動] 已由 {reviewer_name} {action_label}{field_label}，異動紀錄 #{request_id}"
                    if decision == "approve"
                    else f"[手動-資料異動] 已由 {reviewer_name} 退回{field_label}異動，異動紀錄 #{request_id}"
                ),
                f"原資料：{old_value if old_value not in {None, ''} else '空白'}",
                f"申請內容：{new_value if new_value not in {None, ''} else '空白'}",
            ]
            if decision == "reject":
                note_lines.append(f"退回原因：{reject_reason}")
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


def _json_default(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _json_loads(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    if not value:
        return {}
    return json.loads(value)


def _latest_client_by_line_user(cursor, line_user_id: str) -> dict[str, Any] | None:
    cursor.execute(
        """
        SELECT id, case_no, name, phone, due_month, service_days, address
        FROM clients
        WHERE line_user_id=%s
        ORDER BY id DESC
        LIMIT 1
        """,
        (line_user_id,),
    )
    return cursor.fetchone()


def create_profile_change_request(
    *,
    line_user_id: str,
    requested_changes: list[dict[str, Any]],
) -> dict[str, Any]:
    line_user_id = line_user_id.strip()
    if not line_user_id:
        raise ValueError("缺少 LINE 使用者")
    if not requested_changes:
        raise ValueError("請至少選擇一個要修改的項目")

    normalised_changes = []
    for item in requested_changes:
        field_id = str(item.get("field_id") or "").strip()
        value = item.get("value")
        if field_id not in LIFF_CHANGE_FIELD_TO_CLIENT_FIELD:
            raise ValueError("包含不支援的修改項目")
        text_value = "" if value is None else str(value).strip()
        if not text_value:
            raise ValueError("請填寫所有已選項目的新內容")
        if field_id == "service_days":
            try:
                days = int(text_value)
            except ValueError as exc:
                raise ValueError("服務天數必須是數字") from exc
            if days < 1:
                raise ValueError("服務天數必須大於 0")
            text_value = days
        normalised_changes.append(
            {
                "field_id": field_id,
                "client_field": LIFF_CHANGE_FIELD_TO_CLIENT_FIELD[field_id],
                "label": str(item.get("label") or field_id).strip(),
                "value": text_value,
            }
        )

    conn = get_connection()
    try:
        conn.begin()
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            client = _latest_client_by_line_user(cursor, line_user_id)
            if not client:
                raise ValueError("尚未找到您綁定的服務資料，請先完成服務登記或帳號綁定")
            old_values = {
                item["client_field"]: client.get(item["client_field"])
                for item in normalised_changes
            }
            ticket_result = create_or_reopen_ticket(
                cursor,
                line_user_id=line_user_id,
                category="profile_update",
                message="用戶已送出 LIFF 修改登記資料申請",
            )
            cursor.execute(
                """
                INSERT INTO client_profile_change_requests (
                    line_user_id, client_id, case_no, ticket_id,
                    requested_changes_json, old_values_json
                ) VALUES (%s,%s,%s,%s,%s,%s)
                """,
                (
                    line_user_id,
                    client["id"],
                    client.get("case_no"),
                    ticket_result.get("id"),
                    json.dumps(normalised_changes, ensure_ascii=False, default=_json_default),
                    json.dumps(old_values, ensure_ascii=False, default=_json_default),
                ),
            )
            request_id = int(cursor.lastrowid)
            cursor.execute(
                """
                UPDATE customer_service_tickets
                SET message=CONCAT(message, '\n\n', %s), updated_at=CURRENT_TIMESTAMP
                WHERE id=%s
                """,
                (f"異動申請編號：#{request_id}，請至客服中心審核。", ticket_result.get("id")),
            )
        conn.commit()
        return {"id": request_id, "ticket_id": ticket_result.get("id"), "status": "pending"}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def list_profile_change_requests(*, status: str | None = "pending", ticket_id: int | None = None) -> list[dict[str, Any]]:
    clauses = ["1=1"]
    params: list[Any] = []
    if status:
        if status not in PROFILE_CHANGE_STATUSES:
            raise ValueError("不支援的異動申請狀態")
        clauses.append("r.status=%s")
        params.append(status)
    if ticket_id:
        clauses.append("r.ticket_id=%s")
        params.append(ticket_id)
    conn = get_connection()
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute(
                f"""
                SELECT r.*, c.name AS client_name, c.phone AS client_phone,
                       a.display_name AS reviewed_by_admin_name,
                       rv.display_name AS reverted_by_admin_name
                FROM client_profile_change_requests r
                JOIN clients c ON c.id=r.client_id
                LEFT JOIN admin_users a ON a.id=r.reviewed_by_admin_user_id
                LEFT JOIN admin_users rv ON rv.id=r.reverted_by_admin_user_id
                WHERE {' AND '.join(clauses)}
                ORDER BY r.created_at DESC, r.id DESC
                LIMIT 100
                """,
                params,
            )
            rows = list(cursor.fetchall())
        for row in rows:
            row["status_label"] = PROFILE_CHANGE_STATUSES.get(row.get("status"), row.get("status"))
            row["requested_changes"] = _json_loads(row.get("requested_changes_json"))
            row["old_values"] = _json_loads(row.get("old_values_json"))
            row["applied_values"] = _json_loads(row.get("applied_values_json"))
        return rows
    finally:
        conn.close()


def _enqueue_profile_change_rejection_message(
    cursor,
    *,
    to_user_id: str,
    reason: str,
    request_id: int,
    rejected_labels: list[str] | None = None,
) -> None:
    rejected_text = ""
    if rejected_labels:
        rejected_text = "以下修改項目未通過：\n" + "\n".join(
            f"- {label}" for label in rejected_labels
        ) + "\n\n"
    enqueue_line_task(
        cursor,
        to_user_id=to_user_id,
        message_content=(
            "【資料異動申請審核結果】\n"
            f"{rejected_text}"
            f"拒絕原因：{reason}\n\n"
            "如需回覆拒絕修改內容，請重新申請資料異動。"
        ),
        idempotency_key=f"profile-change-rejected:{request_id}",
    )


def approve_profile_change_request(
    request_id: int,
    *,
    reviewer_name: str,
    approved_field_ids: list[str] | None = None,
    rejection_reason: str | None = None,
    admin_user_id: int | None = None,
) -> dict[str, Any]:
    reviewer_name = reviewer_name.strip()
    if not reviewer_name:
        raise ValueError("請選擇審核人員")
    conn = get_connection()
    try:
        conn.begin()
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute("SELECT * FROM client_profile_change_requests WHERE id=%s FOR UPDATE", (request_id,))
            request = cursor.fetchone()
            if not request:
                raise CustomerServiceTicketNotFoundError(f"找不到異動申請 #{request_id}")
            if request["status"] != "pending":
                raise CustomerServiceTicketStateError("此異動申請已處理，不能重複核准")
            changes = _json_loads(request["requested_changes_json"])
            if not isinstance(changes, list) or not changes:
                raise ValueError("異動申請沒有可審核資料")
            approved_ids = (
                {str(field_id) for field_id in approved_field_ids}
                if approved_field_ids is not None
                else {str(change.get("field_id")) for change in changes}
            )
            change_ids = {str(change.get("field_id")) for change in changes}
            invalid_ids = approved_ids - change_ids
            if invalid_ids:
                raise ValueError("同意修改項目包含不存在的欄位")
            approved_changes = [
                change for change in changes if str(change.get("field_id")) in approved_ids
            ]
            rejected_changes = [
                change for change in changes if str(change.get("field_id")) not in approved_ids
            ]
            reject_reason = (rejection_reason or "").strip()
            if rejected_changes and not reject_reason:
                raise ValueError("有不同意修改的項目時，請填寫退回原因")
            applied_values = {}
            assignments = []
            params: list[Any] = []
            for change in approved_changes:
                client_field = change["client_field"]
                if client_field not in CLIENT_PROFILE_FIELDS:
                    raise ValueError("異動申請包含不可套用欄位")
                assignments.append(f"`{client_field}`=%s")
                params.append(change["value"])
                applied_values[client_field] = change["value"]
            if assignments:
                cursor.execute(
                    f"UPDATE clients SET {', '.join(assignments)} WHERE id=%s",
                    [*params, request["client_id"]],
                )
            if approved_changes and rejected_changes:
                next_status = "partially_approved"
            elif approved_changes:
                next_status = "approved"
            else:
                next_status = "rejected"
            cursor.execute(
                """
                UPDATE client_profile_change_requests
                SET status=%s, applied_values_json=%s, rejection_reason=%s,
                    reviewed_by_name=%s, reviewed_by_admin_user_id=%s,
                    reviewed_at=UTC_TIMESTAMP()
                WHERE id=%s
                """,
                (
                    next_status,
                    json.dumps(applied_values, ensure_ascii=False, default=_json_default),
                    reject_reason or None,
                    reviewer_name,
                    admin_user_id,
                    request_id,
                ),
            )
            if rejected_changes:
                _enqueue_profile_change_rejection_message(
                    cursor,
                    to_user_id=request["line_user_id"],
                    reason=reject_reason,
                    request_id=request_id,
                    rejected_labels=[
                        str(change.get("label") or change.get("field_id"))
                        for change in rejected_changes
                    ],
                )
            if request.get("ticket_id"):
                approved_labels = [
                    str(change.get("label") or change.get("field_id"))
                    for change in approved_changes
                ]
                rejected_labels = [
                    str(change.get("label") or change.get("field_id"))
                    for change in rejected_changes
                ]
                note_lines = [
                    f"[LINE-申請資料異動] 已由 {reviewer_name} 審核申請 #{request_id}",
                    f"同意修改：{', '.join(approved_labels) if approved_labels else '無'}",
                    f"退回項目：{', '.join(rejected_labels) if rejected_labels else '無'}",
                ]
                if rejected_labels:
                    note_lines.append(f"退回原因：{reject_reason}")
                cursor.execute(
                    """
                    UPDATE customer_service_tickets
                    SET status='handling',
                        assigned_to_admin_user_id=COALESCE(%s,assigned_to_admin_user_id),
                        internal_note=CONCAT(COALESCE(internal_note,''), CASE WHEN COALESCE(internal_note,'')='' THEN '' ELSE '\n\n' END, %s),
                        updated_at=CURRENT_TIMESTAMP
                    WHERE id=%s
                    """,
                    (
                        admin_user_id,
                        "\n".join(note_lines),
                        request["ticket_id"],
                    ),
                )
        conn.commit()
        return {"id": request_id, "status": next_status}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def reject_profile_change_request(
    request_id: int,
    *,
    reason: str,
    reviewer_name: str,
    admin_user_id: int | None,
) -> dict[str, Any]:
    reason = reason.strip()
    if not reason:
        raise ValueError("請填寫拒絕原因")
    reviewer_name = reviewer_name.strip()
    if not reviewer_name:
        raise ValueError("請選擇審核人員")
    return approve_profile_change_request(
        request_id,
        reviewer_name=reviewer_name,
        approved_field_ids=[],
        rejection_reason=reason,
        admin_user_id=admin_user_id,
    )


def revert_profile_change_request(
    request_id: int,
    *,
    reason: str,
    reviewer_name: str,
    admin_user_id: int | None,
) -> dict[str, Any]:
    reason = reason.strip()
    if not reason:
        raise ValueError("請填寫回復原因")
    reviewer_name = reviewer_name.strip()
    if not reviewer_name:
        raise ValueError("請選擇回復人員")
    conn = get_connection()
    try:
        conn.begin()
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute("SELECT * FROM client_profile_change_requests WHERE id=%s FOR UPDATE", (request_id,))
            request = cursor.fetchone()
            if not request:
                raise CustomerServiceTicketNotFoundError(f"找不到異動申請 #{request_id}")
            if request["status"] != "approved":
                raise CustomerServiceTicketStateError("只有已核准的異動申請可以回復上一版本")
            old_values = _json_loads(request["old_values_json"])
            assignments = []
            params: list[Any] = []
            for client_field, old_value in old_values.items():
                if client_field not in CLIENT_PROFILE_FIELDS:
                    raise ValueError("原始快照包含不可回復欄位")
                assignments.append(f"`{client_field}`=%s")
                params.append(old_value)
            if not assignments:
                raise ValueError("沒有可回復的欄位")
            cursor.execute(
                f"UPDATE clients SET {', '.join(assignments)} WHERE id=%s",
                [*params, request["client_id"]],
            )
            cursor.execute(
                """
                UPDATE client_profile_change_requests
                SET status='reverted', reverted_by_name=%s, reverted_by_admin_user_id=%s,
                    reverted_at=UTC_TIMESTAMP(), revert_reason=%s
                WHERE id=%s
                """,
                (reviewer_name, admin_user_id, reason, request_id),
            )
        conn.commit()
        return {"id": request_id, "status": "reverted"}
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
