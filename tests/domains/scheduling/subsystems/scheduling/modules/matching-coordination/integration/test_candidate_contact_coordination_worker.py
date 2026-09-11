import json
from datetime import datetime, timedelta, timezone

import pytest

from subsystems.line import candidate_contact_coordination_worker as worker_module
from subsystems.line.candidate_contact_coordination_worker import (
    _adjustment_events,
    _candidate_state,
)


NOW = datetime(2026, 9, 10, 12, tzinfo=timezone.utc)


def _delivery(sent_at):
    return {"source_event_id": 9, "sent_at_utc": sent_at}


def _event(event_id, payload):
    return {"id": event_id, "candidate_id": 7, "payload": json.dumps(payload)}



def test_silence_becomes_due_only_after_twenty_four_hours():
    assert _candidate_state(7, [], _delivery(NOW - timedelta(hours=23, minutes=59)), NOW) == "waiting_initial"
    assert _candidate_state(7, [], _delivery(NOW - timedelta(hours=24)), NOW) == "due_timeout"


def test_information_question_is_not_a_terminal_pool_response():
    events = [_event(10, {
        "response_kind": "coordination_requested",
        "willingness": "pending",
        "issues": [{"mode": "information_question", "category": "service_region", "detail": "哪一區？"}],
    })]

    assert _candidate_state(7, events, _delivery(NOW - timedelta(hours=1)), NOW) == "waiting_customer"


def test_customer_answer_starts_a_new_candidate_response_window():
    events = [
        _event(10, {
            "response_kind": "coordination_requested",
            "willingness": "pending",
            "issues": [{"mode": "information_question", "category": "service_region", "detail": "哪一區？"}],
        }),
        _event(11, {"response_kind": "information_answered", "source_response_event_id": 10}),
    ]

    assert _candidate_state(7, events, _delivery(NOW - timedelta(hours=23)), NOW) == "waiting_final_response"
    assert _candidate_state(7, events, _delivery(NOW - timedelta(hours=24)), NOW) == "due_timeout"


def test_willing_response_short_circuits_adjustment_coordination():
    events = [_event(12, {"willingness": "willing", "reason": "LINE 按鈕回覆願意承接"})]

    assert _candidate_state(7, events, _delivery(NOW - timedelta(hours=1)), NOW) == "willing"


def test_only_latest_candidate_response_enters_adjustment_batch():
    old_adjustment = _event(20, {
        "response_kind": "coordination_requested",
        "willingness": "unwilling",
        "issues": [{"mode": "condition_adjustment", "category": "cooking_requirement", "detail": "希望不用下廚"}],
    })
    latest_no_interest = _event(21, {"response_kind": "no_interest", "willingness": "unwilling"})

    assert _adjustment_events([old_adjustment, latest_no_interest]) == ()


def test_customer_cannot_adjust_reclassifies_adjustment_for_union_followup():
    adjustment = _event(20, {
        "response_kind": "coordination_requested",
        "willingness": "unwilling",
        "issues": [{"mode": "condition_adjustment", "category": "cooking_requirement", "detail": "希望不用下廚"}],
    })
    batch = _event(30, {
        "response_kind": "adjustment_batch_dispatched",
        "source_response_event_ids": [20],
    })
    declined = _event(31, {
        "response_kind": "adjustment_customer_answer",
        "decision": "cannot_adjust",
        "source_coordination_event_id": 30,
    })

    assert _adjustment_events([adjustment, batch, declined]) == ()


def test_customer_can_adjust_moves_coordination_to_union_modification_followup():
    adjustment = _event(20, {
        "response_kind": "coordination_requested",
        "willingness": "unwilling",
        "issues": [{"mode": "condition_adjustment", "category": "cooking_requirement", "detail": "希望不用下廚"}],
    })
    batch = _event(30, {
        "response_kind": "adjustment_batch_dispatched",
        "source_response_event_ids": [20],
    })
    accepted = _event(31, {
        "response_kind": "adjustment_customer_answer",
        "decision": "can_adjust",
        "source_coordination_event_id": 30,
    })

    assert _adjustment_events([adjustment, batch, accepted]) == ()


class _PoolCursor:
    rowcount = 0
    lastrowid = 100

    def __init__(self, reads):
        self._reads = iter(reads)
        self.writes = []

    def execute(self, sql, args):
        self.rowcount = 0
        if sql.startswith("INSERT IGNORE"):
            self.lastrowid += 1
            self.rowcount = 1
            self.writes.append((sql, args))

    def fetchall(self):
        return next(self._reads)


