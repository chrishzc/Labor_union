"""The durable recheck runtime composes every existing owner-specific consumer."""

from __future__ import annotations

import pytest

from domains.anomalies.current_issue import build_owner_lock_key
from infrastructure.mysql.anomaly_runtime import MySqlAnomalyRuntime
from subsystems.anomalies.current_issue_recheck import ReconciliationResult


class _CaptureApplication:
    def __init__(self, owner_snapshot_reader, expected_reader: str, expected_consumer: str):
        self.owner_snapshot_reader = owner_snapshot_reader
        self.expected_reader = expected_reader
        self.expected_consumer = expected_consumer

    def reconcile(self, scope, detector, *, completed_intent):
        assert type(self.owner_snapshot_reader.__self__).__name__ == self.expected_reader
        assert type(detector.__self__).__name__ == self.expected_consumer
        assert completed_intent.scope == scope
        return ReconciliationResult((), (), "owner-snapshot")


class _CaptureRuntime(MySqlAnomalyRuntime):
    def __init__(self, expected_reader: str, expected_consumer: str):
        super().__init__(issue_identity_secret="runtime-composition-secret-32-bytes")
        self.expected_reader = expected_reader
        self.expected_consumer = expected_consumer

    def current_issue_application(self, connection, *, owner_snapshot_reader=None):
        del connection
        return _CaptureApplication(
            owner_snapshot_reader,
            self.expected_reader,
            self.expected_consumer,
        )


@pytest.mark.parametrize(
    ("owner_domain", "owner_root_type", "subject_type", "subject_id", "reader", "consumer"),
    (
        (
            "line",
            "identity_binding",
            "customer",
            "U-line-1",
            "MySqlLineIdentityCurrentIssueAdapter",
            "LineIdentityCurrentIssueConsumer",
        ),
        (
            "line",
            "notification_failure",
            "LINE-006",
            "CASE-1:service_date_change",
            "MySqlLineNotificationCurrentIssueAdapter",
            "LineNotificationCurrentIssueConsumer",
        ),
        (
            "scheduling",
            "scheduling_current_fact",
            "SCHEDULE-006",
            "CASE-1:3",
            "MySqlSchedulingCurrentIssueAdapter",
            "SchedulingCurrentIssueConsumer",
        ),
        (
            "government_subsidy",
            "government_subsidy_current_fact",
            "GOVSUB-001",
            "bank-fact:7",
            "MySqlGovernmentSubsidyCurrentIssueAdapter",
            "GovernmentSubsidyCurrentIssueConsumer",
        ),
        (
            "case_import",
            "case_pairing_current_fact",
            "BECLASS-001",
            "CASE-1",
            "MySqlCasePairingCurrentIssueAdapter",
            "CasePairingCurrentIssueConsumer",
        ),
    ),
)
def test_runtime_composes_owner_reader_and_detector(
    owner_domain,
    owner_root_type,
    subject_type,
    subject_id,
    reader,
    consumer,
) -> None:
    lock = build_owner_lock_key(owner_domain, owner_root_type, subject_id)
    payload = {
        "intent_identity": f"runtime:{subject_type}:1",
        "owner_domain": owner_domain,
        "owner_root_type": owner_root_type,
        "subject_type": subject_type,
        "subject_ids": [subject_id],
        "owner_lock_keys": [lock],
        "owner_version": 1,
        "payload_fingerprint": "a" * 64,
    }

    result = _CaptureRuntime(reader, consumer).run_current_issue_recheck(
        object(),
        payload,
    )

    assert result == {
        "present_issue_keys": [],
        "deleted_issue_keys": [],
        "owner_snapshot_token": "owner-snapshot",
    }
