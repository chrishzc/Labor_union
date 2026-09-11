import hashlib
import json
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from domains.line.identities import LineSourceType, LineUserId
from infrastructure.mysql.candidate_contact_pool_line_reply_repository import (
    MySqlCandidateContactPoolLineReplyRepository,
)
from shared_kernel.identities import IdempotencyKey
from subsystems.line.candidate_contact_postback_application import (
    LineCandidateContactPostbackApplication,
)


class _Cursor:
    lastrowid = 44

    def __init__(self, reads, all_reads=()):
        self._reads = iter(reads)
        self._all_reads = iter(all_reads)
        self.executed = []
        self.writes = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, args):
        self.executed.append((sql, args))
        if sql.startswith(("INSERT", "UPDATE")):
            self.writes.append((sql, args))

    def fetchone(self):
        return next(self._reads)

    def fetchall(self):
        return next(self._all_reads, ())


class _Connection:
    def __init__(self, cursor):
        self._cursor = cursor

    def cursor(self):
        return self._cursor


class _ReplySpy:
    def __init__(self):
        self.calls = []

    def record_willingness(self, reference, willingness, line_user_id, event_key):
        self.calls.append((reference, willingness, line_user_id, event_key))
        return 91


def _binding(line_user_id="U-caregiver"):
    return {
        "source_event_id": 12,
        "pool_id": 4,
        "candidate_id": 7,
        "candidate_status": "active",
        "line_user_id": line_user_id,
        "order_status": "洽談中",
        "sent_at_utc": datetime(2026, 9, 10, 11, tzinfo=timezone.utc),
    }


def _inbox(data):
    return SimpleNamespace(event=SimpleNamespace(
        event_id=SimpleNamespace(value="webhook-event-1"),
        occurred_at=datetime(2026, 9, 10, tzinfo=timezone.utc),
        payload_json=json.dumps({"postback": {"data": data}}),
        source=SimpleNamespace(
            source_type=LineSourceType.USER,
            user_id=LineUserId("U-caregiver"),
        ),
    ))


def test_postback_adapter_passes_only_the_opaque_reference_and_event_identity():
    reply_spy = _ReplySpy()
    handled = LineCandidateContactPostbackApplication().handle(
        _inbox(f"candidate-contact:{'a' * 64}:unwilling"),
        SimpleNamespace(candidate_contact_pool_replies=reply_spy),
    )

    assert handled is True
    reference, willingness, line_user_id, event_key = reply_spy.calls[0]
    assert reference == "a" * 64
    assert willingness == "unwilling"
    assert line_user_id == LineUserId("U-caregiver")
    assert event_key.value == (
        "candidate-contact-postback:"
        + hashlib.sha256(b"webhook-event-1").hexdigest()
    )


def test_records_reply_only_for_the_line_user_bound_to_the_sent_information():
    cursor = _Cursor([_binding(), None])
    repository = MySqlCandidateContactPoolLineReplyRepository(
        _Connection(cursor),
        now=lambda: datetime(2026, 9, 10, 12, tzinfo=timezone.utc),
    )

    event_id = repository.record_willingness(
        "a" * 64,
        "willing",
        LineUserId("U-caregiver"),
        IdempotencyKey("candidate-contact-postback:webhook-1"),
    )

    assert event_id == 44
    inserted = next(args for sql, args in cursor.writes if sql.startswith("INSERT"))
    assert inserted[:3] == (4, 7, "candidate-contact-postback:webhook-1")
    assert json.loads(inserted[4]) == {
        "reason": "LINE 按鈕回覆願意承接",
        "source_information_event_id": 12,
        "willingness": "willing",
    }
    binding_sql = cursor.executed[0][0]
    assert "UNHEX(SHA2(source_event.event_key,256))=UNHEX(%s)" in binding_sql
    assert "SHA2(source_event.event_key,256)=%s" not in binding_sql
    assert (
        "CAST(answer_delivery.source_aggregate_identity AS UNSIGNED)=entry.id"
        in binding_sql
    )
    assert (
        "answer_delivery.source_aggregate_identity=CAST(entry.id AS CHAR)"
        not in binding_sql
    )
    cancellation_sql, cancellation_args = next(
        (sql, args)
        for sql, args in cursor.writes
        if sql.startswith("UPDATE line_delivery_tasks")
    )
    assert "CAST(source_aggregate_identity AS UNSIGNED)=%s" in cancellation_sql
    assert "source_aggregate_identity=CAST(%s AS CHAR)" not in cancellation_sql
    assert cancellation_args == (4, 4)


