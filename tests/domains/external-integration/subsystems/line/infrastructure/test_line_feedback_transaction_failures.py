"""Focused transaction-contract regressions for the existing LINE feedback owner."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import pytest

from shared_kernel.identities import CorrelationId, IdempotencyKey
from subsystems.line.feedback_application import FeedbackConflictError, LineFeedbackApplication
from subsystems.line.feedback_contracts import FeedbackOutcome, RecordLineFeedback


@dataclass
class _Ticket:
    ticket_id: int


class _State:
    def __init__(self) -> None:
        self.feedback = {}
        self.receipts = {}
        self.tickets = []


class _FeedbackRepository:
    def __init__(self, staged: _State, *, fail_append: bool = False) -> None:
        self._staged = staged
        self._fail_append = fail_append

    def get(self, actor_id: str, source_response_id: str):
        return self._staged.feedback.get((actor_id, source_response_id))

    def append(self, root) -> None:
        if self._fail_append:
            raise RuntimeError("synthetic feedback persistence failure")
        self._staged.feedback[(root.actor_id, root.source_response_id)] = root


class _Receipts:
    def __init__(self, staged: _State) -> None:
        self._staged = staged

    def get(self, key):
        return self._staged.receipts.get(key.value)

    def append(self, receipt) -> None:
        self._staged.receipts[receipt.key.value] = receipt


class _CustomerService:
    def __init__(self, staged: _State, *, fail_after_stage: bool = False) -> None:
        self._staged = staged
        self._fail_after_stage = fail_after_stage

    def create_or_append(self, _message):
        ticket = _Ticket(len(self._staged.tickets) + 1)
        self._staged.tickets.append(ticket)
        if self._fail_after_stage:
            raise RuntimeError("synthetic ticket persistence failure")
        return ticket


class _TransactionalUnitOfWork:
    def __init__(
        self,
        committed: _State,
        *,
        fail_feedback: bool = False,
        fail_ticket: bool = False,
    ) -> None:
        self._committed = committed
        self._fail_feedback = fail_feedback
        self._fail_ticket = fail_ticket
        self._committed_this_scope = False

    def __enter__(self):
        staged = _State()
        staged.feedback = dict(self._committed.feedback)
        staged.receipts = dict(self._committed.receipts)
        staged.tickets = list(self._committed.tickets)
        self._staged = staged
        self.feedback = _FeedbackRepository(staged, fail_append=self._fail_feedback)
        self.receipts = _Receipts(staged)
        self.customer_service = _CustomerService(staged, fail_after_stage=self._fail_ticket)
        return self

    def __exit__(self, exception_type, exception, traceback):
        return False

    def commit(self) -> None:
        self._committed.feedback = dict(self._staged.feedback)
        self._committed.receipts = dict(self._staged.receipts)
        self._committed.tickets = list(self._staged.tickets)
        self._committed_this_scope = True


def _command(outcome: FeedbackOutcome) -> RecordLineFeedback:
    return RecordLineFeedback(
        actor_id="U-owner",
        source_response_id="knowledge-answer-receipt:42",
        outcome=outcome,
        binding_version=7,
        response_revision=1,
        catalog_revision=9,
        rule_revision=None,
        idempotency_key=IdempotencyKey("feedback-42"),
        correlation_id=CorrelationId("feedback-correlation-42"),
    )


def _application(state: _State, **failure_flags) -> LineFeedbackApplication:
    return LineFeedbackApplication(
        lambda: _TransactionalUnitOfWork(state, **failure_flags),
        lambda: datetime(2026, 9, 16, 12, tzinfo=timezone.utc),
    )


def test_exact_replay_is_stable_and_opposite_feedback_conflicts() -> None:
    state = _State()
    application = _application(state)

    first = application.apply(_command(FeedbackOutcome.RESOLVED))
    replay = application.apply(_command(FeedbackOutcome.RESOLVED))

    assert first.receipt.replayed is False
    assert replay.receipt.replayed is True
    assert replay.receipt.outcome is FeedbackOutcome.RESOLVED
    assert state.tickets == []
    assert len(state.feedback) == 1
    assert len(state.receipts) == 1

    with pytest.raises(FeedbackConflictError):
        application.apply(_command(FeedbackOutcome.UNRESOLVED))

    root = state.feedback[("U-owner", "knowledge-answer-receipt:42")]
    assert root.outcome is FeedbackOutcome.RESOLVED
    assert state.tickets == []
    assert len(state.feedback) == 1
    assert len(state.receipts) == 1


def test_ticket_failure_rolls_back_feedback_and_receipt() -> None:
    state = _State()
    application = _application(state, fail_ticket=True)

    with pytest.raises(RuntimeError, match="ticket persistence failure"):
        application.apply(_command(FeedbackOutcome.UNRESOLVED))

    assert state.tickets == []
    assert state.feedback == {}
    assert state.receipts == {}


def test_feedback_persistence_failure_rolls_back_created_ticket() -> None:
    state = _State()
    application = _application(state, fail_feedback=True)

    with pytest.raises(RuntimeError, match="feedback persistence failure"):
        application.apply(_command(FeedbackOutcome.UNRESOLVED))

    assert state.tickets == []
    assert state.feedback == {}
    assert state.receipts == {}
