"""
================================================================================
檔案名稱: services/line_review_service.py
功能說明: LINE 人工確認交易服務，安全處理月嫂身分與客戶重新綁定申請
================================================================================
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

import pymysql

from typing import Callable
from subsystems.line.ports import unconfigured_connection_factory


get_connection = unconfigured_connection_factory


class _ConnectionUnitOfWork:
    """Protocol-compatible fallback for tests and already borrowed connections."""

    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def __enter__(self):
        begin = getattr(self._connection, "begin", None)
        if callable(begin):
            begin()
        return self

    def __exit__(self, exception_type, exception, traceback):
        if exception_type is not None:
            self._connection.rollback()
        return False

    def commit(self) -> None:
        self._connection.commit()


line_unit_of_work_factory: Callable[[Any], Any] = _ConnectionUnitOfWork


REQUEST_TYPES = {"staff_verification", "client_rebind"}
REQUEST_STATUSES = {"pending", "approved", "rejected", "cancelled"}
TAIPEI_TIMEZONE = ZoneInfo("Asia/Taipei")


class LineReviewNotFoundError(LookupError):
    pass


class LineReviewStateConflictError(RuntimeError):
    def __init__(self, request_id: int, current_status: str):
        super().__init__(f"審查申請 #{request_id} 目前狀態為 {current_status}，不能重複處理")
        self.request_id = request_id
        self.current_status = current_status


class LineReviewDataConflictError(RuntimeError):
    pass


class LegacyLineReviewRetiredError(RuntimeError):
    """Legacy identity writers cannot run without the canonical application."""

    code = "legacy_line_identity_workflow_retired"


LineDeliveryEnqueuer = Callable[[object], object]


def _as_int(value: Any) -> int:
    return int(value or 0)


def _canonical_line_id(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None

def _utc_naive(value: datetime | None) -> datetime | None:
    if value is None or value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def submit_client_rebind_request_in_transaction(
    cursor,
    *,
    client_id: int,
    client_name: str,
    old_line_user_id: str,
    new_line_user_id: str,
) -> dict[str, Any]:
    raise LegacyLineReviewRetiredError(
        "legacy LINE client rebind submission requires the canonical identity application"
    )


def complete_client_binding_in_transaction(
    cursor,
    *,
    client_id: int,
    client_name: str,
    case_no: str | None,
    current_line_user_id: str | None,
    line_user_id: str,
) -> dict[str, Any]:
    # The old wrapper had no verified LIFF identity or canonical Preview→Apply
    # context, so it must never write the owner projection.  The canonical
    # identity application owns that mutation and its delivery intent.
    raise LegacyLineReviewRetiredError(
        "legacy client binding requires the canonical LIFF Preview→Apply workflow"
    )


def submit_staff_verification_in_transaction(
    cursor,
    line_user_id: str,
    *,
    source_event_id: str | None = None,
    delivery_callback: LineDeliveryEnqueuer | None = None,
) -> dict[str, Any]:
    raise LegacyLineReviewRetiredError(
        "legacy LINE staff review submission requires the canonical identity application"
    )


def submit_staff_verification(
    line_user_id: str,
    *,
    source_event_id: str | None = None,
    unit_of_work_factory: Callable[[Any], Any] | None = None,
    delivery_callback: LineDeliveryEnqueuer | None = None,
) -> dict[str, Any]:
    raise LegacyLineReviewRetiredError(
        "legacy LINE staff review submission requires the canonical identity application"
    )


def get_line_review_summary() -> dict[str, int]:
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
                    SUM(status='pending' AND request_type='staff_verification') AS staff_pending,
                    SUM(status='pending' AND request_type='client_rebind') AS rebind_pending,
                    SUM(status IN ('approved','rejected')
                        AND reviewed_at >= %s AND reviewed_at < %s) AS processed_today
                FROM line_confirmation_requests
                """,
                (utc_day_start, utc_day_end),
            )
            row = cursor.fetchone() or {}
        return {
            "pending_total": _as_int(row.get("pending_total")),
            "staff_pending": _as_int(row.get("staff_pending")),
            "rebind_pending": _as_int(row.get("rebind_pending")),
            "processed_today": _as_int(row.get("processed_today")),
        }
    finally:
        conn.close()


