"""
File: non_citizen_registration_application.py
Description: 非市民需求申請之案件意圖投影、重複檢查與歷史非市民案件手動建案。
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from hashlib import sha256
import json
import re
from typing import Any, Mapping

from domains.case_import.client_import_validation import _is_valid_service_time
from domains.case_import.cooking_requirement import normalize_cooking_requirement
from domains.case_import.provisional_registration import ProvisionalRegistrationCandidate
from domains.clients.profile import CLIENT_PHONE_PATTERN, normalize_client_phone
from infrastructure.mysql.case_import_repository import (
    CaseImportMySqlUnitOfWork,
    MySqlCaseImportRepository,
)
from shared_kernel.clock import TAIPEI_TIME_ZONE
from shared_kernel.identities import (
    ActorContext,
    CorrelationId,
    ExpectedVersion,
    IdempotencyKey,
)
from subsystems.case_import.case_import_workflow import (
    ApplyCaseImport,
    CaseImportWorkflow,
)
from subsystems.case_import.hcm_adapter import (
    build_hcm_case_import_intent,
    calculate_hcm_service_end_date,
)

_VIRTUAL_ACCOUNT_PATTERN = re.compile(r"^99781699([0-9]{3})([0-9]{3})$")


def non_citizen_case_intent(
    candidate: ProvisionalRegistrationCandidate,
    case_no: str,
    approved_at: datetime,
    registration_id: int,
    holidays: set[date],
):
    # Reuse the existing field-to-owner projection, not the HCM file intake.
    record = {key: value for key, value in candidate.client_payload.items() if key != "line_user_id"}
    record.update(
        case_no=case_no,
        created_at=approved_at.astimezone(TAIPEI_TIME_ZONE).replace(tzinfo=None),
        service_start_date=date.fromisoformat(record["service_start_date"]),
    )
    end = calculate_hcm_service_end_date(
        record["service_start_date"],
        record["service_days"],
        record["service_type"],
        holidays,
    )
    return build_hcm_case_import_intent(
        record,
        end,
        requires_cooking=normalize_cooking_requirement(candidate.beclass_payload["survey_details"]),
        provisional_registration_id=registration_id,
        pricing_identity_rule="non_citizen",
    )


def check_case_number_duplicate(cursor, case_no: str) -> bool:
    """Check if case_no already exists in orders or clients."""
    cursor.execute(
        "SELECT case_no FROM orders WHERE case_no=%s "
        "UNION "
        "SELECT case_no FROM clients WHERE case_no=%s LIMIT 1",
        (case_no, case_no),
    )
    return cursor.fetchone() is not None


def check_case_accounting_details(cursor, case_no: str) -> tuple[bool, int, str]:
    """Check if an order has any accounting records or received payments.

    Returns (has_accounting_details, received_total_ntd, summary_text)
    """
    cursor.execute(
        "SELECT COALESCE(SUM(CASE ledger.entry_type "
        "WHEN 'receipt' THEN allocation.amount_ntd "
        "WHEN 'adjustment' THEN allocation.amount_ntd "
        "WHEN 'refund' THEN -allocation.amount_ntd "
        "WHEN 'reversal' THEN -allocation.amount_ntd END),0) "
        "AS received_total_ntd FROM client_obligations obligation "
        "JOIN client_ledger_obligation_allocations allocation "
        "ON allocation.obligation_identity=obligation.obligation_identity "
        "JOIN client_ledger_entries ledger ON ledger.id=allocation.ledger_entry_id "
        "WHERE obligation.case_no=%s AND obligation.direction='receivable_from_client' "
        "AND obligation.obligation_type IN ('deposit','first','second','adjustment')",
        (case_no,),
    )
    row = cursor.fetchone()
    received_total = int(row["received_total_ntd"] if isinstance(row, dict) else (row[0] or 0)) if row else 0

    cursor.execute("SELECT COUNT(*) AS cnt FROM client_ledger_entries WHERE case_no=%s", (case_no,))
    row = cursor.fetchone()
    ledger_count = int(row["cnt"] if isinstance(row, dict) else row[0]) if row else 0

    cursor.execute(
        "SELECT COUNT(*) AS cnt FROM client_obligations WHERE case_no=%s AND status IN ('paid', 'partially_paid', 'settled')",
        (case_no,),
    )
    row = cursor.fetchone()
    paid_obligations_count = int(row["cnt"] if isinstance(row, dict) else row[0]) if row else 0

    has_details = received_total > 0 or ledger_count > 0 or paid_obligations_count > 0
    if has_details:
        summary = f"已有帳務紀錄（入帳金額：NT$ {received_total:,}，帳務明細 {ledger_count} 筆）"
    else:
        summary = "無帳務明細與收款紀錄"
    return has_details, received_total, summary


def check_virtual_account_conflict(
    cursor,
    virtual_account: str,
    current_case_no: str | None = None,
) -> dict[str, Any]:
    """Inspect whether a virtual account is tied to another case."""
    va = str(virtual_account).strip()
    match = _VIRTUAL_ACCOUNT_PATTERN.fullmatch(va)
    if not match:
        raise ValueError("虛擬帳號格式不正確，必須為 99781699 開頭之 14 碼數字。")

    conflict_case_no = None

    # 1. Check legacy virtual account mappings
    cursor.execute(
        "SELECT case_no FROM client_legacy_virtual_accounts WHERE virtual_account=%s ORDER BY id DESC LIMIT 1",
        (va,),
    )
    row = cursor.fetchone()
    if row is not None:
        c_no = str(row.get("case_no") if isinstance(row, dict) else row[0])
        if c_no != current_case_no:
            conflict_case_no = c_no

    # 2. If no legacy mapping conflict, check formula candidate in orders
    if conflict_case_no is None:
        roc_year, seq_str = match.groups()
        seq = int(seq_str)
        if seq > 500:
            formula_case_no = f"A{roc_year}{seq - 500:03d}"
        else:
            formula_case_no = f"{roc_year}{seq:06d}"
        if formula_case_no != current_case_no:
            cursor.execute("SELECT case_no FROM orders WHERE case_no=%s", (formula_case_no,))
            if cursor.fetchone() is not None:
                cursor.execute(
                    "SELECT virtual_account FROM client_legacy_virtual_accounts WHERE case_no=%s",
                    (formula_case_no,),
                )
                override_row = cursor.fetchone()
                if override_row is None or str(override_row.get("virtual_account") if isinstance(override_row, dict) else override_row[0]) == va:
                    conflict_case_no = formula_case_no

    if conflict_case_no is None:
        return {
            "conflict": False,
            "virtual_account": va,
            "conflict_case_no": None,
            "conflict_case_status": None,
            "conflict_case_client_name": None,
            "conflict_case_client_phone": None,
            "has_accounting_details": False,
            "received_total_ntd": 0,
            "accounting_description": "此虛擬帳號無衝突，可正常使用。",
            "cancel_reason": None,
        }

    cursor.execute(
        "SELECT o.case_no, o.status, o.cancel_reason, c.name, c.phone "
        "FROM orders o "
        "LEFT JOIN clients c ON c.id=o.client_id "
        "WHERE o.case_no=%s",
        (conflict_case_no,),
    )
    order_info = cursor.fetchone() or {}
    status = str(order_info.get("status") if isinstance(order_info, dict) else "") or "未知"
    cancel_reason = (
        str(order_info.get("cancel_reason") if isinstance(order_info, dict) else "")
        if order_info.get("cancel_reason")
        else None
    )
    name = str(order_info.get("name") if isinstance(order_info, dict) else "") or ""
    phone = str(order_info.get("phone") if isinstance(order_info, dict) else "") or ""

    has_details, received_total, summary = check_case_accounting_details(cursor, conflict_case_no)

    return {
        "conflict": True,
        "virtual_account": va,
        "conflict_case_no": conflict_case_no,
        "conflict_case_status": status,
        "conflict_case_client_name": name,
        "conflict_case_client_phone": phone,
        "has_accounting_details": has_details,
        "received_total_ntd": received_total,
        "accounting_description": summary,
        "cancel_reason": cancel_reason,
    }


def create_manual_non_citizen_case(
    connection,
    payload: Mapping[str, Any],
    actor: str,
) -> dict[str, Any]:
    """Atomically create a non-citizen case with full field customization, validation, and optional conflict override."""
    case_no = str(payload.get("case_no") or "").strip()
    if not case_no:
        raise ValueError("請輸入案件編號。")
    if len(case_no) > 50:
        raise ValueError("案件編號不可超過 50 個字元。")

    va = str(payload.get("virtual_account") or "").strip()
    if not va:
        raise ValueError("請輸入虛擬帳號。")

    name = str(payload.get("name") or "").strip()
    if not name:
        raise ValueError("請輸入客戶姓名。")

    phone_raw = str(payload.get("phone") or "").strip()
    if not phone_raw:
        raise ValueError("請輸入連絡電話。")
    phone = normalize_client_phone(phone_raw)
    if not CLIENT_PHONE_PATTERN.fullmatch(phone):
        raise ValueError("連絡電話格式不正確（需為有效手機號碼 09xxxxxxxx 或市話）。")

    service_start_raw = payload.get("service_start_date")
    if not service_start_raw:
        raise ValueError("請輸入預計服務開始日。")
    service_start_date = (
        date.fromisoformat(str(service_start_raw))
        if not isinstance(service_start_raw, date)
        else service_start_raw
    )

    service_days_raw = payload.get("service_days")
    if service_days_raw is None or isinstance(service_days_raw, bool):
        raise ValueError("請輸入服務天數。")
    try:
        service_days = int(service_days_raw)
        if service_days <= 0:
            raise ValueError()
    except (ValueError, TypeError):
        raise ValueError("服務天數必須為大於 0 的整數。")

    service_time = str(payload.get("service_time") or "").strip()
    if not service_time or not _is_valid_service_time(service_time):
        raise ValueError("服務時段格式不正確，需包含每日時數（如 8小時）與起訖時間（如 09:00-18:00）。")

    override_conflict = bool(payload.get("override_conflict", False))
    override_case_no = (
        str(payload.get("override_case_no") or "").strip()
        if payload.get("override_case_no")
        else None
    )

    with CaseImportMySqlUnitOfWork(connection) as uow:
        with connection.cursor() as cursor:
            # 1. Check case_no duplicate
            if check_case_number_duplicate(cursor, case_no):
                raise ValueError(f"案件編號「{case_no}」已存在，不能與現有案件重複。")

            # 2. Check virtual account conflict
            conflict_info = check_virtual_account_conflict(cursor, va, current_case_no=case_no)
            if conflict_info["conflict"]:
                if not override_conflict:
                    raise ValueError(
                        f"虛擬帳號「{va}」已被案件「{conflict_info['conflict_case_no']}」使用（狀態：{conflict_info['conflict_case_status']}，{conflict_info['accounting_description']}）。請手動決定是否覆蓋。"
                    )
                if override_case_no and override_case_no != conflict_info["conflict_case_no"]:
                    raise ValueError(
                        f"覆蓋案件編號「{override_case_no}」與衝突案件「{conflict_info['conflict_case_no']}」不相符。"
                    )

                cursor.execute(
                    "DELETE FROM client_legacy_virtual_accounts WHERE virtual_account=%s",
                    (va,),
                )
                if conflict_info["conflict_case_status"] == "訂單取消":
                    cursor.execute(
                        "UPDATE orders SET admin_notes=CONCAT(COALESCE(admin_notes, ''), "
                        "'\\n[帳號頂替] 虛擬帳號已被歷史非市民案件 ', %s, ' 頂替覆蓋。') WHERE case_no=%s",
                        (case_no, conflict_info["conflict_case_no"]),
                    )

            # 3. Read holidays for service_end_date calculation if needed
            cursor.execute("SELECT holiday_date FROM holidays")
            holidays = {
                row["holiday_date"] if isinstance(row, dict) else row[0]
                for row in cursor.fetchall()
            }

            service_type = str(payload.get("service_type") or "連續服務").strip()
            service_end_raw = payload.get("service_end_date")
            if service_end_raw:
                service_end_date = (
                    date.fromisoformat(str(service_end_raw))
                    if not isinstance(service_end_raw, date)
                    else service_end_raw
                )
            else:
                calculated_end = calculate_hcm_service_end_date(
                    service_start_date, service_days, service_type, holidays
                )
                service_end_date = calculated_end or (service_start_date + timedelta(days=service_days - 1))

            requires_cooking = bool(payload.get("requires_cooking", False))
            created_at = datetime.now(timezone.utc).astimezone(TAIPEI_TIME_ZONE).replace(tzinfo=None)

            birth_date_raw = payload.get("birth_date")
            birth_date = str(birth_date_raw).strip() if birth_date_raw else None
            due_month = str(payload.get("due_month") or service_start_date.strftime("%Y-%m")).strip()

            record = {
                "case_no": case_no,
                "name": name,
                "phone": phone,
                "gender": str(payload.get("gender") or "女").strip(),
                "identity_status": "非市民",
                "service_start_date": service_start_date,
                "service_days": service_days,
                "service_time": service_time,
                "service_type": service_type,
                "delivery_type": str(payload.get("delivery_type") or "自然產").strip(),
                "residence_type": str(payload.get("residence_type") or "電梯大樓").strip(),
                "baby_info": str(payload.get("baby_info") or "單胞胎").strip(),
                "city": str(payload.get("city") or "").strip(),
                "address": str(payload.get("address") or "").strip(),
                "due_month": due_month,
                "email": str(payload.get("email") or "").strip(),
                "birth_date": birth_date or "",
                "line_id": str(payload.get("line_id") or "").strip(),
                "notes": str(payload.get("notes") or "").strip(),
                "admin_notes": str(payload.get("admin_notes") or "手動新增非市民案件（補齊歷史案件）").strip(),
                "created_at": created_at,
            }

            intent = build_hcm_case_import_intent(
                record,
                planned_end_date=service_end_date,
                requires_cooking=requires_cooking,
                provisional_registration_id=None,
                pricing_identity_rule="non_citizen",
            )

            workflow = CaseImportWorkflow(MySqlCaseImportRepository(connection), lambda: None)
            correlation = CorrelationId(f"manual-non-citizen:{case_no}")
            preview = workflow.preview(intent, correlation)
            receipt = workflow.apply_in_current_uow(ApplyCaseImport(
                intent=intent,
                expected_import_version=ExpectedVersion(preview.import_version),
                preview_fingerprint=preview.fingerprint,
                idempotency_key=IdempotencyKey(f"manual-non-citizen:{case_no}"),
                actor=ActorContext(actor),
                reason="後台手動新增非市民案件（補齊歷史案件）",
                correlation_id=correlation,
            ))

            refund_bank_code = str(payload.get("refund_bank_code") or "").strip()
            refund_account_no = str(payload.get("refund_account_no") or "").strip()
            survey = {
                "服務時間內是否有其他寶寶": "否",
                "是否需要下廚": "是" if requires_cooking else "否",
                "補助款退款:銀行代號+分行代號": refund_bank_code or "0000000",
                "銀行帳號": refund_account_no or "000000000000",
                "_source": "manual_non_citizen_creation",
                "_created_at": created_at.isoformat(),
            }
            cursor.execute(
                "INSERT INTO beclass_records (name, email, birth_date, phone, city, address, "
                "refund_bank_code, refund_account_no, created_at, query_no, bound_case_no, client_id, survey_details) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, UTC_TIMESTAMP(), %s, %s, %s, %s)",
                (
                    name, record["email"], birth_date, phone, record["city"], record["address"],
                    refund_bank_code, refund_account_no,
                    case_no, case_no, receipt.client_id,
                    json.dumps(survey, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
                ),
            )

            source_content = json.dumps(
                {"case_no": case_no, "virtual_account": va, "source": "manual_non_citizen"},
                sort_keys=True,
            ).encode("utf-8")
            source_digest = sha256(source_content).hexdigest()
            cursor.execute(
                "INSERT INTO client_legacy_virtual_accounts (case_no, virtual_account, source_content_digest, source_row, created_by) "
                "VALUES (%s, %s, %s, 2, %s)",
                (case_no, va, source_digest, actor),
            )

        uow.commit()

    return {
        "case_no": case_no,
        "virtual_account": va,
        "client_id": receipt.client_id,
        "overridden_case_no": conflict_info["conflict_case_no"] if conflict_info["conflict"] and override_conflict else None,
        "message": f"歷史非市民案件「{case_no}」建立成功。" + (f"（已覆蓋原案件「{conflict_info['conflict_case_no']}」之虛擬帳號）" if conflict_info["conflict"] and override_conflict else ""),
    }
