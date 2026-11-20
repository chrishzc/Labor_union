"""Named registration answers shared by query and effective corrections."""

import json
import re
from collections.abc import Mapping
from domains.case_import.refund_account import mask_refund_values

REGISTRATION_DETAIL_FIELDS = ("id_number", "holiday_double_pay")
HOLIDAY_DOUBLE_PAY_SURVEY_FIELD = "三節假日是否願意支付雙倍薪水"
_FULLWIDTH_ASCII = str.maketrans({chr(code): chr(code - 0xFEE0) for code in range(0xFF01, 0xFF5F)})


def mask_beclass_values(values: Mapping[str, object]) -> dict[str, object]:
    result = mask_refund_values(values)
    if result.get("id_number"):
        result["id_number"] = "**********"
    return result


def normalize_id_number(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("id_number_invalid")
    candidate = value.strip().translate(_FULLWIDTH_ASCII).upper()
    if not candidate:
        return None
    if not re.fullmatch(r"[A-Z][0-9]{9}", candidate):
        raise ValueError("id_number_invalid")
    return candidate


def normalize_holiday_double_pay(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("holiday_double_pay_invalid")
    candidate = value.strip()
    if not candidate:
        return None
    if candidate not in {"是", "否"}:
        raise ValueError("holiday_double_pay_invalid")
    return candidate


def project_registration_details(raw: object) -> dict[str, str | None]:
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (ValueError, TypeError):
            raw = None
    survey = raw if isinstance(raw, Mapping) else {}
    try:
        id_number = normalize_id_number(survey.get("身分證字號"))
    except ValueError:
        id_number = None
    try:
        holiday_double_pay = normalize_holiday_double_pay(survey.get(HOLIDAY_DOUBLE_PAY_SURVEY_FIELD))
    except ValueError:
        holiday_double_pay = None
    return {"id_number": id_number, "holiday_double_pay": holiday_double_pay}
