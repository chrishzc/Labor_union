"""
File: non_citizen_registration_application.py
Description: 非市民需求申請之案件意圖投影、重複檢查與歷史非市民案件手動建案。
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import json
from typing import Any, Mapping

from domains.case_import.client_import_validation import _is_valid_service_time
from domains.case_import.cooking_requirement import normalize_cooking_requirement
from domains.case_import.provisional_registration import ProvisionalRegistrationCandidate
from domains.clients.profile import CLIENT_PHONE_PATTERN, normalize_client_phone
from infrastructure.mysql.case_import_repository import (
    CaseImportMySqlUnitOfWork,
    MySqlCaseImportRepository,
)
from infrastructure.mysql.non_citizen_case_number_repository import allocate_non_citizen_case_number
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
from subsystems.client_finance.virtual_account_resolution import build_client_virtual_account

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


def create_manual_non_citizen_case(
    connection,
    payload: Mapping[str, Any],
    actor: str,
) -> dict[str, Any]:
    """Create a new case using the shared annual sequence."""
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

    created_at_utc = datetime.now(timezone.utc)
    with CaseImportMySqlUnitOfWork(connection) as uow:
        case_no = allocate_non_citizen_case_number(connection, created_at_utc)
        va = build_client_virtual_account(case_no)
        with connection.cursor() as cursor:
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
            created_at = created_at_utc.astimezone(TAIPEI_TIME_ZONE).replace(tzinfo=None)

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
                "admin_notes": str(payload.get("admin_notes") or "手動新增非市民新案").strip(),
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
                reason="後台手動新增非市民新案",
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

        uow.commit()

    return {
        "case_no": case_no,
        "virtual_account": va,
        "client_id": receipt.client_id,
        "message": f"非市民新案「{case_no}」建立成功。",
    }
