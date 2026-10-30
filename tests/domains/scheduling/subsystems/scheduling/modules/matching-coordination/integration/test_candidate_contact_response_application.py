"""Candidate intake preserves replies and leaves all coordination to staff."""
import json
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from domains.line.identities import LineUserId
from domains.scheduling.candidate_contact_response import parse_candidate_response
from shared_kernel.identities import IdempotencyKey
from subsystems.line import candidate_contact_response_application as application_module

NOW = datetime(2026, 10, 22, 4, tzinfo=timezone.utc)
QUESTION = {
    "source_event_id": 10, "pool_id": 4, "candidate_id": 7,
    "case_no": "CASE-1", "candidate_status": "active", "order_status": "洽談中",
    "line_user_id": "U-candidate", "staff_line_user_id": "U-candidate",
    "customer_line_user_id": "U-customer", "staff_name": "測試月嫂",
    "event_key": "original-question", "sent_at_utc": datetime(2026, 9, 1, tzinfo=timezone.utc),
    "payload": json.dumps({"response_kind": "coordination_requested", "issues": [
        {"category": "service_region", "mode": "information_question", "detail": "請問哪一區？"}
    ]}),
}

class _Connection:
    def __init__(self, cursor):
        self._cursor = cursor
    def cursor(self):
        return self._cursor


class _TransactionCursor:
    lastrowid = 51

    def __init__(self, reads=(), all_reads=()):
        self.reads = iter(reads)
        self.all_reads = iter(all_reads)
        self.executed = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, args):
        self.executed.append((sql, args))

    def fetchone(self):
        return next(self.reads)

    def fetchall(self):
        return next(self.all_reads, ())


class _Transaction(_Connection):
    committed = False
    rolled_back = False
    closed = False

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed = True


def test_staff_question_focus_filters_case_and_identity_before_pagination_without_writes():
    cursor = _TransactionCursor([{'total': 1}, None, None], all_reads=[(QUESTION,)])
    connection = _Transaction(cursor)
    result = application_module.CandidateContactResponseApplication(lambda: connection).query_staff_questions(
        case_no='CASE-1',question_id=10)
    assert [item['question_id'] for item in result['items']] == [10]
    count_sql,count_params = cursor.executed[0]
    list_sql,list_params = cursor.executed[1]
    assert 'pool.case_no=%s' in count_sql and 'source_event.id=%s' in count_sql
    assert count_params == ('CASE-1',10)
    assert list_params == ('CASE-1',10,25,0)
    assert list_sql.index('source_event.id=%s') < list_sql.index('LIMIT')
    assert not connection.committed and not connection.rolled_back and connection.closed


def test_staff_question_focus_does_not_select_another_question_when_unavailable():
    cursor = _TransactionCursor([{'total': 0}], all_reads=[()])
    connection = _Transaction(cursor)
    assert application_module.CandidateContactResponseApplication(lambda: connection).query_staff_questions(
        case_no='OTHER',question_id=10)['items'] == []
    assert not connection.committed


@pytest.fixture
def deliveries(monkeypatch):
    requests = []
    class Repository:
        def __init__(self, connection):
            pass

        def enqueue(self, request):
            requests.append(request)
            return SimpleNamespace(task_id=SimpleNamespace(value=1))

    monkeypatch.setattr(application_module, "MySqlLineDeliveryTaskRepository", Repository)
    monkeypatch.setattr(application_module, "configured_message_payload", lambda connection, code, default, variables: default)
    monkeypatch.setenv("LINE_LIFF_ID", "test-liff")
    return requests


@pytest.mark.parametrize("mode", ["information_question", "condition_adjustment"])
def test_intake_after_24_hours_records_only_an_internal_staff_task(mode, deliveries):
    cursor = _TransactionCursor([QUESTION, None])
    connection = _Transaction(cursor)
    response = parse_candidate_response(no_interest=False, issues=[{
        "category": "service_dates", "mode": mode, "detail": "希望延後一週。"
    }])
    result = application_module.CandidateContactResponseApplication(lambda: connection, lambda: NOW).submit(
        "a" * 64, LineUserId("U-candidate"), response, IdempotencyKey("intake")
    )
    assert connection.committed and connection.closed
    assert result["customer_message_queued"] is False and result["union_followup_required"] is True
    assert deliveries == []
    assert len([sql for sql, _ in cursor.executed if sql.startswith('INSERT')]) == 1


@pytest.mark.parametrize("recipient", ["customer", "caregiver"])
def test_information_reply_uses_authored_text_and_current_recipient(recipient, deliveries):
    cursor = _TransactionCursor(
        [QUESTION, None, None, None if recipient == "customer" else {"event_key": "information-card"}],
        [[{"id": 10, "payload": QUESTION['payload']}]],
    )
    connection = _Transaction(cursor)
    result = application_module.CandidateContactResponseApplication(lambda: connection, lambda: NOW).send_staff_information(
        10, recipient, "人員自己輸入的文案", "admin:1", IdempotencyKey("manual-send")
    )
    assert connection.committed and result["status"] == "queued"
    assert len(deliveries) == 1
    assert json.loads(deliveries[0].payload_json)["contents"]["body"]["contents"][1]["text"] == "人員自己輸入的文案"
    assert deliveries[0].recipient.identity.value == ("U-customer" if recipient == "customer" else "U-candidate")


@pytest.mark.parametrize("text", ["", "   ", "字" * 1001])
def test_staff_requires_valid_authored_text(text, deliveries):
    def unexpected():
        pytest.fail("invalid input must not start a transaction")
    with pytest.raises(ValueError, match="message_invalid"):
        application_module.CandidateContactResponseApplication(unexpected).send_staff_information(
            10, "customer", text, "admin:1", IdempotencyKey("empty")
        )
    assert deliveries == []


def test_exact_staff_replay_does_not_duplicate_delivery(deliveries):
    payload = {"response_kind": "information_answered", "source_response_event_id": 10,
               "recipient": "caregiver", "message_text": "回覆內容", "author": "admin:1"}
    connection = _Transaction(_TransactionCursor([QUESTION, {
        "id": 51, "candidate_id": 7, "event_type": "willingness_changed", "payload": payload
    }]))
    result = application_module.CandidateContactResponseApplication(lambda: connection).send_staff_information(
        10, "caregiver", "回覆內容", "admin:1", IdempotencyKey("replay")
    )
    assert result["status"] == "idempotent_replay" and connection.rolled_back
    assert deliveries == []


def test_candidate_form_stays_open_after_24_hours(deliveries):
    cursor = _TransactionCursor([QUESTION], [[{"id": 15, "payload": {"willingness": "willing"}}]])
    connection = _Transaction(cursor)
    result = application_module.CandidateContactResponseApplication(lambda: connection, lambda: NOW).query(
        "a" * 64, LineUserId("U-candidate")
    )
    assert result["status"] == "open" and result["deadline_at"] is None
    assert not connection.committed and deliveries == []


def test_new_candidate_response_blocks_a_stale_staff_question(deliveries):
    cursor = _TransactionCursor([QUESTION, None], [[{"id": 15, "payload": {"willingness": "willing"}}]])
    connection = _Transaction(cursor)
    with pytest.raises(ValueError, match="question_closed"):
        application_module.CandidateContactResponseApplication(lambda: connection).send_staff_information(
            10, "caregiver", "舊問題回覆", "admin:1", IdempotencyKey("stale")
        )
    assert connection.rolled_back and not connection.committed and deliveries == []
