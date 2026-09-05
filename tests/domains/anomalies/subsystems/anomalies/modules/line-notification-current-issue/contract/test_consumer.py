from domains.anomalies.current_issue import OwnerSnapshot, RecheckScope, build_issue_key, build_owner_lock_key
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


def _readback(*, active=True, complete=True, owner_token="owner-token"):
    return LineNotificationFailureCurrentFactReadback(
        "CASE-006",
        REASON,
        owner_token,
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
    consumer = LineNotificationCurrentIssueConsumer(build_issue_key)

    candidate = consumer.detect(snapshot)[0]

    assert candidate.definition_code == "LINE-006"
    assert candidate.subject_identity == {
        "case_no": "CASE-006",
        "notification_reason": "recipient_unavailable",
    }
    assert candidate.issue_key == build_issue_key(
        "LINE-006", candidate.subject_identity, "owner-token"
    )
    assert candidate.subject_id == "CASE-006"
    assert candidate.details["unresolved_reason_codes"] == (
        "exact_replay_successor_missing",
    )
    action = candidate.details["available_actions"][0]
    assert action["preview_operation"] == "PreviewLineNotificationManualReplay"
    assert action["apply_operation"] == "ApplyLineNotificationManualReplay"
    assert action["source_bindings"] == {
        "case_no": "CASE-006",
        "notification_reason": "recipient_unavailable",
        "source_version": 8,
    }


def test_new_owner_lifecycle_token_proposes_a_different_issue_key() -> None:
    consumer = LineNotificationCurrentIssueConsumer(build_issue_key)
    first = consumer.detect(OwnerSnapshot(_scope(), "snapshot-1", 8, (_readback(owner_token="owner-token-1"),)))[0]
    second = consumer.detect(OwnerSnapshot(_scope(), "snapshot-2", 9, (_readback(owner_token="owner-token-2"),)))[0]

    assert first.issue_key != second.issue_key


def test_inactive_complete_owner_predicate_emits_no_candidate() -> None:
    snapshot = OwnerSnapshot(_scope(), "snapshot", 8, (_readback(active=False),))
    consumer = LineNotificationCurrentIssueConsumer(build_issue_key)

    assert consumer.detect(snapshot) == ()


def test_incomplete_owner_readback_never_synthesizes_a_new_candidate() -> None:
    snapshot = OwnerSnapshot(_scope(), "snapshot", 8, (_readback(complete=False),), False)
    consumer = LineNotificationCurrentIssueConsumer(build_issue_key)

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
