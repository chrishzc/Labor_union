"""Non-citizen LIFF business fields; registration transport owns no case number."""

from __future__ import annotations

from datetime import date, datetime

from shared_kernel.clock import TAIPEI_TIME_ZONE

from domains.case_import.client_import_validation import (
    DELIVERY_TYPE_VALUES,
    EMAIL_PATTERN,
    GENDER_VALUES,
    RESIDENCE_TYPE_VALUES,
    _is_valid_service_time,
)
from domains.clients.profile import CLIENT_PHONE_PATTERN, normalize_client_phone
from domains.case_import.cooking_requirement import normalize_cooking_requirement


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
        "residence_type", "delivery_type", "service_type", "baby_info", "notes", "line_id",
    ):
        value = getattr(intent, name)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{name} is required")
        values[name] = value.strip()
    if len(values["line_id"]) > 50 or len(values["notes"]) > 1000:
        raise ValueError("notes or LINE ID is too long")
    for name, allowed in (
        ("gender", GENDER_VALUES), ("residence_type", RESIDENCE_TYPE_VALUES),
        ("delivery_type", DELIVERY_TYPE_VALUES),
    ):
        if values[name] not in allowed:
            raise ValueError(f"{name} is invalid")
    if not CLIENT_PHONE_PATTERN.fullmatch(normalize_client_phone(intent.phone)):
        raise ValueError("phone is invalid")
    if len(values["email"]) > 100 or not EMAIL_PATTERN.fullmatch(values["email"]):
        raise ValueError("email is invalid")
    if not _is_valid_service_time(values["service_time"]):
        raise ValueError("service_time is invalid")
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
    if not any(survey.get(key) for key in ("是否需要下廚", "是否需要下廚：")):
        raise ValueError("cooking requirement is required")
    normalize_cooking_requirement(survey)
    values["identity_status"] = "非市民"
    return values
