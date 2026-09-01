"""Focused contract for the historical accounting-completed Preview/Apply command."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime

import pytest

from domains.orders.lifecycle import OrderLifecycleStatus
from shared_kernel.clock import FixedBusinessClock, TAIPEI_TIME_ZONE
from shared_kernel.identities import ActorContext, CorrelationId, IdempotencyKey
from subsystems.orders.historical_completion_apply import (
    ApplyHistoricalCompletion,
    HistoricalCompletionApplyError,
    HistoricalCompletionApplyFacts,
    HistoricalCompletionApplyWorkflow,
    HistoricalCompletionClaimState,
    HistoricalCompletionReceipt,
    StoredHistoricalCompletionReceipt,
)
from subsystems.orders.historical_completion_oracle import (
    CompletionOwner,
    HistoricalCompletionFacts,
    HistoricalOrdersCompletionReadback,
    HistoricalSettlementReadback,
    HistoricalSettlementSourceVersion,
    SettlementSourceKind,
    evaluate_historical_completion,
)


def _source_versions():
    identities = {
        SettlementSourceKind.PAYROLL_CASE_ACCOUNT: "CASE-1",
        SettlementSourceKind.STAFF_OBLIGATION: "obligation:1",
        SettlementSourceKind.STAFF_OBLIGATION_EVENT: "event:1",
        SettlementSourceKind.STAFF_PAYABLE_ACCOUNT: "staff:1",
        SettlementSourceKind.STAFF_PAYABLE_PROJECTION: "projection:1",
        SettlementSourceKind.STAFF_PAYOUT_EVENT: "payout:1",
        SettlementSourceKind.STAFF_PAYOUT_ALLOCATION: "allocation:1",
        SettlementSourceKind.STAFF_BANK_FACT: "bank:1",
    }
    return tuple(
        sorted(
            HistoricalSettlementSourceVersion(kind, identity, 2)
            for kind, identity in identities.items()
        )
    )


def _facts(*, status=OrderLifecycleStatus.HISTORICAL_SERVICE_COMPLETED, client_open=0):
    orders = HistoricalOrdersCompletionReadback(
        case_no="CASE-1",
        lifecycle_version=7,
        canonical_status=status,
        completion_lineage_identity="historical-adoption:CASE-1:v7",
        actual_start_date=date(2026, 8, 1),
        official_service_fact_identity=None,
        official_service_dates=(),
        required_service_day_count=40,
        service_time_tuple_complete=False,
        historical_service_day_count_identity="historical-days:CASE-1:v1",
        historical_assignment_day_counts=(("assignment:1", 1, 3),),
    )
    client = HistoricalSettlementReadback(
        "CASE-1",
        CompletionOwner.CLIENT_FINANCE,
        4,
        "client:settlement:4",
        1,
        client_open,
        "client:allocation:4",
    )
    staff = HistoricalSettlementReadback(
        "CASE-1",
        CompletionOwner.STAFF_PAYABLES,
        None,
        "staff:settlement:2",
        1,
        0,
        "staff:allocation:2",
        _source_versions(),
    )
    return HistoricalCompletionApplyFacts(
        evaluate_historical_completion(
            HistoricalCompletionFacts("CASE-1", orders, client, staff)
        ),
        date(2026, 8, 20),
    )


class _Unit:
    def __init__(self):
        self.committed = False
        self.rolled_back = False

    def __enter__(self):
        return self

    def __exit__(self, error_type, error, traceback):
        if error_type is not None or not self.committed:
            self.rolled_back = True

    def commit(self):
        self.committed = True


class _Repository:
    def __init__(self, facts=None):
        self.facts = facts or _facts()
        self.claim_state = HistoricalCompletionClaimState.CREATED
        self.stored = None
        self.loads = []
        self.persisted = []

    def load(self, case_no, *, for_update):
        self.loads.append((case_no, for_update))
        return self.facts

    def claim(self, request, fingerprint):
        self.claim_fingerprint = fingerprint
        return self.claim_state

    def find_receipt(self, key):
        return self.stored

    def persist(self, request, candidate):
        self.persisted.append((request, candidate))
        return HistoricalCompletionReceipt(
            candidate.case_no,
            91,
            candidate.resulting_order_version,
            candidate.after_status,
        )


def _workflow(repository):
    units = []

    def factory():
        unit = _Unit()
        units.append(unit)
        return unit

    return (
        HistoricalCompletionApplyWorkflow(
            repository,
            factory,
            FixedBusinessClock(datetime(2026, 9, 1, 9, tzinfo=TAIPEI_TIME_ZONE)),
        ),
        units,
    )


def _request(candidate, **changes):
    values = {
        "case_no": candidate.case_no,
        "expected_order_version": candidate.expected_order_version,
        "expected_client_finance_version": candidate.expected_client_finance_version,
        "expected_source_versions": candidate.expected_source_versions,
        "preview_fingerprint": candidate.fingerprint,
        "idempotency_key": IdempotencyKey("historical-completion:key-1"),
        "actor": ActorContext("admin"),
        "reason": "雙邊款項已核實結清",
        "correlation_id": CorrelationId("historical-completion:test"),
    }
    values.update(changes)
    return ApplyHistoricalCompletion(**values)


def test_preview_and_apply_append_one_terminal_transition_in_one_uow() -> None:
    repository = _Repository()
    workflow, units = _workflow(repository)
    preview = workflow.preview("CASE-1")

    receipt = workflow.apply(_request(preview))

    assert preview.before_status is OrderLifecycleStatus.HISTORICAL_SERVICE_COMPLETED
    assert preview.after_status is OrderLifecycleStatus.HISTORICAL_ACCOUNTING_COMPLETED
    assert preview.expected_order_version == 7
    assert receipt.resulting_order_version == 8
    assert repository.loads == [("CASE-1", False), ("CASE-1", True)]
    assert len(repository.persisted) == 1
    assert units[0].committed and not units[0].rolled_back


def test_open_client_balance_blocks_preview_and_writes_nothing() -> None:
    repository = _Repository(_facts(client_open=1))
    workflow, _ = _workflow(repository)

    with pytest.raises(ValueError, match="historical_accounting_completion_blocked"):
        workflow.preview("CASE-1")

    assert repository.persisted == []


def test_other_lifecycle_status_fails_closed() -> None:
    repository = _Repository(_facts(status=OrderLifecycleStatus.HISTORICAL_ACCOUNTING_COMPLETED))
    workflow, _ = _workflow(repository)

    with pytest.raises(ValueError, match="historical_order_lifecycle_transition_invalid"):
        workflow.preview("CASE-1")


def test_version_or_fingerprint_drift_rolls_back_without_persisting() -> None:
    repository = _Repository()
    workflow, units = _workflow(repository)
    preview = workflow.preview("CASE-1")

    with pytest.raises(HistoricalCompletionApplyError) as caught:
        workflow.apply(_request(preview, expected_client_finance_version=3))

    assert caught.value.error.code == "historical_accounting_completion_candidate_stale"
    assert repository.persisted == []
    assert units[0].rolled_back


def test_same_key_same_command_replays_without_reloading_or_writing() -> None:
    repository = _Repository()
    workflow, units = _workflow(repository)
    preview = workflow.preview("CASE-1")
    request = _request(preview)
    original = HistoricalCompletionReceipt(
        "CASE-1", 91, 8, OrderLifecycleStatus.HISTORICAL_ACCOUNTING_COMPLETED
    )
    from subsystems.orders.historical_completion_apply import _command_fingerprint

    repository.claim_state = HistoricalCompletionClaimState.MATCHED
    repository.stored = StoredHistoricalCompletionReceipt(
        _command_fingerprint(request), original
    )

    receipt = workflow.apply(request)

    assert receipt.replayed
    assert repository.loads == [("CASE-1", False)]
    assert repository.persisted == []
    assert units[0].rolled_back


def test_same_key_different_command_is_idempotency_conflict() -> None:
    repository = _Repository()
    workflow, _ = _workflow(repository)
    preview = workflow.preview("CASE-1")
    repository.claim_state = HistoricalCompletionClaimState.MISMATCH

    with pytest.raises(HistoricalCompletionApplyError) as caught:
        workflow.apply(_request(preview))

    assert caught.value.error.code == "idempotency_conflict"
    assert repository.persisted == []
