"""
File: non_citizen_registration.py
Description: 定義非市民 LIFF 申請欄位檢核與年度案號，寶寶資訊僅收單胞胎或雙胞胎並將 LINE ID 維持選填。
"""

from __future__ import annotations

from datetime import date, datetime
import re

from shared_kernel.clock import TAIPEI_TIME_ZONE

from domains.case_import.beclass_correction import VALID_MULTI_BIRTH_COUNTS
from domains.case_import.client_import_validation import (
    DELIVERY_TYPE_VALUES,
    EMAIL_PATTERN,
    GENDER_VALUES,
    RESIDENCE_TYPE_VALUES,
)
from domains.case_import.refund_account import normalize_refund_field
from domains.clients.profile import CLIENT_PHONE_PATTERN, VALID_RESIDENCE_TYPES, normalize_client_phone
from domains.case_import.cooking_requirement import normalize_cooking_requirement


_SERVICE_TIME = re.compile(
    r"(?P<start>(?:[01][0-9]|2[0-3]):[0-5][0-9])-"
    r"(?P<end>(?:[01][0-9]|2[0-3]):[0-5][0-9]) \((?P<hours>[48])小時\)"
)
LIFF_SERVICE_TIME_OPTIONS = (
    "08:30-12:30 (4小時)",
    "08:30-16:30 (8小時)",
    "09:00-17:00 (8小時)",
    "13:00-17:00 (4小時)",
)


def validate_non_citizen_service_time(value: str) -> None:
    match = _SERVICE_TIME.fullmatch(value)
    if match is not None:
        start, end = (datetime.strptime(match[field], "%H:%M") for field in ("start", "end"))
        if (end - start).total_seconds() == int(match["hours"]) * 3600:
            return
    raise ValueError("服務時段須為同一天，起訖時間差須等於所選的 4 或 8 小時。")


def non_citizen_case_number(approved_at: datetime, sequence: int) -> str:
    """Use the Taipei approval year, not submission or service dates."""
    if approved_at.tzinfo is None or isinstance(sequence, bool) or not 1 <= sequence <= 999:
        raise ValueError("non_citizen_case_number_invalid")
    year = approved_at.astimezone(TAIPEI_TIME_ZONE).year - 1911
    if not 1 <= year <= 999:
        raise ValueError("non_citizen_case_year_invalid")
    return f"A{year:03d}{sequence:03d}"


def non_citizen_client_fields(intent) -> dict[str, str]:
    """Validate the merged intake without changing HCM/subsidy validation."""
    values = {}
    for name in (
        "gender", "email", "city", "service_start_date", "service_time",
        "residence_type", "delivery_type", "service_type", "baby_info", "notes",
    ):
        value = getattr(intent, name)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{name} is required")
        values[name] = value.strip()
    if len(values["notes"]) > 1000:
        raise ValueError("notes is too long")
    if intent.line_id is not None:
        if not isinstance(intent.line_id, str):
            raise ValueError("line_id is invalid")
        line_id = intent.line_id.strip()
        if len(line_id) > 50:
            raise ValueError("LINE ID is too long")
        if line_id:
            values["line_id"] = line_id
    for name, allowed in (
        ("gender", GENDER_VALUES), ("residence_type", RESIDENCE_TYPE_VALUES | VALID_RESIDENCE_TYPES),
        ("delivery_type", DELIVERY_TYPE_VALUES),
        ("baby_info", VALID_MULTI_BIRTH_COUNTS),
    ):
        if values[name] not in allowed:
            raise ValueError(f"{name} is invalid")
    if not CLIENT_PHONE_PATTERN.fullmatch(normalize_client_phone(intent.phone)):
        raise ValueError("phone is invalid")
    if len(values["email"]) > 100 or not EMAIL_PATTERN.fullmatch(values["email"]):
        raise ValueError("email is invalid")
    if values["service_time"] not in LIFF_SERVICE_TIME_OPTIONS:
        raise ValueError("請選擇表單提供的四個服務時段之一。")
    date.fromisoformat(values["service_start_date"])
    if not intent.birth_date:
        raise ValueError("birth_date is required")
    date.fromisoformat(intent.birth_date)
    survey = intent.survey_details
    for field in ("服務時間內是否有其他寶寶", "補助款退款:銀行代號+分行代號", "銀行帳號"):
        if not isinstance(survey.get(field), str) or not survey[field].strip():
            raise ValueError("required survey field is missing")
    bank_code = survey["補助款退款:銀行代號+分行代號"].strip()
    if len(bank_code) != 7 or not bank_code.isascii() or not bank_code.isdigit():
        raise ValueError("refund bank code is invalid")
    if normalize_refund_field(survey["銀行帳號"], bank=False) is None:
        raise ValueError("refund account number is required")
    if not any(survey.get(key) for key in ("是否需要下廚", "是否需要下廚：")):
        raise ValueError("cooking requirement is required")
    normalize_cooking_requirement(survey)
    values["identity_status"] = "非市民"
    return values
