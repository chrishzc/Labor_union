from domains.anomalies.current_issue import OwnerSnapshot, RecheckScope, build_owner_lock_key
from infrastructure.mysql.line_notification_current_issue_adapter import (
    MySqlLineNotificationCurrentIssueAdapter,
)
from subsystems.anomalies.line_notification_current_issue_consumer import (
    LineNotificationCurrentIssueConsumer,
)
from subsystems.line.notification_failure_current_fact import (
    LINE_NOTIFICATION_FAILURE_OWNER_DOMAIN,
    LINE_NOTIFICATION_FAILURE_OWNER_ROOT_TYPE,
    LineNotificationFailureCurrentFactReadback,
    LineNotificationFailureReason,
    LineNotificationUnresolvedReason,
)


REASON = LineNotificationFailureReason.RECIPIENT_UNAVAILABLE


def _scope():
    return RecheckScope(
        LINE_NOTIFICATION_FAILURE_OWNER_DOMAIN,
        LINE_NOTIFICATION_FAILURE_OWNER_ROOT_TYPE,
        REASON.value,
        ("CASE-006",),
        (
            build_owner_lock_key(
                LINE_NOTIFICATION_FAILURE_OWNER_DOMAIN,
                LINE_NOTIFICATION_FAILURE_OWNER_ROOT_TYPE,
                "CASE-006:recipient_unavailable",
            ),
        ),
    )


def _readback(*, active=True, complete=True):
    return LineNotificationFailureCurrentFactReadback(
        "CASE-006",
        REASON,
        "owner-token",
        8,
        complete,
        1,
        1 if active else 0,
        (
            (LineNotificationUnresolvedReason.EXACT_REPLAY_SUCCESSOR_MISSING,)
            if active
            else ()
        ),
        active,
    )


def test_consumer_preserves_public_case_and_notification_reason_identity() -> None:
    snapshot = OwnerSnapshot(_scope(), "snapshot", 8, (_readback(),))
    consumer = LineNotificationCurrentIssueConsumer(
        lambda code, subject: f"{code}:{subject['case_no']}:{subject['notification_reason']}"
    )

    candidate = consumer.detect(snapshot)[0]

    assert candidate.definition_code == "LINE-006"
    assert candidate.subject_identity == {
        "case_no": "CASE-006",
        "notification_reason": "recipient_unavailable",
    }
    assert candidate.subject_id == "CASE-006"
    assert candidate.details["unresolved_reason_codes"] == (
        "exact_replay_successor_missing",
    )


def test_inactive_complete_owner_predicate_emits_no_candidate() -> None:
    snapshot = OwnerSnapshot(_scope(), "snapshot", 8, (_readback(active=False),))
    consumer = LineNotificationCurrentIssueConsumer(lambda _code, _subject: "unused")

    assert consumer.detect(snapshot) == ()


def test_adapter_propagates_owner_completeness_for_fail_closed_reconcile() -> None:
    class Repository:
        def current_failure_fact(self, _query):
            return _readback(complete=False)

    adapter = MySqlLineNotificationCurrentIssueAdapter(None)
    adapter._repository = Repository()

    snapshot = adapter.read_owner_snapshot(_scope())

    assert snapshot.authoritative_complete is False
    assert snapshot.facts == (_readback(complete=False),)