def test_silence_completes_the_pool_and_dispatches_only_the_adjustment(
    monkeypatch: pytest.MonkeyPatch,
):
    adjustment = _event(
        20,
        {
            "response_kind": "coordination_requested",
            "willingness": "unwilling",
            "issues": [
                {
                    "mode": "condition_adjustment",
                    "category": "cooking_requirement",
                    "detail": "希望不用下廚",
                }
            ],
        },
    )
    cursor = _PoolCursor(
        (
            ({"id": 7, "line_user_id": "U-7"}, {"id": 8, "line_user_id": "U-8"}),
            (adjustment,),
            (
                {"candidate_id": 7, "source_event_id": 70, "sent_at_utc": NOW - timedelta(hours=2)},
                {"candidate_id": 8, "source_event_id": 80, "sent_at_utc": NOW - timedelta(hours=24)},
            ),
            (),
        )
    )
    dispatched = []
    monkeypatch.setattr(
        worker_module,
        "_enqueue_adjustment_summary",
        lambda _connection, _cursor, _pool, events, _now: dispatched.append(events) or True,
    )

    processed = worker_module._process_pool(
        object(), cursor, {"id": 4, "case_no": "CASE-4"}, NOW
    )

    assert processed == 2
    assert len(cursor.writes) == 1
    assert [item["id"] for item in dispatched[0]] == [20]


def test_a_willing_candidate_suppresses_the_adjustment_batch(
    monkeypatch: pytest.MonkeyPatch,
):
    cursor = _PoolCursor(
        (
            ({"id": 7, "line_user_id": "U-7"}, {"id": 8, "line_user_id": "U-8"}),
            (
                _event(20, {"willingness": "willing"}),
                {
                    **_event(
                        21,
                        {
                            "response_kind": "coordination_requested",
                            "willingness": "unwilling",
                            "issues": [
                                {
                                    "mode": "condition_adjustment",
                                    "category": "cooking_requirement",
                                    "detail": "希望不用下廚",
                                }
                            ],
                        },
                    ),
                    "candidate_id": 8,
                },
            ),
            (
                {"candidate_id": 7, "source_event_id": 70, "sent_at_utc": NOW - timedelta(hours=2)},
                {"candidate_id": 8, "source_event_id": 80, "sent_at_utc": NOW - timedelta(hours=2)},
            ),
            (),
        )
    )
    monkeypatch.setattr(
        worker_module,
        "_enqueue_adjustment_summary",
        lambda *_args: pytest.fail("adjustment summary must be suppressed"),
    )

    assert (
        worker_module._process_pool(
            object(), cursor, {"id": 4, "case_no": "CASE-4"}, NOW
        )
        == 0
    )


def test_all_terminal_without_adjustments_enqueues_union_manual_followup_once(
    monkeypatch: pytest.MonkeyPatch,
):
    events = (
        {**_event(20, {"response_kind": "no_interest", "willingness": "unwilling"}), "occurred_at": NOW - timedelta(minutes=2)},
        {
            **_event(21, {"response_kind": "timed_out", "willingness": "pending"}),
            "candidate_id": 8,
            "occurred_at": NOW - timedelta(minutes=1),
        },
    )
    cursor = _PoolCursor(
        (
            ({"id": 7, "line_user_id": "U-7"}, {"id": 8, "line_user_id": "U-8"}),
            events,
            (
                {"candidate_id": 7, "source_event_id": 70, "sent_at_utc": NOW - timedelta(hours=2)},
                {"candidate_id": 8, "source_event_id": 80, "sent_at_utc": NOW - timedelta(hours=25)},
            ),
            (),
        )
    )
    enqueued = []
    monkeypatch.setattr(
        worker_module,
        "_enqueue_manual_followup",
        lambda _connection, _cursor, pool, candidates, source_events, _now: enqueued.append(
            (pool, candidates, source_events)
        )
        or True,
    )
    monkeypatch.setattr(
        worker_module,
        "_enqueue_adjustment_summary",
        lambda *_args: pytest.fail("customer adjustment must not be sent"),
    )

    assert worker_module._process_pool(object(), cursor, {"id": 4, "case_no": "CASE-4"}, NOW) == 1
    assert len(enqueued) == 1


