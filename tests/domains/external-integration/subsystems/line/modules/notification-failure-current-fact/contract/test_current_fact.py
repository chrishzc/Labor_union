import json
import pytest
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


def test_mysql_disposition_is_bound_to_exact_snapshot_and_preserves_failure_results():
    active = _evaluate(_source())
    cursor = _Cursor(one_rows=({'id': 1}, None))
    repository = MySqlLineNotificationRepository(_Connection(cursor))
    dismissed = repository._apply_warning_disposition(active)
    assert dismissed.predicate_active is False and dismissed.unresolved_source_count == active.unresolved_source_count
    assert dismissed.unresolved_reason_codes == active.unresolved_reason_codes
    assert dismissed.owner_snapshot_token != active.owner_snapshot_token
    changed = _evaluate(_source(_replay(22, ('failed',))))
    assert repository._apply_warning_disposition(changed).predicate_active is True
    assert cursor.executed[0][1][-1] == active.owner_snapshot_token
    assert cursor.executed[1][1][-1] == changed.owner_snapshot_token


def test_replay_in_progress_does_not_undo_existing_terminal_success() -> None:
    readback = _evaluate(
        _source(
            _replay(20, ("sent",)),
            _replay(21, ("processing",)),
        )
    )

    assert readback.predicate_active is False
    assert readback.unresolved_reason_codes == ()


def test_initial_replay_in_progress_keeps_original_issue_until_terminal_success() -> None:
    for status in ('pending','processing','retryable_failed'):
        readback = _evaluate(_source(_replay(21,(status,))))
        assert readback.predicate_active is True
        assert readback.unresolved_reason_codes == (LineNotificationUnresolvedReason.REPLAY_IN_PROGRESS,)
        assert readback.unresolved_source_ids == readback.replay_in_progress_source_ids == (11,)


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
        "source_case_current": 1,
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


def test_mysql_readback_includes_terminal_failed_delivery_with_line006_reason() -> None:
    facts = json.dumps({"case_no": "CASE-006"})
    original = {
        "source_event_id": 11,
        "source_domain": "line_task96_fixture",
        "event_code": "deposit_confirmed",
        "source_event_identity": "line-task96:11",
        "source_aggregate_type": "line_task96_runtime",
        "source_aggregate_identity": "CASE-006",
        "source_version": 1,
        "facts_snapshot": facts,
        "rule_id": "rule-a",
        "reason_code": "rule_matched",
        "is_latest_source_version": 1,
        "source_case_current": 1,
    }
    class _TerminalFailureCursor(_Cursor):
        def execute(self, sql, parameters=()):
            # Negative control: before the regression fix this SQL did not
            # admit a delivery-owned terminal failure, so the source is absent.
            if (
                "source.id AS source_event_id" in sql
                and "task.processing_status='failed'" not in sql
            ):
                self.all_rows[0] = ()
            super().execute(sql, parameters)

    cursor = _TerminalFailureCursor(
        all_rows=((original,), ()),
        one_rows=(
            {
                "revision_id": 7,
                "definition_snapshot": json.dumps(
                    {
                        "rules": [
                            {
                                "id": "rule-a",
                                "event_code": "deposit_confirmed",
                                "enabled": True,
                                "predicates": [],
                            }
                        ]
                    }
                ),
            },
        ),
    )

    readback = MySqlLineNotificationRepository(_Connection(cursor)).current_failure_fact(
        QUERY
    )

    assert readback.authoritative_complete is True
    assert readback.applicable_source_count == 1
    assert readback.unresolved_source_count == 1
    assert readback.predicate_active is True


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


@pytest.mark.parametrize('remaining,required,configuration_valid,expected', [
    (10000,10000,True,True), (0,10000,True,False),
    (0,0,True,False), (10000,10000,False,True),
])
def test_failed_second_payment_reuses_current_finance_but_does_not_hide_broken_settings(
    remaining,required,configuration_valid,expected,
):
    from datetime import date
    from subsystems.line.second_payment_notifications import SecondPaymentNotification
    original = SecondPaymentNotification('CASE-006','second-006',1,101,date(2026,10,26),10000,10000,'C-synthetic').event(datetime(2026,10,26,tzinfo=UTC))
    row = {'source_event_id':11,'source_domain':original.source_domain,'event_code':original.event_code,
        'source_event_identity':original.identity,'source_aggregate_type':original.source_aggregate_type,
        'source_aggregate_identity':'CASE-006','source_version':1,'facts_snapshot':json.dumps(original.facts),
        'rule_id':'rule-a','reason_code':'recipient_unavailable','is_latest_source_version':1,'source_case_current':1}
    rule = {'id':'rule-a','event_code':original.event_code,'enabled':True,'predicates':[],
        'recipient_selector':'case_group' if configuration_valid else 'client',
        'schedule':{'kind':'immediate'} if configuration_valid else {'kind':'broken'}}
    stages = ({'obligation_identity':'second-006','amount_due_ntd':remaining,'current_event_id':101,
        'status':'settled' if remaining==0 else 'open','after_amount_ntd':required},)
    cursor = _Cursor(all_rows=((row,),(),stages),one_rows=(
        {'revision_id':7,'definition_snapshot':json.dumps({'rules':[rule]})},
        {'status':'服務中'},{'aggregate_version':1,'second_payment_due_date':date(2026,10,26)},
        {'group_id':'C-synthetic','aggregate_version':0},None))
    readback = MySqlLineNotificationRepository(_Connection(cursor)).current_failure_fact(QUERY)
    assert readback.authoritative_complete and readback.predicate_active is expected
    assert any('client_finance_accounts' in sql for sql,_ in cursor.executed)
    assert all(sql.lstrip().startswith('SELECT') for sql,_ in cursor.executed)


