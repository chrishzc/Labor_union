"""Review workflow for staff leave and substitute requests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

import pymysql

from services.db_service import get_connection
from services.line_task_service import enqueue_line_task


STATUSES = {"pending": "待審核", "approved": "已核准", "rejected": "已拒絕", "cancelled": "已取消"}
TAIPEI_TIMEZONE = ZoneInfo("Asia/Taipei")


class StaffLeaveRequestNotFoundError(LookupError):
    pass


class StaffLeaveRequestStateError(RuntimeError):
    pass


def _as_int(value: Any) -> int:
    return int(value or 0)


def _utc_naive(value: datetime | None) -> datetime | None:
    if value is None or value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def get_staff_leave_review_summary() -> dict[str, int]:
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
                    SUM(status='pending') AS pending_total,
                    SUM(status='pending' AND substitute_found=TRUE) AS substitute_pending,
                    SUM(status IN ('approved','rejected')
                        AND reviewed_at >= %s AND reviewed_at < %s) AS processed_today
                FROM staff_leave_requests
                """,
                (utc_day_start, utc_day_end),
            )
            row = cursor.fetchone() or {}
        return {
            "pending_total": _as_int(row.get("pending_total")),
            "substitute_pending": _as_int(row.get("substitute_pending")),
            "processed_today": _as_int(row.get("processed_today")),
        }
    finally:
        conn.close()


def list_staff_leave_reviews(
    *,
    status: str | None = "pending",
    search: str | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    page: int = 1,
    page_size: int = 25,
) -> dict[str, Any]:
    if status and status not in STATUSES:
        raise ValueError("不支援的請假審核狀態")
    clauses = ["1=1"]
    params: list[Any] = []
    if status:
        clauses.append("r.status=%s")
        params.append(status)
    if search and search.strip():
        keyword = f"%{search.strip()}%"
        clauses.append("(CAST(r.id AS CHAR) LIKE %s OR s.name LIKE %s OR s.phone LIKE %s)")
        params.extend([keyword, keyword, keyword])
    if created_from:
        clauses.append("r.created_at >= %s")
        params.append(_utc_naive(created_from))
    if created_to:
        clauses.append("r.created_at <= %s")
        params.append(_utc_naive(created_to))

    page = max(1, page)
    page_size = max(1, min(page_size, 100))
    offset = (page - 1) * page_size
    where_sql = " AND ".join(clauses)
    conn = get_connection()
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute(
                f"""
                SELECT COUNT(*) AS total
                FROM staff_leave_requests r
                JOIN staff s ON s.id=r.staff_id
                WHERE {where_sql}
                """,
                params,
            )
            total = _as_int((cursor.fetchone() or {}).get("total"))
            cursor.execute(
                f"""
                SELECT r.*, s.name AS staff_name, s.phone AS staff_phone,
                       a.display_name AS reviewer_display_name
                FROM staff_leave_requests r
                JOIN staff s ON s.id=r.staff_id
                LEFT JOIN admin_users a ON a.id=r.reviewed_by_admin_user_id
                WHERE {where_sql}
                ORDER BY r.created_at DESC, r.id DESC
                LIMIT %s OFFSET %s
                """,
                [*params, page_size, offset],
            )
            items = list(cursor.fetchall())
        for item in items:
            item["status_label"] = STATUSES.get(item.get("status"), item.get("status"))
        return {
            "items": items,
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": max(1, (total + page_size - 1) // page_size),
        }
    finally:
        conn.close()


def get_staff_leave_review(request_id: int) -> dict[str, Any]:
    result = list_staff_leave_reviews(status=None, search=str(request_id), page=1, page_size=20)
    for item in result["items"]:
        if int(item["id"]) == int(request_id):
            return item
    raise StaffLeaveRequestNotFoundError(f"找不到月嫂請假申請 #{request_id}")


def decide_staff_leave_review(
    request_id: int,
    *,
    decision: str,
    reason: str,
    admin_user_id: int | None,
) -> dict[str, Any]:
    if decision not in {"approve", "reject"}:
        raise ValueError("不支援的審核決定")
    reason = reason.strip()
    if decision == "reject" and not reason:
        raise ValueError("拒絕請假申請時必須填寫原因")
    next_status = "approved" if decision == "approve" else "rejected"
    conn = get_connection()
    try:
        conn.begin()
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute("SELECT * FROM staff_leave_requests WHERE id=%s FOR UPDATE", (request_id,))
            item = cursor.fetchone()
            if not item:
                raise StaffLeaveRequestNotFoundError(f"找不到月嫂請假申請 #{request_id}")
            if item["status"] != "pending":
                raise StaffLeaveRequestStateError("此請假申請已處理，不能重複審核")
            cursor.execute(
                """
                UPDATE staff_leave_requests
                SET status=%s, reviewed_by_admin_user_id=%s,
                    reviewed_at=UTC_TIMESTAMP(), review_note=%s
                WHERE id=%s
                """,
                (next_status, admin_user_id, reason or None, request_id),
            )
            content = (
                "【請假申請審核結果】\n"
                f"申請日期：{item['leave_start_date']} 至 {item['leave_end_date']}\n"
                f"審核結果：{'已核准' if decision == 'approve' else '已拒絕'}"
            )
            if reason:
                content += f"\n說明：{reason}"
            enqueue_line_task(
                cursor,
                to_user_id=item["line_user_id"],
                message_content=content,
                idempotency_key=f"staff-leave-{next_status}:{request_id}",
            )
        conn.commit()
        return {"id": request_id, "status": next_status, "message": "已完成月嫂請假審核"}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
