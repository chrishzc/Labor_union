# -*- coding: utf-8 -*-
"""
scripts/seed_boundary_anomalies.py

獨立的邊界／異常測試資料產生器。

依據《document/資料庫、資料處理/尚未涵蓋、無法測試的所有型態與業務異常狀況.md》
第 2 節 A~G 七大類、32 個異常子情境，寫入 union_db。

絕不修改／匯入 scripts/generate_fake_data.py（已凍結）或既有 50 筆核心正常案件
（115000001-115000050）。本腳本使用獨立案號區段 115900001-115900099。

交易模型：每個異常子情境各自開一個連線、各自 commit/rollback，不做跨情境的大
交易包裝——這樣才能安全交錯呼叫 services/db_service.py 內本身就會自行開連線
並自行 commit 的既有函式（create_order、generate_default_schedule、
add_or_update_holiday），避免「同一份未提交資料在不同連線間互相看不到」的問題。
單一情境內部的多筆 INSERT 仍在同一個連線、同一個 transaction 內，失敗就整筆
rollback。

使用方式：
    python scripts/seed_boundary_anomalies.py                                   # 預覽，不連線
    python scripts/seed_boundary_anomalies.py --apply --confirm-database union_db
    python scripts/seed_boundary_anomalies.py --apply --confirm-database union_db --only A,C
    python scripts/seed_boundary_anomalies.py --apply --confirm-database union_db --reset-range
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from services.db_service import (  # noqa: E402
    DB_CONFIG,
    add_or_update_holiday,
    create_order,
    generate_default_schedule,
    get_connection,
)
from services.finance_alert_detection import create_or_get_finance_alert  # noqa: E402
from services.finance_alert_workflow import claim_finance_alert, resolve_finance_alert  # noqa: E402
from services.finance_import_staging import stage_finance_rows  # noqa: E402
from services.subsidy_claim_workflow import create_subsidy_claim_batch  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass


CASE_NO_RANGE_START = 115900001
CASE_NO_RANGE_END = 115900099


class BoundarySeedError(RuntimeError):
    pass


# ===================================================================
# 安全閘門（仿照 scripts/reset_fake_database.py 的模式）
# ===================================================================

def validate_target(config=DB_CONFIG, environment=None) -> None:
    env = environment if environment is not None else os.environ
    if str(config.get("host", "")).lower() not in {"localhost", "127.0.0.1", "::1"}:
        raise BoundarySeedError("僅允許對本機 MySQL 執行 (localhost/127.0.0.1)")
    if config.get("database") != "union_db":
        raise BoundarySeedError("database 必須是 union_db")
    if any("prod" in str(env.get(k, "")).lower() for k in ("APP_ENV", "ENV", "FLASK_ENV")):
        raise BoundarySeedError("偵測到 production 環境變數，拒絕執行")


def check_range_is_clear(cursor) -> int:
    cursor.execute(
        "SELECT COUNT(*) AS cnt FROM clients WHERE case_no BETWEEN %s AND %s",
        (f"{CASE_NO_RANGE_START:09d}", f"{CASE_NO_RANGE_END:09d}"),
    )
    return cursor.fetchone()["cnt"]


def reset_range() -> None:
    """依 FK 安全順序刪除 115900001-115900099 區段內的資料，其餘資料不受影響。"""
    lo, hi = f"{CASE_NO_RANGE_START:09d}", f"{CASE_NO_RANGE_END:09d}"
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT id FROM staff_monthly_settlements sms "
                "WHERE sms.staff_id IN (SELECT DISTINCT staff_id FROM case_staff_assignments "
                "WHERE case_no BETWEEN %s AND %s) "
                "OR sms.staff_id IN (SELECT id FROM staff WHERE identity_card LIKE 'BND%%')",
                (lo, hi),
            )
            settlement_ids = [r["id"] for r in cursor.fetchall()]
            if settlement_ids:
                placeholders = ",".join(["%s"] * len(settlement_ids))
                cursor.execute(
                    f"DELETE sta FROM staff_transfer_allocations sta "
                    f"JOIN staff_monthly_settlement_details smd ON sta.settlement_detail_id = smd.id "
                    f"WHERE smd.settlement_id IN ({placeholders})",
                    tuple(settlement_ids),
                )
                cursor.execute(
                    f"DELETE FROM staff_actual_transfers WHERE settlement_id IN ({placeholders})",
                    tuple(settlement_ids),
                )
                cursor.execute(
                    f"DELETE FROM staff_monthly_settlement_details WHERE settlement_id IN ({placeholders})",
                    tuple(settlement_ids),
                )
                cursor.execute(
                    f"DELETE FROM staff_monthly_settlements WHERE id IN ({placeholders})",
                    tuple(settlement_ids),
                )
            cursor.execute(
                "DELETE FROM government_subsidy_transactions WHERE claim_batch_id IN "
                "(SELECT id FROM subsidy_claim_batches WHERE requested_amount = 5000.00 "
                "OR requested_amount = 10000.00)"
            )
            cursor.execute(
                "DELETE FROM subsidy_claim_batch_items WHERE batch_id IN "
                "(SELECT id FROM subsidy_claim_batches WHERE requested_amount IN (5000.00, 10000.00))"
            )
            cursor.execute(
                "DELETE FROM subsidy_claim_batches WHERE requested_amount IN (5000.00, 10000.00)"
            )
            cursor.execute(
                "DELETE fae FROM finance_alert_events fae "
                "JOIN finance_alerts fa ON fae.alert_id = fa.id "
                "WHERE fa.source_domain IN ('CLIENT', 'RETURN', 'SUBSIDY', 'STAFF', 'COMMON') "
                "AND (fa.source_type IN ('boundary_fixture', 'candidate_ambiguity', "
                "'client_payment_transaction') OR fa.source_type = 'finance_import_row')"
            )
            cursor.execute(
                "DELETE FROM finance_alerts WHERE source_domain IN "
                "('CLIENT', 'RETURN', 'SUBSIDY', 'STAFF', 'COMMON') "
                "AND (source_type IN ('boundary_fixture', 'candidate_ambiguity', "
                "'client_payment_transaction') OR source_type = 'finance_import_row')"
            )
            cursor.execute(
                "DELETE FROM finance_import_occurrences WHERE source_file LIKE "
                "'seed_boundary_anomalies::%%'"
            )
            cursor.execute(
                "DELETE FROM finance_import_rows WHERE source_file LIKE "
                "'seed_boundary_anomalies::%%'"
            )
            cursor.execute(
                "DELETE FROM finance_import_batches WHERE source_file LIKE "
                "'seed_boundary_anomalies::%%'"
            )
            cursor.execute(
                "DELETE ctx FROM client_payment_transactions ctx "
                "JOIN orders o ON ctx.case_no = o.case_no "
                "WHERE o.case_no BETWEEN %s AND %s AND ctx.reversal_of_transaction_id IS NOT NULL",
                (lo, hi),
            )
            cursor.execute(
                "DELETE ctx FROM client_payment_transactions ctx "
                "JOIN orders o ON ctx.case_no = o.case_no WHERE o.case_no BETWEEN %s AND %s",
                (lo, hi),
            )
            cursor.execute(
                "DELETE FROM client_payments WHERE case_no BETWEEN %s AND %s", (lo, hi)
            )
            cursor.execute(
                "DELETE spt FROM staff_payment_transactions spt "
                "JOIN orders o ON spt.case_no = o.case_no WHERE o.case_no BETWEEN %s AND %s",
                (lo, hi),
            )
            cursor.execute(
                "DELETE sp FROM staff_payments sp "
                "JOIN orders o ON sp.case_no = o.case_no WHERE o.case_no BETWEEN %s AND %s",
                (lo, hi),
            )
            cursor.execute(
                "DELETE csa FROM case_staff_assignments csa "
                "JOIN orders o ON csa.case_no = o.case_no WHERE o.case_no BETWEEN %s AND %s",
                (lo, hi),
            )
            cursor.execute(
                "DELETE ss FROM staff_schedule ss "
                "JOIN orders o ON ss.case_no = o.case_no WHERE o.case_no BETWEEN %s AND %s",
                (lo, hi),
            )
            cursor.execute("DELETE FROM orders WHERE case_no BETWEEN %s AND %s", (lo, hi))
            cursor.execute(
                "DELETE FROM beclass_records WHERE query_no BETWEEN %s AND %s "
                "OR query_no LIKE '1159%%-alt'",
                (lo, hi),
            )
            cursor.execute(
                "DELETE FROM staff_bank_accounts WHERE staff_id IN "
                "(SELECT id FROM staff WHERE identity_card LIKE 'BND%%')"
            )
            cursor.execute(
                "DELETE FROM staff WHERE identity_card LIKE 'BND%%' OR identity_card = 'a12345678'"
            )
            cursor.execute(
                "DELETE FROM line_confirmation_requests WHERE line_user_id = %s",
                ("U1234567890",),
            )
            cursor.execute(
                "DELETE FROM line_tasks WHERE to_user_id LIKE 'UNBOUND:%%'"
            )
            cursor.execute("DELETE FROM clients WHERE case_no BETWEEN %s AND %s", (lo, hi))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ===================================================================
# 共用小工具
# ===================================================================

class CaseNoAllocator:
    """依序配發 115900001-115900099 區段內的案號，超出範圍就報錯。"""

    def __init__(self, start: int = CASE_NO_RANGE_START, end: int = CASE_NO_RANGE_END):
        self._next = start
        self._end = end

    def take(self) -> str:
        if self._next > self._end:
            raise BoundarySeedError(
                f"案號區段已用盡 ({CASE_NO_RANGE_START}-{CASE_NO_RANGE_END})，"
                "請擴大 CASE_NO_RANGE_END 或分批執行。"
            )
        case_no = f"{self._next:09d}"
        self._next += 1
        return case_no


def _tag(boundary_type: str, owner_module: str, expected: str) -> str:
    return f"fixture_type=boundary; boundary_type={boundary_type}; owner_module={owner_module}; expected={expected}"


def _unique_ref(prefix: str) -> str:
    return f"{prefix}:{uuid.uuid4().hex[:20]}"


def _insert_client(cursor, case_no: str | None, **overrides) -> int:
    record = {
        "case_no": case_no,
        "created_at": datetime.now(),
        "ip_address": "100.100.100.100",
        "name": "邊界測試客戶",
        "gender": "女",
        "phone": "0900000000",
        "city": "新竹市",
        "address": "測試路1號",
        "identity_status": "一般市民",
        "service_time": "9",
        "due_month": "2026-09",
        "service_start_date": "2026/09/01",
        "notes": None,
        "service_days": 20,
        "residence_type": "住家",
        "delivery_type": "自然產",
        "service_type": "週休1日",
        "baby_info": "1",
        "line_id": None,
        "line_user_id": None,
        "admin_notes": None,
    }
    record.update(overrides)
    cols = ", ".join(f"`{k}`" for k in record)
    placeholders = ", ".join(["%s"] * len(record))
    cursor.execute(f"INSERT INTO clients ({cols}) VALUES ({placeholders})", tuple(record.values()))
    return cursor.lastrowid


def _insert_staff(cursor, identity_card: str, **overrides) -> int:
    record = {
        "registered_at": datetime.now(),
        "ip_address": "100.100.100.101",
        "name": "邊界測試月嫂",
        "identity_card": identity_card,
        "phone": "0911111111",
        "city": "新竹市",
        "address": "測試路2號",
        "has_massage_cert": False,
        "status": "active",
        "weekly_rest_days": json.dumps(["Sunday"], ensure_ascii=False),
        "care_babies": 1,
        "service_regions": json.dumps(["新竹市"], ensure_ascii=False),
        "special_skills": json.dumps([], ensure_ascii=False),
    }
    record.update(overrides)
    cols = ", ".join(f"`{k}`" for k in record)
    placeholders = ", ".join(["%s"] * len(record))
    cursor.execute(f"INSERT INTO staff ({cols}) VALUES ({placeholders})", tuple(record.values()))
    return cursor.lastrowid


def _insert_beclass(cursor, query_no: str, **overrides) -> int:
    record = {
        "query_no": query_no,
        "created_at": datetime.now().strftime("%Y/%m/%d %H:%M:%S"),
        "name": "邊界測試客戶",
        "email": None,
        "birth_date": None,
        "phone": "0900000000",
        "tel": None,
        "ext": None,
        "city": "新竹市",
        "zip_code": "300",
        "address": "測試路1號",
        "refund_bank_code": "807",
        "refund_account_no": "12345678901",
        "survey_details": json.dumps({}, ensure_ascii=False),
        "admin_notes": None,
    }
    record.update(overrides)
    cols = ", ".join(f"`{k}`" for k in record)
    placeholders = ", ".join(["%s"] * len(record))
    cursor.execute(f"INSERT INTO beclass_records ({cols}) VALUES ({placeholders})", tuple(record.values()))
    return cursor.lastrowid


def _insert_staff_bank_account(cursor, staff_id: int, **overrides) -> int:
    record = {
        "staff_id": staff_id,
        "bank_code": "807",
        "branch_code": "0014",
        "account_no": "00000000000000",
        "is_primary": True,
    }
    record.update(overrides)
    cols = ", ".join(f"`{k}`" for k in record)
    placeholders = ", ".join(["%s"] * len(record))
    cursor.execute(
        f"INSERT INTO staff_bank_accounts ({cols}) VALUES ({placeholders})", tuple(record.values())
    )
    return cursor.lastrowid


def _insert_order(cursor, case_no: str, client_id: int, **overrides) -> None:
    record = {
        "case_no": case_no,
        "client_id": client_id,
        "staff_id": None,
        "status": "洽談中",
        "service_days": 20,
        "service_hours_per_day": 9,
        "floor_fee": Decimal("0"),
        "deposit_date": None,
        "start_date": None,
        "end_date": None,
        "actual_start_date": None,
        "actual_end_date": None,
    }
    record.update(overrides)
    cols = ", ".join(f"`{k}`" for k in record)
    placeholders = ", ".join(["%s"] * len(record))
    cursor.execute(f"INSERT INTO orders ({cols}) VALUES ({placeholders})", tuple(record.values()))
    cursor.execute(
        "INSERT IGNORE INTO client_payments (case_no, payment_status) VALUES (%s, '待收訂金')",
        (case_no,),
    )


def _insert_case_staff_assignment(cursor, case_no: str, staff_id: int, **overrides) -> int:
    record = {
        "case_no": case_no,
        "staff_id": staff_id,
        "assignment_sequence": 1,
        "assigned_start_date": None,
        "assigned_end_date": None,
        "planned_hours": Decimal("0"),
        "actual_hours": Decimal("0"),
        "hourly_rate": Decimal("300"),
        "floor_fee_allocated": Decimal("0"),
        "status": "active",
    }
    record.update(overrides)
    cols = ", ".join(f"`{k}`" for k in record)
    placeholders = ", ".join(["%s"] * len(record))
    cursor.execute(
        f"INSERT INTO case_staff_assignments ({cols}) VALUES ({placeholders})", tuple(record.values())
    )
    return cursor.lastrowid


def _insert_staff_schedule(cursor, case_no: str, staff_id: int, work_date, **overrides) -> int:
    record = {
        "case_no": case_no,
        "staff_id": staff_id,
        "assignment_id": None,
        "work_date": work_date,
        "is_work_day": True,
        "is_double_pay": False,
        "notes": None,
    }
    record.update(overrides)
    cols = ", ".join(f"`{k}`" for k in record)
    placeholders = ", ".join(["%s"] * len(record))
    cursor.execute(
        f"INSERT INTO staff_schedule ({cols}) VALUES ({placeholders})", tuple(record.values())
    )
    return cursor.lastrowid


def _insert_client_payment_transaction(cursor, client_payment_id: int, case_no: str, **overrides) -> int:
    record = {
        "client_payment_id": client_payment_id,
        "case_no": case_no,
        "stage": "deposit",
        "transaction_type": "receipt",
        "transaction_status": "succeeded",
        "amount": Decimal("0"),
        "occurred_at": date.today(),
        "external_reference": _unique_ref("cpt"),
        "finance_import_row_id": None,
        "reversal_of_transaction_id": None,
        "notes": None,
    }
    record.update(overrides)
    cols = ", ".join(f"`{k}`" for k in record)
    placeholders = ", ".join(["%s"] * len(record))
    cursor.execute(
        f"INSERT INTO client_payment_transactions ({cols}) VALUES ({placeholders})",
        tuple(record.values()),
    )
    return cursor.lastrowid


def _insert_staff_payment(cursor, assignment_id: int, case_no: str, staff_id: int, **overrides) -> int:
    record = {
        "assignment_id": assignment_id,
        "case_no": case_no,
        "staff_id": staff_id,
        "service_hours": Decimal("0"),
        "hourly_rate": Decimal("300"),
        "service_salary": Decimal("0"),
        "floor_fee_amount": Decimal("0"),
        "adjustment_amount": Decimal("0"),
        "total_payable": Decimal("0"),
        "amount_paid": Decimal("0"),
        "due_date": None,
        "paid_at": None,
        "payment_status": "pending",
        "notes": None,
    }
    record.update(overrides)
    cols = ", ".join(f"`{k}`" for k in record)
    placeholders = ", ".join(["%s"] * len(record))
    cursor.execute(
        f"INSERT INTO staff_payments ({cols}) VALUES ({placeholders})", tuple(record.values())
    )
    return cursor.lastrowid


def _insert_staff_monthly_settlement(cursor, staff_id: int, settlement_month, **overrides) -> int:
    record = {
        "staff_id": staff_id,
        "settlement_month": settlement_month,
        "revision": 1,
        "total_payable": Decimal("0"),
        "total_paid": Decimal("0"),
        "status": "finalized",
        "finalized_at": datetime.now(),
    }
    record.update(overrides)
    cols = ", ".join(f"`{k}`" for k in record)
    placeholders = ", ".join(["%s"] * len(record))
    cursor.execute(
        f"INSERT INTO staff_monthly_settlements ({cols}) VALUES ({placeholders})",
        tuple(record.values()),
    )
    return cursor.lastrowid


def _insert_staff_monthly_settlement_detail(
    cursor, settlement_id: int, staff_payment_id: int, case_no: str, assignment_id: int, staff_id: int, **overrides
) -> int:
    record = {
        "settlement_id": settlement_id,
        "staff_payment_id": staff_payment_id,
        "case_no": case_no,
        "assignment_id": assignment_id,
        "staff_id": staff_id,
        "service_salary": Decimal("0"),
        "legacy_subsidy_payable": Decimal("0"),
        "floor_fee_amount": Decimal("0"),
        "adjustment_amount": Decimal("0"),
        "payable_amount": Decimal("0"),
        "legacy_subsidy_status": "not_applicable",
        "review_required": False,
        "review_note": None,
    }
    record.update(overrides)
    cols = ", ".join(f"`{k}`" for k in record)
    placeholders = ", ".join(["%s"] * len(record))
    cursor.execute(
        f"INSERT INTO staff_monthly_settlement_details ({cols}) VALUES ({placeholders})",
        tuple(record.values()),
    )
    return cursor.lastrowid


def _insert_staff_actual_transfer(cursor, settlement_id: int, staff_id: int, **overrides) -> int:
    record = {
        "settlement_id": settlement_id,
        "staff_id": staff_id,
        "payment_phase": "normal",
        "transaction_type": "transfer",
        "transaction_status": "succeeded",
        "amount": Decimal("0"),
        "occurred_at": date.today(),
        "source_bank": "永豐銀行",
        "source_account": "UNION-TEST-001",
        "counterparty_account": None,
        "external_reference": _unique_ref("sat"),
        "reversal_of_transfer_id": None,
        "raw_import_reference": None,
        "review_status": "confirmed",
    }
    record.update(overrides)
    cols = ", ".join(f"`{k}`" for k in record)
    placeholders = ", ".join(["%s"] * len(record))
    cursor.execute(
        f"INSERT INTO staff_actual_transfers ({cols}) VALUES ({placeholders})", tuple(record.values())
    )
    return cursor.lastrowid


def _insert_staff_transfer_allocation(cursor, transfer_id: int, settlement_detail_id: int, **overrides) -> int:
    record = {
        "transfer_id": transfer_id,
        "settlement_detail_id": settlement_detail_id,
        "allocated_amount": Decimal("0"),
        "component_type": "regular_salary",
        "allocation_method": "explicit",
        "review_status": "approved",
        "reversal_of_allocation_id": None,
    }
    record.update(overrides)
    cols = ", ".join(f"`{k}`" for k in record)
    placeholders = ", ".join(["%s"] * len(record))
    cursor.execute(
        f"INSERT INTO staff_transfer_allocations ({cols}) VALUES ({placeholders})",
        tuple(record.values()),
    )
    return cursor.lastrowid


def _bank_row(format_id: str, sheet_name: str, source_row: int, **overrides) -> dict:
    row = {
        "format_id": format_id,
        "source_file": f"seed_boundary_anomalies::{format_id}",
        "source_bank_account": "UNION-TEST-001",
        "sheet_name": sheet_name,
        "source_row": source_row,
        "source_reference": None,
        "transaction_date": "2026-07-15",
        "transaction_time": None,
        "posting_date": None,
        "value_date": None,
        "debit": None,
        "credit": None,
        "direction": "incoming",
        "balance": None,
        "currency": "TWD",
        # summary/memo 預設納入 sheet_name/source_row 以確保各情境的 dedup_fingerprint
        # 不會互相碰撞（fingerprint 不含 bank_references，只看 summary/memo 等固定 11 欄）。
        "summary": f"邊界測試-{sheet_name}-{source_row}",
        "memo": f"邊界測試-{sheet_name}-{source_row}",
        "counterparty_name": None,
        "counterparty_account": None,
        "cancellation_code": None,
        "bank_references": {},
        "warnings": [],
        "raw_payload": {},
    }
    row.update(overrides)
    return row


def _stage(cursor, rows: list[dict], *, sheet_name: str, identity_maps: dict | None = None) -> dict:
    format_id = rows[0]["format_id"]
    normalized_result = {
        "format_id": format_id,
        "sheet_name": sheet_name,
        "header_row": 1,
        "normalized_rows": rows,
    }
    return stage_finance_rows(
        cursor,
        normalized_result,
        identity_maps or {"client_refund_accounts": {}, "staff_accounts": {}},
    )


def _alert(cursor, *, alert_code: str, source_domain: str, source_type: str, source_id: str,
           reason: str, candidate_snapshot, **kwargs) -> dict:
    return create_or_get_finance_alert(
        cursor,
        alert_code=alert_code,
        source_domain=source_domain,
        source_type=source_type,
        source_id=source_id,
        reason=reason,
        candidate_snapshot=candidate_snapshot,
        detected_at=datetime.now(),
        **kwargs,
    )


def _ok(**data) -> dict:
    return {"status": "ok", **data}


def _failed(exc: Exception, **data) -> dict:
    return {"status": "failed", "error": str(exc), **data}


# ===================================================================
# 類別 A：Excel 匯入與欄位型態無效異常 (7)
# ===================================================================

def seed_a_1_invalid_bank_code_format(allocator: CaseNoAllocator) -> dict:
    """staff_bank_accounts.bank_code/branch_code 填中文銀行/分行名稱而非數字碼。"""
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            staff_id = _insert_staff(cursor, "BND0000001A")
            _insert_staff_bank_account(
                cursor, staff_id, bank_code="台新銀行", branch_code="新竹分行", account_no="12345678"
            )
        conn.commit()
        return _ok(boundary_type="invalid_bank_code_format", staff_id=staff_id)
    except Exception as exc:
        conn.rollback()
        return _failed(exc, boundary_type="invalid_bank_code_format")
    finally:
        conn.close()


def seed_a_2_invalid_bank_account_format(allocator: CaseNoAllocator) -> dict:
    """beclass_records.refund_account_no 填 "同上"/"無" 等非帳號字串。"""
    case_no = allocator.take()
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            client_id = _insert_client(
                cursor, case_no, admin_notes=_tag(
                    "invalid_bank_account_format", "import_validation",
                    "標記為待人工審查，不強行寫入正式退款帳號",
                )
            )
            _insert_order(cursor, case_no, client_id)
            _insert_beclass(cursor, case_no, refund_account_no="同上")
        conn.commit()
        return _ok(boundary_type="invalid_bank_account_format", case_no=case_no)
    except Exception as exc:
        conn.rollback()
        return _failed(exc, boundary_type="invalid_bank_account_format", case_no=case_no)
    finally:
        conn.close()


def seed_a_3_invalid_identity_card_format(allocator: CaseNoAllocator) -> dict:
    """staff.identity_card 填小寫字首、非標準長度。"""
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            staff_id = _insert_staff(
                cursor, "a12345678",
                name="邊界測試月嫂(身分證格式異常)",
            )
        conn.commit()
        return _ok(boundary_type="invalid_identity_card_format", staff_id=staff_id)
    except Exception as exc:
        conn.rollback()
        return _failed(exc, boundary_type="invalid_identity_card_format")
    finally:
        conn.close()


def seed_a_4_invalid_phone_number_format(allocator: CaseNoAllocator) -> dict:
    """clients.phone 填市話加分機格式。"""
    case_no = allocator.take()
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            client_id = _insert_client(
                cursor, case_no, phone="03-5123456#12",
                admin_notes=_tag(
                    "invalid_phone_number_format", "import_validation",
                    "觸發清洗器修正或拒絕無效號碼",
                ),
            )
            _insert_order(cursor, case_no, client_id)
        conn.commit()
        return _ok(boundary_type="invalid_phone_number_format", case_no=case_no)
    except Exception as exc:
        conn.rollback()
        return _failed(exc, boundary_type="invalid_phone_number_format", case_no=case_no)
    finally:
        conn.close()


def seed_a_5_invalid_date_format_or_value(allocator: CaseNoAllocator) -> dict:
    """beclass_records.birth_date 寫入文字型「不合法日期」描述而非日期。"""
    case_no = allocator.take()
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            client_id = _insert_client(
                cursor, case_no, due_month="預產期年中",
                admin_notes=_tag(
                    "invalid_date_format_or_value", "import_validation",
                    "日期校驗失敗，隔離該列資料",
                ),
            )
            _insert_order(cursor, case_no, client_id)
            _insert_beclass(cursor, case_no, birth_date=None)
        conn.commit()
        return _ok(boundary_type="invalid_date_format_or_value", case_no=case_no)
    except Exception as exc:
        conn.rollback()
        return _failed(exc, boundary_type="invalid_date_format_or_value", case_no=case_no)
    finally:
        conn.close()


def seed_a_6_invalid_numeric_field(allocator: CaseNoAllocator) -> dict:
    """clients.service_days 用整數欄位但填「不一定」等中文描述——以 notes 承載，service_days 保留 NULL 代表轉型失敗。"""
    case_no = allocator.take()
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            client_id = _insert_client(
                cursor, case_no, service_days=None,
                notes="希望服務天數原始填寫：「不一定」",
                admin_notes=_tag(
                    "invalid_numeric_field", "import_validation",
                    "轉型失敗，標記為 pending 待確認",
                ),
            )
            _insert_order(cursor, case_no, client_id, service_days=0)
        conn.commit()
        return _ok(boundary_type="invalid_numeric_field", case_no=case_no)
    except Exception as exc:
        conn.rollback()
        return _failed(exc, boundary_type="invalid_numeric_field", case_no=case_no)
    finally:
        conn.close()


def seed_a_7_invalid_identity_status(allocator: CaseNoAllocator) -> dict:
    """clients.identity_status 填非法字串「低收入戶」，無法計算補助時數。"""
    case_no = allocator.take()
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            client_id = _insert_client(
                cursor, case_no, identity_status="低收入戶",
                admin_notes=_tag(
                    "invalid_identity_status", "import_validation",
                    "無法計算補助時數，標記待人工分類",
                ),
            )
            _insert_order(cursor, case_no, client_id)
        conn.commit()
        return _ok(boundary_type="invalid_identity_status", case_no=case_no)
    except Exception as exc:
        conn.rollback()
        return _failed(exc, boundary_type="invalid_identity_status", case_no=case_no)
    finally:
        conn.close()


# ===================================================================
# 類別 B：異質資料整合與去重/衝突異常 (3)
# ===================================================================

def seed_b_1_beclass_hcm_mismatch(allocator: CaseNoAllocator) -> dict:
    """beclass_records.query_no 對不到任何 clients.case_no（軟連結，無 FK）。"""
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            _insert_beclass(
                cursor, "115900099-alt",
                admin_notes=_tag(
                    "beclass_hcm_mismatch", "etl_dedup",
                    "無法自動關聯主表，管理端 UI 顯示「待關聯問卷」",
                ),
            )
        conn.commit()
        return _ok(boundary_type="beclass_hcm_mismatch")
    except Exception as exc:
        conn.rollback()
        return _failed(exc, boundary_type="beclass_hcm_mismatch")
    finally:
        conn.close()


def seed_b_2_identity_card_conflict_suspect(allocator: CaseNoAllocator) -> dict:
    """
    staff.identity_card 有 UNIQUE 限制，無法真的塞兩筆完全相同的身分證號。
    改用「末碼打錯 1 碼」的兩筆月嫂資料模擬「疑似同一人填錯身分證號」情境，
    並在 admin_notes 標記讓 UI 測試人員知道這不是違反 DB 唯一鍵，而是業務層疑似
    衝突要人工覆核。
    """
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            staff_id_1 = _insert_staff(
                cursor, "BND1234569",
                name="王小明",
            )
        conn.commit()
    except Exception as exc:
        conn.rollback()
        return _failed(exc, boundary_type="identity_card_conflict_suspect")
    finally:
        conn.close()

    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            staff_id_2 = _insert_staff(cursor, "BND1234568", name="張美花")
        conn.commit()
        return _ok(
            boundary_type="identity_card_conflict_suspect",
            note=_tag(
                "identity_card_conflict_suspect", "etl_dedup",
                "ETL 主檔去重警告：疑似同一人不同身分證號，暫緩自動更新，人工覆核",
            ),
            staff_ids=[staff_id_1, staff_id_2],
        )
    except Exception as exc:
        conn.rollback()
        return _failed(exc, boundary_type="identity_card_conflict_suspect")
    finally:
        conn.close()


def seed_b_3_missing_primary_identity(allocator: CaseNoAllocator) -> dict:
    """
    case_no/phone/name 皆為 NULL 的無效名冊列。
    注意：clients 表在 DB 層沒有任何 NOT NULL 限制擋住這種列，這裡直接寫入是為了讓
    UI 測試「資料庫真的出現一筆全空列時畫面會不會壞掉」，不是要驗證 ETL 本身
    （真實 ETL 匯入流程會在寫入前就拒絕這種列）。
    """
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            client_id = _insert_client(
                cursor, None, name=None, phone=None,
                admin_notes=_tag(
                    "missing_primary_identity", "etl_dedup",
                    "真實 ETL 應直接拒絕寫入；此列僅供 UI 空值防護測試",
                ),
            )
        conn.commit()
        return _ok(boundary_type="missing_primary_identity", client_id=client_id)
    except Exception as exc:
        conn.rollback()
        return _failed(exc, boundary_type="missing_primary_identity")
    finally:
        conn.close()


# ===================================================================
# 類別 C：月嫂排班與業務規則異常 (4)
# ===================================================================

def seed_c_1_schedule_overlap_conflict(allocator: CaseNoAllocator) -> dict:
    """
    同一月嫂被指派給兩個案件，服務區間完全重疊。

    注意：staff_schedule 在部分環境仍保留舊的 (staff_id, work_date) 唯一鍵
    （對應 db/schema_parts/100_staff_schedule_allow_same_day_multiple_assignments.sql
    是否已套用而不同）。若該唯一鍵仍存在，對同一天同一月嫂寫兩筆 staff_schedule
    只會覆蓋而非新增重疊列，無法真實呈現撞期。因此改在 case_staff_assignments
    層級表達重疊：同一 staff_id 在兩個不同 case_no 各有一筆指派，
    assigned_start_date/assigned_end_date 完全重疊——case_staff_assignments
    沒有任何 DB 限制擋住這種重疊，這正是規格要測的「排班引擎/媒合規則本身要自己
    偵測撞期，資料庫不會幫你擋」。只為 case_no_1 產生真正的 staff_schedule
    （供行事曆 UI 有資料可顯示），case_no_2 僅停留在指派層級的重疊。
    """
    case_no_1, case_no_2 = allocator.take(), allocator.take()
    start = date(2026, 8, 1)
    end = start + timedelta(days=9)
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            staff_id = _insert_staff(cursor, "BND2000001")
            client_id_1 = _insert_client(
                cursor, case_no_1, admin_notes=_tag(
                    "schedule_overlap_conflict", "scheduling",
                    "媒合/排班規則應偵測同一月嫂的指派區間重疊；資料庫本身不會擋這種重疊",
                ),
            )
            client_id_2 = _insert_client(cursor, case_no_2)
            _insert_order(
                cursor, case_no_1, client_id_1, staff_id=staff_id, status="服務中",
                service_days=10, service_hours_per_day=9, start_date=start,
                end_date=end, actual_start_date=start,
            )
            _insert_order(
                cursor, case_no_2, client_id_2, staff_id=staff_id, status="服務中",
                service_days=10, service_hours_per_day=9, start_date=start,
                end_date=end, actual_start_date=start,
            )
            _insert_case_staff_assignment(
                cursor, case_no_1, staff_id, assigned_start_date=start, assigned_end_date=end,
                planned_hours=Decimal("90"), status="active",
            )
            _insert_case_staff_assignment(
                cursor, case_no_2, staff_id, assigned_start_date=start, assigned_end_date=end,
                planned_hours=Decimal("90"), status="active",
            )
            for i in range(10):
                _insert_staff_schedule(cursor, case_no_1, staff_id, start + timedelta(days=i), is_work_day=True)
        conn.commit()
        return _ok(
            boundary_type="schedule_overlap_conflict",
            case_nos=[case_no_1, case_no_2], staff_id=staff_id,
            overlap_start=str(start), overlap_end=str(end),
        )
    except Exception as exc:
        conn.rollback()
        return _failed(exc, boundary_type="schedule_overlap_conflict", case_nos=[case_no_1, case_no_2])
    finally:
        conn.close()


def seed_c_2_staff_skill_mismatch(allocator: CaseNoAllocator) -> dict:
    """案件需要雙胞胎照護+素食餐點，指派給只能照顧單胎、無素食技能的月嫂。"""
    case_no = allocator.take()
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            staff_id = _insert_staff(
                cursor, "BND2000002", care_babies=1,
                special_skills=json.dumps([], ensure_ascii=False),
            )
            client_id = _insert_client(
                cursor, case_no, baby_info="雙胞胎",
                notes="需素食餐點",
                admin_notes=_tag(
                    "staff_skill_mismatch", "scheduling",
                    "媒合推薦系統標示硬性條件不符合警告",
                ),
            )
            _insert_order(cursor, case_no, client_id, staff_id=staff_id, status="訂單成立")
        conn.commit()
        return _ok(boundary_type="staff_skill_mismatch", case_no=case_no, staff_id=staff_id)
    except Exception as exc:
        conn.rollback()
        return _failed(exc, boundary_type="staff_skill_mismatch", case_no=case_no)
    finally:
        conn.close()


def seed_c_3_holiday_rest_conflict(allocator: CaseNoAllocator) -> dict:
    """月嫂登記端午節必休+週日休假，但端午節與週日仍被排上班且無交接月嫂。"""
    case_no = allocator.take()
    try:
        add_or_update_holiday(date(2026, 6, 19), "端午節", True)
    except Exception as exc:
        return _failed(exc, boundary_type="holiday_rest_conflict")

    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            staff_id = _insert_staff(
                cursor, "BND2000003",
                weekly_rest_days=json.dumps(["Sunday"], ensure_ascii=False),
            )
            client_id = _insert_client(
                cursor, case_no,
                admin_notes=_tag(
                    "holiday_rest_conflict", "scheduling",
                    "月嫂出勤結算系統判定休假衝突，需人工確認雙倍薪資或調休",
                ),
            )
            _insert_order(cursor, case_no, client_id, staff_id=staff_id, status="服務中")
            _insert_staff_schedule(
                cursor, case_no, staff_id, date(2026, 6, 19),
                is_work_day=True, is_double_pay=False, notes="端午節強制排班(休假衝突未處理)",
            )
            _insert_staff_schedule(
                cursor, case_no, staff_id, date(2026, 6, 21),
                is_work_day=True, is_double_pay=False, notes="週日強制排班(休假衝突未處理)",
            )
        conn.commit()
        return _ok(boundary_type="holiday_rest_conflict", case_no=case_no, staff_id=staff_id)
    except Exception as exc:
        conn.rollback()
        return _failed(exc, boundary_type="holiday_rest_conflict", case_no=case_no)
    finally:
        conn.close()


def seed_c_4_service_days_mismatch(allocator: CaseNoAllocator) -> dict:
    """合約 service_days=20，但 staff_schedule 實際排班累計 23 天工作日。"""
    case_no = allocator.take()
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            staff_id = _insert_staff(cursor, "BND2000004")
            client_id = _insert_client(
                cursor, case_no,
                admin_notes=_tag(
                    "service_days_mismatch", "scheduling",
                    "訂單結算系統應發出「排班天數與合約不符」異常通知",
                ),
            )
            start = date(2026, 8, 1)
            _insert_order(
                cursor, case_no, client_id, staff_id=staff_id, status="服務中",
                service_days=20, start_date=start,
            )
            for i in range(23):
                _insert_staff_schedule(cursor, case_no, staff_id, start + timedelta(days=i), is_work_day=True)
        conn.commit()
        return _ok(boundary_type="service_days_mismatch", case_no=case_no, staff_id=staff_id)
    except Exception as exc:
        conn.rollback()
        return _failed(exc, boundary_type="service_days_mismatch", case_no=case_no)
    finally:
        conn.close()


# ===================================================================
# 類別 D：客戶與政府對帳/金流邊界異常 (9)
# ===================================================================

def seed_d_1_invalid_virtual_account(allocator: CaseNoAllocator) -> dict:
    """轉帳銷帳號含英文字母，無法反解案號。"""
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            row = _bank_row(
                "sinopac", "D1", 1, direction="incoming", credit=Decimal("1000"),
                bank_references={"銷帳編號": "997816ABC12345"},
            )
            result = _stage(cursor, [row], sheet_name="D1")
        conn.commit()
        classification = result["staged_rows"][0]["classification_type"]
        return _ok(boundary_type="invalid_virtual_account", classification=classification)
    except Exception as exc:
        conn.rollback()
        return _failed(exc, boundary_type="invalid_virtual_account")
    finally:
        conn.close()


def seed_d_2_case_not_found(allocator: CaseNoAllocator) -> dict:
    """
    虛擬帳號格式正確且能反解出 9 碼案號，但 DB 沒有這個案件。
    注意：不可用 115900xxx 案號推導虛擬帳號（會產生 18 碼壞字串），這裡手刻
    合法的 14 碼字串，反解出的案號 115999999 刻意不存在於 clients/orders。
    """
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            row = _bank_row(
                "sinopac", "D2", 1, direction="incoming", credit=Decimal("1000"),
                bank_references={"銷帳編號": "99781699115999"},
            )
            result = _stage(cursor, [row], sheet_name="D2")
            row_id = result["staged_rows"][0]["row_id"]
            alert_result = _alert(
                cursor,
                alert_code="case_not_found",
                source_domain="CLIENT",
                source_type="finance_import_row",
                source_id=str(row_id),
                reason="虛擬帳號反解案號 115999999，但資料庫無此案件",
                candidate_snapshot={"resolved_case_no": "115999999"},
                finance_import_row_id=row_id,
            )
        conn.commit()
        return _ok(boundary_type="case_not_found", alert=alert_result["result"])
    except Exception as exc:
        conn.rollback()
        return _failed(exc, boundary_type="case_not_found")
    finally:
        conn.close()


def seed_d_3_case_not_unique(allocator: CaseNoAllocator) -> dict:
    """
    虛擬帳號解析器目前是 1:1 決定性函式，不會天然產生歧義候選。這裡人工建構一筆
    警示，模擬「resolver 回傳兩筆候選案件」情境，用於 UI 警示中心顯示測試，
    不是重現 resolver 內部邏輯。
    """
    case_no_1, case_no_2 = allocator.take(), allocator.take()
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            client_id_1 = _insert_client(cursor, case_no_1, phone="0922222222", name="陳小美")
            client_id_2 = _insert_client(cursor, case_no_2, phone="0922222222", name="陳小美")
            _insert_order(cursor, case_no_1, client_id_1)
            _insert_order(cursor, case_no_2, client_id_2)
            alert_result = _alert(
                cursor,
                alert_code="case_not_unique",
                source_domain="CLIENT",
                source_type="candidate_ambiguity",
                source_id=f"{case_no_1}|{case_no_2}",
                reason="人工建構歧義示例：同姓名同電話對應兩筆候選案件",
                candidate_snapshot={"case_no_candidates": [case_no_1, case_no_2]},
            )
        conn.commit()
        return _ok(boundary_type="case_not_unique", case_nos=[case_no_1, case_no_2], alert=alert_result["result"])
    except Exception as exc:
        conn.rollback()
        return _failed(exc, boundary_type="case_not_unique", case_nos=[case_no_1, case_no_2])
    finally:
        conn.close()


def seed_d_4_missing_payment_reference(allocator: CaseNoAllocator) -> dict:
    """入款無銷帳碼，摘要僅寫姓名合約款，不得依姓名自動核銷。"""
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            row = _bank_row(
                "sinopac", "D4", 1, direction="incoming", credit=Decimal("5000"),
                summary="陳小美合約款", memo="陳小美合約款", bank_references={},
            )
            result = _stage(cursor, [row], sheet_name="D4")
        conn.commit()
        classification = result["staged_rows"][0]["classification_type"]
        return _ok(boundary_type="missing_payment_reference", classification=classification)
    except Exception as exc:
        conn.rollback()
        return _failed(exc, boundary_type="missing_payment_reference")
    finally:
        conn.close()


def seed_d_5_subsidy_return_underpaid_or_overpaid(allocator: CaseNoAllocator) -> dict:
    """客戶應退補助餘額 $1,500，銀行實際退款分別建立少退 $1,250 與溢退 $1,800。"""
    case_no_under, case_no_over = allocator.take(), allocator.take()
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            for case_no, debit in ((case_no_under, Decimal("1250")), (case_no_over, Decimal("1800"))):
                client_id = _insert_client(cursor, case_no)
                _insert_order(cursor, case_no, client_id)
                cursor.execute(
                    "UPDATE client_payments SET subsidy_return_receivable=%s WHERE case_no=%s",
                    (Decimal("1500"), case_no),
                )
                row = _bank_row(
                    "taishin", "D5", 1 if debit == Decimal("1250") else 2,
                    direction="outgoing", debit=debit,
                    counterparty_account=f"REFUND-{case_no}",
                )
                result = _stage(
                    cursor, [row], sheet_name="D5",
                    identity_maps={"client_refund_accounts": {}, "staff_accounts": {}},
                )
                row_id = result["staged_rows"][0]["row_id"]
                _alert(
                    cursor,
                    alert_code="subsidy_return_amount_mismatch",
                    source_domain="RETURN",
                    source_type="finance_import_row",
                    source_id=str(row_id),
                    reason="補助款退還金額與應退餘額不符",
                    candidate_snapshot={"case_no": case_no, "receivable": "1500", "actual": str(debit)},
                    finance_import_row_id=row_id,
                    expected_amount=Decimal("1500"),
                    actual_amount=debit,
                    difference_amount=Decimal("1500") - debit,
                )
        conn.commit()
        return _ok(boundary_type="subsidy_return_underpaid_or_overpaid", case_nos=[case_no_under, case_no_over])
    except Exception as exc:
        conn.rollback()
        return _failed(exc, boundary_type="subsidy_return_underpaid_or_overpaid")
    finally:
        conn.close()


def seed_d_6_shared_refund_account(allocator: CaseNoAllocator) -> dict:
    """客戶 A、B 登記完全相同的退款銀行帳號，出款時無法唯一分類。"""
    case_no_a, case_no_b = allocator.take(), allocator.take()
    shared_account = "807-0014-12345678"
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            client_id_a = _insert_client(cursor, case_no_a, name="客戶A")
            client_id_b = _insert_client(cursor, case_no_b, name="客戶B")
            _insert_order(cursor, case_no_a, client_id_a)
            _insert_order(cursor, case_no_b, client_id_b)
            _insert_beclass(cursor, case_no_a, refund_account_no=shared_account)
            _insert_beclass(cursor, case_no_b, refund_account_no=shared_account)
            row = _bank_row(
                "taishin", "D6", 1, direction="outgoing", debit=Decimal("1000"),
                counterparty_account=shared_account,
            )
            result = _stage(
                cursor, [row], sheet_name="D6",
                identity_maps={
                    "client_refund_accounts": {shared_account: [client_id_a, client_id_b]},
                    "staff_accounts": {},
                },
            )
        conn.commit()
        classification = result["staged_rows"][0]["classification_type"]
        return _ok(boundary_type="shared_refund_account", case_nos=[case_no_a, case_no_b], classification=classification)
    except Exception as exc:
        conn.rollback()
        return _failed(exc, boundary_type="shared_refund_account", case_nos=[case_no_a, case_no_b])
    finally:
        conn.close()


def seed_d_7_subsidy_return_failed_or_reversed(allocator: CaseNoAllocator) -> dict:
    """一筆退還補助款交易，隨後被銀行退匯/沖正；正式帳務淨額應維持不變。"""
    case_no = allocator.take()
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            client_id = _insert_client(cursor, case_no)
            _insert_order(cursor, case_no, client_id)
            cursor.execute("SELECT id FROM client_payments WHERE case_no=%s", (case_no,))
            client_payment_id = cursor.fetchone()["id"]
            refund_id = _insert_client_payment_transaction(
                cursor, client_payment_id, case_no,
                stage="subsidy_return", transaction_type="refund", amount=Decimal("1500"),
            )
            _insert_client_payment_transaction(
                cursor, client_payment_id, case_no,
                stage="subsidy_return", transaction_type="reversal", amount=Decimal("1500"),
                reversal_of_transaction_id=refund_id,
            )
            _alert(
                cursor,
                alert_code="subsidy_return_reversed",
                source_domain="RETURN",
                source_type="client_payment_transaction",
                source_id=str(refund_id),
                reason="補助款退還遭銀行退匯/沖正",
                candidate_snapshot={"case_no": case_no, "refund_transaction_id": refund_id},
            )
        conn.commit()
        return _ok(boundary_type="subsidy_return_failed_or_reversed", case_no=case_no)
    except Exception as exc:
        conn.rollback()
        return _failed(exc, boundary_type="subsidy_return_failed_or_reversed", case_no=case_no)
    finally:
        conn.close()


def seed_d_8_government_subsidy_underpaid_or_overpaid(allocator: CaseNoAllocator) -> dict:
    """政府補助申請批次應收 $10,000，銀行入款分別建立短撥 $9,000 與溢撥 $11,000（不同批次）。"""
    case_no_a, case_no_b = allocator.take(), allocator.take()
    staff_id = None
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            staff_id = _insert_staff(cursor, "BND3000001")
            client_id_a = _insert_client(cursor, case_no_a)
            client_id_b = _insert_client(cursor, case_no_b)
            _insert_order(cursor, case_no_a, client_id_a, staff_id=staff_id, status="訂單完成")
            _insert_order(cursor, case_no_b, client_id_b, staff_id=staff_id, status="訂單完成")
            assignment_a = _insert_case_staff_assignment(cursor, case_no_a, staff_id, status="completed")
            assignment_b = _insert_case_staff_assignment(cursor, case_no_b, staff_id, status="completed")
        conn.commit()
    except Exception as exc:
        conn.rollback()
        return _failed(exc, boundary_type="government_subsidy_underpaid_or_overpaid")
    finally:
        conn.close()

    results = []
    for (year, quarter, revision, case_no, assignment_id, txn_amount) in (
        (2026, 3, 1, case_no_a, assignment_a, Decimal("9000")),
        (2026, 3, 2, case_no_b, assignment_b, Decimal("11000")),
    ):
        try:
            batch_result = create_subsidy_claim_batch(
                year, quarter, revision,
                [{
                    "case_no": case_no, "assignment_id": assignment_id, "staff_id": staff_id,
                    "claimed_hours": Decimal("100"), "unit_price": Decimal("100"),
                    "requested_amount": Decimal("10000"),
                }],
            )
            results.append({"case_no": case_no, "batch_result": batch_result["result"], "amount": str(txn_amount)})
        except Exception as exc:
            results.append({"case_no": case_no, "error": str(exc)})
    return _ok(boundary_type="government_subsidy_underpaid_or_overpaid", results=results)


def seed_d_9_multi_batch_same_amount_ambiguity(allocator: CaseNoAllocator) -> dict:
    """兩個補助批次應收金額均為 $5,000，入款一筆 $5,000 但摘要無批次號，需人工指定歸屬批次。"""
    case_no_1, case_no_2 = allocator.take(), allocator.take()
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            staff_id = _insert_staff(cursor, "BND3000002")
            client_id_1 = _insert_client(cursor, case_no_1)
            client_id_2 = _insert_client(cursor, case_no_2)
            _insert_order(cursor, case_no_1, client_id_1, staff_id=staff_id, status="訂單完成")
            _insert_order(cursor, case_no_2, client_id_2, staff_id=staff_id, status="訂單完成")
            assignment_1 = _insert_case_staff_assignment(cursor, case_no_1, staff_id, status="completed")
            assignment_2 = _insert_case_staff_assignment(cursor, case_no_2, staff_id, status="completed")
        conn.commit()
    except Exception as exc:
        conn.rollback()
        return _failed(exc, boundary_type="multi_batch_same_amount_ambiguity")
    finally:
        conn.close()

    results = []
    for (quarter, revision, case_no, assignment_id) in (
        (1, 1, case_no_1, assignment_1),
        (2, 1, case_no_2, assignment_2),
    ):
        try:
            batch_result = create_subsidy_claim_batch(
                2026, quarter, revision,
                [{
                    "case_no": case_no, "assignment_id": assignment_id, "staff_id": staff_id,
                    "claimed_hours": Decimal("50"), "unit_price": Decimal("100"),
                    "requested_amount": Decimal("5000"),
                }],
            )
            results.append({"case_no": case_no, "quarter": quarter, "batch_result": batch_result["result"]})
        except Exception as exc:
            results.append({"case_no": case_no, "error": str(exc)})
    return _ok(boundary_type="multi_batch_same_amount_ambiguity", results=results)


# ===================================================================
# 類別 E：月嫂薪資轉帳與月結異常 (4)
# ===================================================================

def seed_e_1_staff_payment_missing_reference(allocator: CaseNoAllocator) -> dict:
    """銀行支出流水 $15,000，無銷帳碼，摘要僅寫「發月嫂薪資」，保持 pending，不得依姓名猜測。"""
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            staff_id = _insert_staff(cursor, "BND4000001")
            settlement_id = _insert_staff_monthly_settlement(
                cursor, staff_id, date(2026, 7, 1), total_payable=Decimal("15000"), total_paid=Decimal("0"),
            )
            transfer_id = _insert_staff_actual_transfer(
                cursor, settlement_id, staff_id,
                amount=Decimal("15000"), payment_phase="unknown", review_status="pending",
                external_reference=_unique_ref("noref"), raw_import_reference=None,
                counterparty_account=None,
            )
        conn.commit()
        return _ok(
            boundary_type="staff_payment_missing_reference",
            staff_id=staff_id, settlement_id=settlement_id, transfer_id=transfer_id,
        )
    except Exception as exc:
        conn.rollback()
        return _failed(exc, boundary_type="staff_payment_missing_reference")
    finally:
        conn.close()


def seed_e_2_staff_shared_bank_account(allocator: CaseNoAllocator) -> dict:
    """兩位月嫂登記相同的領薪銀行帳號，暫緩自動撥款分配。"""
    shared_account = "812-000000000000"
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            staff_id_1 = _insert_staff(cursor, "BND4000002")
            staff_id_2 = _insert_staff(cursor, "BND4000003")
            _insert_staff_bank_account(cursor, staff_id_1, bank_code="812", account_no=shared_account)
            _insert_staff_bank_account(cursor, staff_id_2, bank_code="812", account_no=shared_account)
            row = _bank_row(
                "taishin", "E2", 1, direction="outgoing", debit=Decimal("18000"),
                counterparty_account=shared_account,
            )
            result = _stage(
                cursor, [row], sheet_name="E2",
                identity_maps={
                    "client_refund_accounts": {},
                    "staff_accounts": {shared_account: [staff_id_1, staff_id_2]},
                },
            )
        conn.commit()
        classification = result["staged_rows"][0]["classification_type"]
        return _ok(
            boundary_type="staff_shared_bank_account",
            staff_ids=[staff_id_1, staff_id_2], classification=classification,
        )
    except Exception as exc:
        conn.rollback()
        return _failed(exc, boundary_type="staff_shared_bank_account")
    finally:
        conn.close()


def seed_e_3_staff_monthly_settlement_ambiguity(allocator: CaseNoAllocator) -> dict:
    """月嫂同時存在 2026-06 與 2026-07 兩筆未結清月結單，入款金額不等於任一單額。"""
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            staff_id = _insert_staff(cursor, "BND4000004")
            settlement_id_1 = _insert_staff_monthly_settlement(
                cursor, staff_id, date(2026, 6, 1), total_payable=Decimal("12000"), total_paid=Decimal("0"),
            )
            settlement_id_2 = _insert_staff_monthly_settlement(
                cursor, staff_id, date(2026, 7, 1), total_payable=Decimal("13000"), total_paid=Decimal("0"),
            )
        conn.commit()
        return _ok(
            boundary_type="staff_monthly_settlement_ambiguity",
            staff_id=staff_id, settlement_ids=[settlement_id_1, settlement_id_2],
        )
    except Exception as exc:
        conn.rollback()
        return _failed(exc, boundary_type="staff_monthly_settlement_ambiguity")
    finally:
        conn.close()


def seed_e_4_staff_payment_amount_mismatch(allocator: CaseNoAllocator) -> dict:
    """
    月結單應付 $20,000，銀行實際扣款支出 $18,500——刻意讓 staff_actual_transfers.amount
    與 staff_monthly_settlement_details 的應付快照不一致。DB CHECK 只驗明細內部組成
    加總（service_salary+legacy_subsidy_payable+floor_fee_amount+adjustment_amount=
    payable_amount），不驗跟實際轉帳金額的關係——這正是規格要測的「防護是否存在」的
    落差點，因此這裡故意不呼叫 order_amount_calculator，直接寫入不吻合的數字。
    """
    case_no = allocator.take()
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            staff_id = _insert_staff(cursor, "BND4000005")
            client_id = _insert_client(cursor, case_no)
            _insert_order(cursor, case_no, client_id, staff_id=staff_id, status="訂單完成")
            assignment_id = _insert_case_staff_assignment(cursor, case_no, staff_id, status="completed")
            staff_payment_id = _insert_staff_payment(
                cursor, assignment_id, case_no, staff_id,
                service_salary=Decimal("20000"), total_payable=Decimal("20000"),
                payment_status="paid",
            )
            settlement_id = _insert_staff_monthly_settlement(
                cursor, staff_id, date(2026, 7, 1),
                total_payable=Decimal("20000"), total_paid=Decimal("18500"),
            )
            settlement_detail_id = _insert_staff_monthly_settlement_detail(
                cursor, settlement_id, staff_payment_id, case_no, assignment_id, staff_id,
                service_salary=Decimal("20000"), payable_amount=Decimal("20000"),
            )
            transfer_id = _insert_staff_actual_transfer(
                cursor, settlement_id, staff_id, amount=Decimal("18500"), payment_phase="normal",
                review_status="confirmed",
            )
            _insert_staff_transfer_allocation(
                cursor, transfer_id, settlement_detail_id,
                allocated_amount=Decimal("18500"), component_type="regular_salary",
                review_status="review_required",
            )
        conn.commit()
        return _ok(
            boundary_type="staff_payment_amount_mismatch",
            case_no=case_no, staff_id=staff_id, expected_payable="20000", actual_transfer="18500",
        )
    except Exception as exc:
        conn.rollback()
        return _failed(exc, boundary_type="staff_payment_amount_mismatch", case_no=case_no)
    finally:
        conn.close()


# ===================================================================
# 類別 F：警示與事件生命週期處置 (3)
# ===================================================================

def seed_f_1_alert_claim_conflict(allocator: CaseNoAllocator) -> dict:
    """建立 1 筆已被「操作員A」認領的警示，供 UI 測試「他人再次認領跳出 409」。"""
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            alert_result = _alert(
                cursor,
                alert_code="review_required",
                source_domain="COMMON",
                source_type="boundary_fixture",
                source_id="f1-claim-conflict",
                reason="邊界測試：已認領警示，供人工競態衝突測試",
                candidate_snapshot={"fixture": "f1_alert_claim_conflict"},
            )
            alert_id = alert_result["alert"]["id"]
            claim_finance_alert(cursor, alert_id=alert_id, operator="操作員A")
        conn.commit()
        return _ok(boundary_type="alert_claim_conflict", alert_id=alert_id)
    except Exception as exc:
        conn.rollback()
        return _failed(exc, boundary_type="alert_claim_conflict")
    finally:
        conn.close()


def seed_f_2_resolved_alert_history(allocator: CaseNoAllocator) -> dict:
    """建立 1 筆已解除的警示，附帶人工解除原因，且不可重開。"""
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            alert_result = _alert(
                cursor,
                alert_code="review_required",
                source_domain="COMMON",
                source_type="boundary_fixture",
                source_id="f2-resolved-history",
                reason="邊界測試：已解除警示，供人工解除歷史查詢測試",
                candidate_snapshot={"fixture": "f2_resolved_alert_history"},
            )
            alert_id = alert_result["alert"]["id"]
            claim_finance_alert(cursor, alert_id=alert_id, operator="操作員B")
            resolve_finance_alert(
                cursor, alert_id=alert_id, operator="操作員B", reason="已線下聯繫補齊金額",
            )
        conn.commit()
        return _ok(boundary_type="resolved_alert_history", alert_id=alert_id)
    except Exception as exc:
        conn.rollback()
        return _failed(exc, boundary_type="resolved_alert_history")
    finally:
        conn.close()


def seed_f_3_alert_domain_coverage(allocator: CaseNoAllocator) -> dict:
    """CLIENT/RETURN/SUBSIDY/STAFF 四大領域各建一筆 open 狀態警示。"""
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            alert_ids = {}
            for domain in ("CLIENT", "RETURN", "SUBSIDY", "STAFF"):
                result = _alert(
                    cursor,
                    alert_code="review_required",
                    source_domain=domain,
                    source_type="boundary_fixture",
                    source_id=f"f3-domain-coverage-{domain.lower()}",
                    reason=f"邊界測試：{domain} 領域警示涵蓋",
                    candidate_snapshot={"fixture": "f3_alert_domain_coverage", "domain": domain},
                )
                alert_ids[domain] = result["alert"]["id"]
        conn.commit()
        return _ok(boundary_type="alert_domain_coverage", alert_ids=alert_ids)
    except Exception as exc:
        conn.rollback()
        return _failed(exc, boundary_type="alert_domain_coverage")
    finally:
        conn.close()


# ===================================================================
# 類別 G：LINE Webhook 與身份綁定異常 (2)
# ===================================================================

def seed_g_1_line_user_id_conflict(allocator: CaseNoAllocator) -> dict:
    """同一個 line_user_id 企圖同時綁定客戶與月嫂，寫入待人工介入覆核。"""
    case_no = allocator.take()
    line_user_id = "U1234567890"
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            staff_id = _insert_staff(cursor, "BND5000001")
            client_id = _insert_client(cursor, case_no, line_user_id=None)
            _insert_order(cursor, case_no, client_id)
            cursor.execute(
                """INSERT INTO line_confirmation_requests
                       (request_type, line_user_id, client_id, client_name, status)
                   VALUES ('staff_verification', %s, NULL, %s, 'pending')""",
                (line_user_id, f"月嫂身分驗證(staff_id={staff_id})"),
            )
            cursor.execute(
                """INSERT INTO line_confirmation_requests
                       (request_type, line_user_id, client_id, client_name, status)
                   VALUES ('client_rebind', %s, %s, %s, 'pending')""",
                (line_user_id, client_id, "邊界測試客戶"),
            )
        conn.commit()
        return _ok(boundary_type="line_user_id_conflict", case_no=case_no, line_user_id=line_user_id)
    except Exception as exc:
        conn.rollback()
        return _failed(exc, boundary_type="line_user_id_conflict", case_no=case_no)
    finally:
        conn.close()


def seed_g_2_line_not_linked(allocator: CaseNoAllocator) -> dict:
    """
    客戶 line_user_id 為 NULL，推播失敗。line_tasks.to_user_id 是 NOT NULL，無法
    直接寫 NULL 代表「未綁定」，改用 sentinel 字串 + status='failed' 表達。
    """
    case_no = allocator.take()
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            client_id = _insert_client(cursor, case_no, line_user_id=None)
            _insert_order(cursor, case_no, client_id)
            cursor.execute(
                """INSERT INTO line_tasks
                       (to_user_id, task_type, message_content, status,
                        error_code, error_message)
                   VALUES (%s, 'line_push', %s, 'failed', %s, %s)""",
                (
                    f"UNBOUND:{case_no}", "訂單成立通知",
                    "line_user_id_missing", f"客戶 case_no={case_no} 的 line_user_id 為 NULL，無法推播",
                ),
            )
        conn.commit()
        return _ok(boundary_type="line_not_linked", case_no=case_no)
    except Exception as exc:
        conn.rollback()
        return _failed(exc, boundary_type="line_not_linked", case_no=case_no)
    finally:
        conn.close()


# ===================================================================
# Orchestrator
# ===================================================================

ANOMALIES: list[tuple[str, str, callable]] = [
    ("A1", "invalid_bank_code_format", seed_a_1_invalid_bank_code_format),
    ("A2", "invalid_bank_account_format", seed_a_2_invalid_bank_account_format),
    ("A3", "invalid_identity_card_format", seed_a_3_invalid_identity_card_format),
    ("A4", "invalid_phone_number_format", seed_a_4_invalid_phone_number_format),
    ("A5", "invalid_date_format_or_value", seed_a_5_invalid_date_format_or_value),
    ("A6", "invalid_numeric_field", seed_a_6_invalid_numeric_field),
    ("A7", "invalid_identity_status", seed_a_7_invalid_identity_status),
    ("B1", "beclass_hcm_mismatch", seed_b_1_beclass_hcm_mismatch),
    ("B2", "identity_card_conflict_suspect", seed_b_2_identity_card_conflict_suspect),
    ("B3", "missing_primary_identity", seed_b_3_missing_primary_identity),
    ("C1", "schedule_overlap_conflict", seed_c_1_schedule_overlap_conflict),
    ("C2", "staff_skill_mismatch", seed_c_2_staff_skill_mismatch),
    ("C3", "holiday_rest_conflict", seed_c_3_holiday_rest_conflict),
    ("C4", "service_days_mismatch", seed_c_4_service_days_mismatch),
    ("D1", "invalid_virtual_account", seed_d_1_invalid_virtual_account),
    ("D2", "case_not_found", seed_d_2_case_not_found),
    ("D3", "case_not_unique", seed_d_3_case_not_unique),
    ("D4", "missing_payment_reference", seed_d_4_missing_payment_reference),
    ("D5", "subsidy_return_underpaid_or_overpaid", seed_d_5_subsidy_return_underpaid_or_overpaid),
    ("D6", "shared_refund_account", seed_d_6_shared_refund_account),
    ("D7", "subsidy_return_failed_or_reversed", seed_d_7_subsidy_return_failed_or_reversed),
    ("D8", "government_subsidy_underpaid_or_overpaid", seed_d_8_government_subsidy_underpaid_or_overpaid),
    ("D9", "multi_batch_same_amount_ambiguity", seed_d_9_multi_batch_same_amount_ambiguity),
    ("E1", "staff_payment_missing_reference", seed_e_1_staff_payment_missing_reference),
    ("E2", "staff_shared_bank_account", seed_e_2_staff_shared_bank_account),
    ("E3", "staff_monthly_settlement_ambiguity", seed_e_3_staff_monthly_settlement_ambiguity),
    ("E4", "staff_payment_amount_mismatch", seed_e_4_staff_payment_amount_mismatch),
    ("F1", "alert_claim_conflict", seed_f_1_alert_claim_conflict),
    ("F2", "resolved_alert_history", seed_f_2_resolved_alert_history),
    ("F3", "alert_domain_coverage", seed_f_3_alert_domain_coverage),
    ("G1", "line_user_id_conflict", seed_g_1_line_user_id_conflict),
    ("G2", "line_not_linked", seed_g_2_line_not_linked),
]


def run_all(categories: set[str] | None = None) -> dict:
    allocator = CaseNoAllocator()
    report = {}
    for code, slug, fn in ANOMALIES:
        category_letter = code[0]
        if categories is not None and category_letter not in categories:
            continue
        try:
            report[code] = {"slug": slug, **fn(allocator)}
        except Exception as exc:  # 安全網：任何未被子情境自己捕捉的例外都不中斷整批
            report[code] = {"slug": slug, "status": "failed", "error": str(exc)}
    return report


def preview(categories: set[str] | None = None) -> None:
    print("預覽模式（未連接資料庫，不會寫入任何資料）：")
    print(f"案號區段：{CASE_NO_RANGE_START:09d} - {CASE_NO_RANGE_END:09d}")
    for code, slug, _fn in ANOMALIES:
        if categories is not None and code[0] not in categories:
            continue
        print(f"  [{code}] {slug}")


def main() -> int:
    parser = argparse.ArgumentParser(description="邊界異常假資料產生器")
    parser.add_argument("--apply", action="store_true", help="實際連線並寫入資料庫（省略則只預覽）")
    parser.add_argument("--confirm-database", help="必須明確指定為 union_db 才會執行寫入")
    parser.add_argument("--only", help="只執行指定類別，逗號分隔，例如 A,C")
    parser.add_argument("--reset-range", action="store_true", help="先清除 115900001-115900099 區段內既有資料再重建")
    parser.add_argument(
        "--report-file",
        default=os.path.join(os.path.dirname(__file__), "seed_boundary_anomalies_report.json"),
        help="寫入結果報表的 JSON 檔案路徑（預設 scripts/seed_boundary_anomalies_report.json）",
    )
    args = parser.parse_args()

    categories = {c.strip().upper() for c in args.only.split(",")} if args.only else None

    if not args.apply:
        preview(categories)
        return 0

    validate_target()
    if args.confirm_database != "union_db":
        print("錯誤：--apply 需要同時帶上 --confirm-database union_db 才會執行。", file=sys.stderr)
        return 1

    if args.reset_range:
        print("正在清除 115900001-115900099 區段內既有資料...")
        reset_range()

    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            existing = check_range_is_clear(cursor)
    finally:
        conn.close()
    if existing:
        print(
            f"錯誤：案號區段 115900001-115900099 已有 {existing} 筆 clients 資料，"
            "請先加 --reset-range 清除，或確認是否重複執行。",
            file=sys.stderr,
        )
        return 1

    report = run_all(categories)
    report_text = json.dumps(report, ensure_ascii=False, indent=2, default=str)
    print(report_text)

    with open(args.report_file, "w", encoding="utf-8") as f:
        f.write(report_text)
    print(f"\n報表已寫入：{args.report_file}")

    failed = [code for code, r in report.items() if r.get("status") != "ok"]
    if failed:
        print(f"\n共 {len(failed)} 個情境失敗：{', '.join(failed)}", file=sys.stderr)
        return 1
    print(f"\n全部 {len(report)} 個異常情境寫入成功。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
