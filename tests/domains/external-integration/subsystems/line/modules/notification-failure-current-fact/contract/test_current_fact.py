import json
from datetime import UTC, datetime

from infrastructure.mysql.line_notification_repository import (
    MySqlLineNotificationRepository,
)
from subsystems.line.notification_failure_current_fact import (
    LineNotificationFailedSourceFact,
    LineNotificationFailureCurrentFactQuery,
    LineNotificationFailureReason,
    LineNotificationReplaySuccessorFact,
    LineNotificationUnresolvedReason,
    evaluate_line_notification_failure_current_fact,
)


QUERY = LineNotificationFailureCurrentFactQuery(
    "CASE-006", LineNotificationFailureReason.RECIPIENT_UNAVAILABLE
)


def _source(*successors, applicable=True, complete=True):
    return LineNotificationFailedSourceFact(
        11, applicable, complete, tuple(successors)
    )


def _replay(source_id, statuses, *, lineage=True, validation=True):
    return LineNotificationReplaySuccessorFact(
        source_id, lineage, validation, tuple(statuses)
    )


def _evaluate(*sources, complete=True):
    return evaluate_line_notification_failure_current_fact(
        QUERY, tuple(sources), owner_version=31, authoritative_complete=complete
    )


def test_no_currently_applicable_failed_source_is_inactive() -> None:
    readback = _evaluate(_source(applicable=False))

    assert readback.authoritative_complete is True
    assert readback.applicable_source_count == 0
    assert readback.unresolved_source_count == 0
    assert readback.predicate_active is False


def test_configuration_correction_alone_does_not_replace_manual_replay() -> None:
    readback = _evaluate(_source())

    assert readback.predicate_active is True
    assert readback.unresolved_reason_codes == (
        LineNotificationUnresolvedReason.EXACT_REPLAY_SUCCESSOR_MISSING,
    )


def test_replay_in_progress_is_not_a_new_business_issue() -> None:
    readback = _evaluate(
        _source(
            _replay(20, ("sent",)),
            _replay(21, ("processing",)),
        )
    )

    assert readback.predicate_active is False
    assert readback.unresolved_reason_codes == ()


def test_exact_fresh_replay_with_terminal_delivery_success_is_inactive() -> None:
    readback = _evaluate(_source(_replay(21, ("sent", "sent"))))

    assert readback.authoritative_complete is True
    assert readback.applicable_source_count == 1
    assert readback.unresolved_source_count == 0
    assert readback.predicate_active is False


def test_incomplete_owner_interpretation_is_closed_and_cannot_authorize_removal() -> None:
    readback = _evaluate(_source(complete=False))

    assert readback.authoritative_complete is False
    assert LineNotificationUnresolvedReason.OWNER_READBACK_INCOMPLETE in (
        readback.unresolved_reason_codes
    )
    assert readback.predicate_active is True


def test_incomplete_empty_readback_does_not_create_a_new_business_issue() -> None:
    readback = _evaluate(complete=False)

    assert readback.authoritative_complete is False
    assert readback.applicable_source_count == 0
    assert readback.unresolved_source_count == 0
    assert readback.unresolved_reason_codes == (
        LineNotificationUnresolvedReason.OWNER_READBACK_INCOMPLETE,
    )
    assert readback.predicate_active is False


class _Cursor:
    def __init__(self, *, one_rows=(), all_rows=()):
        self.one_rows = list(one_rows)
        self.all_rows = list(all_rows)
        self.executed = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, parameters=()):
        assert sql.count("%s") == len(parameters)
        self.executed.append((sql, tuple(parameters)))

    def fetchone(self):
        return self.one_rows.pop(0) if self.one_rows else None

    def fetchall(self):
        return self.all_rows.pop(0) if self.all_rows else ()


class _Connection:
    def __init__(self, cursor):
        self._cursor = cursor

    def cursor(self):
        return self._cursor


