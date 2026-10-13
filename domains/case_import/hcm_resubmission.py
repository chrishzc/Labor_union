"""
File: hcm_resubmission.py
Description: 保留 HCM 欄位的正式 root 映射與歷史修正事件讀回 facts。
"""

from __future__ import annotations

from dataclasses import dataclass

_FIELD_TARGETS = {
    "報名時間(建檔)": ("clients.created_at",),
    "IP位址": ("clients.ip_address",),
    "姓名": ("clients.name",),
    "性別": ("clients.gender",),
    "行動電話": ("clients.phone",),
    "email": ("clients.email",),
    "縣市": ("clients.city",),
    "預產期/預計服務開始月份": ("clients.due_month",),
    "不符合原因": ("clients.reject_reason",),
    "居住型態": ("clients.residence_type",),
    "生產方式": ("clients.delivery_type",),
    "寶寶資訊": ("clients.baby_info",),
    "服務時間": (
        "orders.service_hours_per_day",
        "orders.service_start_time",
        "orders.service_end_time",
        "orders.service_end_day_offset",
    ),
    "預計服務日期": ("orders.start_date", "orders.end_date"),
    "希望服務天數": ("orders.service_days", "orders.end_date"),
    # 服務方式 is a Client root fact.  The derived Order end date belongs to
    # Orders terms/lifecycle and is never part of this Client correction.
    "服務方式": ("clients.service_type",),
}


@dataclass(frozen=True, slots=True)
class HcmResubmissionFacts:
    review_identity: str
    logical_code: str
    field_path: str
    case_no: str
    client_id: int
    review_binding_id: int
    prior_source_event_identity: str
    review_version: int
    root_fingerprint: str
    client_version: int = 0
    order_version: int = 0


def hcm_field_targets(field_path: str) -> tuple[str, ...]:
    """Return authoritative root targets for review queries and historical evidence."""
    field = _required_text(field_path, "field path")
    if field not in _FIELD_TARGETS:
        raise ValueError("hcm_resubmission_field_not_owned")
    return _FIELD_TARGETS[field]


def _required_text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} is required")
    return value.strip()


__all__ = [
    "HcmResubmissionFacts",
    "hcm_field_targets",
]
