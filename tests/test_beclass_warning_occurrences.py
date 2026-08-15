"""
File: test_beclass_warning_occurrences.py
Description: 驗證 BeClass 已登錄警示、姓名追溯、明確 no-warning 與未知 issue。
"""

import pytest

from domains.anomalies.import_warning_tracking import (
    ImportWarningTrackingStatus,
    UnknownImportWarningIssueError,
)
from domains.case_import.beclass_import_review import BeClassImportSourceKind
from domains.case_import.beclass_warning_review import build_beclass_warning_occurrences


def test_client_beclass_maps_real_missing_invalid_and_legacy_source_defects():
    warnings = build_beclass_warning_occurrences(
        source_kind=BeClassImportSourceKind.CLIENT,
        source_event_identity="client-beclass:source:3",
        masked_identifier="client-***-0003",
        issue_codes=(
            "client_field_missing:姓名",
            "client_field_invalid:Email",
            "報名時間",
            "duplicate_query_no",
        ),
    )

    assert {(item.logical_code, item.field_path) for item in warnings} == {
        ("CLIENT-BECLASS-SOURCE-001", "姓名"),
        ("CLIENT-BECLASS-SOURCE-001", "Email"),
        ("CLIENT-BECLASS-SOURCE-001", "報名時間"),
    }


def test_client_beclass_source_payload_conflict_is_registered() -> None:
    warning = build_beclass_warning_occurrences(
        source_kind=BeClassImportSourceKind.CLIENT,
        source_event_identity="client-beclass:source:4",
        masked_identifier="client-***-0004",
        issue_codes=("client_beclass_source_payload_conflict",),
    )[0]

    assert (warning.logical_code, warning.field_path) == (
        "CLIENT-BECLASS-SOURCE-001",
        "$source_row",
    )


def test_client_beclass_binding_outcomes_keep_distinct_business_codes() -> None:
    warnings = build_beclass_warning_occurrences(
        source_kind=BeClassImportSourceKind.CLIENT,
        source_event_identity="client-beclass:source:binding",
        masked_identifier="client-***-0005",
        issue_codes=(
            "client_case_binding_no_client",
            "client_case_binding_multiple_clients",
            "client_case_binding_case_not_unique",
        ),
    )

    assert [(warning.logical_code, warning.field_path) for warning in warnings] == [
        ("CLIENT-BECLASS-BIND-001", "$client_link"),
        ("CLIENT-BECLASS-BIND-002", "$client_link"),
        ("CLIENT-BECLASS-BIND-003", "$case_link"),
    ]


def test_staff_beclass_maps_identity_name_and_typed_field_defects():
    warnings = build_beclass_warning_occurrences(
        source_kind=BeClassImportSourceKind.STAFF,
        source_event_identity="staff-beclass:source:4",
        masked_identifier="staff-***-0004",
        issue_codes=("身分證字號", "identity_name_mismatch", "staff_field_invalid:銀行代號"),
    )

    assert {(item.logical_code, item.field_path) for item in warnings} == {
        ("STAFF-BECLASS-IDENTITY-001", "身分證字號"),
        ("STAFF-BECLASS-FIELD-002", "姓名"),
        ("STAFF-BECLASS-FIELD-002", "銀行代號"),
    }


def test_beclass_unknown_issue_fails_closed_instead_of_being_silently_dropped():
    with pytest.raises(UnknownImportWarningIssueError):
        build_beclass_warning_occurrences(
            source_kind=BeClassImportSourceKind.CLIENT,
            source_event_identity="client-beclass:source:5",
            masked_identifier="client-***-0005",
            issue_codes=("future_client_state",),
        )


def test_staff_historical_nonempty_conflict_is_a_registered_field_warning():
    warning = build_beclass_warning_occurrences(
        source_kind=BeClassImportSourceKind.STAFF,
        source_event_identity="staff-beclass:source:6",
        masked_identifier="staff-***-0006",
        issue_codes=("historical_nonempty_conflict:bank_accounts",),
    )[0]

    assert (warning.logical_code, warning.field_path) == (
        "STAFF-BECLASS-FIELD-002",
        "bank_accounts",
    )


def test_staff_newer_name_trace_starts_auto_resolved() -> None:
    warning = build_beclass_warning_occurrences(
        source_kind=BeClassImportSourceKind.STAFF,
        source_event_identity="staff-beclass:source:name-change",
        masked_identifier="staff-***-0007",
        issue_codes=("historical_name_changed",),
    )[0]

    assert (warning.logical_code, warning.field_path) == (
        "STAFF-BECLASS-NAME-002",
        "姓名",
    )
    assert warning.tracking_status is ImportWarningTrackingStatus.AUTO_RESOLVED
