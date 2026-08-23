"""
File: staff_monthly_calendar_query.py
Description: 查詢月嫂月份排班、正式占用與尚未開始服務的防撞緩衝。
"""

from typing import Dict, Any, List
from calendar import monthrange
from datetime import date, datetime, timedelta
from infrastructure.mysql.mysql_adapter import get_connection
from shared_kernel.clock import BusinessClock, SystemBusinessClock, TAIPEI_TIME_ZONE


def _as_date(value: Any) -> date | None:
    if isinstance(value, date):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str):
        try:
            return datetime.strptime(value, "%Y-%m-%d").date()
        except ValueError:
            return None
    return None


def _coerce_bool(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    return bool(value)


def _priority_status(status: str) -> int:
    return {"red": 3, "green": 2, "yellow": 1, "historical": 1}.get(status, 0)

def get_staff_monthly_calendar_schedule(
    staff_id: int,
    year: int,
    month: int,
    *,
    clock: BusinessClock | None = None,
) -> Dict[str, Any]:
    """
    查詢月嫂在指定年月的每日檔期排班視圖。
    關鍵約束：
    1. 輸出包含計畫要求的 days: [...] 標準陣列，內含 assignment_id、case_no、client_name、status。
    2. 同時包含相容舊版 UI 的 schedule_map。
    """
    conn = get_connection()
    days_list: List[Dict[str, Any]] = []
    grouped_rows: Dict[int, List[Dict[str, Any]]] = {}
    schedule_map: Dict[int, Dict[str, Any]] = {}
    evaluated_on = (clock or SystemBusinessClock()).now().astimezone(TAIPEI_TIME_ZONE).date()

    try:
        num_days = monthrange(year, month)[1]
        month_start = date(year, month, 1)
        month_end = date(year, month, num_days)

        with conn.cursor() as cursor:
            cursor.execute("SELECT 1 AS staff_exists FROM staff WHERE id = %s", (staff_id,))
            if cursor.fetchone() is None:
                raise ValueError(f"服務人員不存在：{staff_id}")

            cursor.execute("""
                SELECT
                    ss.work_date,
                    ss.is_work_day,
                    ss.is_double_pay,
                    ss.notes,
                    ss.id AS schedule_id,
                    csa.case_no,
                    csa.staff_id,
                    csa.id AS assignment_id,
                    c.name AS client_name,
                    o.status AS order_status,
                    s.name AS staff_name
                FROM staff_schedule ss
                JOIN case_staff_assignments csa ON ss.assignment_id = csa.id
                JOIN orders o ON csa.case_no = o.case_no
                JOIN clients c ON o.client_id = c.id
                JOIN staff s ON csa.staff_id = s.id
                WHERE csa.staff_id = %s
                  AND ss.assignment_id IS NOT NULL
                  AND (csa.status IS NULL OR csa.status <> 'cancelled')
                  AND ss.work_date BETWEEN %s AND %s
                ORDER BY ss.work_date, ss.id
            """, (staff_id, month_start, month_end))
            schedule_rows = cursor.fetchall()

            for row in schedule_rows:
                work_date = _as_date(row.get("work_date"))
                if work_date is None:
                    continue
                assignment_id = row.get("assignment_id")
                if assignment_id is None:
                    # 排除 legacy 無法確認 ownership 的排班列，避免誤映到 assignment_id
                    continue

                is_work_day = _coerce_bool(row.get("is_work_day"))
                is_double_pay = _coerce_bool(row.get("is_double_pay"))
                day = work_date.day
                item = {
                    "work_date": work_date.strftime("%Y-%m-%d"),
                    "status": "working" if is_work_day else "resting",
                    "assignment_id": assignment_id,
                    "case_no": row.get("case_no"),
                    "staff_id": row.get("staff_id", staff_id),
                    "client_name": row.get("client_name"),
                    "order_status": row.get("order_status"),
                    "staff_name": row.get("staff_name"),
                    "is_work_day": is_work_day,
                    "is_double_pay": is_double_pay,
                    "notes": row.get("notes"),
                }
                grouped_rows.setdefault(day, []).append(item)

                day_status = "red" if is_work_day else "green"
                candidate = {
                    "status": day_status,
                    "case_no": row.get("case_no"),
                    "client_name": row.get("client_name"),
                    "is_work_day": is_work_day,
                    "is_double_pay": is_double_pay,
                    "assignment_id": assignment_id,
                }
                current = schedule_map.get(day)
                if current is None or _priority_status(day_status) > _priority_status(current["status"]) or (
                    current["status"] == day_status and current.get("assignment_id") is None and assignment_id is not None
                ):
                    schedule_map[day] = candidate

            # Completed legacy cases may retain an assignment interval without
            # assignment-owned daily schedule rows. Show that immutable history
            # without claiming its days are current service ownership.
            cursor.execute(
                """
                SELECT csa.id AS assignment_id,csa.case_no,csa.staff_id,
                       csa.assigned_start_date,csa.assigned_end_date,
                       c.name AS client_name,o.status AS order_status,s.name AS staff_name
                FROM case_staff_assignments csa
                JOIN orders o ON o.case_no=csa.case_no
                JOIN clients c ON c.id=o.client_id
                JOIN staff s ON s.id=csa.staff_id
                WHERE csa.staff_id=%s AND csa.status='completed'
                  AND csa.assigned_start_date<=%s AND csa.assigned_end_date>=%s
                ORDER BY csa.assigned_start_date,csa.id
                """,
                (staff_id, month_end, month_start),
            )
            for row in cursor.fetchall():
                assigned_start = _as_date(row["assigned_start_date"])
                assigned_end = _as_date(row["assigned_end_date"])
                if assigned_start is None or assigned_end is None:
                    continue
                start = max(assigned_start, month_start)
                end = min(assigned_end, month_end)
                while start <= end:
                    day = start.day
                    if not grouped_rows.get(day):
                        item = {
                            "work_date": start.strftime("%Y-%m-%d"),
                            "status": "historical_assignment",
                            "assignment_id": row["assignment_id"],
                            "case_no": row["case_no"],
                            "staff_id": row["staff_id"],
                            "client_name": row["client_name"],
                            "order_status": row["order_status"],
                            "staff_name": row["staff_name"],
                            "is_work_day": False,
                            "is_double_pay": False,
                            "notes": "歷史正式指派區段",
                        }
                        grouped_rows[day] = [item]
                        schedule_map[day] = {
                            "status": "historical",
                            "case_no": row["case_no"],
                            "client_name": row["client_name"],
                            "is_work_day": False,
                            "is_double_pay": False,
                            "assignment_id": row["assignment_id"],
                        }
                    start += timedelta(days=1)

            cursor.execute(
                """
                SELECT
                    d.lock_date AS work_date,
                    d.staff_id,
                    d.lock_id,
                    p.id AS plan_id,
                    p.case_no,
                    c.name AS client_name,
                    o.status AS order_status,
                    s.name AS staff_name
                FROM caregiver_availability_lock_days d
                JOIN caregiver_availability_locks l ON l.id = d.lock_id
                JOIN caregiver_matching_plans p ON p.id = l.plan_id
                JOIN orders o ON o.case_no = p.case_no
                JOIN clients c ON c.id = o.client_id
                JOIN staff s ON s.id = d.staff_id
                WHERE d.staff_id = %s
                  AND d.active_marker = 1
                  AND l.status = 'active'
                  AND l.is_active = 1
                  AND d.lock_date BETWEEN %s AND %s
                ORDER BY d.lock_date, d.id
                """,
                (staff_id, month_start, month_end),
            )
            lock_rows = cursor.fetchall()
            for row in lock_rows:
                work_date = _as_date(row.get("work_date"))
                if work_date is None:
                    continue
                day = work_date.day
                item = {
                    "work_date": work_date.strftime("%Y-%m-%d"),
                    "status": "waiting_deposit_lock",
                    "assignment_id": None,
                    "case_no": row.get("case_no"),
                    "staff_id": row.get("staff_id", staff_id),
                    "client_name": row.get("client_name"),
                    "order_status": row.get("order_status"),
                    "staff_name": row.get("staff_name"),
                    "is_work_day": False,
                    "is_double_pay": False,
                    "notes": "已鎖定／待成立",
                    "lock_id": row.get("lock_id"),
                    "plan_id": row.get("plan_id"),
                }
                grouped_rows.setdefault(day, []).append(item)
                if day not in schedule_map:
                    schedule_map[day] = {
                        "status": "yellow",
                        "case_no": row.get("case_no"),
                        "client_name": row.get("client_name"),
                        "is_work_day": False,
                        "is_double_pay": False,
                        "assignment_id": None,
                        "lock_id": row.get("lock_id"),
                        "plan_id": row.get("plan_id"),
                    }

            # 補齊正式排班完工後的 7 天緩衝期
            cursor.execute(
                """
                SELECT
                    csa.id AS assignment_id,
                    csa.case_no,
                    csa.staff_id,
                    COALESCE(o.actual_start_date, csa.assigned_start_date) AS calc_start_date,
                    COALESCE(o.actual_end_date, csa.assigned_end_date) AS calc_end_date,
                    c.name AS client_name,
                    o.status AS order_status,
                    s.name AS staff_name
                FROM case_staff_assignments csa
                JOIN orders o ON csa.case_no = o.case_no
                JOIN clients c ON o.client_id = c.id
                JOIN staff s ON csa.staff_id = s.id
                WHERE csa.staff_id = %s
                  AND o.status = '訂單成立'
                  AND (csa.status IS NULL OR csa.status <> 'cancelled')
                  AND COALESCE(o.actual_end_date, csa.assigned_end_date) IS NOT NULL
                """,
                (staff_id,)
            )
            assignment_rows = cursor.fetchall()
            for row in assignment_rows:
                start_date = _as_date(row.get("calc_start_date"))
                end_date = _as_date(row.get("calc_end_date"))
                if (
                    row.get("order_status") != "訂單成立"
                    or not start_date
                    or not end_date
                    or start_date <= evaluated_on
                ):
                    continue
                for offset in range(1, 8):
                    buffer_date = end_date + timedelta(days=offset)
                    if month_start <= buffer_date <= month_end:
                        day = buffer_date.day
                        item = {
                            "work_date": buffer_date.strftime("%Y-%m-%d"),
                            "status": "waiting_deposit_lock",
                            "assignment_id": row.get("assignment_id"),
                            "case_no": row.get("case_no"),
                            "staff_id": row.get("staff_id", staff_id),
                            "client_name": row.get("client_name"),
                            "order_status": row.get("order_status"),
                            "staff_name": row.get("staff_name"),
                            "is_work_day": False,
                            "is_double_pay": False,
                            "notes": "已鎖定／待成立 (排班完工後7天緩衝)",
                            "lock_id": None,
                            "plan_id": None,
                        }
                        grouped_rows.setdefault(day, []).append(item)
                        if day not in schedule_map:
                            schedule_map[day] = {
                                "status": "yellow",
                                "case_no": row.get("case_no"),
                                "client_name": row.get("client_name"),
                                "is_work_day": False,
                                "is_double_pay": False,
                                "assignment_id": row.get("assignment_id"),
                                "lock_id": None,
                                "plan_id": None,
                            }

            for d in range(1, num_days + 1):
                cur_d = date(year, month, d)
                cur_str = cur_d.strftime("%Y-%m-%d")
                day_rows = grouped_rows.get(d, [])
                if not day_rows:
                    days_list.append({
                        "work_date": cur_str,
                        "status": "available",
                        "assignment_id": None,
                        "case_no": None,
                        "staff_id": staff_id,
                        "client_name": None,
                        "order_status": None,
                        "staff_name": None,
                        "is_work_day": False,
                        "is_double_pay": False,
                        "notes": None,
                    })
                    schedule_map[d] = {
                        "status": "white",
                        "case_no": None,
                        "client_name": None,
                        "is_work_day": False,
                        "is_double_pay": False,
                        "assignment_id": None,
                    }
                else:
                    days_list.extend(day_rows)

        return {
            "staff_id": staff_id,
            "year": year,
            "month": month,
            "days": days_list,
            "schedule_map": schedule_map,
        }
    finally:
        conn.close()