def test_mysql_readback_composes_exact_replay_and_delivery_without_raw_payload() -> None:
    facts = json.dumps({"case_no": "CASE-006"})
    original = {
        "source_event_id": 11,
        "source_domain": "orders",
        "event_code": "deposit_confirmed",
        "source_event_identity": "orders:11",
        "source_aggregate_type": "order",
        "source_aggregate_identity": "CASE-006",
        "source_version": 3,
        "facts_snapshot": facts,
        "rule_id": "rule-a",
        "reason_code": "recipient_unavailable",
        "is_latest_source_version": 1,
    }
    replay = {
        "replay_source_event_id": 21,
        "source_event_identity": "manual-replay:11:retry-1",
        "event_code": "deposit_confirmed",
        "source_aggregate_type": "order",
        "source_aggregate_identity": "CASE-006",
        "source_version": 3,
        "facts_snapshot": facts,
        "decision_id": 31,
        "decision_status": "intent_created",
        "reason_code": "rule_matched",
        "intent_id": 41,
        "delivery_status": "sent",
        "delivery_task_id": 51,
    }
    cursor = _Cursor(
        all_rows=((original,), (replay,)),
        one_rows=(({
            "revision_id": 7,
            "definition_snapshot": json.dumps({
                "rules": [{
                    "id": "rule-a",
                    "event_code": "deposit_confirmed",
                    "enabled": True,
                    "predicates": [],
                }]
            }),
        }),),
    )

    readback = MySqlLineNotificationRepository(
        _Connection(cursor)
    ).current_failure_fact(QUERY)

    assert readback.predicate_active is False
    assert readback.unresolved_source_count == 0
    assert readback.owner_version == 21
    assert all("recipient_identity" not in sql for sql, _ in cursor.executed)
    assert all("payload_snapshot" not in sql for sql, _ in cursor.executed)


def test_existing_exact_manual_replay_is_idempotent_without_revalidation_or_write() -> None:
    facts = json.dumps({"case_no": "CASE-006"})
    cursor = _Cursor(one_rows=(
        {
            "source_domain": "orders",
            "event_code": "deposit_confirmed",
            "source_event_identity": "orders:11",
            "source_aggregate_type": "order",
            "source_aggregate_identity": "CASE-006",
            "source_version": 3,
            "historical_silent": 0,
            "facts_snapshot": facts,
            "occurred_at_utc": datetime(2026, 8, 31, tzinfo=UTC),
        },
        {
            "id": 21,
            "source_aggregate_type": "order",
            "source_aggregate_identity": "CASE-006",
            "source_version": 3,
            "historical_silent": 0,
            "facts_snapshot": facts,
        },
    ))
    repository = MySqlLineNotificationRepository(_Connection(cursor))

    replay_id = repository.manual_replay_source(
        11,
        "manual-replay:11:retry-1",
        datetime(2026, 8, 31, 1, tzinfo=UTC),
    )

    assert replay_id == 21
    assert len(cursor.executed) == 2
    assert all(not sql.startswith("INSERT") for sql, _ in cursor.executed)


def test_provider_send_validation_reads_current_binding_and_rejects_changed_recipient() -> None:
    facts = json.dumps({"case_no": "CASE-006"})
    replay_task = {
        "source_event_identity": "manual-replay:11:retry-1",
        "event_code": "deposit_confirmed",
        "source_aggregate_type": "order",
        "source_aggregate_identity": "CASE-006",
        "source_version": 3,
        "facts_snapshot": facts,
        "rule_id": "rule-a",
        "recipient_type": "group",
        "recipient_identity": "G-old",
        "template_id": "deposit",
        "task_recipient_type": "group",
        "task_recipient_identity": "G-old",
    }
    original = {
        "source_domain": "orders",
        "event_code": "deposit_confirmed",
        "source_event_identity": "orders:11",
        "source_aggregate_type": "order",
        "source_aggregate_identity": "CASE-006",
        "source_version": 3,
        "historical_silent": 0,
        "facts_snapshot": facts,
        "occurred_at_utc": datetime(2026, 8, 31, tzinfo=UTC),
    }
    rules = {
        "revision_id": 7,
        "definition_snapshot": json.dumps({
            "rules": [{
                "id": "rule-a",
                "event_code": "deposit_confirmed",
                "enabled": True,
                "recipient_selector": "case_group",
                "template_id": "deposit",
                "predicates": [],
            }]
        }),
    }
    templates = {
        "revision_id": 8,
        "definition_snapshot": json.dumps({
            "templates": [{
                "id": "deposit",
                "message_type": "text",
                "content": "received",
                "variables": [],
            }]
        }),
    }
    cursor = _Cursor(one_rows=(
        replay_task,
        original,
        None,
        rules,
        templates,
        {"group_id": "G-new"},
    ))

    failure = MySqlLineNotificationRepository(
        _Connection(cursor)
    ).manual_replay_delivery_validation_failure(51)

    assert failure == "recipient_binding_changed"
    assert any("line_order_group_bindings" in sql for sql, _ in cursor.executed)