@pytest.mark.parametrize(
    ("decision", "expected_instruction"),
    (
        ("cannot_adjust", "客戶目前無法調整條件"),
        ("can_adjust", "請先完成正式案件資料修改，再重新詢問相關月嫂"),
    ),
)
def test_manual_followup_message_is_group_scoped_minimal_and_idempotent(
    monkeypatch: pytest.MonkeyPatch,
    decision: str,
    expected_instruction: str,
):
    class TargetCursor:
        def execute(self, sql, _args=None):
            self.sql = sql

        def fetchall(self):
            return ({"id": 3, "group_id": "C-union-group"},)

        def fetchone(self):
            return None

    captured = []

    class DeliveryRepository:
        def __init__(self, _connection):
            pass

        def enqueue(self, request):
            captured.append(request)
            return type("Result", (), {"outcome": "created"})()

    monkeypatch.setattr(worker_module, "MySqlLineDeliveryTaskRepository", DeliveryRepository)
    monkeypatch.setenv("LINE_LIFF_ID", "2000000000-test")
    events = (
        {**_event(20, {
            "response_kind": "coordination_requested",
            "willingness": "unwilling",
            "issues": [{"mode": "condition_adjustment", "category": "cooking_requirement", "detail": "希望不用下廚"}],
        }), "occurred_at": NOW},
        {
            **_event(21, {"response_kind": "no_interest", "willingness": "unwilling"}),
            "candidate_id": 8,
            "occurred_at": NOW,
        },
        {**_event(30, {"response_kind": "adjustment_batch_dispatched", "source_response_event_ids": [20]}), "occurred_at": NOW},
        {**_event(31, {
            "response_kind": "adjustment_customer_answer",
            "decision": decision,
            "source_coordination_event_id": 30,
        }), "occurred_at": NOW},
    )

    created = worker_module._enqueue_manual_followup(
        object(),
        TargetCursor(),
        {"id": 4, "case_no": "CASE-4"},
        ({"id": 7}, {"id": 8}),
        events,
        NOW,
    )

    assert created is True
    request = captured[0]
    payload = json.loads(request.payload_json)
    assert request.recipient.recipient_type.value == "group"
    assert request.recipient.identity.value == "C-union-group"
    assert request.source_aggregate_type == "candidate_contact_manual_followup"
    assert request.source_aggregate_identity.startswith("4:31:")
    assert payload["type"] == "flex"
    assert "CASE-4" in payload["altText"]
    assert expected_instruction in request.payload_json
    assert "U-7" not in request.payload_json
    assert "target=staff_review" in request.payload_json
    assert "case_no=CASE-4" in request.payload_json


def test_existing_manual_followup_is_not_rebuilt_with_a_new_schedule_time(
    monkeypatch: pytest.MonkeyPatch,
):
    class ExistingCursor:
        def __init__(self):
            self.query_count = 0
            self.idempotency_key = None

        def execute(self, sql, args=None):
            self.query_count += 1
            if "WHERE idempotency_key=%s" in sql:
                self.idempotency_key = args[0]

        def fetchall(self):
            return ({"id": 3, "group_id": "C-union-group"},)

        def fetchone(self):
            return {"id": 73}

    monkeypatch.setattr(
        worker_module,
        "MySqlLineDeliveryTaskRepository",
        lambda _connection: pytest.fail("existing notification must not be enqueued again"),
    )
    events = (
        {
            **_event(20, {"response_kind": "no_interest", "willingness": "unwilling"}),
            "occurred_at": NOW,
        },
    )
    cursor = ExistingCursor()

    created = worker_module._enqueue_manual_followup(
        object(),
        cursor,
        {"id": 4, "case_no": "CASE-4"},
        ({"id": 7},),
        events,
        NOW + timedelta(minutes=5),
    )

    assert created is False
    assert cursor.idempotency_key is not None
    assert cursor.idempotency_key.startswith("candidate-contact-manual:4:20:")


class _CustomerLookupCursor:
    def __init__(self):
        self.sql = ""

    def execute(self, sql, _args):
        self.sql = sql

    def fetchone(self):
        return None


def test_adjustment_customer_lookup_aligns_binding_identity_collation():
    cursor = _CustomerLookupCursor()

    queued = worker_module._enqueue_adjustment_summary(
        object(), cursor, {"case_no": "CASE-COLLATION"}, (), NOW
    )

    assert queued is False
    assert "JOIN line_identity_role_bindings binding" in cursor.sql
    assert (
        "CAST(orders.client_id AS CHAR CHARACTER SET utf8mb4) COLLATE utf8mb4_unicode_ci"
        in cursor.sql
    )


