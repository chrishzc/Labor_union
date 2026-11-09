"""
File: historical_baseline_obligation_sync.py
Description: 自動為歷史服務完成訂單建立月嫂薪資基準應付義務，避免逐案手動調整天數。
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
import hashlib
import json
from typing import Any

from domains.payroll.payment_due_date import (
    calculate_staff_payment_due_date,
    is_full_subsidy_eligible,
)


_HISTORICAL_COMPLETED_STATUSES = (
    "歷史訂單－服務完成",
    "歷史訂單－帳務完成",
)

DEFAULT_HISTORICAL_HOURLY_RATE = 250
DEFAULT_HISTORICAL_HOURS_PER_DAY = Decimal("9.0")
DEFAULT_HISTORICAL_SERVICE_DAYS = 20


def sync_historical_staff_baseline_obligations(
    connection: Any,
    case_no: str | None = None,
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    """為歷史服務完成或帳務完成訂單建立或同步月嫂基準應付義務。

    若指定 case_no 則只同步單案；未指定時掃描全庫所有符合條件的歷史訂單。
    """
    with connection.cursor() as cursor:
        if case_no:
            cursor.execute(
                "SELECT o.case_no, o.client_id, o.staff_id, o.status, o.lifecycle_version, "
                "o.service_days, o.service_hours_per_day, o.floor_fee, o.start_date, o.end_date, "
                "o.actual_start_date, o.actual_end_date, o.staff_payment_due_date, "
                "c.identity_status "
                "FROM orders o "
                "LEFT JOIN clients c ON c.id = o.client_id "
                "WHERE o.case_no = %s AND o.status IN (%s, %s)",
                (case_no, *_HISTORICAL_COMPLETED_STATUSES),
            )
        else:
            cursor.execute(
                "SELECT o.case_no, o.client_id, o.staff_id, o.status, o.lifecycle_version, "
                "o.service_days, o.service_hours_per_day, o.floor_fee, o.start_date, o.end_date, "
                "o.actual_start_date, o.actual_end_date, o.staff_payment_due_date, "
                "c.identity_status "
                "FROM orders o "
                "LEFT JOIN clients c ON c.id = o.client_id "
                "WHERE o.status IN (%s, %s) "
                "ORDER BY o.case_no",
                _HISTORICAL_COMPLETED_STATUSES,
            )
        orders = cursor.fetchall()

    created_count = 0
    updated_count = 0
    skipped_count = 0
    details = []

    for order in orders:
        c_no = str(order["case_no"])
        status = str(order["status"])
        res = _sync_single_order(connection, order, dry_run=dry_run)
        if res["action"] == "created":
            created_count += 1
            details.append({"case_no": c_no, "action": "created", **res})
        elif res["action"] == "updated":
            updated_count += 1
            details.append({"case_no": c_no, "action": "updated", **res})
        else:
            skipped_count += 1

    return {
        "scanned_orders": len(orders),
        "created_count": created_count,
        "updated_count": updated_count,
        "skipped_count": skipped_count,
        "details": details,
    }


def _sync_single_order(
    connection: Any,
    order: dict[str, Any],
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    case_no = str(order["case_no"])
    is_settled = str(order["status"]) == "歷史訂單－帳務完成"

    with connection.cursor() as cursor:
        # 1. 查找現有有效的月嫂指派
        cursor.execute(
            "SELECT id, staff_id, hourly_rate, planned_hours, actual_hours, floor_fee_allocated "
            "FROM case_staff_assignments "
            "WHERE case_no = %s AND status NOT IN ('cancelled', 'replaced') "
            "ORDER BY assignment_sequence ASC, id ASC",
            (case_no,),
        )
        assignments = cursor.fetchall()

        # 若指派為空但訂單上有 staff_id，補建一筆 completed assignment
        staff_id = order.get("staff_id")
        if not assignments and staff_id:
            staff_id = int(staff_id)
            days = int(order.get("service_days") or DEFAULT_HISTORICAL_SERVICE_DAYS)
            hpd = Decimal(str(order.get("service_hours_per_day") or DEFAULT_HISTORICAL_HOURS_PER_DAY))
            hours = Decimal(days) * hpd
            if not dry_run:
                cursor.execute(
                    "INSERT INTO case_staff_assignments "
                    "(case_no, generation_id, staff_id, assignment_sequence, "
                    "assigned_start_date, assigned_end_date, original_assigned_start_date, original_assigned_end_date, "
                    "planned_hours, actual_hours, hourly_rate, floor_fee_allocated, status) "
                    "VALUES (%s, 1, %s, 1, %s, %s, %s, %s, %s, %s, %s, %s, 'completed')",
                    (
                        case_no, staff_id,
                        order.get("actual_start_date") or order.get("start_date"),
                        order.get("actual_end_date") or order.get("end_date"),
                        order.get("start_date"), order.get("end_date"),
                        hours, hours, DEFAULT_HISTORICAL_HOURLY_RATE,
                        order.get("floor_fee") or 0,
                    ),
                )
                assignment_id = int(cursor.lastrowid)
            else:
                assignment_id = 0
            assignments = [{
                "id": assignment_id,
                "staff_id": staff_id,
                "hourly_rate": DEFAULT_HISTORICAL_HOURLY_RATE,
                "planned_hours": hours,
                "actual_hours": hours,
                "floor_fee_allocated": order.get("floor_fee") or 0,
            }]

        if not assignments:
            return {"action": "skipped", "reason": "no_staff_assigned"}

        # 2. 計算完工日與應付款日
        completed_on = (
            order.get("actual_end_date")
            or order.get("end_date")
            or order.get("actual_start_date")
            or order.get("start_date")
            or date.today()
        )
        identity_status = str(order.get("identity_status") or "一般市民")
        is_full_subsidy = False
        try:
            is_full_subsidy = is_full_subsidy_eligible(identity_status)
        except Exception:
            pass

        due_date = order.get("staff_payment_due_date")
        if due_date is None:
            try:
                due_date = calculate_staff_payment_due_date(
                    completed_on,
                    Decimal("1"),
                    is_full_subsidy,
                )
            except Exception:
                month_idx = completed_on.month
                due_date = date(completed_on.year + month_idx // 12, month_idx % 12 + 1, 15)

            if not dry_run:
                cursor.execute(
                    "UPDATE orders SET staff_payment_due_date = %s WHERE case_no = %s",
                    (due_date, case_no),
                )

        # 3. 檢查歷史服務天數項目中是否已有計算過的金額
        cursor.execute(
            "SELECT assignment_id, staff_id, staff_obligation_amount_ntd, actual_service_days "
            "FROM historical_service_day_items "
            "WHERE event_id = ("
            "  SELECT MAX(id) FROM historical_service_day_events WHERE case_no = %s"
            ")",
            (case_no,),
        )
        saved_items = {int(r["staff_id"]): r for r in cursor.fetchall()}

        # 4. 針對每一筆 assignment 同步 staff_obligations
        created_any = False
        updated_any = False

        for a in assignments:
            a_staff_id = int(a["staff_id"])
            a_id = int(a["id"])

            if a_staff_id in saved_items and saved_items[a_staff_id].get("staff_obligation_amount_ntd"):
                amount_ntd = int(saved_items[a_staff_id]["staff_obligation_amount_ntd"])
            else:
                days = int(order.get("service_days") or DEFAULT_HISTORICAL_SERVICE_DAYS)
                hpd = Decimal(str(order.get("service_hours_per_day") or DEFAULT_HISTORICAL_HOURS_PER_DAY))
                rate = Decimal(str(a.get("hourly_rate") or DEFAULT_HISTORICAL_HOURLY_RATE))
                floor = Decimal(str(a.get("floor_fee_allocated") or order.get("floor_fee") or 0))
                hours = Decimal(days) * hpd
                amount_ntd = int(round(hours * rate)) + int(floor)

            obligation_identity = f"staff-obligation:{case_no}:{a_staff_id}"

            cursor.execute(
                "SELECT obligation_identity, amount_due_ntd, due_date, status, current_event_id "
                "FROM staff_obligations WHERE obligation_identity = %s",
                (obligation_identity,),
            )
            existing = cursor.fetchone()

            if existing:
                # 已存在義務，若到期日不同或為空則更新
                if existing.get("due_date") != due_date or (existing.get("amount_due_ntd") == 0 and not is_settled and amount_ntd > 0):
                    if not dry_run:
                        cursor.execute(
                            "UPDATE staff_obligations SET due_date = %s, "
                            "amount_due_ntd = CASE WHEN status='open' AND amount_due_ntd=0 THEN %s ELSE amount_due_ntd END "
                            "WHERE obligation_identity = %s",
                            (due_date, amount_ntd, obligation_identity),
                        )
                    updated_any = True
                continue

            if dry_run:
                created_any = True
                continue

            # 確保 payroll_case_accounts 與 staff_payable_accounts 存在
            cursor.execute("INSERT IGNORE INTO payroll_case_accounts (case_no) VALUES (%s)", (case_no,))
            cursor.execute("SELECT aggregate_version FROM payroll_case_accounts WHERE case_no = %s FOR UPDATE", (case_no,))
            payroll_ver = int(cursor.fetchone()["aggregate_version"])

            cursor.execute("INSERT IGNORE INTO staff_payable_accounts (staff_id) VALUES (%s)", (a_staff_id,))
            cursor.execute("SELECT aggregate_version FROM staff_payable_accounts WHERE staff_id = %s FOR UPDATE", (a_staff_id,))
            cursor.fetchone()

            event_key = f"historical-baseline-payable:{case_no}:{a_staff_id}"
            digest = hashlib.sha256(f"{case_no}:{a_staff_id}:{amount_ntd}".encode("utf-8")).hexdigest()
            status_val = "settled" if is_settled else "open"

            cursor.execute(
                "INSERT INTO staff_obligation_events "
                "(obligation_identity, assignment_id, case_no, staff_id, obligation_kind, "
                "direction, source_obligation_identity, event_type, before_amount_ntd, "
                "after_amount_ntd, due_date, payroll_fingerprint, expected_payroll_version, "
                "resulting_payroll_version, idempotency_key, actor, reason) "
                "VALUES (%s, %s, %s, %s, 'service_pay', 'payable_to_staff', NULL, 'established', "
                "0, %s, %s, %s, %s, %s, %s, 'system:historical-sync', '自動建立歷史完成訂單月嫂薪資基準')",
                (
                    obligation_identity, a_id, case_no, a_staff_id,
                    amount_ntd, due_date, digest, payroll_ver, payroll_ver + 1, event_key,
                ),
            )
            event_id = int(cursor.lastrowid)

            cursor.execute(
                "INSERT INTO staff_obligations "
                "(obligation_identity, assignment_id, case_no, staff_id, obligation_kind, "
                "direction, source_obligation_identity, amount_due_ntd, due_date, status, "
                "current_event_id, payroll_version, payout_history_exists) "
                "VALUES (%s, %s, %s, %s, 'service_pay', 'payable_to_staff', NULL, "
                "%s, %s, %s, %s, %s, %s) "
                "ON DUPLICATE KEY UPDATE "
                "amount_due_ntd = VALUES(amount_due_ntd), "
                "due_date = VALUES(due_date), "
                "current_event_id = VALUES(current_event_id), "
                "payroll_version = payroll_version + 1",
                (
                    obligation_identity, a_id, case_no, a_staff_id,
                    amount_ntd, due_date, status_val, event_id, payroll_ver + 1,
                    1 if is_settled else 0,
                ),
            )

            cursor.execute(
                "UPDATE payroll_case_accounts SET aggregate_version = %s WHERE case_no = %s",
                (payroll_ver + 1, case_no),
            )
            cursor.execute(
                "UPDATE staff_payable_accounts SET aggregate_version = aggregate_version + 1 WHERE staff_id = %s",
                (a_staff_id,),
            )
            created_any = True

    if created_any:
        return {"action": "created", "staff_id": a_staff_id, "amount_ntd": amount_ntd, "due_date": str(due_date)}
    if updated_any:
        return {"action": "updated", "due_date": str(due_date)}
    return {"action": "skipped", "reason": "already_synced"}
