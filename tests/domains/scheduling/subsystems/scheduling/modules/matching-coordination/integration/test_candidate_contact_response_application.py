import json
from datetime import datetime, timezone

from subsystems.line.candidate_contact_response_application import (
    _candidate_context,
    _customer_coordination_context,
    _enqueue_customer_questions,
    _pool_has_willing_candidate,
)
from domains.line.identities import LineUserId


class _Cursor:
    def __init__(self, rows):
        self._rows = rows

    def execute(self, _sql, _args):
        pass

    def fetchall(self):
        return self._rows


class _CandidateContextCursor:
    def __init__(self, row=None):
        self.sql = ""
        self.row = row if row is not None else {
            "line_user_id": "U-candidate",
            "sent_at_utc": object(),
        }

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, _args):
        self.sql = sql

    def fetchone(self):
        return self.row


class _Connection:
    def __init__(self, cursor):
        self._cursor = cursor

    def cursor(self):
        return self._cursor


def _event(candidate_id, payload):
    return {"candidate_id": candidate_id, "payload": json.dumps(payload)}


def test_pool_resolution_uses_each_candidate_latest_structured_response():
    cursor = _Cursor(
        (
            _event(7, {"willingness": "willing"}),
            _event(7, {"response_kind": "no_interest", "willingness": "unwilling"}),
            _event(8, {"willingness": "willing"}),
        )
    )

    assert _pool_has_willing_candidate(cursor, 4) is True


def test_coordination_system_events_do_not_mask_a_willing_candidate():
    cursor = _Cursor(
        (
            _event(7, {"willingness": "willing"}),
            _event(7, {"response_kind": "adjustment_batch_dispatched"}),
            _event(7, {"response_kind": "adjustment_customer_answer"}),
        )
    )

    assert _pool_has_willing_candidate(cursor, 4) is True


def test_candidate_may_replace_their_own_latest_willing_response():
    cursor = _Cursor(
        (
            _event(7, {"willingness": "willing"}),
        )
    )

    assert (
        _pool_has_willing_candidate(cursor, 4, excluding_candidate_id=7) is False
    )


def test_candidate_cannot_replace_response_when_another_candidate_is_willing():
    cursor = _Cursor(
        (
            _event(7, {"willingness": "willing"}),
            _event(8, {"willingness": "willing"}),
        )
    )

    assert _pool_has_willing_candidate(cursor, 4, excluding_candidate_id=7) is True


def test_candidate_context_aligns_cast_with_delivery_identity_collation():
    cursor = _CandidateContextCursor()

    _candidate_context(cursor, "a" * 64, LineUserId("U-candidate"), lock=False)

    assert (
        "CAST(entry.id AS CHAR CHARACTER SET utf8mb4) COLLATE utf8mb4_unicode_ci"
        in cursor.sql
    )


def test_customer_binding_lookup_aligns_cast_with_binding_identity_collation():
    cursor = _CandidateContextCursor(row={})

    queued = _enqueue_customer_questions(
        _Connection(cursor),
        {"case_no": "CASE-COLLATION"},
        object(),
        1,
        "event-key",
        datetime.now(timezone.utc),
    )

    assert queued is False
    assert "FROM orders JOIN line_identity_role_bindings binding" in cursor.sql
    assert (
        "CAST(orders.client_id AS CHAR CHARACTER SET utf8mb4) COLLATE utf8mb4_unicode_ci"
        in cursor.sql
    )


def test_customer_context_aligns_cast_with_binding_identity_collation():
    cursor = _CandidateContextCursor(
        row={
            "customer_line_user_id": "U-customer",
            "payload": json.dumps({
                "response_kind": "coordination_requested",
                "issues": [{"mode": "information_question"}],
            }),
        }
    )

    _customer_coordination_context(
        cursor,
        "b" * 64,
        LineUserId("U-customer"),
        lock=False,
    )

    assert (
        "CAST(orders.client_id AS CHAR CHARACTER SET utf8mb4) COLLATE utf8mb4_unicode_ci"
        in cursor.sql
    )
    assert "JOIN line_identity_role_bindings binding" in cursor.sql
