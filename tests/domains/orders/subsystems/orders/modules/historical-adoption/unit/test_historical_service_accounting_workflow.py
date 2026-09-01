"""Historical day-count accounting is one stale-safe outer transaction."""

from dataclasses import replace

import pytest

from domains.orders.historical_service_accounting import HistoricalActualServiceDaysInput
from domains.orders.lifecycle import OrderLifecycleStatus
from domains.payroll.calculation import PayrollPolicyKind, rate_snapshot
from shared_kernel.identities import ActorContext, CorrelationId, IdempotencyKey
from shared_kernel.money import MoneyNTD
from subsystems.orders.historical_service_accounting_workflow import (
    ApplyHistoricalServiceAccounting,
    ConfirmHistoricalServiceDaysIntent,
    HistoricalServiceAccountingAssignmentFacts,
    HistoricalServiceAccountingError,
    HistoricalServiceAccountingFacts,
    HistoricalServiceAccountingReceipt,
    HistoricalServiceAccountingWorkflow,
    StoredHistoricalServiceAccountingReceipt,
)


def _facts():
    return HistoricalServiceAccountingFacts(
        case_no="CASE-19",
        lifecycle_status=OrderLifecycleStatus.HISTORICAL_SERVICE_COMPLETED,
        lifecycle_version=3,
        adoption_receipt_id=19,
        adoption_source_identity="historical-source:19",
        historical_day_revision=0,
        client_finance_version=2,
        payroll_version=4,
        contracted_service_days=40,
        service_hours_per_day=9,
        contractual_floor_fee=MoneyNTD(4_000),
        client_identity_status="一般市民",
        assignments=(
            HistoricalServiceAccountingAssignmentFacts(
                "assignment:19",
                3,
                "月嫂甲",
                rate_snapshot("assignment:19", "policy:1", PayrollPolicyKind.CITIZEN),
                MoneyNTD(150),
            ),
        ),
        client_policy_version="client-policy:case-19",
        client_hourly_rate=MoneyNTD(275),
    )


class _Unit:
    def __init__(self, events):
        self.events = events

    def __enter__(self):
        self.events.append("enter")
        return self

    def __exit__(self, error_type, *_):
        self.events.append("rollback" if error_type else "exit")
        return False

    def commit(self):
        self.events.append("commit")


class _Repository:
    def __init__(self):
        self.facts = _facts()
        self.stored = None
        self.persist_calls = 0

    def load(self, case_no, *, for_update):
        assert case_no == "CASE-19"
        return self.facts

    def find_receipt(self, key):
        return self.stored

    def persist(self, request, candidate):
        self.persist_calls += 1
        receipt = HistoricalServiceAccountingReceipt(
            "CASE-19",
            1,
            3,
            5,
            candidate.service_days.total_actual_service_days,
            candidate.client_finance.total_receivable.amount,
            candidate.payroll.total_payable.amount,
            candidate.fingerprint,
        )
        return receipt


def _intent(days=3):
    return ConfirmHistoricalServiceDaysIntent(
        "CASE-19", (HistoricalActualServiceDaysInput("assignment:19", 3, days),)
    )


def _request(candidate):
    return ApplyHistoricalServiceAccounting(
        _intent(),
        3,
        0,
        2,
        4,
        candidate.fingerprint,
        IdempotencyKey("historical-days:19"),
        ActorContext("operator"),
        "核對舊系統實際服務天數",
        CorrelationId("historical-days:19"),
    )


def test_preview_uses_actual_three_days_for_both_client_and_staff() -> None:
    repository = _Repository()
    workflow = HistoricalServiceAccountingWorkflow(repository, lambda: _Unit([]))

    candidate = workflow.preview(_intent())

    assert candidate.service_days.total_actual_service_days == 3
    assert candidate.service_days.historical_floor_fee_ntd == 300
    assert candidate.client_finance.total_receivable == MoneyNTD(7_725)
    assert candidate.payroll.total_payable == MoneyNTD(8_550)
    assert candidate.payroll.assignments[0].effective_adjustments == MoneyNTD(150)
    assert candidate.payroll.assignments[0].double_pay_hours == 0


def test_apply_locks_rebuilds_and_commits_once() -> None:
    events = []
    repository = _Repository()
    workflow = HistoricalServiceAccountingWorkflow(repository, lambda: _Unit(events))
    preview = workflow.preview(_intent())

    receipt = workflow.apply(_request(preview))

    assert receipt.total_actual_service_days == 3
    assert repository.persist_calls == 1
    assert events == ["enter", "commit", "exit"]


def test_apply_rejects_stale_owner_version_and_rolls_back() -> None:
    events = []
    repository = _Repository()
    workflow = HistoricalServiceAccountingWorkflow(repository, lambda: _Unit(events))
    preview = workflow.preview(_intent())
    repository.facts = replace(repository.facts, client_finance_version=3)

    with pytest.raises(HistoricalServiceAccountingError) as caught:
        workflow.apply(_request(preview))

    assert caught.value.error.code == "historical_actual_service_days_candidate_stale"
    assert repository.persist_calls == 0
    assert events == ["enter", "rollback"]


def test_apply_replays_same_command_without_persisting_again() -> None:
    repository = _Repository()
    workflow = HistoricalServiceAccountingWorkflow(repository, lambda: _Unit([]))
    preview = workflow.preview(_intent())
    request = _request(preview)
    receipt = repository.persist(request, preview)
    from subsystems.orders.historical_service_accounting_workflow import _command_fingerprint

    repository.stored = StoredHistoricalServiceAccountingReceipt(
        _command_fingerprint(request), receipt
    )

    replay = workflow.apply(request)

    assert replay.replayed is True
    assert repository.persist_calls == 1


def test_only_historical_service_completed_is_eligible() -> None:
    repository = _Repository()
    repository.facts = replace(
        repository.facts,
        lifecycle_status=OrderLifecycleStatus.HISTORICAL_IN_SERVICE,
    )
    workflow = HistoricalServiceAccountingWorkflow(repository, lambda: _Unit([]))

    with pytest.raises(ValueError, match="historical_order_lifecycle_transition_invalid"):
        workflow.preview(_intent())


def test_confirmed_historical_service_days_are_immutable() -> None:
    repository = _Repository()
    repository.facts = replace(repository.facts, historical_day_revision=1)
    workflow = HistoricalServiceAccountingWorkflow(repository, lambda: _Unit([]))

    with pytest.raises(
        ValueError, match="historical_actual_service_days_already_confirmed"
    ):
        workflow.preview(_intent())
