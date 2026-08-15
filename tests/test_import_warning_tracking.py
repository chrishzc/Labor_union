"""
File: test_import_warning_tracking.py
Description: 驗證匯入警示追蹤、業務顯示文字與 owning screen 導向。
"""

from __future__ import annotations

import pytest

from domains.anomalies.import_warning_tracking import (
    ImportWarningTrackingStatus,
    WarningTransitionError,
    build_import_warning_occurrence,
    preview_warning_transition,
)
from subsystems.anomalies.import_warning_tracking_workflow import (
    ImportWarningTask,
    ImportWarningTrackingApplication,
    _display_message,
    _navigation_action,
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


def test_hcm_warning_navigation_is_an_owner_screen_action_not_a_mutation() -> None:
    task = ImportWarningTask(
        "warning-1", "hcm", "HCM-FIELD-001", "服務日期", "hcm-***-0001",
        ("hcm_field_missing:服務日期",), ImportWarningTrackingStatus.OPEN, 1, None,
    )

    assert _navigation_action(task) == "hcm_import_center"

    closed = ImportWarningTask(
        "warning-1", "hcm", "HCM-FIELD-001", "服務日期", "hcm-***-0001",
        ("hcm_field_missing:服務日期",), ImportWarningTrackingStatus.CLOSED, 2, None,
    )
    assert _navigation_action(closed) is None


def test_hcm_field_codes_remain_generic_while_display_names_the_field() -> None:
    missing = ImportWarningTask(
        "warning-1", "hcm", "HCM-FIELD-001", "身分證字號", "hcm-***-0001",
        ("hcm_field_missing:身分證字號",), ImportWarningTrackingStatus.OPEN, 1, None,
    )
    invalid = ImportWarningTask(
        "warning-2", "hcm", "HCM-FIELD-002", "行動電話", "hcm-***-0002",
        ("hcm_field_invalid:行動電話",), ImportWarningTrackingStatus.OPEN, 1, None,
    )

    assert _display_message(missing) == "缺少身分證"
    assert _display_message(invalid) == "行動電話格式錯誤"

    conflict = ImportWarningTask(
        "warning-3", "beclass_staff", "STAFF-BECLASS-FIELD-002", "bank_accounts",
        "staff-***-0003", ("historical_nonempty_conflict:bank_accounts",),
        ImportWarningTrackingStatus.OPEN, 1, None,
    )
    assert _display_message(conflict) == "bank_accounts與現有資料衝突"


def test_client_field_code_remains_generic_while_display_uses_issue_semantics() -> None:
    missing = ImportWarningTask(
        "warning-client-1", "beclass_client", "CLIENT-BECLASS-SOURCE-001", "姓名",
        "client-***-0001", ("client_field_missing:姓名",),
        ImportWarningTrackingStatus.OPEN, 1, None,
    )
    invalid = ImportWarningTask(
        "warning-client-2", "beclass_client", "CLIENT-BECLASS-SOURCE-001", "Email",
        "client-***-0002", ("client_field_invalid:Email",),
        ImportWarningTrackingStatus.OPEN, 1, None,
    )

    assert _display_message(missing) == "缺少姓名"
    assert _display_message(invalid) == "Email格式錯誤"


def test_auto_resolved_staff_name_trace_has_completed_business_message() -> None:
    task = ImportWarningTask(
        "warning-staff-name-trace",
        "beclass_staff",
        "STAFF-BECLASS-NAME-002",
        "姓名",
        "staff-***-0007",
        ("historical_name_changed",),
        ImportWarningTrackingStatus.AUTO_RESOLVED,
        1,
        None,
    )

    assert _display_message(task) == "歷史姓名已更新"


def test_task_query_adds_navigation_descriptor_without_writing_source_data() -> None:
    task = ImportWarningTask(
        "warning-1", "hcm", "HCM-FIELD-002", "服務時間", "hcm-***-0001",
        ("hcm_field_invalid:服務時間",), ImportWarningTrackingStatus.OPEN, 1, None,
    )

    class Repository:
        def query_tasks(self, **_):
            return (task,)

    result = ImportWarningTrackingApplication(Repository(), object).query_tasks()

    assert result[0].navigation_action == "hcm_import_center"
    assert result[0].display_message == "服務時間格式錯誤"
    assert result[0].occurrence_identity == task.occurrence_identity


def test_hcm_referral_requires_fresh_active_warning_and_never_locks() -> None:
    task = ImportWarningTask(
        "warning-referral", "hcm", "HCM-FIELD-002", "服務時間", "hcm-***-0001",
        ("hcm_field_invalid:服務時間",), ImportWarningTrackingStatus.OPEN, 3, None,
    )

    class Repository:
        def __init__(self):
            self.lock_requests = []

        def load_task(self, occurrence_identity, *, for_update):
            assert occurrence_identity == "warning-referral"
            self.lock_requests.append(for_update)
            return task

    repository = Repository()
    application = ImportWarningTrackingApplication(repository, object)

    referral = application.query_referral("warning-referral", expected_version=3)

    assert repository.lock_requests == [False]
    assert referral.target_command == "preview_hcm_resubmission"
    assert referral.masked_subject == "hcm-***-0001"
    with pytest.raises(ValueError, match="import_warning_version_conflict"):
        application.query_referral("warning-referral", expected_version=2)


def test_referral_fails_closed_for_completed_or_non_hcm_warning() -> None:
    tasks = {
        "closed": ImportWarningTask(
            "closed", "hcm", "HCM-FIELD-001", "姓名", "hcm-***-0002",
            ("hcm_field_missing:姓名",), ImportWarningTrackingStatus.CLOSED, 2, None,
        ),
        "finance": ImportWarningTask(
            "finance", "finance_import", "FINANCE-ROW-001", "$classification",
            "finance-***-0003", ("finance_manual_review",),
            ImportWarningTrackingStatus.OPEN, 1, None,
        ),
    }

    class Repository:
        def load_task(self, occurrence_identity, *, for_update):
            assert for_update is False
            return tasks[occurrence_identity]

    application = ImportWarningTrackingApplication(Repository(), object)

    with pytest.raises(ValueError, match="import_warning_referral_unavailable"):
        application.query_referral("closed", expected_version=2)
    with pytest.raises(ValueError, match="import_warning_referral_unavailable"):
        application.query_referral("finance", expected_version=1)


def test_historical_order_warning_navigation_targets_its_owner_import_screen() -> None:
    task = ImportWarningTask(
        "warning-2", "historical_order", "ORDER-HIST-STAFF-001", "$staff",
        "order-***-0002", ("staff_missing",), ImportWarningTrackingStatus.OPEN, 1, None,
    )

    assert _navigation_action(task) == "historical_order_import_center"


def test_beclass_warning_navigation_targets_its_owner_import_screen() -> None:
    task = ImportWarningTask(
        "warning-3", "beclass_staff", "STAFF-BECLASS-FIELD-002", "銀行代號",
        "staff-***-0003", ("staff_field_invalid:銀行代號",),
        ImportWarningTrackingStatus.OPEN, 1, None,
    )

    assert _navigation_action(task) == "staff_beclass_import_center"

    client_binding = ImportWarningTask(
        "warning-5", "beclass_client", "CLIENT-BECLASS-BIND-003", "$case_link",
        "client-***-0005", ("client_case_binding_not_unique",),
        ImportWarningTrackingStatus.OPEN, 1, None,
    )
    assert _navigation_action(client_binding) == "client_beclass_import_center"
    assert _display_message(client_binding) == "客戶案件關聯無法唯一確認"


def test_finance_warning_navigation_targets_finance_owner_screen() -> None:
    task = ImportWarningTask(
        "warning-4", "finance_import", "FINANCE-ROW-001", "$classification",
        "finance-row-***-4", ("finance_manual_review",), ImportWarningTrackingStatus.OPEN,
        1, None,
    )

    assert _navigation_action(task) == "finance_import_recovery_center"
