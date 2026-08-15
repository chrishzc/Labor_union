"""
File: test_import_warning_tracking.py
Description: 驗證 WP88 匯入警示追蹤狀態機與欄位級 occurrence 的不可破壞契約。
"""

from __future__ import annotations

import pytest

from domains.anomalies.import_warning_tracking import (
    ImportWarningTrackingStatus,
    WarningTransitionError,
    build_import_warning_occurrence,
    preview_warning_transition,
)


def test_hcm_field_issues_expand_to_independent_field_occurrences() -> None:
    first = build_import_warning_occurrence(
        owning_lane="hcm",
        source_event_identity="hcm-workbook:source:sheet:row:7",
        logical_code="HCM-FIELD-002",
        field_path="服務時間",
        masked_subject="hcm-***-0007",
        issue_codes=("hcm_field_invalid:服務時間",),
    )
    second = build_import_warning_occurrence(
        owning_lane="hcm",
        source_event_identity="hcm-workbook:source:sheet:row:7",
        logical_code="HCM-FIELD-002",
        field_path="行動電話",
        masked_subject="hcm-***-0007",
        issue_codes=("hcm_field_invalid:行動電話",),
    )

    assert first.occurrence_identity != second.occurrence_identity
    assert first.tracking_status is ImportWarningTrackingStatus.OPEN


def test_human_close_records_tracking_only_and_never_auto_resolves() -> None:
    preview = preview_warning_transition(
        current_status=ImportWarningTrackingStatus.OPEN,
        current_version=1,
        target_status=ImportWarningTrackingStatus.CLOSED,
        actor_kind="union_operator",
    )

    assert preview.allowed is True
    assert preview.resulting_status is ImportWarningTrackingStatus.CLOSED


def test_union_operator_cannot_claim_data_is_fixed() -> None:
    with pytest.raises(WarningTransitionError, match="system actor"):
        preview_warning_transition(
            current_status=ImportWarningTrackingStatus.OPEN,
            current_version=1,
            target_status=ImportWarningTrackingStatus.AUTO_RESOLVED,
            actor_kind="union_operator",
        )
