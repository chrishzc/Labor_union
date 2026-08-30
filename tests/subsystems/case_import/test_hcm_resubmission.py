"""
File: test_hcm_resubmission.py
Description: 驗證 HCM 修正來源只能更新 prior warning 的固定欄位集合。
"""

from __future__ import annotations

import pytest
from datetime import date
from pathlib import Path

from domains.case_import.hcm_resubmission import (
    HcmResubmissionFacts,
    build_hcm_field_correction_candidate,
    hcm_field_targets,
)
from subsystems.case_import.hcm_resubmission_source import hcm_resubmission_target_values


ROOT = Path(__file__).resolve().parents[3]


def _facts(*, code: str = "HCM-FIELD-001", field: str = "服務方式") -> HcmResubmissionFacts:
    return HcmResubmissionFacts(
        review_identity="hcm-review:sample",
        logical_code=code,
        field_path=field,
        case_no="HCM-001",
        client_id=2,
        review_binding_id=3,
        prior_source_event_identity="hcm-source:prior",
        review_version=1,
        root_fingerprint="a" * 64,
    )


def test_correction_adopts_only_the_prior_warning_field() -> None:
    candidate = build_hcm_field_correction_candidate(
        _facts(),
        {"服務方式": "週休二日", "姓名": "不應覆寫的既有姓名"},
        {},
        {"clients.service_type": "週休二日"},
    )

    assert candidate.source_field == "服務方式"
    assert candidate.target_fields == ("clients.service_type",)
    assert candidate.target_values == {"clients.service_type": "週休二日"}


def test_canonical_hcm_writer_does_not_append_legacy_occurrence_association() -> None:
    source = (
        ROOT / "infrastructure/mysql/hcm_resubmission_repository.py"
    ).read_text(encoding="utf-8")

    assert "import_warning_resubmission_associations" not in source


@pytest.mark.parametrize(
    ("field_path", "targets"),
    [
        ("服務時間", ("orders.service_hours_per_day", "orders.service_start_time", "orders.service_end_time", "orders.service_end_day_offset")),
        ("預計服務日期", ("orders.start_date", "orders.end_date")),
        ("希望服務天數", ("orders.service_days", "orders.end_date")),
        ("服務方式", ("clients.service_type",)),
    ],
)
def test_order_warning_field_has_a_fixed_derived_write_set(field_path, targets) -> None:
    assert hcm_field_targets(field_path) == targets


def test_service_day_warning_derives_only_days_and_end_date() -> None:
    values = hcm_resubmission_target_values(
        "希望服務天數",
        {"service_start_date": date(2026, 8, 3), "service_days": 2, "service_type": "週休2日"},
        holiday_dates=set(),
    )

    assert values == {"orders.service_days": 2, "orders.end_date": date(2026, 8, 4)}


def test_service_type_correction_is_client_owned_and_does_not_write_order_end_date() -> None:
    values = hcm_resubmission_target_values(
        "服務方式",
        {"service_start_date": date(2026, 8, 3), "service_days": 2, "service_type": "週休2日"},
        holiday_dates=set(),
    )

    assert values == {"clients.service_type": "週休2日"}


@pytest.mark.parametrize(
    ("facts", "record", "errors", "target_values", "code"),
    [
        (_facts(code="HCM-CASE-002", field="$source_row"), {"姓名": "x"}, {}, {}, "hcm_resubmission_field_scope_ambiguous"),
        (_facts(field="案件狀態"), {"案件狀態": "符合"}, {}, {}, "hcm_resubmission_field_not_owned"),
        (_facts(), {"服務方式": "週休二日"}, {"服務方式": "格式錯誤"}, {}, "hcm_resubmission_field_still_invalid"),
        (_facts(), {"服務方式": "週休二日"}, {}, {"clients.name": "不得寫入"}, "hcm_resubmission_target_values_invalid"),
        (_facts(field="身分資格"), {"身分資格": "一般市民"}, {}, {"clients.identity_status": "一般市民"}, "hcm_resubmission_field_not_owned"),
    ],
)
def test_correction_fails_closed_when_the_warning_cannot_define_one_safe_write(
    facts: HcmResubmissionFacts,
    record: dict[str, object],
    errors: dict[str, str],
    target_values: dict[str, object],
    code: str,
) -> None:
    with pytest.raises(ValueError, match=code):
        build_hcm_field_correction_candidate(facts, record, errors, target_values)
