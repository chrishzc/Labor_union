"""
File: hcm_resubmission_source.py
Description: 將已驗證 HCM 修正列轉成單一 warning 欄位的固定 formal target values。
"""

from __future__ import annotations

from datetime import date
from typing import Mapping

from domains.case_import.hcm_resubmission import hcm_field_targets
from subsystems.case_import.hcm_adapter import (
    calculate_hcm_service_end_date,
    parse_hcm_service_time,
)


_CLIENT_FIELDS = {
    "報名時間(建檔)": "created_at", "IP位址": "ip_address", "姓名": "name",
    "性別": "gender", "行動電話": "phone", "縣市": "city",
    "身分資格": "identity_status", "預產期/預計服務開始月份": "due_month",
    "居住型態": "residence_type", "生產方式": "delivery_type", "寶寶資訊": "baby_info",
}


def hcm_resubmission_target_values(
    field_path: str,
    normalized_record: Mapping[str, object],
    *,
    holiday_dates: set[date],
) -> dict[str, object]:
    """Return exactly the formal targets derived from one warning field."""
    expected = hcm_field_targets(field_path)
    if field_path in _CLIENT_FIELDS:
        value = normalized_record.get(_CLIENT_FIELDS[field_path])
        return _exact(expected, {expected[0]: value})
    start = normalized_record.get("service_start_date")
    days = normalized_record.get("service_days")
    kind = normalized_record.get("service_type")
    if not isinstance(start, date) or not isinstance(days, int) or not isinstance(kind, str):
        raise ValueError("hcm_resubmission_service_terms_incomplete")
    end = calculate_hcm_service_end_date(start, days, kind, holiday_dates)
    if end is None:
        raise ValueError("hcm_resubmission_service_terms_incomplete")
    if field_path == "服務時間":
        hours, start_time, end_time, end_offset = parse_hcm_service_time(str(normalized_record.get("service_time") or ""))
        return _exact(expected, {
            "orders.service_hours_per_day": hours,
            "orders.service_start_time": start_time,
            "orders.service_end_time": end_time,
            "orders.service_end_day_offset": end_offset,
        })
    if field_path == "預計服務日期":
        return _exact(expected, {"orders.start_date": start, "orders.end_date": end})
    if field_path == "希望服務天數":
        return _exact(expected, {"orders.service_days": days, "orders.end_date": end})
    if field_path == "服務方式":
        return _exact(expected, {"orders.service_type": kind, "orders.end_date": end})
    raise ValueError("hcm_resubmission_field_not_owned")


def _exact(expected: tuple[str, ...], values: dict[str, object]) -> dict[str, object]:
    if set(values) != set(expected) or any(value is None for value in values.values()):
        raise ValueError("hcm_resubmission_target_values_invalid")
    return values


__all__ = ["hcm_resubmission_target_values"]
