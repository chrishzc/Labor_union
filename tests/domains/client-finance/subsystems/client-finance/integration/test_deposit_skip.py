from __future__ import annotations

from contextlib import AbstractContextManager
from types import SimpleNamespace

import pytest

from domains.client_finance.deposit_skip import (
    DepositSkipFacts,
    build_deposit_skip_candidate,
)
from shared_kernel.identities import (
    ActorContext,
    CorrelationId,
    ExpectedVersion,
    IdempotencyKey,
)
from subsystems.client_finance.deposit_skip_workflow import (
    DepositSkipApplyRequest,
    DepositSkipError,
    DepositSkipReceipt,
    DepositSkipSelection,
    DepositSkipWorkflow,
    StoredDepositSkipReceipt,
)
from subsystems.scheduling.assignment_plan_impacts import (
    _assignment_plan_readiness_blockers,
)


def facts(*, identity_status: str = "一般市民", received: int = 0) -> DepositSkipFacts:
    return DepositSkipFacts("CASE-001", 3, identity_status, 12000, received, False, "洽談中")


@pytest.mark.parametrize("identity_status", ["低收入戶", "中低收入戶", "非市民"])
def test_only_general_citizen_can_use_manual_deposit_skip(
    identity_status: str,
) -> None:
    candidate = build_deposit_skip_candidate(facts(identity_status=identity_status))

    assert candidate.blockers == ("deposit_skip.general_citizen_required",)
    assert candidate.mutates is False
    assert candidate.resulting_account_version == 3


def test_general_citizen_override_keeps_deposit_amount_and_allows_progression() -> None:
    candidate = build_deposit_skip_candidate(facts())

    assert candidate.blockers == ()
    assert candidate.deposit_required_ntd == 12000
    assert candidate.deposit_net_received_ntd == 0
    assert candidate.override_active is True
    assert candidate.mutates is True
    assert candidate.resulting_account_version == 4


def test_existing_override_repairs_pending_order_without_changing_finance_version() -> None:
    candidate = build_deposit_skip_candidate(
        DepositSkipFacts("CASE-001", 4, "一般市民", 12000, 0, True, "洽談中")
    )

    assert candidate.mutates is True
    assert candidate.resulting_account_version == 4
    assert candidate.override_active is True


def test_fully_settled_deposit_does_not_need_override() -> None:
    candidate = build_deposit_skip_candidate(facts(received=12000))

    assert candidate.blockers == (
        "deposit_skip.deposit_already_settled",
    )


def test_assignment_gate_accepts_override_without_marking_deposit_settled() -> None:
    workflow_facts = SimpleNamespace(
        assignment_plan=SimpleNamespace(
            current_waiting_lock_ids=(1,), effective_assignments=()
        ),
        lifecycle=SimpleNamespace(contract_completed=True),
        order_terms=SimpleNamespace(service_time=SimpleNamespace(complete=True)),
        client_finance=SimpleNamespace(deposit_gate_override_active=True),
    )

    blockers = _assignment_plan_readiness_blockers(
        workflow_facts,
        SimpleNamespace(deposit_settled=False),
    )

    assert blockers == ()


class UnitOfWork(AbstractContextManager["UnitOfWork"]):
    committed = False

    def __exit__(self, *_: object) -> None:
        return None

    def commit(self) -> None:
        self.committed = True


class Repository:
    def __init__(self) -> None:
        self.current = facts()
        self.receipts: dict[str, StoredDepositSkipReceipt] = {}
        self.audit: tuple[str, str] | None = None

    def load(self, selection: DepositSkipSelection, *, for_update: bool) -> DepositSkipFacts:
        assert selection.case_no == self.current.case_no
        return self.current

    def find_receipt(self, key: IdempotencyKey) -> StoredDepositSkipReceipt | None:
        return self.receipts.get(key.value)

    def apply(self, candidate: object, request: DepositSkipApplyRequest) -> None:
        self.audit = (request.actor.actor_id, request.reason)
        self.current = DepositSkipFacts("CASE-001", 4, "一般市民", 12000, 0, True, "洽談中")

    def save_receipt(
        self,
        key: IdempotencyKey,
        stored: StoredDepositSkipReceipt,
        preview: object,
    ) -> None:
        self.receipts[key.value] = stored


def test_apply_keeps_actor_reason_and_replays_same_command() -> None:
    repository = Repository()
    workflow = DepositSkipWorkflow(repository, UnitOfWork)
    preview = workflow.preview(DepositSkipSelection("CASE-001"))
    request = DepositSkipApplyRequest(
        selection=DepositSkipSelection("CASE-001"),
        expected_account_version=ExpectedVersion(3),
        preview_fingerprint=preview.fingerprint,
        idempotency_key=IdempotencyKey("deposit-skip-001"),
        actor=ActorContext("system-admin"),
        reason="公會突發狀況測試",
        correlation_id=CorrelationId("correlation-001"),
    )

    first = workflow.apply(request)
    replay = workflow.apply(request)

    assert first == DepositSkipReceipt("CASE-001", 4, True, False)
    assert replay == DepositSkipReceipt("CASE-001", 4, True, True)
    assert repository.audit == ("system-admin", "公會突發狀況測試")


def test_apply_rejects_stale_preview() -> None:
    repository = Repository()
    workflow = DepositSkipWorkflow(repository, UnitOfWork)
    preview = workflow.preview(DepositSkipSelection("CASE-001"))
    repository.current = DepositSkipFacts("CASE-001", 4, "一般市民", 12000, 0, False, "洽談中")
    request = DepositSkipApplyRequest(
        selection=DepositSkipSelection("CASE-001"),
        expected_account_version=ExpectedVersion(3),
        preview_fingerprint=preview.fingerprint,
        idempotency_key=IdempotencyKey("deposit-skip-stale"),
        actor=ActorContext("system-admin"),
        reason="公會突發狀況測試",
        correlation_id=CorrelationId("correlation-002"),
    )

    with pytest.raises(DepositSkipError) as caught:
        workflow.apply(request)

    assert caught.value.error.code == "deposit_skip.candidate_stale"