def test_rejects_a_forged_reply_from_a_different_line_user():
    cursor = _Cursor([_binding("U-right-user")])
    repository = MySqlCandidateContactPoolLineReplyRepository(
        _Connection(cursor),
        now=lambda: datetime(2026, 9, 10, 12, tzinfo=timezone.utc),
    )

    with pytest.raises(LookupError, match="recipient mismatch"):
        repository.record_willingness(
            "a" * 64,
            "willing",
            LineUserId("U-wrong-user"),
            IdempotencyKey("candidate-contact-postback:webhook-2"),
        )

    assert cursor.writes == []


def test_same_webhook_event_is_an_idempotent_replay():
    payload = {
        "reason": "LINE 按鈕回覆目前無法承接",
        "source_information_event_id": 12,
        "willingness": "unwilling",
    }
    cursor = _Cursor([
        _binding(),
        {
            "id": 43,
            "candidate_id": 7,
            "event_type": "willingness_changed",
            "payload": json.dumps(payload, ensure_ascii=False, sort_keys=True),
        },
    ])
    repository = MySqlCandidateContactPoolLineReplyRepository(
        _Connection(cursor),
        now=lambda: datetime(2026, 9, 10, 12, tzinfo=timezone.utc),
    )

    assert repository.record_willingness(
        "a" * 64,
        "unwilling",
        LineUserId("U-caregiver"),
        IdempotencyKey("candidate-contact-postback:webhook-3"),
    ) == 43
    assert cursor.writes == []


def test_rejects_a_new_postback_after_the_twenty_four_hour_window():
    binding = _binding()
    binding["sent_at_utc"] = datetime(2026, 9, 9, 12, tzinfo=timezone.utc)
    cursor = _Cursor([binding, None])
    repository = MySqlCandidateContactPoolLineReplyRepository(
        _Connection(cursor),
        now=lambda: datetime(2026, 9, 10, 12, tzinfo=timezone.utc),
    )

    with pytest.raises(ValueError, match="response expired"):
        repository.record_willingness(
            "a" * 64,
            "willing",
            LineUserId("U-caregiver"),
            IdempotencyKey("candidate-contact-postback:webhook-expired"),
        )

    assert cursor.writes == []


def test_rejects_other_candidate_responses_after_pool_has_a_willing_caregiver():
    cursor = _Cursor(
        [_binding(), None],
        all_reads=[
            (
                {
                    "candidate_id": 8,
                    "payload": json.dumps({"willingness": "willing"}),
                },
            )
        ],
    )
    repository = MySqlCandidateContactPoolLineReplyRepository(
        _Connection(cursor),
        now=lambda: datetime(2026, 9, 10, 12, tzinfo=timezone.utc),
    )

    with pytest.raises(ValueError, match="already resolved"):
        repository.record_willingness(
            "a" * 64,
            "unwilling",
            LineUserId("U-caregiver"),
            IdempotencyKey("candidate-contact-postback:webhook-late"),
        )

    assert cursor.writes == []


def test_candidate_can_replace_their_own_willing_response_with_unwilling():
    cursor = _Cursor(
        [_binding(), None],
        all_reads=[
            (
                {
                    "candidate_id": 7,
                    "payload": json.dumps({"willingness": "willing"}),
                },
            )
        ],
    )
    repository = MySqlCandidateContactPoolLineReplyRepository(
        _Connection(cursor),
        now=lambda: datetime(2026, 9, 10, 12, tzinfo=timezone.utc),
    )

    event_id = repository.record_willingness(
        "a" * 64,
        "unwilling",
        LineUserId("U-caregiver"),
        IdempotencyKey("candidate-contact-postback:webhook-revision"),
    )

    assert event_id == 44
    inserted = next(args for sql, args in cursor.writes if sql.startswith("INSERT"))
    assert json.loads(inserted[4])["willingness"] == "unwilling"
