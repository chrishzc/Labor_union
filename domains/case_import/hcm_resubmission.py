"""
File: hcm_resubmission.py
Description: 限定 HCM 修正來源只能採納 prior warning 指定欄位的領域契約。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

_FIELD_TARGETS = {
    "報名時間(建檔)": ("clients.created_at",),
    "IP位址": ("clients.ip_address",),
    "姓名": ("clients.name",),
    "性別": ("clients.gender",),
    "行動電話": ("clients.phone",),
    "縣市": ("clients.city",),
    "預產期/預計服務開始月份": ("clients.due_month",),
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


@dataclass(frozen=True, slots=True)
class HcmFieldCorrectionCandidate:
    review_identity: str
    case_no: str
    source_field: str
    target_fields: tuple[str, ...]
    target_values: Mapping[str, object]


def build_hcm_field_correction_candidate(
    facts: HcmResubmissionFacts,
    corrected_record: Mapping[str, object],
    validation_errors: Mapping[str, str],
    corrected_target_values: Mapping[str, object],
) -> HcmFieldCorrectionCandidate:
    """Build a zero-ambiguity, single-warning correction candidate.

    A complete workbook is validation input only.  Its other valid cells never
    expand the formal write set beyond the warning's field path.
    """
    if facts.logical_code not in {"HCM-FIELD-001", "HCM-FIELD-002"}:
        raise ValueError("hcm_resubmission_field_scope_ambiguous")
    field = _required_text(facts.field_path, "field path")
    targets = _FIELD_TARGETS.get(field)
    if targets is None:
        raise ValueError("hcm_resubmission_field_not_owned")
    if field in validation_errors:
        raise ValueError("hcm_resubmission_field_still_invalid")
    if field not in corrected_record or corrected_record[field] is None:
        raise ValueError("hcm_resubmission_field_missing")
    target_values = {str(key): value for key, value in corrected_target_values.items()}
    if set(target_values) != set(targets) or any(value is None for value in target_values.values()):
        raise ValueError("hcm_resubmission_target_values_invalid")
    return HcmFieldCorrectionCandidate(
        review_identity=_required_text(facts.review_identity, "review identity"),
        case_no=_required_text(facts.case_no, "case number"),
        source_field=field,
        target_fields=targets,
        target_values=target_values,
    )


def hcm_field_targets(field_path: str) -> tuple[str, ...]:
    """Return the fixed formal targets for one warning field, or fail closed."""
    field = _required_text(field_path, "field path")
    if field not in _FIELD_TARGETS:
        raise ValueError("hcm_resubmission_field_not_owned")
    return _FIELD_TARGETS[field]


def _required_text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} is required")
    return value.strip()


__all__ = [
    "HcmFieldCorrectionCandidate",
    "HcmResubmissionFacts",
    "build_hcm_field_correction_candidate",
    "hcm_field_targets",
]