def test_order_leaving_negotiation_cancels_only_unsent_manual_followup():
    class CancellationCursor:
        rowcount = 2

        def execute(self, sql, args):
            self.sql = sql
            self.args = args

    cursor = CancellationCursor()

    assert worker_module._cancel_inactive_order_manual_followups(cursor) == 2
    assert cursor.args == ("candidate_contact_manual_followup",)
    assert "SUBSTRING_INDEX(task.source_aggregate_identity,':',1) AS UNSIGNED" in cursor.sql
    assert " LIKE " not in cursor.sql
    assert "orders.status<>'洽談中'" in cursor.sql
    assert "processing_status IN ('pending','retryable_failed')" in cursor.sql
    assert "task.processing_status='cancelled'" in cursor.sql


def test_operation_requires_post_acceptance_terms_receipt_before_recontact():
    answered_at = datetime(2026, 9, 11, 8, tzinfo=timezone.utc)
    receipt_at = datetime(2026, 9, 11, 8, 5, tzinfo=timezone.utc)
    events = (
        {
            "id": 20,
            "candidate_id": 7,
            "event_type": "willingness_changed",
            "event_key": "response-20",
            "actor": "line:staff",
            "payload": json.dumps(
                {
                    "response_kind": "coordination_requested",
                    "issues": [
                        {
                            "mode": "condition_adjustment",
                            "category": "cooking_requirement",
                            "detail": "希望不需要下廚",
                        }
                    ],
                }
            ),
            "occurred_at": answered_at - timedelta(hours=1),
        },
        {
            "id": 30,
            "candidate_id": 7,
            "event_type": "willingness_changed",
            "event_key": "batch-30",
            "actor": "system",
            "payload": json.dumps(
                {
                    "response_kind": "adjustment_batch_dispatched",
                    "source_response_event_ids": [20],
                }
            ),
            "occurred_at": answered_at - timedelta(minutes=10),
        },
        {
            "id": 31,
            "candidate_id": 7,
            "event_type": "willingness_changed",
            "event_key": "answer-31",
            "actor": "line:customer",
            "payload": json.dumps(
                {
                    "response_kind": "adjustment_customer_answer",
                    "decision": "can_adjust",
                    "source_coordination_event_id": 30,
                }
            ),
            "occurred_at": answered_at,
        },
    )

    class Cursor:
        def __init__(self, receipt):
            self.receipt = receipt
            self.step = 0

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def execute(self, sql, args):
            self.step += 1
            if self.step == 4:
                assert "order_terms_apply_receipts" in sql
                assert args == (
                    "CASE-7",
                    "mobile-matching-followup:4:%",
                    answered_at,
                )

        def fetchone(self):
            if self.step == 1:
                return {"id": 4, "case_no": "CASE-7", "order_status": "洽談中"}
            if self.step == 4:
                return self.receipt
            return None

        def fetchall(self):
            if self.step == 2:
                return ({"id": 7, "staff_name": "王月嫂"},)
            if self.step == 3:
                return events
            return ()

    class Connection:
        def __init__(self, receipt):
            self._cursor = Cursor(receipt)

        def cursor(self):
            return self._cursor

        def close(self):
            pass

    blocked = worker_module.query_manual_followup_operation(
        lambda: Connection(None), 4, "CASE-7"
    )
    assert blocked.terms_change_completed is False
    assert blocked.recontact_allowed is False
    assert blocked.issues[0].formal_terms_supported is True
    assert blocked.candidates[0].recontact_queued is False

    ready = worker_module.query_manual_followup_operation(
        lambda: Connection({"created_at": receipt_at}), 4, "CASE-7"
    )
    assert ready.terms_change_completed is True
    assert ready.terms_change_receipt_at == receipt_at
    assert ready.recontact_allowed is True


def test_operation_does_not_reuse_an_older_acceptance_after_latest_decline():
    events = [
        _event(20, {"response_kind": "coordination_requested", "issues": [{"mode": "condition_adjustment"}]}),
        _event(30, {"response_kind": "adjustment_batch_dispatched", "source_response_event_ids": [20]}),
        _event(31, {"response_kind": "adjustment_customer_answer", "decision": "can_adjust", "source_coordination_event_id": 30}),
        _event(40, {"response_kind": "coordination_requested", "issues": [{"mode": "condition_adjustment"}]}),
        _event(50, {"response_kind": "adjustment_batch_dispatched", "source_response_event_ids": [40]}),
        _event(51, {"response_kind": "adjustment_customer_answer", "decision": "cannot_adjust", "source_coordination_event_id": 50}),
    ]

    with pytest.raises(ValueError, match="candidate_contact_customer_adjustment_not_accepted"):
        worker_module._latest_accepted_adjustment_answer(events)