def list_line_reviews(
    *,
    request_type: str | None = None,
    status: str | None = "pending",
    search: str | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    page: int = 1,
    page_size: int = 25,
) -> dict[str, Any]:
    if request_type and request_type not in REQUEST_TYPES:
        raise ValueError("不支援的審查類型")
    if status and status not in REQUEST_STATUSES:
        raise ValueError("不支援的審查狀態")
    clauses = ["1=1"]
    params: list[Any] = []
    if request_type:
        clauses.append("r.request_type=%s")
        params.append(request_type)
    if status:
        clauses.append("r.status=%s")
        params.append(status)
    if search and search.strip():
        keyword = f"%{search.strip()}%"
        clauses.append(
            "(CAST(r.id AS CHAR) LIKE %s OR r.client_name LIKE %s "
            "OR r.line_user_id LIKE %s OR r.old_line_user_id LIKE %s "
            "OR r.new_line_user_id LIKE %s)"
        )
        params.extend([keyword] * 5)
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
    order_sql = "r.created_at ASC, r.id ASC" if status == "pending" else "r.created_at DESC, r.id DESC"
    conn = get_connection()
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute(
                f"SELECT COUNT(*) AS total FROM line_confirmation_requests r WHERE {where_sql}",
                params,
            )
            total = _as_int((cursor.fetchone() or {}).get("total"))
            cursor.execute(
                f"""
                SELECT r.id, r.request_type, r.status, r.client_id, r.client_name,
                       r.line_user_id, r.old_line_user_id, r.new_line_user_id,
                       r.decision_reason, r.created_at, r.reviewed_at, r.resolved_at,
                       a.display_name AS reviewer_display_name
                FROM line_confirmation_requests r
                LEFT JOIN admin_users a ON a.id=r.reviewed_by_admin_user_id
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
            item["line_user_id"] = _canonical_line_id(item.pop("line_user_id", None))
            item["old_line_user_id"] = _canonical_line_id(item.pop("old_line_user_id", None))
            item["new_line_user_id"] = _canonical_line_id(item.pop("new_line_user_id", None))
            item["display_name"] = item.get("client_name") or item["line_user_id"]
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


def get_line_review(request_id: int) -> dict[str, Any]:
    conn = get_connection()
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute(
                """
                SELECT r.*, c.case_no,
                       c.line_user_id AS current_client_line_user_id,
                       lu.role AS current_line_role,
                       lu.status AS current_line_status,
                       a.username AS reviewer_username,
                       a.display_name AS reviewer_display_name
                FROM line_confirmation_requests r
                LEFT JOIN clients c ON c.id=r.client_id
                LEFT JOIN line_users lu ON lu.line_user_id=r.line_user_id
                LEFT JOIN admin_users a ON a.id=r.reviewed_by_admin_user_id
                WHERE r.id=%s
                """,
                (request_id,),
            )
            item = cursor.fetchone()
        if not item:
            raise LineReviewNotFoundError(f"找不到審查申請 #{request_id}")
        return dict(item)
    finally:
        conn.close()


def approve_line_review(
    request_id: int,
    *,
    admin_user_id: int | None,
    reviewer_line_user_id: str | None = None,
    reason: str = "",
    unit_of_work_factory: Callable[[Any], Any] | None = None,
) -> dict[str, Any]:
    # Approval used to mutate legacy role/projection tables and enqueue a
    # provider-shaped Rich Menu task.  Canonical Preview→Apply owns both
    # binding and Rich Menu intent, so this compatibility function is retired.
    raise LegacyLineReviewRetiredError(
        "legacy LINE review approval requires the canonical identity application"
    )


def reject_line_review(
    request_id: int,
    *,
    admin_user_id: int | None,
    reviewer_line_user_id: str | None = None,
    reason: str,
    unit_of_work_factory: Callable[[Any], Any] | None = None,
    delivery_callback: LineDeliveryEnqueuer | None = None,
) -> dict[str, Any]:
    raise LegacyLineReviewRetiredError(
        "legacy LINE review rejection requires the canonical identity application"
    )