def test_failure_work_is_associated_with_its_original_source_only():
    original = {'source_event_id':11,'source_domain':'orders','event_code':'deposit_confirmed',
        'source_event_identity':'orders:11','source_aggregate_type':'order','source_aggregate_identity':'CASE-006',
        'source_version':1,'facts_snapshot':json.dumps({'case_no':'CASE-006'}),'rule_id':'rule-a',
        'reason_code':'recipient_unavailable','is_latest_source_version':1,'source_case_current':1,'delivery_task_id':99}
    other = {**original,'source_event_id':12,'source_event_identity':'orders:12','delivery_task_id':None}
    replay = {'replay_source_event_id':21,'source_event_identity':'manual-replay:11:one','event_code':'deposit_confirmed',
        'source_aggregate_type':'order','source_aggregate_identity':'CASE-006','source_version':1,'facts_snapshot':original['facts_snapshot'],
        'decision_id':31,'decision_status':'intent_created','reason_code':'rule_matched','intent_id':41,
        'delivery_status':'failed','delivery_task_id':51}
    cursor = _Cursor(all_rows=((original,other),(replay,)),one_rows=(
        {'revision_id':7,'definition_snapshot':json.dumps({'rules':[{'id':'rule-a','event_code':'deposit_confirmed','enabled':True,'predicates':[]}]})},None))
    result = MySqlLineNotificationRepository(_Connection(cursor)).current_failure_fact(QUERY)
    assert result.related_task_ids == (51,99)
    assert result.source_task_ids == ((11,(51,99)),(12,()))


@pytest.mark.parametrize('status,expected', [('sent',(98,96,94)),('processing',(99,98,97,96,94)),('failed',(99,98,97,96,94))])
def test_resolved_original_and_replay_tasks_exit_but_unrelated_failures_remain(status,expected):
    from subsystems.line.notification_failure_current_fact import LineNotificationFailureRecheckTarget
    rows = tuple({'delivery_task_id':task,'source_event_id':source,'source_event_identity':identity} for task,source,identity in (
        (99,11,'orders:11'),(98,12,'orders:12'),(97,21,'manual-replay:11:one'),(95,13,'orders:13'),(94,14,'orders:14')))
    cursor = _Cursor(all_rows=(rows,))
    repository = MySqlLineNotificationRepository(_Connection(cursor))
    reads = []
    current = _evaluate(_source(_replay(21,(status,))),LineNotificationFailedSourceFact(12,True,True,()),LineNotificationFailedSourceFact(13,False,True,()))
    repository.line006_recheck_targets_for_source = lambda source: () if source==14 else (LineNotificationFailureRecheckTarget('CASE-006',QUERY.notification_reason),)
    repository.current_failure_fact = lambda query: (reads.append(query) or current)
    assert repository.unresolved_delivery_task_ids((99,98,97,96,95,94)) == expected
    assert len(reads)==1, 'same case/reason must reuse one fresh readback within the page'
    assert all(sql.lstrip().startswith('SELECT') for sql,_ in cursor.executed)


def test_delivery_filter_cannot_treat_incomplete_readback_as_completion():
    from subsystems.line.notification_failure_current_fact import LineNotificationFailureRecheckTarget
    cursor = _Cursor(all_rows=(({'delivery_task_id':99,'source_event_id':11,'source_event_identity':'orders:11'},),))
    repository = MySqlLineNotificationRepository(_Connection(cursor))
    repository.line006_recheck_targets_for_source = lambda _: (LineNotificationFailureRecheckTarget('CASE-006',QUERY.notification_reason),)
    repository.current_failure_fact = lambda _: _evaluate(_source(),complete=False)
    with pytest.raises(RuntimeError,match='incomplete'):
        repository.unresolved_delivery_task_ids((99,))
