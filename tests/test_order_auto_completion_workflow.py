"""Unit invariants for the canonical Orders service-completion command."""

from datetime import datetime

import pytest

from shared_kernel.errors import ErrorCategory
from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
from subsystems.orders.auto_completion_workflow import (
    AutoCompleteOrderService,
    AutoCompletionApplyRequest,
    AutoCompletionClaimState,
    AutoCompletionRepositoryConflictError,
    AutoCompletionRepositoryIntegrityError,
    AutoCompletionRepositoryNotFoundError,
    AutoCompletionWorkflowError,
)


class _UnitOfWork:
    def __enter__(self): return self
    def __exit__(self, *_): return False
    def commit(self): self.committed = True


class _Repository:
    def __init__(self, facts):
        self.facts, self.receipt, self.writes = facts, None, []

    def claim_command(self, *_): return AutoCompletionClaimState.CREATED
    def find_receipt(self, *_): return self.receipt
    def load_locked_facts(self, _): return self.facts
    def append_lifecycle_event(self, *_): self.writes.append("event"); return 9
    def update_order(self, *_): self.writes.append("order")
    def append_outbox(self, *_): self.writes.append("outbox")
    def save_receipt(self, receipt): self.writes.append("receipt"); self.receipt = type("Stored", (), {"command_fingerprint": receipt.command_fingerprint, "receipt": receipt})()


def _request(evaluation_at="2026-08-04T17:00:00+08:00"):
    return AutoCompletionApplyRequest("G05-CASE", ExpectedVersion(3), datetime.fromisoformat(evaluation_at), IdempotencyKey("g05-unit-key"), ActorContext("g05-test"), "scheduled completion evaluation", CorrelationId("g05-unit"))


def _facts(*, blockers=(), status="服務中", cancellation=False, completion="2026-08-04T17:00:00+08:00"):
    return {
        "locked_order": {"status": status},
        "authoritative_facts": {
            "cancellation": cancellation,
            "cancellation_reason": "fixture cancellation" if cancellation else None,
            "deposit_reconciled": False,
            "deposit_settlement_identity": None,
            "actual_start_date": "2026-08-04",
            "actual_end_date": "2026-08-04",
            "evaluation_at": "2026-08-04T17:00:00+08:00",
            "completion_instant": completion,
            "completion_facts_consistent": True,
            "actual_start_reconfirmed": True,
            "effective_scheduling_generation_id": 1,
            "official_service_dates": ("2026-08-04",),
            "transition_blockers": {"enter_service": (), "auto_complete": blockers},
            "manual_correction_target": None,
        },
    }


def test_auto_completion_applies_only_orders_lifecycle_and_outbox_once():
    repository = _Repository(_facts())
    service = AutoCompleteOrderService(repository, _UnitOfWork)
    receipt = service.apply(_request())
    assert receipt.order_version == 4
    assert repository.writes == ["event", "order", "outbox", "receipt"]


def test_auto_completion_before_instant_is_domain_blocked_without_writes():
    repository = _Repository(_facts(completion="2026-08-04T17:01:00+08:00"))
    with pytest.raises(AutoCompletionWorkflowError) as error:
        AutoCompleteOrderService(repository, _UnitOfWork).apply(_request())
    assert error.value.error.category is ErrorCategory.DOMAIN_BLOCKED
    assert repository.writes == []


def test_auto_completion_human_hold_is_domain_blocked_without_writes():
    repository = _Repository(_facts(blockers=("auto_complete.human_hold_active",)))
    with pytest.raises(AutoCompletionWorkflowError) as error:
        AutoCompleteOrderService(repository, _UnitOfWork).apply(_request())
    assert error.value.error.domain_blockers == ("auto_complete.human_hold_active",)
    assert repository.writes == []


@pytest.mark.parametrize(
    "facts",
    (_facts(status="訂單完成"), _facts(cancellation=True)),
)
def test_non_service_or_cancelled_order_is_domain_blocked_without_writes(facts):
    repository = _Repository(facts)
    with pytest.raises(AutoCompletionWorkflowError) as error:
        AutoCompleteOrderService(repository, _UnitOfWork).apply(_request())
    assert error.value.error.category is ErrorCategory.DOMAIN_BLOCKED
    assert repository.writes == []


def test_same_instant_is_normalized_to_taipei_before_fingerprinting():
    request = _request("2026-08-04T09:00:00+00:00")
    assert request.evaluation_at.isoformat() == "2026-08-04T17:00:00+08:00"


def test_idempotency_mismatch_is_typed_without_writes():
    repository = _Repository(_facts())
    repository.claim_command = lambda *_: AutoCompletionClaimState.MISMATCH
    with pytest.raises(AutoCompletionWorkflowError) as error:
        AutoCompleteOrderService(repository, _UnitOfWork).apply(_request())
    assert error.value.error.category is ErrorCategory.IDEMPOTENCY_MISMATCH
    assert repository.writes == []


@pytest.mark.parametrize(
    "exception, category, code",
    (
        (AutoCompletionRepositoryConflictError("stale"), ErrorCategory.CONFLICT, "order_version_conflict"),
        (AutoCompletionRepositoryIntegrityError("bad facts"), ErrorCategory.DOMAIN_BLOCKED, "auto_completion_authoritative_facts_invalid"),
        (AutoCompletionRepositoryNotFoundError("missing"), ErrorCategory.NOT_FOUND, "order_not_found"),
    ),
)
def test_repository_errors_keep_their_typed_meaning(exception, category, code):
    repository = _Repository(_facts())
    repository.load_locked_facts = lambda _: (_ for _ in ()).throw(exception)
    with pytest.raises(AutoCompletionWorkflowError) as error:
        AutoCompleteOrderService(repository, _UnitOfWork).apply(_request())
    assert error.value.error.category is category
    assert error.value.error.code == code
    assert repository.writes == []
