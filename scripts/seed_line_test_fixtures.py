"""
File: seed_line_test_fixtures.py
Description: 依照「LINE 四大模組詳細測試手冊與前置條件」自動建立與復原測試資料與架構。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import date, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv()

import pymysql
from infrastructure.mysql.mysql_adapter import get_connection
from api.dependencies.case_architecture_bootstrap import (
    get_case_architecture_bootstrap_status_service,
    get_case_architecture_bootstrap_workflow,
)
from shared_kernel.identities import (
    ActorContext,
    CorrelationId,
    ExpectedVersion,
    IdempotencyKey,
)
from subsystems.bootstrap.case_architecture_workflow import (
    EnsureCaseArchitectureBootstrap,
)


_ORDER_SCENARIOS: tuple[dict[str, object], ...] = (
    {"case_no": "CASE-2026-M301", "name": "陳雅婷", "phone": "0912345678", "identity_status": "一般市民", "status": "待補件", "service_days": 30, "start_date": "2026-10-05", "end_date": "2026-11-03", "staff_keys": (), "scenario": "待補件（LINE 舊客完整命中）"},
    {"case_no": "CASE-2026-M302", "name": "林怡君", "phone": "0922333444", "identity_status": "一般市民", "status": "洽談中", "service_days": 20, "start_date": "2026-11-01", "end_date": "2026-11-20", "staff_keys": (), "scenario": "洽談中（資料完整）"},
    {"case_no": "CASE-2026-M303", "name": "測試客戶－一般待收訂金", "phone": "0988000303", "identity_status": "一般市民", "status": "洽談中", "service_days": 20, "start_date": "2026-10-01", "end_date": "2026-10-20", "staff_keys": (), "payment": (54000, 0, "待收訂金"), "scenario": "洽談中－一般案／待收訂金"},
    {"case_no": "CASE-2026-M304", "name": "測試客戶－補助成立", "phone": "0988000304", "identity_status": "補助市民", "status": "訂單成立", "service_days": 20, "start_date": "2026-11-05", "end_date": "2026-11-24", "staff_keys": (), "payment": (48000, 9600, "訂金已收"), "scenario": "訂單成立－補助案／訂金已收"},
    {"case_no": "CASE-2026-M305", "name": "測試客戶－服務中", "phone": "0988000305", "identity_status": "一般市民", "status": "服務中", "service_days": 30, "start_date": "2026-09-01", "end_date": "2026-09-30", "actual_start_date": "2026-09-01", "staff_keys": ("staff_1",), "assignment_status": "active", "service_mode": "連續服務", "scenario": "服務中－單一月嫂"},
    {"case_no": "CASE-2026-M306", "name": "測試客戶－多人服務", "phone": "0988000306", "identity_status": "一般市民", "status": "服務中", "service_days": 20, "start_date": "2026-09-05", "end_date": "2026-09-24", "actual_start_date": "2026-09-05", "staff_keys": ("staff_2", "staff_3"), "assignment_statuses": ("active", "planned"), "assignment_periods": (("2026-09-05", "2026-09-14", 10), ("2026-09-15", "2026-09-24", 10)), "service_mode": "連續服務", "scenario": "服務中－多月嫂分段"},
    {"case_no": "CASE-2026-M307", "name": "測試客戶－完成待結算", "phone": "0988000307", "identity_status": "一般市民", "status": "訂單完成", "service_days": 20, "start_date": "2026-06-01", "end_date": "2026-06-20", "actual_start_date": "2026-06-01", "actual_end_date": "2026-06-20", "staff_keys": ("staff_1",), "assignment_status": "completed", "service_mode": "連續服務", "payment": (54000, 36000, "待結算"), "scenario": "訂單完成－待結算"},
    {"case_no": "CASE-2026-M308", "name": "測試客戶－完成已結清", "phone": "0988000308", "identity_status": "一般市民", "status": "訂單完成", "service_days": 20, "start_date": "2026-05-01", "end_date": "2026-05-20", "actual_start_date": "2026-05-01", "actual_end_date": "2026-05-20", "staff_keys": ("staff_2",), "assignment_status": "completed", "service_mode": "連續服務", "payment": (54000, 54000, "已結清"), "scenario": "訂單完成－已結清"},
    {"case_no": "CASE-2026-M309", "name": "測試客戶－成立前取消", "phone": "0988000309", "identity_status": "一般市民", "status": "訂單取消", "service_days": 20, "start_date": "2026-12-01", "end_date": "2026-12-20", "staff_keys": (), "cancel_reason": "測試情境：成立前取消", "scenario": "訂單取消－成立前"},
    {"case_no": "CASE-2026-M310", "name": "測試客戶－排班後取消", "phone": "0988000310", "identity_status": "一般市民", "status": "訂單取消", "service_days": 20, "start_date": "2026-09-15", "end_date": "2026-10-04", "staff_keys": ("staff_6",), "assignment_status": "cancelled", "service_mode": "連續服務", "cancel_reason": "測試情境：成立並排班後取消", "scenario": "訂單取消－成立／排班後"},
    {"case_no": "CASE-2026-H301", "name": "測試客戶－歷史完成待結算", "phone": "0988001301", "identity_status": "一般市民", "status": "歷史訂單－服務完成", "service_days": 20, "start_date": "2025-11-30", "end_date": "2025-12-19", "actual_start_date": "2025-12-01", "actual_end_date": "2025-12-20", "staff_keys": ("staff_1",), "assignment_status": "completed", "assignment_periods": (("2025-12-01", "2025-12-20", 20),), "service_mode": "連續服務", "payment": (54000, 36000, "歷史待結算"), "scenario": "歷史訂單－服務完成／待帳務結算"},
    {"case_no": "CASE-2026-H302", "name": "測試客戶－歷史服務中", "phone": "0988001302", "identity_status": "一般市民", "status": "歷史訂單－服務中", "service_days": 20, "start_date": "2026-08-31", "end_date": "2026-09-19", "actual_start_date": "2026-09-01", "actual_end_date": "2026-09-20", "staff_keys": ("staff_5",), "assignment_status": "active", "assignment_periods": (("2026-09-01", "2026-09-20", 20),), "service_mode": "連續服務", "scenario": "歷史訂單－服務中／可重啟正常流程"},
    {"case_no": "CASE-2026-H303", "name": "測試客戶－歷史服務完成", "phone": "0988001303", "identity_status": "補助市民", "status": "歷史訂單－服務完成", "service_days": 20, "start_date": "2025-09-30", "end_date": "2025-10-19", "actual_start_date": "2025-10-01", "actual_end_date": "2025-10-20", "staff_keys": ("staff_1", "staff_2"), "assignment_status": "completed", "assignment_periods": (("2025-10-01", "2025-10-10", 10), ("2025-10-11", "2025-10-20", 10)), "service_mode": "連續服務", "payment": (48000, 32000, "歷史待結算"), "scenario": "歷史訂單－服務完成／待結算"},
    {"case_no": "CASE-2026-H304", "name": "測試客戶－歷史帳務完成", "phone": "0988001304", "identity_status": "一般市民", "status": "歷史訂單－帳務完成", "service_days": 20, "start_date": "2025-08-31", "end_date": "2025-09-19", "actual_start_date": "2025-09-01", "actual_end_date": "2025-09-20", "staff_keys": ("staff_2",), "assignment_status": "completed", "assignment_periods": (("2025-09-01", "2025-09-20", 20),), "service_mode": "連續服務", "payment": (54000, 54000, "已結清"), "scenario": "歷史訂單－帳務完成／唯讀"},
    {"case_no": "CASE-2026-H305", "name": "測試客戶－歷史未服務", "phone": "0988001305", "identity_status": "一般市民", "status": "歷史訂單－未服務", "service_days": 20, "start_date": "2026-12-01", "end_date": "2026-12-20", "staff_keys": ("staff_1",), "service_mode": "連續服務", "scenario": "歷史訂單－未服務／可重啟正常流程"},
)


_CORE_STAGE_SCENARIOS: tuple[dict[str, object], ...] = (
    {"case_no": "CASE-2026-S01", "name": "階段測試－01進件", "phone": "0988010001", "identity_status": "一般市民", "status": "待補件", "service_days": 20, "start_date": "2026-12-01", "end_date": "2026-12-20", "staff_keys": (), "stage_code": "intake_validation", "scenario": "核心階段01－進件與資料完整性驗證"},
    {"case_no": "CASE-2026-S02", "name": "階段測試－02候選池", "phone": "0988010002", "identity_status": "一般市民", "status": "洽談中", "service_days": 20, "start_date": "2026-12-01", "end_date": "2026-12-20", "staff_keys": (), "stage_code": "matching_pool", "scenario": "核心階段02－建立候選月嫂池"},
    {"case_no": "CASE-2026-S03", "name": "階段測試－03詢問", "phone": "0988010003", "identity_status": "一般市民", "status": "洽談中", "service_days": 20, "start_date": "2026-12-01", "end_date": "2026-12-20", "staff_keys": (), "stage_code": "caregiver_line_delivery", "scenario": "核心階段03－詢問月嫂接案意願"},
    {"case_no": "CASE-2026-S04", "name": "階段測試－04回覆", "phone": "0988010004", "identity_status": "一般市民", "status": "洽談中", "service_days": 20, "start_date": "2026-12-01", "end_date": "2026-12-20", "staff_keys": (), "stage_code": "caregiver_willingness_reply", "scenario": "核心階段04－等待月嫂意願回覆"},
    {"case_no": "CASE-2026-S05", "name": "階段測試－05推薦", "phone": "0988010005", "identity_status": "一般市民", "status": "洽談中", "service_days": 20, "start_date": "2026-12-01", "end_date": "2026-12-20", "staff_keys": (), "stage_code": "formal_recommendation", "scenario": "核心階段05－推薦月嫂給客戶確認"},
    {"case_no": "CASE-2026-S06", "name": "階段測試－06送簽", "phone": "0988010006", "identity_status": "一般市民", "status": "洽談中", "service_days": 20, "start_date": "2026-12-01", "end_date": "2026-12-20", "staff_keys": (), "stage_code": "external_signing_dispatch", "scenario": "核心階段06－建立契約並送交外部簽署平台"},
    {"case_no": "CASE-2026-S07", "name": "階段測試－07簽署", "phone": "0988010007", "identity_status": "一般市民", "status": "洽談中", "service_days": 20, "start_date": "2026-12-01", "end_date": "2026-12-20", "staff_keys": (), "stage_code": "external_signing_completion", "scenario": "核心階段07－雙方外部簽署完成"},
    {"case_no": "CASE-2026-S08", "name": "階段測試－08定金", "phone": "0988010008", "identity_status": "一般市民", "status": "洽談中", "service_days": 20, "start_date": "2026-12-01", "end_date": "2026-12-20", "staff_keys": (), "stage_code": "deposit_settlement", "scenario": "核心階段08－客戶定金核銷"},
    {"case_no": "CASE-2026-S09", "name": "階段測試－09日期", "phone": "0988010009", "identity_status": "一般市民", "status": "訂單成立", "service_days": 20, "start_date": "2026-12-01", "end_date": "2026-12-20", "staff_keys": (), "stage_code": "confirmed_service_dates", "scenario": "核心階段09－正式服務日期確認"},
    {"case_no": "CASE-2026-S10", "name": "階段測試－10服務", "phone": "0988010010", "identity_status": "一般市民", "status": "服務中", "service_days": 20, "start_date": "2026-09-01", "end_date": "2026-09-20", "actual_start_date": "2026-09-01", "staff_keys": ("staff_4",), "assignment_status": "active", "service_mode": "連續服務", "stage_code": "formal_service", "scenario": "核心階段10－正式排班與服務履約"},
    {"case_no": "CASE-2026-S11", "name": "階段測試－11完工", "phone": "0988010011", "identity_status": "一般市民", "status": "服務中", "service_days": 20, "start_date": "2024-01-01", "end_date": "2024-01-20", "actual_start_date": "2024-01-01", "actual_end_date": "2024-01-20", "staff_keys": ("staff_1",), "assignment_status": "completed", "service_mode": "連續服務", "stage_code": "service_completion", "scenario": "核心階段11－完工／服務完成確認"},
    {"case_no": "CASE-2026-S12", "name": "階段測試－12客戶結算", "phone": "0988010012", "identity_status": "一般市民", "status": "訂單完成", "service_days": 20, "start_date": "2024-02-01", "end_date": "2024-02-20", "actual_start_date": "2024-02-01", "actual_end_date": "2024-02-20", "staff_keys": ("staff_1",), "assignment_status": "completed", "service_mode": "連續服務", "stage_code": "client_settlement", "scenario": "核心階段12－客戶端結算"},
    {"case_no": "CASE-2026-S13", "name": "階段測試－13月嫂結算", "phone": "0988010013", "identity_status": "一般市民", "status": "訂單完成", "service_days": 20, "start_date": "2024-03-01", "end_date": "2024-03-20", "actual_start_date": "2024-03-01", "actual_end_date": "2024-03-20", "staff_keys": ("staff_2",), "assignment_status": "completed", "service_mode": "連續服務", "stage_code": "staff_payout", "scenario": "核心階段13－月嫂端結算"},
)


_ALL_ORDER_SCENARIOS = _ORDER_SCENARIOS + _CORE_STAGE_SCENARIOS
_SUPPORTED_SERVICE_MODES = frozenset({"週休1日", "週休2日", "連續服務"})


def _seed_scenario_client(cursor, scenario: dict[str, object]) -> int:
    case_no = str(scenario["case_no"])
    name = str(scenario["name"])
    phone = str(scenario["phone"])
    service_mode = str(scenario.get("service_mode", "週休1日"))
    if service_mode not in _SUPPORTED_SERVICE_MODES:
        raise ValueError(f"unsupported fixture service mode: {service_mode}")
    cursor.execute("SELECT id FROM clients WHERE case_no=%s", (case_no,))
    existing = cursor.fetchone()
    if existing is None:
        cursor.execute("SELECT id FROM clients WHERE name=%s AND phone=%s", (name, phone))
        existing = cursor.fetchone()
    values = (name, phone, str(scenario["identity_status"]), scenario["service_days"], str(scenario["start_date"])[:7], scenario["start_date"], f"LINE 訂單全情境測試：{scenario['scenario']}", service_mode, case_no)
    if existing:
        client_id = int(existing["id"])
        cursor.execute(
            "UPDATE clients SET name=%s,gender='female',phone=%s,city='新竹市',address='東區測試路100號',identity_status=%s,"
            "service_time='9小時日間',service_days=%s,due_month=%s,service_start_date=%s,notes=%s,residence_type='大樓',"
            "delivery_type='自然產',service_type=%s,baby_info='單胞胎',case_no=%s,line_user_id=NULL,"
            "admin_notes='ORDER_SCENARIO_FIXTURE',created_at=DATE_SUB(%s,INTERVAL 60 DAY) WHERE id=%s",
            (*values, scenario["start_date"], client_id),
        )
        return client_id
    cursor.execute(
        "INSERT INTO clients (name,gender,phone,city,address,identity_status,service_time,service_days,due_month,service_start_date,"
        "notes,residence_type,delivery_type,service_type,baby_info,case_no,line_user_id,admin_notes,created_at) "
        "VALUES (%s,'female',%s,'新竹市','東區測試路100號',%s,'9小時日間',%s,%s,%s,%s,'大樓','自然產',%s,"
        "'單胞胎',%s,NULL,'ORDER_SCENARIO_FIXTURE',DATE_SUB(%s,INTERVAL 60 DAY))",
        (*values, scenario["start_date"]),
    )
    return int(cursor.lastrowid)


def _seed_scenario_order(cursor, scenario: dict[str, object], client_id: int, staff_ids: dict[str, int]) -> None:
    staff_keys = tuple(scenario.get("staff_keys", ()))
    primary_staff_id = staff_ids[str(staff_keys[0])] if staff_keys else None
    final_status = str(scenario["status"])
    stored_status = (
        "洽談中"
        if final_status in {"訂單成立", "服務中", "訂單完成", "訂單取消"}
        or final_status.startswith("歷史訂單")
        else final_status
    )
    contract_identity = f"fixture-contract:{scenario['case_no']}"
    values = (client_id, primary_staff_id, stored_status, contract_identity, scenario.get("cancel_reason"), scenario["service_days"], scenario["start_date"], scenario["end_date"], scenario.get("actual_start_date"), scenario.get("actual_end_date"))
    cursor.execute("SELECT case_no FROM orders WHERE case_no=%s", (scenario["case_no"],))
    if cursor.fetchone():
        cursor.execute(
            "UPDATE orders SET client_id=%s,staff_id=%s,status=%s,lifecycle_version=1,contract_identity=%s,cancel_reason=%s,service_days=%s,"
            "service_hours_per_day=9,service_start_time='09:00:00',service_end_time='18:00:00',service_end_day_offset=0,"
            "floor_fee=0,start_date=%s,end_date=%s,actual_start_date=%s,actual_end_date=%s,requires_cooking=1 WHERE case_no=%s",
            (*values, scenario["case_no"]),
        )
    else:
        cursor.execute(
            "INSERT INTO orders (case_no,client_id,staff_id,status,lifecycle_version,contract_identity,cancel_reason,service_days,service_hours_per_day,"
            "service_start_time,service_end_time,service_end_day_offset,floor_fee,start_date,end_date,actual_start_date,actual_end_date,requires_cooking) "
            "VALUES (%s,%s,%s,%s,1,%s,%s,%s,9,'09:00:00','18:00:00',0,0,%s,%s,%s,%s,1)",
            (scenario["case_no"], *values),
        )

    assignment_periods = tuple(scenario.get("assignment_periods", ()))
    assignment_statuses = tuple(scenario.get("assignment_statuses", ()))
    for sequence, staff_key in enumerate(staff_keys, start=1):
        assigned_start, assigned_end, assigned_days = (
            assignment_periods[sequence - 1]
            if assignment_periods
            else (scenario["start_date"], scenario["end_date"], scenario["service_days"])
        )
        assignment_status = str(
            assignment_statuses[sequence - 1]
            if assignment_statuses
            else "planned"
            if final_status == "訂單取消"
            else scenario.get("assignment_status", "planned")
        )
        cursor.execute(
            "INSERT INTO case_staff_assignments (case_no,generation_id,candidate_key,staff_id,assignment_sequence,assigned_start_date,"
            "assigned_end_date,planned_hours,actual_hours,hourly_rate,status) VALUES (%s,NULL,%s,%s,%s,%s,%s,%s,%s,300,%s) "
            "ON DUPLICATE KEY UPDATE staff_id=VALUES(staff_id),assigned_start_date=VALUES(assigned_start_date),"
            "assigned_end_date=VALUES(assigned_end_date),planned_hours=VALUES(planned_hours),actual_hours=VALUES(actual_hours),"
            "hourly_rate=VALUES(hourly_rate),status=VALUES(status)",
            (scenario["case_no"], f"line-order-scenario:{scenario['case_no']}:{sequence}", staff_ids[str(staff_key)], sequence, assigned_start, assigned_end, int(assigned_days) * 9, int(assigned_days) * 9 if assignment_status == "completed" else None, assignment_status),
        )

    payment = scenario.get("payment")
    if payment is not None:
        receivable, received, payment_status = payment
        deposit_receivable = int(receivable) // 5
        first_receivable = (int(receivable) - deposit_receivable) // 2
        second_receivable = int(receivable) - deposit_receivable - first_receivable
        deposit_received = min(int(received), deposit_receivable)
        first_received = min(max(int(received) - deposit_received, 0), first_receivable)
        second_received = min(
            max(int(received) - deposit_received - first_received, 0),
            second_receivable,
        )
        cursor.execute(
            "INSERT INTO client_payments (case_no,deposit_receivable,deposit_received,first_payment_receivable,first_payment_received,"
            "second_payment_receivable,second_payment_received,amount_receivable,amount_received,payment_status,notes) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE deposit_receivable=VALUES(deposit_receivable),"
            "deposit_received=VALUES(deposit_received),first_payment_receivable=VALUES(first_payment_receivable),"
            "first_payment_received=VALUES(first_payment_received),second_payment_receivable=VALUES(second_payment_receivable),"
            "second_payment_received=VALUES(second_payment_received),amount_receivable=VALUES(amount_receivable),amount_received=VALUES(amount_received),"
            "payment_status=VALUES(payment_status),notes=VALUES(notes)",
            (scenario["case_no"], deposit_receivable, deposit_received, first_receivable, first_received, second_receivable, second_received, receivable, received, payment_status, f"ORDER_SCENARIO_FIXTURE：{scenario['scenario']}"),
        )


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _seed_import_receipt(cursor, case_no: str, client_id: int) -> None:
    cursor.execute(
        "SELECT id FROM case_architecture_bootstrap_events WHERE case_no=%s",
        (case_no,),
    )
    bootstrap = cursor.fetchone()
    if not bootstrap:
        raise RuntimeError(f"case architecture bootstrap missing: {case_no}")
    digest = _sha(f"line-stage-import:{case_no}")
    cursor.execute(
        "INSERT IGNORE INTO case_import_events "
        "(case_no,client_id,bootstrap_event_id,source_fingerprint,candidate_fingerprint,source_snapshot,"
        "idempotency_key,actor,reason,correlation_id) VALUES (%s,%s,%s,%s,%s,%s,%s,'system:seed',%s,%s)",
        (
            case_no,
            client_id,
            bootstrap["id"],
            digest,
            digest,
            json.dumps({"fixture": "core_stage", "case_no": case_no}),
            f"line-stage-import:{case_no.lower()}",
            "建立十三核心階段測試進件根事實",
            f"line-stage-import:{case_no.lower()}",
        ),
    )
    cursor.execute("SELECT id FROM case_import_events WHERE case_no=%s", (case_no,))
    import_event_id = cursor.fetchone()["id"]
    cursor.execute(
        "INSERT IGNORE INTO case_import_receipts "
        "(idempotency_key,command_fingerprint,source_fingerprint,preview_fingerprint,case_no,client_id,"
        "import_event_id,bootstrap_event_id,order_version,client_finance_version,payroll_version,"
        "scheduling_version,scheduling_generation,result_snapshot) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        (
            f"line-stage-import-receipt:{case_no.lower()}",
            digest,
            digest,
            digest,
            case_no,
            client_id,
            import_event_id,
            bootstrap["id"],
            0,
            0,
            0,
            0,
            0,
            json.dumps({"fixture": "core_stage", "case_no": case_no}),
        ),
    )


def _seed_contact_pool(cursor, case_no: str, staff_id: int, progress: str) -> None:
    cursor.execute("SELECT start_date,end_date FROM orders WHERE case_no=%s", (case_no,))
    order = cursor.fetchone()
    if not order:
        raise RuntimeError(f"fixture order missing: {case_no}")
    cursor.execute(
        "INSERT INTO caregiver_candidate_contact_pools (case_no,created_by) "
        "VALUES (%s,'system:seed') ON DUPLICATE KEY UPDATE case_no=VALUES(case_no)",
        (case_no,),
    )
    cursor.execute("SELECT id FROM caregiver_candidate_contact_pools WHERE case_no=%s", (case_no,))
    pool_id = cursor.fetchone()["id"]
    if progress == "empty":
        return
    cursor.execute(
        "INSERT INTO caregiver_candidate_contact_entries "
        "(pool_id,staff_id,service_start_date,service_end_date,coverage_fingerprint,status,active_marker) "
        "VALUES (%s,%s,%s,%s,%s,'active',1) "
        "ON DUPLICATE KEY UPDATE status='active',active_marker=1",
        (pool_id, staff_id, order["start_date"], order["end_date"], _sha(f"line-stage-pool:{case_no}")),
    )
    cursor.execute(
        "SELECT id FROM caregiver_candidate_contact_entries WHERE pool_id=%s AND staff_id=%s AND active_marker=1",
        (pool_id, staff_id),
    )
    candidate_id = cursor.fetchone()["id"]
    if progress in {"contacted", "replied"}:
        cursor.execute(
            "INSERT IGNORE INTO caregiver_candidate_contact_events "
            "(pool_id,candidate_id,event_type,event_key,actor,payload) "
            "VALUES (%s,%s,'info_1_sent',%s,'system:seed',%s)",
            (pool_id, candidate_id, f"line-stage-contact:{case_no}:{staff_id}", json.dumps({"fixture": "core_stage"})),
        )
    if progress == "replied":
        cursor.execute(
            "INSERT IGNORE INTO caregiver_candidate_contact_events "
            "(pool_id,candidate_id,event_type,event_key,actor,payload) "
            "VALUES (%s,%s,'willingness_changed',%s,'system:seed',%s)",
            (pool_id, candidate_id, f"line-stage-reply:{case_no}:{staff_id}", json.dumps({"willingness": "willing"})),
        )


def _seed_matching_plan(cursor, case_no: str) -> int:
    cursor.execute("SELECT start_date,end_date FROM orders WHERE case_no=%s", (case_no,))
    order = cursor.fetchone()
    if not order:
        raise RuntimeError(f"fixture order missing: {case_no}")
    cursor.execute(
        "INSERT INTO caregiver_matching_plans "
        "(case_no,version,status,is_active,start_date,end_date,created_by) "
        "VALUES (%s,1,'accepted',1,%s,%s,'system:seed') "
        "ON DUPLICATE KEY UPDATE status='accepted',is_active=1,start_date=VALUES(start_date),end_date=VALUES(end_date)",
        (case_no, order["start_date"], order["end_date"]),
    )
    cursor.execute(
        "SELECT id FROM caregiver_matching_plans WHERE case_no=%s AND is_active=1",
        (case_no,),
    )
    return int(cursor.fetchone()["id"])


def _seed_accepted_matching_evidence(cursor, case_no: str, staff_id: int) -> int:
    """建立媒合完成前真正會存在的意願、接受與履歷送達根事實。"""
    cursor.execute(
        "SELECT staff_id,assignment_sequence,assigned_start_date,assigned_end_date "
        "FROM case_staff_assignments WHERE case_no=%s ORDER BY assignment_sequence",
        (case_no,),
    )
    assignments = cursor.fetchall()
    if not assignments:
        cursor.execute("SELECT start_date,end_date FROM orders WHERE case_no=%s", (case_no,))
        order = cursor.fetchone()
        assignments = ({
            "staff_id": staff_id,
            "assignment_sequence": 1,
            "assigned_start_date": order["start_date"],
            "assigned_end_date": order["end_date"],
        },)
    for assignment in assignments:
        _seed_contact_pool(cursor, case_no, int(assignment["staff_id"]), "replied")
    plan_id = _seed_matching_plan(cursor, case_no)
    for assignment in assignments:
        segment_order = int(assignment["assignment_sequence"])
        assigned_staff_id = int(assignment["staff_id"])
        cursor.execute(
            "INSERT IGNORE INTO caregiver_matching_plan_segments "
            "(plan_id,segment_order,staff_id,assigned_start_date,assigned_end_date) "
            "VALUES (%s,%s,%s,%s,%s)",
            (plan_id, segment_order, assigned_staff_id,
             assignment["assigned_start_date"], assignment["assigned_end_date"]),
        )
        cursor.execute(
            "SELECT id FROM caregiver_matching_plan_segments WHERE plan_id=%s AND segment_order=%s",
            (plan_id, segment_order),
        )
        segment_id = int(cursor.fetchone()["id"])
        cursor.execute(
            "INSERT INTO matching_records "
            "(case_no,staff_id,caregiver_accepted,sent_at,replied_at,sent_info_1_at,sent_resume_at) "
            "VALUES (%s,%s,1,UTC_TIMESTAMP(),UTC_TIMESTAMP(),UTC_TIMESTAMP(),UTC_TIMESTAMP()) "
            "ON DUPLICATE KEY UPDATE caregiver_accepted=1,replied_at=VALUES(replied_at),"
            "sent_info_1_at=VALUES(sent_info_1_at),sent_resume_at=VALUES(sent_resume_at)",
            (case_no, assigned_staff_id),
        )
        cursor.execute(
            "INSERT IGNORE INTO matching_response_events "
            "(plan_id,segment_id,response_type,response_value,response_source,actor_id,line_user_id,reason,"
            "idempotency_key,payload_fingerprint,occurred_at_utc) "
            "VALUES (%s,%s,'caregiver_willingness','willing','admin','system:seed',NULL,"
            "'測試月嫂確認願意接案',%s,%s,UTC_TIMESTAMP(6))",
            (plan_id, segment_id, f"line-stage-willing:{case_no.lower()}:{segment_order}",
             _sha(f"line-stage-willing:{case_no}:{segment_order}")),
        )
        cursor.execute(
            "INSERT IGNORE INTO caregiver_matching_plan_events "
            "(plan_id,segment_id,event_type,event_key,actor,payload) "
            "VALUES (%s,%s,'resume_sent',%s,'system:seed',%s)",
            (plan_id, segment_id, f"line-stage-resume:{case_no.lower()}:{segment_order}",
             json.dumps({"delivery_status": "manually_confirmed"})),
        )
    cursor.execute(
        "INSERT IGNORE INTO matching_response_events "
        "(plan_id,segment_id,response_type,response_value,response_source,actor_id,line_user_id,reason,"
        "idempotency_key,payload_fingerprint,occurred_at_utc) "
        "VALUES (%s,NULL,'customer_decision','accepted','admin','system:seed',NULL,"
        "'測試客戶接受正式推薦',%s,%s,UTC_TIMESTAMP(6))",
        (plan_id, f"line-stage-customer-accepted:{case_no.lower()}",
         _sha(f"line-stage-customer-accepted:{case_no}")),
    )
    return plan_id


def _seed_external_signing(cursor, case_no: str, plan_id: int, *, completed: bool) -> None:
    session_token = _sha(f"line-stage-session:{case_no}")[:32]
    commitment_id = None
    reminder_id = None
    if completed:
        cursor.execute(
            "INSERT IGNORE INTO precontract_service_commitments "
            "(case_no,matching_plan_id,commitment_key,plan_snapshot_sha256,created_by) "
            "VALUES (%s,%s,%s,%s,'system:seed')",
            (case_no, plan_id, f"line-stage-commitment:{case_no}", _sha(f"line-stage-plan:{case_no}")),
        )
        cursor.execute("SELECT id FROM precontract_service_commitments WHERE matching_plan_id=%s", (plan_id,))
        commitment_id = cursor.fetchone()["id"]
        cursor.execute(
            "SELECT id,staff_id,assigned_start_date,assigned_end_date "
            "FROM caregiver_matching_plan_segments WHERE plan_id=%s ORDER BY segment_order",
            (plan_id,),
        )
        for segment in cursor.fetchall():
            for service_date in _inclusive_dates(
                segment["assigned_start_date"], segment["assigned_end_date"]
            ):
                cursor.execute(
                    "INSERT IGNORE INTO precontract_service_commitment_days "
                    "(commitment_id,matching_segment_id,staff_id,service_date) VALUES (%s,%s,%s,%s)",
                    (commitment_id, segment["id"], segment["staff_id"], service_date),
                )
        cursor.execute(
            "INSERT IGNORE INTO line_delivery_tasks "
            "(recipient_type,recipient_identity,message_kind,payload_snapshot,payload_fingerprint,scheduled_at_utc,"
            "source_aggregate_type,source_aggregate_identity,idempotency_key,correlation_id,processing_status,"
            "completed_attempts,provider_message_id,sent_at_utc) "
            "VALUES ('user',%s,'text',%s,%s,UTC_TIMESTAMP(6),'contract_external_signing',%s,%s,%s,'sent',"
            "1,%s,UTC_TIMESTAMP(6))",
            (
                f"fixture-client:{case_no}",
                json.dumps({"text": "外部簽署完成測試通知"}),
                _sha(f"line-stage-reminder:{case_no}"),
                case_no,
                f"line-stage-reminder:{case_no.lower()}",
                f"line-stage-reminder:{case_no.lower()}",
                f"fixture-provider:{case_no}",
            ),
        )
        cursor.execute("SELECT id FROM line_delivery_tasks WHERE idempotency_key=%s", (f"line-stage-reminder:{case_no.lower()}",))
        reminder_id = cursor.fetchone()["id"]
    cursor.execute(
        "INSERT INTO contract_external_signing_sessions "
        "(external_signing_session_id,case_no,matching_plan_id,current_document_set_sha256,commitment_id,"
        "client_reminder_task_id,session_state,aggregate_version,activated_by_actor) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,1,'system:seed') "
        "ON DUPLICATE KEY UPDATE session_state=VALUES(session_state),commitment_id=VALUES(commitment_id),"
        "client_reminder_task_id=VALUES(client_reminder_task_id),aggregate_version=1",
        (
            f"ces_{session_token}",
            case_no,
            plan_id,
            _sha(f"line-stage-docset:{case_no}"),
            commitment_id,
            reminder_id,
            "completed" if completed else "staff_reporting",
        ),
    )
    if not completed:
        return
    cursor.execute(
        "SELECT id FROM contract_external_signing_sessions WHERE external_signing_session_id=%s",
        (f"ces_{session_token}",),
    )
    session_id = cursor.fetchone()["id"]
    suffix = _sha(f"line-stage-final:{case_no}")[:32]
    cursor.execute(
        "INSERT IGNORE INTO controlled_file_staging_objects "
        "(staging_id,storage_locator,owner_type,subject_reference,object_key,purpose,logical_folder,"
        "original_filename,content_type,size_bytes,content_sha256,staging_state,staging_version,idempotency_key,"
        "command_fingerprint,created_by_actor,expires_at_utc,applied_at_utc) "
        "VALUES (%s,%s,'contract_signing',%s,'final-contract','final_signed_contract',%s,%s,"
        "'application/pdf',128,%s,'applied',1,%s,%s,'system:seed',DATE_ADD(UTC_TIMESTAMP(6),INTERVAL 1 DAY),UTC_TIMESTAMP(6))",
        (
            f"cfs_{suffix}",
            f"fixture://contracts/{case_no}/final.pdf",
            case_no,
            f"contracts/{case_no}",
            f"{case_no}-final.pdf",
            _sha(f"line-stage-content:{case_no}"),
            f"line-stage-file:{case_no.lower()}",
            _sha(f"line-stage-file-command:{case_no}"),
        ),
    )
    cursor.execute("SELECT id FROM controlled_file_staging_objects WHERE staging_id=%s", (f"cfs_{suffix}",))
    staging_id = cursor.fetchone()["id"]
    cursor.execute(
        "INSERT IGNORE INTO controlled_file_objects "
        "(opaque_object_id,source_staging_id,owner_type,subject_reference,object_key,purpose,logical_folder,filename,"
        "storage_locator,content_type,size_bytes,content_sha256,version_number,created_by_actor) "
        "VALUES (%s,%s,'contract_signing',%s,'final-contract','final_signed_contract',%s,%s,%s,"
        "'application/pdf',128,%s,1,'system:seed')",
        (
            f"cf_{suffix}",
            staging_id,
            case_no,
            f"contracts/{case_no}",
            f"{case_no}-final.pdf",
            f"fixture://contracts/{case_no}/final.pdf",
            _sha(f"line-stage-content:{case_no}"),
        ),
    )
    cursor.execute("SELECT id FROM controlled_file_objects WHERE opaque_object_id=%s", (f"cf_{suffix}",))
    object_id = cursor.fetchone()["id"]
    cursor.execute(
        "INSERT IGNORE INTO contract_final_document_versions "
        "(final_document_id,external_signing_session_id,case_no,source_document_set_sha256,controlled_file_object_id,"
        "version_number,contract_identity,content_type,size_bytes,content_sha256,created_by_actor) "
        "VALUES (%s,%s,%s,%s,%s,1,%s,'application/pdf',128,%s,'system:seed')",
        (
            f"cfd_{suffix}",
            session_id,
            case_no,
            _sha(f"line-stage-docset:{case_no}"),
            object_id,
            f"fixture-contract:{case_no}",
            _sha(f"line-stage-content:{case_no}"),
        ),
    )


def _seed_contract_completion(cursor, case_no: str) -> None:
    cursor.execute(
        "INSERT IGNORE INTO order_contract_flow_events "
        "(case_no,contract_identity,event_type,actor,reason,idempotency_key) "
        "VALUES (%s,%s,'contract_completed','system:seed','測試契約雙方簽署完成',%s)",
        (
            case_no,
            f"fixture-contract:{case_no}",
            f"line-stage-contract-completed:{case_no.lower()}",
        ),
    )
    lifecycle_key = f"line-stage-contract-lifecycle:{case_no.lower()}"
    cursor.execute(
        "INSERT IGNORE INTO order_lifecycle_state_events "
        "(case_no,trigger_event,before_status,after_status,actor,business_date,expected_version,idempotency_key,facts_snapshot) "
        "VALUES (%s,'contract_completed','洽談中','訂單成立','system:seed','2026-09-10',1,%s,%s)",
        (case_no, lifecycle_key, json.dumps({"fixture": "core_stage", "contract_completed": True})),
    )
    cursor.execute(
        "UPDATE orders SET status='訂單成立',lifecycle_version=2 WHERE case_no=%s",
        (case_no,),
    )


def _seed_service_start(cursor, case_no: str) -> None:
    cursor.execute("SELECT actual_start_date,lifecycle_version FROM orders WHERE case_no=%s", (case_no,))
    order = cursor.fetchone()
    if not order or order["actual_start_date"] is None:
        raise RuntimeError(f"service fixture lacks actual start date: {case_no}")
    expected_version = int(order["lifecycle_version"])
    event_key = f"line-stage-service-start:{case_no.lower()}"
    cursor.execute(
        "INSERT IGNORE INTO order_lifecycle_state_events "
        "(case_no,trigger_event,before_status,after_status,actor,business_date,expected_version,idempotency_key,facts_snapshot) "
        "VALUES (%s,'actual_start_confirmed','訂單成立','服務中','system:seed',%s,%s,%s,%s)",
        (case_no, order["actual_start_date"], expected_version, event_key,
         json.dumps({"fixture": "core_stage", "actual_start_confirmed": True})),
    )
    cursor.execute(
        "UPDATE orders SET status='服務中',lifecycle_version=%s WHERE case_no=%s",
        (expected_version + 1, case_no),
    )


def _seed_client_obligation(cursor, case_no: str, obligation_type: str, *, settled: bool) -> None:
    identity = f"line-stage-client:{case_no}:{obligation_type}"
    idempotency_key = f"line-stage-client-obligation:{case_no.lower()}:{obligation_type}"
    cursor.execute(
        "SELECT o.end_date,p.deposit_receivable,p.first_payment_receivable,p.second_payment_receivable "
        "FROM orders o LEFT JOIN client_payments p ON p.case_no=o.case_no WHERE o.case_no=%s",
        (case_no,),
    )
    payment = cursor.fetchone()
    due_date = payment["end_date"]
    amount_field = {
        "deposit": "deposit_receivable",
        "first": "first_payment_receivable",
        "second": "second_payment_receivable",
    }.get(obligation_type)
    amount = int(payment[amount_field]) if amount_field and payment[amount_field] else 1000
    cursor.execute("SELECT id FROM client_obligation_events WHERE idempotency_key=%s", (idempotency_key,))
    row = cursor.fetchone()
    if row:
        event_id = row["id"]
    else:
        cursor.execute("SELECT aggregate_version FROM client_finance_accounts WHERE case_no=%s", (case_no,))
        account_version = int(cursor.fetchone()["aggregate_version"])
        cursor.execute(
            "INSERT INTO client_obligation_events "
            "(obligation_identity,case_no,obligation_type,direction,event_type,before_amount_ntd,after_amount_ntd,"
            "before_due_date,after_due_date,source_event_identity,expected_account_version,idempotency_key,actor,reason) "
            "VALUES (%s,%s,%s,'receivable_from_client','established',0,%s,NULL,%s,%s,%s,%s,"
            "'system:seed','建立核心階段客戶 obligation')",
            (identity, case_no, obligation_type, amount, due_date, idempotency_key, account_version, idempotency_key),
        )
        event_id = cursor.lastrowid
        cursor.execute(
            "UPDATE client_finance_accounts SET aggregate_version=aggregate_version+1 WHERE case_no=%s",
            (case_no,),
        )
    cursor.execute(
        "INSERT INTO client_obligations "
        "(obligation_identity,case_no,obligation_type,direction,amount_due_ntd,due_date,status,current_event_id,projection_version) "
        "VALUES (%s,%s,%s,'receivable_from_client',%s,%s,'open',%s,1) "
        "ON DUPLICATE KEY UPDATE current_event_id=VALUES(current_event_id)",
        (identity, case_no, obligation_type, amount, due_date, event_id),
    )
    if not settled:
        cursor.execute(
            "UPDATE client_obligations SET amount_due_ntd=%s,status='open' WHERE obligation_identity=%s",
            (amount, identity),
        )
        if obligation_type == "deposit":
            cursor.execute("SELECT aggregate_version FROM client_finance_accounts WHERE case_no=%s", (case_no,))
            projection_version = int(cursor.fetchone()["aggregate_version"])
            cursor.execute(
                "INSERT INTO client_deposit_settlement_projection "
                "(case_no,deposit_obligation_identity,settlement_state,contracted_amount_ntd,allocated_net_amount_ntd,"
                "settlement_identity,source_fingerprint,projection_version,latest_ledger_entry_id) "
                "VALUES (%s,%s,'unsettled',%s,0,NULL,%s,%s,NULL) ON DUPLICATE KEY UPDATE "
                "deposit_obligation_identity=VALUES(deposit_obligation_identity),settlement_state='unsettled',"
                "contracted_amount_ntd=VALUES(contracted_amount_ntd),allocated_net_amount_ntd=0,settlement_identity=NULL,"
                "source_fingerprint=VALUES(source_fingerprint),projection_version=VALUES(projection_version),latest_ledger_entry_id=NULL",
                (case_no, identity, amount, _sha(f"line-stage-deposit-source:{case_no}"), projection_version),
            )
        return
    ledger_key = f"line-stage-client-ledger:{case_no.lower()}:{obligation_type}"
    cursor.execute("SELECT id FROM client_ledger_entries WHERE idempotency_key=%s", (ledger_key,))
    existing_ledger = cursor.fetchone()
    cursor.execute(
        "INSERT IGNORE INTO client_ledger_entries "
        "(case_no,entry_type,amount_ntd,occurred_on,reconciliation_reference,idempotency_key,actor,reason) "
        "VALUES (%s,'receipt',%s,%s,%s,%s,'system:seed','核心階段已核銷測試款')",
        (case_no, amount, due_date, ledger_key, ledger_key),
    )
    cursor.execute("SELECT id FROM client_ledger_entries WHERE idempotency_key=%s", (ledger_key,))
    ledger_id = cursor.fetchone()["id"]
    cursor.execute(
        "INSERT IGNORE INTO client_ledger_obligation_allocations "
        "(ledger_entry_id,obligation_identity,amount_ntd,allocation_ordinal) VALUES (%s,%s,%s,1)",
        (ledger_id, identity, amount),
    )
    cursor.execute(
        "SELECT aggregate_version FROM client_finance_accounts WHERE case_no=%s",
        (case_no,),
    )
    current_version = int(cursor.fetchone()["aggregate_version"])
    if not existing_ledger:
        current_version += 1
        cursor.execute(
            "UPDATE client_finance_accounts SET aggregate_version=%s WHERE case_no=%s",
            (current_version, case_no),
        )
    cursor.execute(
        "UPDATE client_obligations SET amount_due_ntd=0,status='settled',projection_version=%s "
        "WHERE obligation_identity=%s",
        (current_version, identity),
    )
    if obligation_type == "deposit":
        settlement_identity = _sha(f"line-stage-deposit-settlement:{case_no}")
        cursor.execute(
            "INSERT INTO client_deposit_settlement_projection "
            "(case_no,deposit_obligation_identity,settlement_state,contracted_amount_ntd,allocated_net_amount_ntd,"
            "settlement_identity,source_fingerprint,projection_version,latest_ledger_entry_id) "
            "VALUES (%s,%s,'settled',%s,%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE "
            "deposit_obligation_identity=VALUES(deposit_obligation_identity),settlement_state='settled',"
            "contracted_amount_ntd=VALUES(contracted_amount_ntd),allocated_net_amount_ntd=VALUES(allocated_net_amount_ntd),settlement_identity=VALUES(settlement_identity),"
            "source_fingerprint=VALUES(source_fingerprint),projection_version=VALUES(projection_version),"
            "latest_ledger_entry_id=VALUES(latest_ledger_entry_id)",
            (case_no, identity, amount, amount, settlement_identity, settlement_identity, current_version, ledger_id),
        )


def _inclusive_dates(start_value: object, end_value: object) -> tuple[date, ...]:
    start = date.fromisoformat(str(start_value))
    end = date.fromisoformat(str(end_value))
    if end < start:
        raise ValueError("fixture assignment end precedes start")
    return tuple(start + timedelta(days=offset) for offset in range((end - start).days + 1))


def _ensure_fixture_scheduling_generation(cursor, case_no: str) -> tuple[int, int]:
    """建立 fixture 專用的有效世代，語意與 metadata-only bootstrap 相同。"""
    cursor.execute(
        "SELECT aggregate_version,generation_counter,effective_generation_id "
        "FROM scheduling_aggregates WHERE case_no=%s",
        (case_no,),
    )
    aggregate = cursor.fetchone()
    if not aggregate:
        raise RuntimeError(f"scheduling aggregate missing: {case_no}")
    effective_generation_id = aggregate["effective_generation_id"]
    if effective_generation_id is not None:
        generation_id = int(effective_generation_id)
        cursor.execute(
            "SELECT COUNT(*) AS count FROM case_staff_assignments "
            "WHERE case_no=%s AND generation_id<>%s",
            (case_no, generation_id),
        )
        if int(cursor.fetchone()["count"]):
            raise RuntimeError(f"fixture assignments span scheduling generations: {case_no}")
        return generation_id, int(aggregate["aggregate_version"])

    generation_number = int(aggregate["generation_counter"]) + 1
    resulting_version = int(aggregate["aggregate_version"]) + 1
    cursor.execute(
        "INSERT INTO scheduling_generations "
        "(case_no,generation_number,resulting_aggregate_version,status,effective_marker,created_by,change_reason) "
        "VALUES (%s,%s,%s,'effective',1,'system:seed','Fixture metadata bootstrap from declared assignment ownership')",
        (case_no, generation_number, resulting_version),
    )
    generation_id = int(cursor.lastrowid)
    cursor.execute(
        "UPDATE case_staff_assignments SET generation_id=%s WHERE case_no=%s",
        (generation_id, case_no),
    )
    if cursor.rowcount < 1:
        raise RuntimeError(f"fixture scheduling generation has no assignments: {case_no}")
    cursor.execute(
        "UPDATE scheduling_aggregates SET aggregate_version=%s,generation_counter=%s,effective_generation_id=%s "
        "WHERE case_no=%s AND effective_generation_id IS NULL",
        (resulting_version, generation_number, generation_id, case_no),
    )
    if cursor.rowcount != 1:
        raise RuntimeError(f"fixture scheduling generation activation conflict: {case_no}")
    return generation_id, resulting_version


def _seed_service_schedule(cursor, scenario: dict[str, object]) -> tuple[int, ...]:
    case_no = str(scenario["case_no"])
    generation_id, scheduling_version = _ensure_fixture_scheduling_generation(cursor, case_no)
    cursor.execute(
        "SELECT id,staff_id,assigned_start_date,assigned_end_date,planned_hours,status,generation_id "
        "FROM case_staff_assignments WHERE case_no=%s ORDER BY assignment_sequence",
        (case_no,),
    )
    assignments = cursor.fetchall()
    if not assignments:
        raise RuntimeError(f"fixture assignment missing: {case_no}")
    assignment_ids: list[int] = []
    official_dates: list[date] = []
    for assignment in assignments:
        assignment_id = int(assignment["id"])
        assignment_ids.append(assignment_id)
        if assignment["generation_id"] != generation_id:
            raise RuntimeError(f"fixture assignment is outside effective generation: {case_no}")
        dates = _inclusive_dates(assignment["assigned_start_date"], assignment["assigned_end_date"])
        declared_days = int(assignment["planned_hours"]) // 9
        if len(dates) != declared_days:
            raise RuntimeError(f"fixture assignment day count mismatch: {case_no}")
        if assignment["status"] not in {"cancelled", "replaced"}:
            official_dates.extend(dates)
        for work_date in dates:
            cursor.execute(
                "SELECT case_no,assignment_id,generation_id FROM staff_schedule "
                "WHERE staff_id=%s AND work_date=%s AND effective_marker=1",
                (assignment["staff_id"], work_date),
            )
            existing_schedule = cursor.fetchone()
            expected_owner = (case_no, assignment_id, generation_id)
            if existing_schedule is None:
                cursor.execute(
                    "INSERT INTO staff_schedule "
                    "(case_no,staff_id,assignment_id,generation_id,work_date,is_work_day,is_double_pay,effective_marker,notes) "
                    "VALUES (%s,%s,%s,%s,%s,1,0,1,'ORDER_SCENARIO_FIXTURE')",
                    (case_no, assignment["staff_id"], assignment_id, generation_id, work_date),
                )
            elif (
                existing_schedule["case_no"],
                int(existing_schedule["assignment_id"]),
                int(existing_schedule["generation_id"]),
            ) != expected_owner:
                raise RuntimeError(
                    f"fixture staff date conflicts with another effective schedule: {case_no}/{work_date}"
                )
            if assignment["status"] not in {"cancelled", "replaced"}:
                cursor.execute(
                    "SELECT generation_id,assignment_id,occupancy_type FROM scheduling_effective_occupancy "
                    "WHERE staff_id=%s AND occupancy_date=%s",
                    (assignment["staff_id"], work_date),
                )
                existing_occupancy = cursor.fetchone()
                if existing_occupancy is None:
                    cursor.execute(
                        "INSERT INTO scheduling_effective_occupancy "
                        "(staff_id,occupancy_date,generation_id,assignment_id,occupancy_type) "
                        "VALUES (%s,%s,%s,%s,'assignment_interval')",
                        (assignment["staff_id"], work_date, generation_id, assignment_id),
                    )
                elif (
                    int(existing_occupancy["generation_id"]),
                    int(existing_occupancy["assignment_id"]),
                    existing_occupancy["occupancy_type"],
                ) != (generation_id, assignment_id, "assignment_interval"):
                    raise RuntimeError(
                        f"fixture staff date conflicts with another effective occupancy: {case_no}/{work_date}"
                    )
    official_dates = sorted(set(official_dates))
    if not official_dates:
        return tuple(assignment_ids)
    if len(official_dates) != int(scenario["service_days"]):
        raise RuntimeError(f"fixture official service day count mismatch: {case_no}")
    fingerprint = _sha("|".join(item.isoformat() for item in official_dates))
    cursor.execute(
        "SELECT id,service_day_count,service_date_fingerprint FROM confirmed_service_date_versions "
        "WHERE case_no=%s AND is_current=1",
        (case_no,),
    )
    current = cursor.fetchone()
    if current and int(current["service_day_count"]) == len(official_dates) and current["service_date_fingerprint"] == fingerprint:
        return tuple(assignment_ids)
    if current:
        cursor.execute(
            "UPDATE confirmed_service_date_versions SET is_current=NULL,invalidated_at_utc=UTC_TIMESTAMP(6) WHERE id=%s",
            (current["id"],),
        )
    cursor.execute(
        "SELECT COALESCE(MAX(version),0)+1 AS next_version FROM confirmed_service_date_versions WHERE case_no=%s",
        (case_no,),
    )
    next_version = int(cursor.fetchone()["next_version"])
    cursor.execute("SELECT lifecycle_version FROM orders WHERE case_no=%s", (case_no,))
    order_version = int(cursor.fetchone()["lifecycle_version"])
    cursor.execute(
        "INSERT INTO confirmed_service_date_versions "
        "(case_no,version,order_version,scheduling_version,service_day_count,service_date_fingerprint,is_current,confirmed_by_actor_id,reason) "
        "VALUES (%s,%s,%s,%s,%s,%s,1,'system:seed','建立真實服務日測試根事實')",
        (case_no, next_version, order_version, scheduling_version, len(official_dates), fingerprint),
    )
    confirmed_version_id = int(cursor.lastrowid)
    cursor.executemany(
        "INSERT INTO confirmed_service_date_days (confirmed_version_id,ordinal,service_date) VALUES (%s,%s,%s)",
        tuple((confirmed_version_id, ordinal, value) for ordinal, value in enumerate(official_dates, start=1)),
    )
    cursor.execute(
        "INSERT INTO confirmed_service_date_receipts "
        "(idempotency_key,command_fingerprint,confirmed_version_id,actor_id) VALUES (%s,%s,%s,'system:seed')",
        (f"line-stage-service-dates:{case_no.lower()}:{next_version}", fingerprint, confirmed_version_id),
    )
    return tuple(assignment_ids)


def _seed_completion_receipt(cursor, case_no: str) -> None:
    cursor.execute(
        "SELECT actual_end_date,service_end_time,service_end_day_offset,lifecycle_version FROM orders WHERE case_no=%s",
        (case_no,),
    )
    order = cursor.fetchone()
    if not order or order["actual_end_date"] is None:
        raise RuntimeError(f"completion fixture lacks actual end date: {case_no}")
    completion_date = order["actual_end_date"] + timedelta(days=int(order["service_end_day_offset"]))
    completion_instant = f"{completion_date.isoformat()} {order['service_end_time']}"
    expected_version = int(order["lifecycle_version"])
    resulting_version = expected_version + 1
    event_key = f"line-stage-completion-event:{case_no.lower()}"
    cursor.execute(
        "INSERT IGNORE INTO order_lifecycle_state_events "
        "(case_no,trigger_event,before_status,after_status,actor,business_date,expected_version,idempotency_key,facts_snapshot) "
        "VALUES (%s,'evaluation_time_reached','服務中','訂單完成','system:seed',%s,%s,%s,%s)",
        (case_no, completion_date, expected_version, event_key, json.dumps({"fixture": "core_stage", "completion_confirmed": True})),
    )
    cursor.execute(
        "SELECT id FROM order_lifecycle_state_events WHERE case_no=%s AND idempotency_key=%s",
        (case_no, event_key),
    )
    lifecycle_event_id = cursor.fetchone()["id"]
    cursor.execute(
        "INSERT IGNORE INTO order_auto_completion_apply_receipts "
        "(idempotency_key,command_fingerprint,case_no,lifecycle_event_id,order_version,completion_instant,evaluation_at,result_snapshot) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
        (
            f"line-stage-completion:{case_no.lower()}",
            _sha(f"line-stage-completion:{case_no}"),
            case_no,
            lifecycle_event_id,
            resulting_version,
            completion_instant,
            completion_instant,
            json.dumps({"fixture": "core_stage", "case_no": case_no}),
        ),
    )
    cursor.execute(
        "UPDATE orders SET status='訂單完成',lifecycle_version=%s WHERE case_no=%s",
        (resulting_version, case_no),
    )


def _seed_cancellation_event(cursor, case_no: str, before_status: str, reason: str) -> None:
    cursor.execute("SELECT lifecycle_version,status FROM orders WHERE case_no=%s", (case_no,))
    order = cursor.fetchone()
    if not order or order["status"] != before_status:
        raise RuntimeError(f"cancellation fixture predecessor mismatch: {case_no}")
    expected_version = int(order["lifecycle_version"])
    event_key = f"line-stage-cancellation:{case_no.lower()}"
    cancellation_fingerprint = _sha(f"line-stage-cancellation:{case_no}:{expected_version}")
    cursor.execute(
        "INSERT IGNORE INTO order_cancellation_events "
        "(case_no,cancellation_date,actual_end_date,official_service_day_count,official_service_hours,confirmed_service_days,"
        "expected_order_version,resulting_order_version,preview_fingerprint,idempotency_key,actor,reason,correlation_id) "
        "VALUES (%s,'2026-09-10',NULL,0,0,%s,%s,%s,%s,%s,'system:seed',%s,%s)",
        (case_no, json.dumps([]), expected_version, expected_version + 1, cancellation_fingerprint,
         event_key, reason, event_key),
    )
    cursor.execute(
        "INSERT IGNORE INTO order_lifecycle_state_events "
        "(case_no,trigger_event,before_status,after_status,actor,business_date,expected_version,idempotency_key,facts_snapshot) "
        "VALUES (%s,'order_cancellation_applied',%s,'訂單取消','system:seed','2026-09-10',%s,%s,%s)",
        (case_no, before_status, expected_version, event_key, json.dumps({"fixture": "order_scenario", "reason": reason})),
    )
    cursor.execute(
        "UPDATE orders SET status='訂單取消',lifecycle_version=%s,cancel_reason=%s WHERE case_no=%s",
        (expected_version + 1, reason, case_no),
    )
    cursor.execute(
        "UPDATE case_staff_assignments SET status='cancelled' WHERE case_no=%s AND status NOT IN ('cancelled','replaced')",
        (case_no,),
    )
    cursor.execute(
        "DELETE FROM scheduling_effective_occupancy WHERE generation_id="
        "(SELECT effective_generation_id FROM scheduling_aggregates WHERE case_no=%s)",
        (case_no,),
    )
    cursor.execute(
        "UPDATE staff_schedule SET effective_marker=NULL WHERE case_no=%s AND effective_marker=1",
        (case_no,),
    )
    cursor.execute(
        "UPDATE scheduling_generations SET status='cancelled',effective_marker=NULL,cancelled_at=UTC_TIMESTAMP() "
        "WHERE id=(SELECT effective_generation_id FROM scheduling_aggregates WHERE case_no=%s)",
        (case_no,),
    )
    cursor.execute(
        "UPDATE scheduling_aggregates SET effective_generation_id=NULL,aggregate_version=aggregate_version+1 WHERE case_no=%s",
        (case_no,),
    )


def _seed_staff_obligation(cursor, case_no: str, assignment_id: int, staff_id: int, *, settled: bool = False) -> None:
    identity = f"line-stage-staff:{case_no}:service"
    idempotency_key = f"line-stage-staff-obligation:{case_no.lower()}"
    cursor.execute("SELECT id FROM staff_obligation_events WHERE idempotency_key=%s", (idempotency_key,))
    row = cursor.fetchone()
    if row:
        event_id = row["id"]
    else:
        cursor.execute(
            "INSERT IGNORE INTO staff_payable_accounts (staff_id,aggregate_version) VALUES (%s,0)",
            (staff_id,),
        )
        cursor.execute(
            "INSERT INTO staff_obligation_events "
            "(obligation_identity,assignment_id,case_no,staff_id,obligation_kind,direction,event_type,before_amount_ntd,"
            "after_amount_ntd,due_date,payroll_fingerprint,expected_payroll_version,resulting_payroll_version,"
            "idempotency_key,actor,reason) VALUES (%s,%s,%s,%s,'service_pay','payable_to_staff','established',"
            "0,54000,'2024-02-01',%s,0,1,%s,'system:seed','建立核心階段月嫂應付 obligation')",
            (identity, assignment_id, case_no, staff_id, _sha(f"line-stage-payroll:{case_no}"), idempotency_key),
        )
        event_id = cursor.lastrowid
    cursor.execute(
        "INSERT INTO staff_obligations "
        "(obligation_identity,assignment_id,case_no,staff_id,obligation_kind,direction,amount_due_ntd,due_date,status,"
        "current_event_id,payroll_version,payout_history_exists) "
        "VALUES (%s,%s,%s,%s,'service_pay','payable_to_staff',54000,'2024-02-01','open',%s,1,0) "
        "ON DUPLICATE KEY UPDATE amount_due_ntd=54000,status='open',current_event_id=VALUES(current_event_id)",
        (identity, assignment_id, case_no, staff_id, event_id),
    )
    cursor.execute(
        "UPDATE payroll_case_accounts SET aggregate_version=1 WHERE case_no=%s",
        (case_no,),
    )
    if not settled:
        return
    cursor.execute(
        "SELECT aggregate_version FROM staff_payable_projections WHERE obligation_identity=%s",
        (identity,),
    )
    existing_projection = cursor.fetchone()
    if existing_projection:
        staff_payables_version = int(existing_projection["aggregate_version"])
    else:
        cursor.execute("SELECT aggregate_version FROM staff_payable_accounts WHERE staff_id=%s", (staff_id,))
        staff_payables_version = int(cursor.fetchone()["aggregate_version"]) + 1
    payout_key = f"line-stage-staff-payout:{case_no.lower()}"
    cursor.execute(
        "INSERT IGNORE INTO staff_payout_events "
        "(staff_id,finance_import_row_id,event_type,amount_ntd,occurred_on,bank_account_identity_hash,"
        "reversal_of_event_id,reconciliation_reference,idempotency_key,actor,reason) "
        "VALUES (%s,NULL,'payout',54000,'2026-09-09',%s,NULL,%s,%s,'system:seed','測試月嫂薪資已結清')",
        (staff_id, _sha(f"fixture-bank:{staff_id}"), payout_key, payout_key),
    )
    cursor.execute("SELECT id FROM staff_payout_events WHERE idempotency_key=%s", (payout_key,))
    payout_event_id = int(cursor.fetchone()["id"])
    cursor.execute(
        "INSERT IGNORE INTO staff_payout_obligation_links "
        "(payout_event_id,obligation_identity,allocated_amount_ntd,allocation_ordinal) VALUES (%s,%s,54000,1)",
        (payout_event_id, identity),
    )
    cursor.execute(
        "UPDATE staff_payable_accounts SET aggregate_version=%s WHERE staff_id=%s",
        (staff_payables_version, staff_id),
    )
    cursor.execute(
        "INSERT INTO staff_payable_projections "
        "(obligation_identity,staff_id,obligation_amount_ntd,net_paid_ntd,balance_ntd,status,aggregate_version,current_event_id) "
        "VALUES (%s,%s,54000,54000,0,'completed',%s,%s) ON DUPLICATE KEY UPDATE "
        "net_paid_ntd=54000,balance_ntd=0,status='completed',aggregate_version=VALUES(aggregate_version),current_event_id=VALUES(current_event_id)",
        (identity, staff_id, staff_payables_version, payout_event_id),
    )
    cursor.execute(
        "UPDATE staff_obligations SET payout_history_exists=1 WHERE obligation_identity=%s",
        (identity,),
    )


def _seed_historical_adoption(cursor, scenario: dict[str, object]) -> None:
    case_no = str(scenario["case_no"])
    digest = _sha(f"line-historical-adoption:{case_no}")
    cursor.execute("SELECT COUNT(*) AS count FROM case_staff_assignments WHERE case_no=%s", (case_no,))
    assignment_count = int(cursor.fetchone()["count"])
    result_by_status = {
        "歷史訂單－未服務": "historical_unserved",
        "歷史訂單－服務中": "historical_in_service",
        "歷史訂單－服務完成": "historical_service_completed",
        "歷史訂單－帳務完成": "historical_service_completed",
    }
    step_by_status = {
        "歷史訂單－未服務": 9,
        "歷史訂單－服務中": 10,
        "歷史訂單－服務完成": 11,
        "歷史訂單－帳務完成": 11,
    }
    snapshot = {
        "outcome": "adopted",
        "result": result_by_status[str(scenario["status"])],
        "operational_baseline_step": step_by_status[str(scenario["status"])],
        "operational_baseline_actual_start_date": scenario.get("actual_start_date"),
        "service_calendar_status": "historical_evidence_preserved",
        "fixture": "line_order_history",
    }
    adoption_status = (
        "歷史訂單－服務完成"
        if str(scenario["status"]) == "歷史訂單－帳務完成"
        else str(scenario["status"])
    )
    cursor.execute("SELECT status,lifecycle_version FROM orders WHERE case_no=%s", (case_no,))
    order = cursor.fetchone()
    if not order or order["status"] != "洽談中":
        raise RuntimeError(f"historical adoption predecessor mismatch: {case_no}")
    adoption_expected_version = int(order["lifecycle_version"])
    adoption_resulting_version = adoption_expected_version + 1
    lifecycle_key = f"line-historical-adoption-lifecycle:{case_no.lower()}"
    cursor.execute(
        "INSERT IGNORE INTO order_lifecycle_state_events "
        "(case_no,trigger_event,before_status,after_status,actor,business_date,expected_version,idempotency_key,facts_snapshot) "
        "VALUES (%s,'historical_order_adoption','洽談中',%s,'system:seed',%s,%s,%s,%s)",
        (
            case_no,
            adoption_status,
            scenario.get("actual_end_date") or scenario["end_date"],
            adoption_expected_version,
            lifecycle_key,
            json.dumps({"fixture": "line_order_history", "result": result_by_status[str(scenario["status"])]}),
        ),
    )
    cursor.execute(
        "SELECT id FROM order_lifecycle_state_events WHERE case_no=%s AND idempotency_key=%s",
        (case_no, lifecycle_key),
    )
    lifecycle_event_id = int(cursor.fetchone()["id"])
    cursor.execute(
        "INSERT IGNORE INTO historical_order_adoption_receipts "
        "(idempotency_key,command_fingerprint,source_event_identity,source_fingerprint,preview_fingerprint,case_no,"
        "outcome,expected_version,resulting_version,lifecycle_event_id,assignment_count,result_snapshot,actor,reason,correlation_id) "
        "VALUES (%s,%s,%s,%s,%s,%s,'adopted',%s,%s,%s,%s,%s,'system:seed','建立可查詢的歷史訂單測試資料',%s)",
        (
            f"line-historical-adoption:{case_no.lower()}", digest,
            f"line-historical-source:{case_no.lower()}", digest, digest, case_no,
            adoption_expected_version, adoption_resulting_version, lifecycle_event_id,
            assignment_count, json.dumps(snapshot),
            f"line-historical-adoption:{case_no.lower()}",
        ),
    )
    cursor.execute(
        "UPDATE orders SET status=%s,lifecycle_version=%s WHERE case_no=%s",
        (adoption_status, adoption_resulting_version, case_no),
    )
    cursor.execute(
        "SELECT id FROM historical_order_adoption_receipts WHERE idempotency_key=%s",
        (f"line-historical-adoption:{case_no.lower()}",),
    )
    receipt_id = cursor.fetchone()["id"]
    cursor.execute(
        "SELECT id,staff_id,assignment_sequence,assigned_start_date,assigned_end_date "
        "FROM case_staff_assignments WHERE case_no=%s ORDER BY assignment_sequence",
        (case_no,),
    )
    for assignment in cursor.fetchall():
        cursor.execute("SELECT name FROM staff WHERE id=%s", (assignment["staff_id"],))
        staff_name = cursor.fetchone()["name"]
        cursor.execute(
            "INSERT IGNORE INTO historical_order_pairing_evidence "
            "(receipt_id,caregiver_ordinal,staff_name,staff_id,resolution,source_start_date,source_end_date,assignment_id,issue_codes) "
            "VALUES (%s,%s,%s,%s,'assignment_candidate',%s,%s,%s,%s)",
            (receipt_id, assignment["assignment_sequence"], staff_name, assignment["staff_id"],
             assignment["assigned_start_date"], assignment["assigned_end_date"], assignment["id"], json.dumps([])),
        )


def _seed_historical_accounting_completion(cursor, case_no: str) -> None:
    """為歷史帳務完成情境建立服務日、客戶與月嫂三個 owner 的完整 lineage。"""
    cursor.execute(
        "SELECT id FROM historical_order_adoption_receipts WHERE case_no=%s ORDER BY id DESC LIMIT 1",
        (case_no,),
    )
    adoption_id = int(cursor.fetchone()["id"])
    cursor.execute(
        "SELECT id,staff_id,planned_hours FROM case_staff_assignments WHERE case_no=%s ORDER BY assignment_sequence",
        (case_no,),
    )
    assignments = cursor.fetchall()
    if len(assignments) != 1:
        raise RuntimeError(f"historical accounting fixture requires one assignment: {case_no}")
    assignment = assignments[0]
    assignment_id = int(assignment["id"])
    staff_id = int(assignment["staff_id"])
    service_days = int(assignment["planned_hours"]) // 9
    service_hours = service_days * 9
    amount = service_hours * 300
    digest = _sha(f"line-historical-accounting:{case_no}")
    cursor.execute(
        "INSERT IGNORE INTO assignment_payroll_rate_snapshots "
        "(assignment_id,policy_version,policy_kind,hourly_rate_ntd,source_identity_status) "
        "VALUES (%s,'approved-rates-v1','citizen',300,'一般市民')",
        (assignment_id,),
    )
    cursor.execute(
        "INSERT IGNORE INTO historical_service_day_events "
        "(event_identity,case_no,historical_adoption_receipt_id,expected_day_revision,resulting_day_revision,"
        "total_actual_service_days,total_actual_service_hours,historical_floor_fee_ntd,client_obligation_amount_ntd,"
        "staff_obligation_amount_ntd,preview_fingerprint,command_fingerprint,idempotency_key,actor_id,reason,"
        "correlation_id,result_snapshot) VALUES (%s,%s,%s,0,1,%s,%s,0,%s,%s,%s,%s,%s,'system:seed',"
        "'建立歷史服務日與帳務測試根事實',%s,%s)",
        (
            f"historical-service-days:{digest}", case_no, adoption_id, service_days, service_hours,
            amount, amount, digest, digest, f"line-historical-accounting:{case_no.lower()}",
            f"line-historical-accounting:{case_no.lower()}",
            json.dumps({"case_no": case_no, "total_actual_service_days": service_days}),
        ),
    )
    cursor.execute(
        "SELECT id FROM historical_service_day_events WHERE idempotency_key=%s",
        (f"line-historical-accounting:{case_no.lower()}",),
    )
    historical_event_id = int(cursor.fetchone()["id"])
    cursor.execute(
        "INSERT IGNORE INTO historical_service_day_items "
        "(event_id,assignment_id,staff_id,item_ordinal,actual_service_days,actual_service_hours,floor_fee_allocated_ntd,"
        "staff_obligation_amount_ntd,payroll_policy_version,payroll_policy_kind,hourly_rate_ntd) "
        "VALUES (%s,%s,%s,1,%s,%s,0,%s,'approved-rates-v1','citizen',300)",
        (historical_event_id, assignment_id, staff_id, service_days, service_hours, amount),
    )
    cursor.execute(
        "INSERT INTO historical_service_day_projections "
        "(case_no,current_event_id,historical_adoption_receipt_id,day_revision,total_actual_service_days,total_actual_service_hours) "
        "VALUES (%s,%s,%s,1,%s,%s) ON DUPLICATE KEY UPDATE current_event_id=VALUES(current_event_id),"
        "historical_adoption_receipt_id=VALUES(historical_adoption_receipt_id),day_revision=1,"
        "total_actual_service_days=VALUES(total_actual_service_days),total_actual_service_hours=VALUES(total_actual_service_hours)",
        (case_no, historical_event_id, adoption_id, service_days, service_hours),
    )

    client_identity = f"historical-service:{case_no}:revision:1:client:receivable_from_client"
    client_event_key = f"line-historical-accounting:{case_no.lower()}:client"
    cursor.execute(
        "INSERT IGNORE INTO client_obligation_events "
        "(obligation_identity,case_no,obligation_type,direction,event_type,before_amount_ntd,after_amount_ntd,"
        "before_due_date,after_due_date,source_event_identity,source_obligation_identity,expected_account_version,"
        "idempotency_key,actor,reason) VALUES (%s,%s,'adjustment','receivable_from_client','established',0,%s,"
        "NULL,NULL,%s,NULL,0,%s,'system:seed','建立歷史客戶應收根事實')",
        (client_identity, case_no, amount, f"historical-service-days:{digest}", client_event_key),
    )
    cursor.execute("SELECT id FROM client_obligation_events WHERE idempotency_key=%s", (client_event_key,))
    client_obligation_event_id = int(cursor.fetchone()["id"])
    cursor.execute(
        "INSERT INTO client_obligations "
        "(obligation_identity,case_no,obligation_type,direction,source_obligation_identity,amount_due_ntd,due_date,status,current_event_id,projection_version) "
        "VALUES (%s,%s,'adjustment','receivable_from_client',NULL,%s,NULL,'open',%s,1) "
        "ON DUPLICATE KEY UPDATE current_event_id=VALUES(current_event_id),projection_version=1",
        (client_identity, case_no, amount, client_obligation_event_id),
    )
    cursor.execute(
        "INSERT IGNORE INTO historical_client_payment_events "
        "(event_identity,case_no,direction,confirmation_kind,payer_role,payee_role,payment_date,payment_date_unknown_reason,"
        "source_availability,evidence_reference,historical_adoption_receipt_id,expected_account_version,resulting_account_version,"
        "idempotency_key,actor_id,reason,correlation_id) VALUES (%s,%s,'receivable_from_client','settled','client','union',"
        "NULL,'歷史來源未保留付款日期','unrecoverable',NULL,%s,1,2,%s,'system:seed','確認歷史客戶款已結清',%s)",
        (f"historical-client-settlement:{case_no}", case_no, adoption_id,
         f"line-historical-client-settlement:{case_no.lower()}", f"line-historical-client-settlement:{case_no.lower()}"),
    )
    cursor.execute(
        "SELECT id FROM historical_client_payment_events WHERE idempotency_key=%s",
        (f"line-historical-client-settlement:{case_no.lower()}",),
    )
    client_payment_event_id = int(cursor.fetchone()["id"])
    cursor.execute(
        "INSERT IGNORE INTO historical_client_payment_obligation_links "
        "(event_id,obligation_identity,amount_snapshot_ntd,obligation_type,obligation_direction,obligation_projection_version,link_ordinal) "
        "VALUES (%s,%s,%s,'adjustment','receivable_from_client',1,1)",
        (client_payment_event_id, client_identity, amount),
    )
    cursor.execute(
        "INSERT INTO historical_client_payment_projections "
        "(obligation_identity,case_no,current_event_id,confirmation_kind,amount_snapshot_ntd,obligation_projection_version,account_version) "
        "VALUES (%s,%s,%s,'settled',%s,1,2) ON DUPLICATE KEY UPDATE current_event_id=VALUES(current_event_id),"
        "confirmation_kind='settled',amount_snapshot_ntd=VALUES(amount_snapshot_ntd),account_version=2",
        (client_identity, case_no, client_payment_event_id, amount),
    )
    cursor.execute("UPDATE client_finance_accounts SET aggregate_version=2 WHERE case_no=%s", (case_no,))

    staff_identity = f"historical-service:{case_no}:revision:1:assignment:{assignment_id}:payable_to_staff"
    staff_event_key = f"line-historical-accounting:{case_no.lower()}:staff:1"
    cursor.execute(
        "SELECT event.expected_staff_payables_version,event.resulting_staff_payables_version "
        "FROM historical_staff_payout_projections projection JOIN historical_staff_payout_events event "
        "ON event.id=projection.current_event_id WHERE projection.obligation_identity=%s",
        (staff_identity,),
    )
    existing_historical_payout = cursor.fetchone()
    if existing_historical_payout:
        expected_staff_payables_version = int(existing_historical_payout["expected_staff_payables_version"])
        resulting_staff_payables_version = int(existing_historical_payout["resulting_staff_payables_version"])
    else:
        cursor.execute("SELECT aggregate_version FROM staff_payable_accounts WHERE staff_id=%s", (staff_id,))
        expected_staff_payables_version = int(cursor.fetchone()["aggregate_version"])
        resulting_staff_payables_version = expected_staff_payables_version + 1
    cursor.execute(
        "INSERT IGNORE INTO staff_obligation_events "
        "(obligation_identity,assignment_id,case_no,staff_id,obligation_kind,direction,source_obligation_identity,event_type,"
        "before_amount_ntd,after_amount_ntd,due_date,payroll_fingerprint,expected_payroll_version,resulting_payroll_version,"
        "idempotency_key,actor,reason) VALUES (%s,%s,%s,%s,'service_pay','payable_to_staff',NULL,'established',0,%s,NULL,%s,0,1,%s,"
        "'system:seed','建立歷史月嫂應付根事實')",
        (staff_identity, assignment_id, case_no, staff_id, amount, digest, staff_event_key),
    )
    cursor.execute("SELECT id FROM staff_obligation_events WHERE idempotency_key=%s", (staff_event_key,))
    staff_obligation_event_id = int(cursor.fetchone()["id"])
    cursor.execute(
        "INSERT INTO staff_obligations "
        "(obligation_identity,assignment_id,case_no,staff_id,obligation_kind,direction,source_obligation_identity,amount_due_ntd,"
        "due_date,status,current_event_id,payroll_version,payout_history_exists) VALUES (%s,%s,%s,%s,'service_pay',"
        "'payable_to_staff',NULL,%s,NULL,'open',%s,1,0) ON DUPLICATE KEY UPDATE current_event_id=VALUES(current_event_id),payroll_version=1",
        (staff_identity, assignment_id, case_no, staff_id, amount, staff_obligation_event_id),
    )
    cursor.execute(
        "INSERT IGNORE INTO historical_staff_payout_events "
        "(event_identity,case_no,staff_id,confirmation_kind,payer_role,payee_role,payment_date,payment_date_unknown_reason,"
        "source_availability,evidence_reference,historical_adoption_receipt_id,expected_staff_payables_version,"
        "resulting_staff_payables_version,idempotency_key,actor_id,reason,correlation_id) VALUES (%s,%s,%s,'settled','union','staff',"
        "NULL,'歷史來源未保留付款日期','unrecoverable',NULL,%s,%s,%s,%s,'system:seed','確認歷史月嫂款已結清',%s)",
        (f"historical-staff-settlement:{case_no}:{staff_id}", case_no, staff_id, adoption_id,
         expected_staff_payables_version, resulting_staff_payables_version,
         f"line-historical-staff-settlement:{case_no.lower()}", f"line-historical-staff-settlement:{case_no.lower()}"),
    )
    cursor.execute(
        "SELECT id FROM historical_staff_payout_events WHERE idempotency_key=%s",
        (f"line-historical-staff-settlement:{case_no.lower()}",),
    )
    staff_payout_event_id = int(cursor.fetchone()["id"])
    cursor.execute(
        "INSERT IGNORE INTO historical_staff_payout_obligation_links "
        "(event_id,obligation_identity,amount_snapshot_ntd,obligation_payroll_version,link_ordinal) VALUES (%s,%s,%s,1,1)",
        (staff_payout_event_id, staff_identity, amount),
    )
    cursor.execute(
        "INSERT INTO historical_staff_payout_projections "
        "(obligation_identity,case_no,staff_id,current_event_id,confirmation_kind,amount_snapshot_ntd,obligation_payroll_version,staff_payables_version) "
        "VALUES (%s,%s,%s,%s,'settled',%s,1,%s) ON DUPLICATE KEY UPDATE current_event_id=VALUES(current_event_id),"
        "confirmation_kind='settled',amount_snapshot_ntd=VALUES(amount_snapshot_ntd),staff_payables_version=VALUES(staff_payables_version)",
        (staff_identity, case_no, staff_id, staff_payout_event_id, amount, resulting_staff_payables_version),
    )
    cursor.execute("UPDATE payroll_case_accounts SET aggregate_version=1 WHERE case_no=%s", (case_no,))
    cursor.execute(
        "UPDATE staff_payable_accounts SET aggregate_version=%s WHERE staff_id=%s",
        (resulting_staff_payables_version, staff_id),
    )
    cursor.execute("SELECT status,lifecycle_version FROM orders WHERE case_no=%s", (case_no,))
    order = cursor.fetchone()
    if not order or order["status"] != "歷史訂單－服務完成":
        raise RuntimeError(f"historical accounting predecessor mismatch: {case_no}")
    expected_order_version = int(order["lifecycle_version"])
    lifecycle_key = f"line-historical-accounting-completed:{case_no.lower()}"
    cursor.execute(
        "INSERT IGNORE INTO order_lifecycle_state_events "
        "(case_no,trigger_event,before_status,after_status,actor,business_date,expected_version,idempotency_key,facts_snapshot) "
        "VALUES (%s,'historical_accounting_settled','歷史訂單－服務完成','歷史訂單－帳務完成',"
        "'system:seed','2026-09-10',%s,%s,%s)",
        (case_no, expected_order_version, lifecycle_key, json.dumps({
            "fixture": "line_order_history",
            "client_settled": True,
            "all_staff_settled": True,
            "service_day_counts_complete": True,
        })),
    )
    cursor.execute(
        "UPDATE orders SET status='歷史訂單－帳務完成',lifecycle_version=%s WHERE case_no=%s",
        (expected_order_version + 1, case_no),
    )


def _seed_post_bootstrap_owner_facts(
    scenario_client_ids: dict[str, int], staff_ids: dict[str, int]
) -> None:
    connection = get_connection()
    cursor = None
    try:
        cursor = connection.cursor(pymysql.cursors.DictCursor)
        import_cases = {
            "CASE-2026-M302", "CASE-2026-M303", "CASE-2026-M304", "CASE-2026-M305",
            "CASE-2026-M306", "CASE-2026-M307", "CASE-2026-M308", "CASE-2026-M309",
            "CASE-2026-M310",
            *(f"CASE-2026-S{ordinal:02d}" for ordinal in range(2, 14)),
        }
        for case_no in sorted(import_cases):
            _seed_import_receipt(cursor, case_no, scenario_client_ids[case_no])
        _seed_contact_pool(cursor, "CASE-2026-S02", staff_ids["staff_1"], "empty")
        _seed_contact_pool(cursor, "CASE-2026-S03", staff_ids["staff_1"], "candidate")
        _seed_contact_pool(cursor, "CASE-2026-S04", staff_ids["staff_1"], "contacted")
        _seed_contact_pool(cursor, "CASE-2026-S05", staff_ids["staff_1"], "replied")

        fully_matched_cases = {
            "CASE-2026-M303", "CASE-2026-M304", "CASE-2026-M305", "CASE-2026-M306",
            "CASE-2026-M307", "CASE-2026-M308", "CASE-2026-M310",
            *(f"CASE-2026-S{ordinal:02d}" for ordinal in range(6, 14)),
        }
        by_case = {str(item["case_no"]): item for item in _ALL_ORDER_SCENARIOS}
        plans = {}
        for case_no in sorted(fully_matched_cases):
            staff_keys = tuple(by_case[case_no].get("staff_keys", ()))
            evidence_staff_id = staff_ids[str(staff_keys[0])] if staff_keys else staff_ids["staff_1"]
            plans[case_no] = _seed_accepted_matching_evidence(cursor, case_no, evidence_staff_id)
        signing_handoff_cases = fully_matched_cases - {"CASE-2026-S06"}
        final_contract_cases = signing_handoff_cases - {"CASE-2026-S07"}
        for case_no in sorted(signing_handoff_cases):
            completed = case_no in final_contract_cases
            _seed_external_signing(cursor, case_no, plans[case_no], completed=completed)

        deposit_open_cases = {"CASE-2026-M303", "CASE-2026-S08"}
        deposit_settled_cases = final_contract_cases - deposit_open_cases
        for case_no in sorted(deposit_open_cases):
            _seed_client_obligation(cursor, case_no, "deposit", settled=False)
        for case_no in sorted(deposit_settled_cases):
            _seed_client_obligation(cursor, case_no, "deposit", settled=True)
        fully_client_settled_cases = {"CASE-2026-M308", "CASE-2026-S13"}
        for case_no in sorted(deposit_settled_cases - {"CASE-2026-M310"}):
            for obligation_type in ("first", "second"):
                _seed_client_obligation(
                    cursor,
                    case_no,
                    obligation_type,
                    settled=case_no in fully_client_settled_cases,
                )
        for case_no in sorted(deposit_settled_cases):
            _seed_contract_completion(cursor, case_no)

        scheduled_cases = {
            "CASE-2026-M305", "CASE-2026-M306", "CASE-2026-M307", "CASE-2026-M308",
            "CASE-2026-M310", "CASE-2026-H301", "CASE-2026-H302", "CASE-2026-H303",
            "CASE-2026-H304", "CASE-2026-H305", "CASE-2026-S10", "CASE-2026-S11",
            "CASE-2026-S12", "CASE-2026-S13",
        }
        assignments_by_case = {
            case_no: _seed_service_schedule(cursor, by_case[case_no])
            for case_no in sorted(scheduled_cases)
        }

        for case_no in (
            "CASE-2026-M305", "CASE-2026-M306", "CASE-2026-M307", "CASE-2026-M308",
            "CASE-2026-S10", "CASE-2026-S11", "CASE-2026-S12", "CASE-2026-S13",
        ):
            _seed_service_start(cursor, case_no)
        for case_no in ("CASE-2026-M307", "CASE-2026-M308", "CASE-2026-S12", "CASE-2026-S13"):
            _seed_completion_receipt(cursor, case_no)
        for case_no, settled in (
            ("CASE-2026-M307", False),
            ("CASE-2026-M308", True),
            ("CASE-2026-S12", True),
            ("CASE-2026-S13", False),
        ):
            assignment_id = assignments_by_case[case_no][0]
            cursor.execute("SELECT staff_id FROM case_staff_assignments WHERE id=%s", (assignment_id,))
            staff_id = int(cursor.fetchone()["staff_id"])
            _seed_staff_obligation(cursor, case_no, assignment_id, staff_id, settled=settled)

        _seed_cancellation_event(cursor, "CASE-2026-M309", "洽談中", "測試情境：成立前取消")
        _seed_cancellation_event(cursor, "CASE-2026-M310", "訂單成立", "測試情境：成立並排班後取消")

        for scenario in _ORDER_SCENARIOS:
            if str(scenario["status"]).startswith("歷史訂單"):
                _seed_historical_adoption(cursor, scenario)
        _seed_historical_accounting_completion(cursor, "CASE-2026-H304")
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        try:
            if cursor is not None:
                cursor.close()
        finally:
            connection.close()


def _verify_fixture_readback() -> dict[str, dict[str, int]]:
    from api.dependencies.orders_stage_projection import (
        get_orders_stage_projection_application,
    )
    from subsystems.orders.core_stage_filter_query import (
        CoreStageProjectionFilterQuery,
        query_core_stage_page,
    )

    dependency = get_orders_stage_projection_application()
    try:
        application = next(dependency)
        active = query_core_stage_page(
            application,
            CoreStageProjectionFilterQuery(page_size=200, workbench_scope="in_progress"),
        )
        completed = query_core_stage_page(
            application,
            CoreStageProjectionFilterQuery(page_size=200, workbench_scope="completed"),
        )
        cancelled = query_core_stage_page(
            application,
            CoreStageProjectionFilterQuery(page_size=200, workbench_scope="cancelled"),
        )
    finally:
        dependency.close()
    historical_counts = {
        code: int(active.historical_lifecycle_counts[code])
        + int(completed.historical_lifecycle_counts[code])
        for code in active.historical_lifecycle_counts
    }
    fixture_items = {
        item.case_no: item
        for page in (active, completed, cancelled)
        for item in page.items
        if item.case_no.startswith("CASE-2026-")
    }
    stage_counts = {str(item["stage_code"]): 0 for item in _CORE_STAGE_SCENARIOS}
    for item in fixture_items.values():
        if item.current_core_stage_code in stage_counts:
            stage_counts[item.current_core_stage_code] += 1
    missing_stages = [code for code, count in stage_counts.items() if count < 1]
    missing_history = [code for code, count in historical_counts.items() if count < 1]
    if missing_stages or missing_history:
        raise RuntimeError(
            "fixture readback incomplete: "
            f"missing_stages={missing_stages}, missing_history={missing_history}"
        )
    expected_stages = {
        str(item["case_no"]): str(item["stage_code"])
        for item in _CORE_STAGE_SCENARIOS
    }
    stage_mismatches = {
        case_no: None if fixture_items.get(case_no) is None else fixture_items[case_no].current_core_stage_code
        for case_no, expected in expected_stages.items()
        if fixture_items.get(case_no) is None
        or fixture_items[case_no].current_core_stage_code != expected
    }
    lifecycle_mismatches = {
        str(item["case_no"]): None
        if fixture_items.get(str(item["case_no"])) is None
        else fixture_items[str(item["case_no"])].lifecycle_status.value
        for item in _ALL_ORDER_SCENARIOS
        if fixture_items.get(str(item["case_no"])) is None
        or fixture_items[str(item["case_no"])].lifecycle_status.value != str(item["status"])
    }
    predecessor_mismatches: dict[str, tuple[tuple[str, str], ...]] = {}
    for case_no, fixture_item in fixture_items.items():
        if fixture_item.branch_type != "normal":
            continue
        if fixture_item.current_core_stage_ordinal is None:
            if fixture_item.lifecycle_status.value != "訂單完成":
                continue
            expected_ordinal = 14
        else:
            expected_ordinal = int(fixture_item.current_core_stage_ordinal)
        mismatches = tuple(
            (stage.code, stage.status)
            for stage in fixture_item.core_stages
            if stage.ordinal < expected_ordinal and stage.status != "completed"
        )
        if mismatches:
            predecessor_mismatches[case_no] = mismatches
    if stage_mismatches or lifecycle_mismatches or predecessor_mismatches:
        raise RuntimeError(
            "fixture projection mismatch: "
            f"stage_mismatches={stage_mismatches}, lifecycle_mismatches={lifecycle_mismatches}, "
            f"predecessor_mismatches={predecessor_mismatches}"
        )

    connection = get_connection()
    cursor = None
    try:
        cursor = connection.cursor(pymysql.cursors.DictCursor)
        cursor.execute(
            "SELECT a.case_no,COUNT(DISTINCT s.work_date) AS scheduled_days,MAX(a.generation_id IS NULL) AS missing_generation "
            "FROM case_staff_assignments a LEFT JOIN staff_schedule s ON s.assignment_id=a.id AND s.generation_id=a.generation_id "
            "AND s.effective_marker=1 AND s.is_work_day=1 WHERE a.case_no LIKE 'CASE-2026-%' "
            "AND a.status NOT IN ('cancelled','replaced') GROUP BY a.case_no"
        )
        schedule_roots = {row["case_no"]: row for row in cursor.fetchall()}
        schedule_mismatches = {
            case_no: schedule_roots.get(case_no)
            for case_no in {
                "CASE-2026-M305", "CASE-2026-M306", "CASE-2026-M307", "CASE-2026-M308",
                "CASE-2026-H301", "CASE-2026-H302", "CASE-2026-H303", "CASE-2026-H304",
                "CASE-2026-H305", "CASE-2026-S10", "CASE-2026-S11", "CASE-2026-S12", "CASE-2026-S13",
            }
            if schedule_roots.get(case_no) is None
            or int(schedule_roots[case_no]["scheduled_days"]) != int(next(item["service_days"] for item in _ALL_ORDER_SCENARIOS if item["case_no"] == case_no))
            or int(schedule_roots[case_no]["missing_generation"]) != 0
        }
        cursor.execute(
            "SELECT a.case_no,COUNT(DISTINCT occupancy.occupancy_date) AS occupied_days "
            "FROM case_staff_assignments a JOIN scheduling_effective_occupancy occupancy "
            "ON occupancy.assignment_id=a.id AND occupancy.generation_id=a.generation_id "
            "WHERE a.case_no LIKE 'CASE-2026-%' AND a.status NOT IN ('cancelled','replaced') "
            "GROUP BY a.case_no"
        )
        occupancy_roots = {row["case_no"]: int(row["occupied_days"]) for row in cursor.fetchall()}
        occupancy_mismatches = {
            case_no: occupancy_roots.get(case_no)
            for case_no in {
                "CASE-2026-M305", "CASE-2026-M306", "CASE-2026-M307", "CASE-2026-M308",
                "CASE-2026-H301", "CASE-2026-H302", "CASE-2026-H303", "CASE-2026-H304",
                "CASE-2026-H305", "CASE-2026-S10", "CASE-2026-S11", "CASE-2026-S12", "CASE-2026-S13",
            }
            if occupancy_roots.get(case_no) != int(next(
                item["service_days"] for item in _ALL_ORDER_SCENARIOS if item["case_no"] == case_no
            ))
        }
        cursor.execute(
            "SELECT case_no,after_status FROM order_lifecycle_state_events WHERE case_no IN "
            "('CASE-2026-M307','CASE-2026-M308','CASE-2026-M309','CASE-2026-M310','CASE-2026-H301',"
            "'CASE-2026-H303','CASE-2026-H304','CASE-2026-S12','CASE-2026-S13')"
        )
        lifecycle_events = {(row["case_no"], row["after_status"]) for row in cursor.fetchall()}
        required_events = {
            ("CASE-2026-M307", "訂單完成"), ("CASE-2026-M308", "訂單完成"),
            ("CASE-2026-M309", "訂單取消"), ("CASE-2026-M310", "訂單取消"),
            ("CASE-2026-H301", "歷史訂單－服務完成"),
            ("CASE-2026-H302", "歷史訂單－服務中"),
            ("CASE-2026-H303", "歷史訂單－服務完成"),
            ("CASE-2026-H304", "歷史訂單－服務完成"),
            ("CASE-2026-H304", "歷史訂單－帳務完成"),
            ("CASE-2026-H305", "歷史訂單－未服務"),
            ("CASE-2026-S12", "訂單完成"), ("CASE-2026-S13", "訂單完成"),
        }
        cursor.execute(
            "SELECT (EXISTS(SELECT 1 FROM historical_service_day_projections WHERE case_no='CASE-2026-H304') "
            "+ EXISTS(SELECT 1 FROM historical_client_payment_projections WHERE case_no='CASE-2026-H304') "
            "+ EXISTS(SELECT 1 FROM historical_staff_payout_projections WHERE case_no='CASE-2026-H304')) AS root_count"
        )
        historical_accounting_root_count = int(cursor.fetchone()["root_count"])
        if (
            schedule_mismatches
            or occupancy_mismatches
            or not required_events.issubset(lifecycle_events)
            or historical_accounting_root_count != 3
        ):
            raise RuntimeError(
                "fixture owner-root mismatch: "
                f"schedule_mismatches={schedule_mismatches}, "
                f"occupancy_mismatches={occupancy_mismatches}, "
                f"missing_lifecycle_events={sorted(required_events - lifecycle_events)}, "
                f"historical_accounting_root_count={historical_accounting_root_count}"
            )
    finally:
        try:
            if cursor is not None:
                cursor.close()
        finally:
            connection.close()
    return {
        "stage_counts": stage_counts,
        "historical_lifecycle_counts": historical_counts,
        "owner_root_counts": {"historical_accounting": historical_accounting_root_count},
    }


def seed_fixtures(verbose: bool = True) -> dict[str, object]:
    app_env = os.getenv("APP_ENV", "development").strip().lower()
    if app_env in {"prod", "production"}:
        raise RuntimeError("此腳本禁止在 production 正式環境執行！")

    conn = get_connection()
    cursor = None

    try:
        cursor = conn.cursor(pymysql.cursors.DictCursor)

        # 1. 客戶資料 (Clients)：生命週期與十三核心階段共用 deterministic 定義。
        scenario_client_ids = {
            str(scenario["case_no"]): _seed_scenario_client(cursor, scenario)
            for scenario in _ALL_ORDER_SCENARIOS
        }
        c1_id = scenario_client_ids["CASE-2026-M301"]
        c2_id = scenario_client_ids["CASE-2026-M302"]

        # Client 3: 李詩涵 (【狀態 B：有案號但缺問卷】專用測試資料)
        cursor.execute("SELECT id FROM clients WHERE name = '李詩涵' AND phone = '0933111222'")
        existing_c3 = cursor.fetchone()
        if existing_c3:
            c3_id = existing_c3['id']
            cursor.execute(
                "UPDATE clients SET case_no='CASE-2026-STATE-B', city='新竹市', address='東區科學園路1號', "
                "identity_status='一般市民', service_days=NULL, due_month='2026-12', service_start_date=NULL, "
                "notes=NULL, baby_info=NULL, residence_type=NULL, delivery_type=NULL, service_type=NULL, "
                "admin_notes='STATE_B_UNFILLED_SURVEY', created_at=NOW(), line_user_id=NULL WHERE id = %s", (c3_id,)
            )
        else:
            cursor.execute(
                "INSERT INTO clients (name, gender, phone, city, address, identity_status, "
                "service_time, due_month, service_start_date, notes, service_days, residence_type, "
                "delivery_type, service_type, baby_info, case_no, line_user_id, admin_notes, created_at) "
                "VALUES ('李詩涵', 'female', '0933111222', '新竹市', '東區科學園路1號', '一般市民', "
                "NULL, '2026-12', NULL, NULL, NULL, NULL, "
                "NULL, NULL, NULL, 'CASE-2026-STATE-B', NULL, 'STATE_B_UNFILLED_SURVEY', NOW())",
            )
            c3_id = cursor.lastrowid

        # 2. 月嫂資料 (Staff)
        # Staff 1: 王美華
        cursor.execute("SELECT id FROM staff WHERE name = '王美華' AND identity_card = 'A234567890'")
        existing_s1 = cursor.fetchone()
        if existing_s1:
            s1_id = existing_s1['id']
            cursor.execute(
                "UPDATE staff SET phone='0923456789', birthday='1980-05-15', city='新竹市', "
                "address='東區建中一路50號', status='active', has_massage_cert=1, "
                "weekly_rest_days=%s, care_babies=1, service_regions=%s, special_skills=%s, "
                "registered_at=NOW(), line_user_id=NULL WHERE id = %s",
                (json.dumps(["週日"]), json.dumps(["新竹市", "新竹縣"]), json.dumps(["產婦催乳按摩", "月子膳食調理"]), s1_id)
            )
        else:
            cursor.execute(
                "INSERT INTO staff (name, identity_card, phone, birthday, city, address, "
                "has_massage_cert, status, weekly_rest_days, care_babies, service_regions, "
                "special_skills, registered_at, line_user_id) "
                "VALUES ('王美華', 'A234567890', '0923456789', '1980-05-15', '新竹市', '東區建中一路50號', "
                "1, 'active', %s, 1, %s, %s, NOW(), NULL)",
                (json.dumps(["週日"]), json.dumps(["新竹市", "新竹縣"]), json.dumps(["產婦催乳按摩", "月子膳食調理"]))
            )
            s1_id = cursor.lastrowid

        # Staff 2: 張淑芬
        cursor.execute("SELECT id FROM staff WHERE name = '張淑芬' AND identity_card = 'B234567891'")
        existing_s2 = cursor.fetchone()
        if existing_s2:
            s2_id = existing_s2['id']
            cursor.execute(
                "UPDATE staff SET phone='0934567890', birthday='1982-08-20', city='新竹市', "
                "address='北區北大路88號', status='active', has_massage_cert=1, "
                "weekly_rest_days=%s, care_babies=1, service_regions=%s, special_skills=%s, "
                "registered_at=NOW(), line_user_id=NULL WHERE id = %s",
                (json.dumps(["週六", "週日"]), json.dumps(["新竹市", "新竹縣"]), json.dumps(["新生兒照護", "嬰幼兒按摩"]), s2_id)
            )
        else:
            cursor.execute(
                "INSERT INTO staff (name, identity_card, phone, birthday, city, address, "
                "has_massage_cert, status, weekly_rest_days, care_babies, service_regions, "
                "special_skills, registered_at, line_user_id) "
                "VALUES ('張淑芬', 'B234567891', '0934567890', '1982-08-20', '新竹市', '北區北大路88號', "
                "1, 'active', %s, 1, %s, %s, NOW(), NULL)",
                (json.dumps(["週六", "週日"]), json.dumps(["新竹市", "新竹縣"]), json.dumps(["新生兒照護", "嬰幼兒按摩"]))
            )
            s2_id = cursor.lastrowid

        extra_staff = (
            ("staff_3", "測試月嫂丙", "C234567892", "0945678901", "1984-03-10"),
            ("staff_4", "測試月嫂丁", "D234567893", "0956789012", "1986-06-12"),
            ("staff_5", "測試月嫂戊", "E234567894", "0967890123", "1988-09-14"),
            ("staff_6", "測試月嫂己", "F234567895", "0978901234", "1990-12-16"),
        )
        extra_staff_ids: dict[str, int] = {}
        for staff_key, name, identity_card, phone, birthday in extra_staff:
            cursor.execute(
                "SELECT id FROM staff WHERE name=%s AND identity_card=%s",
                (name, identity_card),
            )
            existing_staff = cursor.fetchone()
            if existing_staff:
                staff_id = int(existing_staff["id"])
                cursor.execute(
                    "UPDATE staff SET phone=%s,birthday=%s,city='新竹市',address='東區測試路200號',"
                    "status='active',has_massage_cert=1,weekly_rest_days=%s,care_babies=1,service_regions=%s,"
                    "special_skills=%s,registered_at=NOW(),line_user_id=NULL WHERE id=%s",
                    (phone, birthday, json.dumps([]), json.dumps(["新竹市", "新竹縣"]), json.dumps(["新生兒照護"]), staff_id),
                )
            else:
                cursor.execute(
                    "INSERT INTO staff (name,identity_card,phone,birthday,city,address,has_massage_cert,status,"
                    "weekly_rest_days,care_babies,service_regions,special_skills,registered_at,line_user_id) "
                    "VALUES (%s,%s,%s,%s,'新竹市','東區測試路200號',1,'active',%s,1,%s,%s,NOW(),NULL)",
                    (name, identity_card, phone, birthday, json.dumps([]), json.dumps(["新竹市", "新竹縣"]), json.dumps(["新生兒照護"])),
                )
                staff_id = int(cursor.lastrowid)
            extra_staff_ids[staff_key] = staff_id

        # 3. 訂單案件與直接可見的月嫂／帳務變體。
        staff_ids = {"staff_1": int(s1_id), "staff_2": int(s2_id), **extra_staff_ids}
        for scenario in _ALL_ORDER_SCENARIOS:
            _seed_scenario_order(
                cursor,
                scenario,
                scenario_client_ids[str(scenario["case_no"])],
                staff_ids,
            )

        # 4. 清除可能殘留的測試用 LINE 綁定與解除申請 (保留乾淨狀態，遵循 FK 關聯順序)
        cursor.execute("DELETE FROM line_identity_revocation_requests")
        cursor.execute("DELETE FROM line_identity_role_binding_events")
        cursor.execute("DELETE FROM line_identity_role_bindings")
        cursor.execute("DELETE FROM line_identity_bindings")

        # 4.1 確保已發布的 LINE Rich Menu 任務存在 (供解除綁定 M1-06 回復 fallback menu 使用)
        rich_menu_fixtures = [
            ("default_menu", "richmenu-afe3c90c191abd8613ca7f9a06049a7b", "一般用戶選單", "seed-default-menu-publication", "seed-corr-default-menu"),
            ("staff_menu", "richmenu-b1c86786d69f902c79690842dd133afb", "月嫂專屬選單", "seed-staff-menu-publication", "seed-corr-staff-menu"),
            ("union_staff_menu", "richmenu-e5f8b155c10220e5d3296d50c0a8e027", "工會人員專屬選單", "seed-union-staff-menu-publication", "seed-corr-union-staff-menu"),
        ]
        for m_def_id, p_menu_id, m_name, idem_key, corr_id in rich_menu_fixtures:
            cursor.execute(
                "INSERT INTO line_rich_menu_publication_tasks ("
                "  menu_definition_id, configuration_revision, operation, publication_status,"
                "  definition_snapshot, provider_menu_id, idempotency_key, correlation_id, requested_by_actor_id"
                ") VALUES (%s, 1, 'publish', 'published', %s, %s, %s, %s, 'system:seed') "
                "ON DUPLICATE KEY UPDATE publication_status='published', provider_menu_id=%s",
                (m_def_id, json.dumps({"id": m_def_id, "name": m_name}), p_menu_id, idem_key, corr_id, p_menu_id),
            )
            task_id = cursor.lastrowid
            if not task_id:
                cursor.execute("SELECT id FROM line_rich_menu_publication_tasks WHERE idempotency_key=%s", (idem_key,))
                task_id = cursor.fetchone()["id"]
            cursor.execute(
                "INSERT IGNORE INTO line_rich_menu_publication_step_acknowledgements ("
                "  publication_id, step_name, request_fingerprint, idempotency_key, provider_menu_id, acknowledged_at_utc"
                ") VALUES (%s, 'cleanup', '0000000000000000000000000000000000000000000000000000000000000000', %s, %s, UTC_TIMESTAMP(6))",
                (task_id, f"seed-cleanup-ack-{task_id}", p_menu_id),
            )

        # 清理測試中可能產生的重複客戶資料
        cursor.execute(
            "SELECT id FROM clients WHERE id NOT IN (%s, %s, %s) AND (phone IN ('0912345678', '0922333444', '0933111222') OR name IN ('陳雅婷', '林怡君', '李詩涵'))",
            (c1_id, c2_id, c3_id)
        )
        fetchall = getattr(cursor, "fetchall", None)
        extra_clients = fetchall() if callable(fetchall) else []
        extra_client_ids = [
            r["id"] for r in extra_clients
            if isinstance(r, dict) and "id" in r
        ]
        if extra_client_ids:
            format_strings = ','.join(['%s'] * len(extra_client_ids))
            cursor.execute(f"DELETE FROM provisional_client_registrations WHERE client_id IN ({format_strings})", tuple(extra_client_ids))
            cursor.execute(f"DELETE FROM client_profile_change_requests WHERE client_id IN ({format_strings})", tuple(extra_client_ids))
            cursor.execute(f"DELETE FROM clients WHERE id IN ({format_strings})", tuple(extra_client_ids))

        cursor.execute("UPDATE clients SET line_user_id=NULL")
        cursor.execute("UPDATE staff SET line_user_id=NULL")
        cursor.execute("UPDATE provisional_client_registrations SET active_line_user_id=NULL")

        conn.commit()
    finally:
        try:
            if cursor is not None:
                cursor.close()
        finally:
            conn.close()

    # 5. 跨領域架構初始化 (Case Architecture Bootstrap)
    s_gen = get_case_architecture_bootstrap_status_service()
    w_gen = None
    try:
        status_service = next(s_gen)
        w_gen = get_case_architecture_bootstrap_workflow()
        workflow = next(w_gen)

        cases_bootstrapped = []
        for case_no in [str(item["case_no"]) for item in _ALL_ORDER_SCENARIOS]:
            status = status_service.query(case_no)
            if not status.ready and status.recommendation:
                correlation_id = CorrelationId(f"line-seed-prev-{case_no.lower()}")
                preview = workflow.preview(status.recommendation, correlation_id)
                cmd = EnsureCaseArchitectureBootstrap(
                    intent=status.recommendation,
                    expected_order_version=ExpectedVersion(1),
                    preview_fingerprint=preview.fingerprint,
                    idempotency_key=IdempotencyKey(f"line-seed-idem-{case_no.lower()}"),
                    actor=ActorContext(actor_id="admin", permission_scope=("admin", "system_admin")),
                    reason="LINE 模組測試前置架構初始化",
                    correlation_id=CorrelationId(f"line-seed-corr-{case_no.lower()}"),
                )
                workflow.ensure(cmd)
                cases_bootstrapped.append(case_no)
    finally:
        try:
            if w_gen is not None:
                w_gen.close()
        finally:
            s_gen.close()

    # 6. Bootstrap 後再建立各 owner 的正式根事實，讓十三階段皆有獨立案件。
    _seed_post_bootstrap_owner_facts(scenario_client_ids, staff_ids)
    fixture_readback = _verify_fixture_readback()

    result = {
        "status": "ready",
        "client_1": {"id": c1_id, "name": "陳雅婷", "phone": "0912345678", "case_no": "CASE-2026-M301"},
        "client_2": {"id": c2_id, "name": "林怡君", "phone": "0922333444", "case_no": "CASE-2026-M302"},
        "client_3": {"id": c3_id, "name": "李詩涵", "phone": "0933111222", "case_no": "CASE-2026-STATE-B"},
        "staff_1": {"id": s1_id, "name": "王美華", "identity_card": "A234567890", "birthday": "1980-05-15", "phone": "0923456789"},
        "staff_2": {"id": s2_id, "name": "張淑芬", "identity_card": "B234567891", "birthday": "1982-08-20", "phone": "0934567890"},
        "order_scenarios": [
            {"case_no": item["case_no"], "status": item["status"], "scenario": item["scenario"]}
            for item in _ORDER_SCENARIOS
        ],
        "core_stage_scenarios": [
            {"case_no": item["case_no"], "stage_code": item["stage_code"], "scenario": item["scenario"]}
            for item in _CORE_STAGE_SCENARIOS
        ],
        "bootstrapped_cases": cases_bootstrapped,
        "fixture_readback": fixture_readback,
    }

    if verbose:
        print("================================================================================")
        print("✅ LINE 四大模組測試前置資料復原完成！")
        print("================================================================================")
        print("📱 測試客戶 1 (【狀態 A：舊客完全命中】/ M3 主測)：")
        print("   - 姓名：陳雅婷")
        print("   - 手機：0912345678")
        print("   - 案件：CASE-2026-M301 (服務期間 2026-10-05 ~ 2026-11-03)")
        print("   - 預期效果：bind.html 輸入後自動完成綁定，顯示 CASE-2026-M301，無需重填問卷！")
        print("--------------------------------------------------------------------------------")
        print("📱 測試客戶 3 (【狀態 B：有案號但缺問卷】專用測試)：")
        print("   - 姓名：李詩涵")
        print("   - 手機：0933111222")
        print("   - 案件：CASE-2026-STATE-B")
        print("   - 預期效果：bind.html 輸入後提示找到案號，自動預填 姓名+電話+案號 跳轉問卷！")
        print("--------------------------------------------------------------------------------")
        print("📱 測試月嫂 1 (M1-04 / M3 主測)：")
        print("   - 姓名：王美華")
        print("   - 身分證字號：A234567890")
        print("   - 出生年月日：1980-05-15")
        print("   - 手機：0923456789")
        print("--------------------------------------------------------------------------------")
        print("📱 測試月嫂 2 (M3 第二候選月嫂)：")
        print("   - 姓名：張淑芬")
        print("   - 身分證字號：B234567891")
        print("   - 出生年月日：1982-08-20")
        print("--------------------------------------------------------------------------------")
        print("📋 訂單全情境（15 筆）：")
        for item in _ORDER_SCENARIOS:
            print(f"   - {item['case_no']}｜{item['status']}｜{item['scenario']}")
        print("--------------------------------------------------------------------------------")
        print("🧭 十三核心階段（每階段至少 1 筆）：")
        for item in _CORE_STAGE_SCENARIOS:
            print(f"   - {item['case_no']}｜{item['stage_code']}｜{item['scenario']}")
        print("================================================================================")

    return result


if __name__ == "__main__":
    seed_fixtures()
