"""Canonical M1 oracle for the Orders terminal-closure LINE handoff."""

from __future__ import annotations

import json

import pytest

from domains.line.identities import LineUserId
from domains.line.identity_binding import (
    LineBindingSubjectType,
    LineIdentityBindingSnapshot,
    LineIdentityBindingStatus,
)
from shared_kernel.identities import ExpectedVersion
from infrastructure.mysql.orders_terminal_closure_source import _event_from_payload
from subsystems.line.terminal_closure_application import (
    TerminalClosureConsumerError,
    consume_terminal_closure,
)
from subsystems.line.terminal_closure_contracts import (
    TerminalClosureDecision,
    TerminalClosureSourceEvent,
)
from subsystems.line.terminal_closure_worker import LineTerminalClosureWorker


class _Receipts:
    def __init__(self):
        self.items = {}

    def get(self, key):
        return self.items.get(key.value)

    def append(self, receipt):
        self.items[receipt.key.value] = receipt


class _Outbox:
    def __init__(self):
        self.items = []

    def append(self, intent):
        self.items.append(intent)
        return len(self.items)


class _IdentityManagement:
    def __init__(self, case, active_cases=(), publication=None):
        self.case = case
        self.active = tuple(active_cases)
        self.publication = publication or {"id": 7, "line_rich_menu_id": "staff-menu"}

    def terminal_closure_case(self, case_no):
        return self.case

    def active_client_cases(self, line_user_id):
        return self.active

    def staff_menu_publication(self):
        return self.publication


class _Uow:
    def __init__(self, bindings, case, active_cases=(), publication=None):
        self.identities = type("Identities", (), {"list_by_user": lambda _self, _id: tuple(bindings)})()
        self.identity_management = _IdentityManagement(case, active_cases, publication)
        self.receipts = _Receipts()
        self.outbox = _Outbox()
        self.commits = 0

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def commit(self):
        self.commits += 1


class _OrdersClosureSource:
    def __init__(self, items):
        self.items = tuple(items)
        self.limits = []

    def list_pending(self, *, limit):
        self.limits.append(limit)
        return self.items


def _event(**changes):
    payload = {
        "source_event_identity": "case-terminal:CASE-M1:cancellation:4",
        "case_no": "CASE-M1",
        "terminal_kind": "cancellation",
        "orders_version": 4,
        "source_subject": "U-M1",
        "producer_reference": "orders.lifecycle_event:CASE-M1:4",
        "occurred_at": "2026-09-01T00:00:00+00:00",
        "correlation_id": "corr-M1",
        "idempotency_identity": "case-terminal:CASE-M1:cancellation:4",
    }
    payload.update(changes)
    return TerminalClosureSourceEvent(**payload)


def _binding(status=LineIdentityBindingStatus.BOUND, version=3):
    return LineIdentityBindingSnapshot(
        LineUserId("U-M1"), status, ExpectedVersion(version), LineBindingSubjectType.STAFF, "staff-9"
    )


def _factory(uow):
    def factory():
        return uow

    return factory


def _case(status="訂單取消"):
    return {"case_no": "CASE-M1", "status": status, "lifecycle_version": 4, "line_user_id": "U-M1"}


def test_terminal_closure_restores_staff_menu_once_and_keeps_opaque_line_intent():
    uow = _Uow([_binding()], _case())

    readback = consume_terminal_closure(_factory(uow), _event())

    assert readback.decision is TerminalClosureDecision.RESTORED
    assert readback.menu_intent_identity == "staff-default-restore:case-terminal:CASE-M1:cancellation:4"
    assert len(uow.outbox.items) == 1
    payload = json.loads(uow.outbox.items[0].payload_json)
    assert payload["restore_reason"] == "case_terminal_closure"
    assert payload["menu_definition_id"] == "staff_menu"
    assert payload["source_event_identity"] == _event().source_event_identity
    assert uow.commits == 1


def test_active_client_case_is_typed_noop_and_does_not_queue_menu():
    uow = _Uow([_binding()], _case(), active_cases=({"status": "服務中"},))

    readback = consume_terminal_closure(_factory(uow), _event())

    assert readback.decision is TerminalClosureDecision.BLOCKED_ACTIVE_CLIENT_CASE
    assert not uow.outbox.items
    assert uow.commits == 1


@pytest.mark.parametrize("status", [LineIdentityBindingStatus.REVOCATION_PENDING, LineIdentityBindingStatus.REVOKED])
def test_retirement_or_revocation_has_priority_over_restore(status):
    uow = _Uow([_binding(status)], _case())

    readback = consume_terminal_closure(_factory(uow), _event())

    assert readback.decision is TerminalClosureDecision.BLOCKED_REVOKED_STAFF
    assert not uow.outbox.items


def test_exact_replay_returns_noop_replay_without_duplicate_intent():
    uow = _Uow([_binding()], _case())
    first = consume_terminal_closure(_factory(uow), _event())
    replay = consume_terminal_closure(_factory(uow), _event())

    assert first.decision is TerminalClosureDecision.RESTORED
    assert replay.decision is TerminalClosureDecision.NOOP_REPLAY
    assert replay.replay_of is TerminalClosureDecision.RESTORED
    assert len(uow.outbox.items) == 1
    assert uow.commits == 1


def test_payload_mismatch_and_stale_orders_fail_closed_before_write():
    uow = _Uow([_binding()], _case())
    consume_terminal_closure(_factory(uow), _event())
    with pytest.raises(TerminalClosureConsumerError, match="idempotency_conflict"):
        consume_terminal_closure(_factory(uow), _event(correlation_id="different"))

    stale_uow = _Uow([_binding()], {**_case(), "lifecycle_version": 5})
    with pytest.raises(TerminalClosureConsumerError, match="orders_stale"):
        consume_terminal_closure(_factory(stale_uow), _event())
    assert not stale_uow.receipts.items
    assert not stale_uow.outbox.items


def test_subject_mismatch_fails_closed_without_receipt_or_menu():
    uow = _Uow([_binding()], {**_case(), "line_user_id": "U-other"})

    with pytest.raises(TerminalClosureConsumerError, match="subject_mismatch"):
        consume_terminal_closure(_factory(uow), _event())
    assert not uow.receipts.items
    assert not uow.outbox.items


def test_orders_outbox_payload_is_typed_without_a_new_schema_table():
    event = _event_from_payload(
        {
            "event_type": "case_terminal_closure",
            "source_event_identity": "case-terminal:CASE-M1:cancellation:4",
            "terminal_kind": "cancellation",
            "resulting_order_version": 4,
            "source_subject": "U-M1",
            "producer_reference": "orders.lifecycle_event:CASE-M1:4",
            "occurred_at": "2026-09-01T00:00:00+00:00",
            "correlation_id": "corr-M1",
            "idempotency_identity": "case-terminal:CASE-M1:cancellation:4",
        },
        case_no="CASE-M1",
    )
    assert event.case_no == "CASE-M1"
    assert event.orders_version == 4
    assert event.source_subject == "U-M1"


def test_terminal_closure_worker_bridges_read_only_orders_source_once_and_replays_safely():
    uow = _Uow([_binding()], _case())
    source = _OrdersClosureSource(((42, _event()),))
    uow.orders_terminal_closure_source = source

    worker = LineTerminalClosureWorker(_factory(uow), "line-worker:test", lambda: None)

    assert worker.run_once() == 1
    assert worker.run_once() == 1
    assert source.limits == [25, 25]
    assert len(uow.outbox.items) == 1
    assert uow.receipts.get(_event().idempotency_key).result_reference.endswith(":restored")
