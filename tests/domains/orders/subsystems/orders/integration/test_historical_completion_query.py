"""
File: test_historical_completion_query.py
Description: 驗證完成查詢只讀組合 owner roots、身分檢查與不可用 fail-closed。
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date

import pytest

from domains.orders.lifecycle import OrderLifecycleStatus
from shared_kernel.identities import CorrelationId
from subsystems.orders.historical_completion_oracle import (
    CompletionOwner,
    HistoricalCompletionState,
    HistoricalOrdersCompletionReadback,
    HistoricalSettlementReadback,
    HistoricalSettlementSourceVersion,
    SettlementSourceKind,
)
from subsystems.orders.historical_completion_query import (
    HistoricalCompletionQueryError,
    HistoricalCompletionQueryRequest,
    HistoricalCompletionQueryWorkflow,
)


class _Port:
    def __init__(self, value=None, error=None):
        self.value = value
        self.error = error
        self.calls = []

    def load_completion_readback(self, case_no, *, for_update=False):
        self.calls.append((case_no, for_update))
        if self.error:
            raise self.error
        return self.value


def _orders(case_no="CASE-1"):
    return HistoricalOrdersCompletionReadback(
        case_no=case_no,
        lifecycle_version=7,
        canonical_status=OrderLifecycleStatus.COMPLETED,
        completion_lineage_identity="orders-completion:CASE-1:v7",
        actual_start_date=date(2026, 8, 1),
        official_service_fact_identity="assignment-service:CASE-1:v3",
        official_service_dates=(date(2026, 8, 1), date(2026, 8, 2)),
        required_service_day_count=2,
        service_time_tuple_complete=True,
    )


def _settlement(owner, case_no="CASE-1"):
    return HistoricalSettlementReadback(
        case_no=case_no,
        owner=owner,
        aggregate_version=4 if owner is CompletionOwner.CLIENT_FINANCE else None,
        settlement_lineage_identity=f"{owner.value}:settlement:CASE-1:v4",
        obligation_count=2,
        open_obligation_count=0,
        allocation_lineage_identity=f"{owner.value}:allocation:CASE-1:v4",
        source_versions=tuple(sorted((
            HistoricalSettlementSourceVersion(SettlementSourceKind.PAYROLL_CASE_ACCOUNT, case_no, 4),
            HistoricalSettlementSourceVersion(SettlementSourceKind.STAFF_BANK_FACT, "bank:1", 1),
            HistoricalSettlementSourceVersion(SettlementSourceKind.STAFF_OBLIGATION, "obligation:1", 2),
            HistoricalSettlementSourceVersion(SettlementSourceKind.STAFF_OBLIGATION_EVENT, "event:1", 2),
            HistoricalSettlementSourceVersion(SettlementSourceKind.STAFF_PAYABLE_ACCOUNT, "staff:1", 3),
            HistoricalSettlementSourceVersion(SettlementSourceKind.STAFF_PAYABLE_PROJECTION, "obligation:1", 3),
            HistoricalSettlementSourceVersion(SettlementSourceKind.STAFF_PAYOUT_ALLOCATION, "allocation:1", 1),
            HistoricalSettlementSourceVersion(SettlementSourceKind.STAFF_PAYOUT_EVENT, "payout:1", 1),
        ))) if owner is CompletionOwner.STAFF_PAYABLES else (),
    )


def _workflow(orders=None, client=None, staff=None):
    ports = (
        _Port(orders if orders is not None else _orders()),
        _Port(
            client
            if client is not None
            else _settlement(CompletionOwner.CLIENT_FINANCE)
        ),
        _Port(
            staff
            if staff is not None
            else _settlement(CompletionOwner.STAFF_PAYABLES)
        ),
    )
    return HistoricalCompletionQueryWorkflow(*ports), ports


def test_query_reads_each_owner_once_without_lock_or_write() -> None:
    workflow, ports = _workflow()

    result = workflow.query(
        HistoricalCompletionQueryRequest("CASE-1"), CorrelationId("correlation:query")
    )

    assert result.state is HistoricalCompletionState.COMPLETED
    assert result.owner_versions == (("orders", 7), ("client_finance", 4))
    assert result.owner_source_versions == _settlement(CompletionOwner.STAFF_PAYABLES).source_versions
    assert [port.calls for port in ports] == [
        [("CASE-1", False)],
        [("CASE-1", False)],
        [("CASE-1", False)],
    ]


def test_missing_owner_readback_calls_oracle_and_stays_unavailable() -> None:
    workflow, ports = _workflow(client=None)
    ports[1].value = None

    result = workflow.execute(
        HistoricalCompletionQueryRequest("CASE-1"), CorrelationId("correlation:unavailable")
    )

    assert result.state is HistoricalCompletionState.UNAVAILABLE
    assert "client_finance_readback_unavailable" in {
        item.code for item in result.missing_roots
    }


def test_transient_owner_read_failure_is_fail_closed() -> None:
    workflow, ports = _workflow()
    ports[2].error = TimeoutError("database unavailable")

    result = workflow.query(
        HistoricalCompletionQueryRequest("CASE-1"), CorrelationId("correlation:timeout")
    )

    assert result.state is HistoricalCompletionState.UNAVAILABLE
    assert "staff_payables_readback_unavailable" in {
        item.code for item in result.missing_roots
    }


def test_unknown_database_driver_failure_is_also_fail_closed() -> None:
    workflow, ports = _workflow()
    ports[2].error = RuntimeError("driver-specific failure")

    result = workflow.query(
        HistoricalCompletionQueryRequest("CASE-1"), CorrelationId("correlation:driver")
    )

    assert result.state is HistoricalCompletionState.UNAVAILABLE


def test_owner_identity_mismatch_is_a_typed_conflict() -> None:
    workflow, _ = _workflow(orders=_orders("CASE-2"))

    with pytest.raises(HistoricalCompletionQueryError) as caught:
        workflow.query(
            HistoricalCompletionQueryRequest("CASE-1"),
            CorrelationId("correlation:identity"),
        )

    assert caught.value.error.code == "historical_completion_orders_scheduling_identity_mismatch"


def test_settlement_owner_mismatch_is_a_typed_conflict() -> None:
    workflow, _ = _workflow(
        client=_settlement(CompletionOwner.STAFF_PAYABLES)
    )

    with pytest.raises(HistoricalCompletionQueryError) as caught:
        workflow.query(
            HistoricalCompletionQueryRequest("CASE-1"),
            CorrelationId("correlation:owner"),
        )

    assert caught.value.error.code == "historical_completion_client_finance_owner_mismatch"


def test_invalid_owner_payload_is_rejected_before_oracle() -> None:
    workflow, ports = _workflow()
    ports[1].value = object()

    with pytest.raises(HistoricalCompletionQueryError) as caught:
        workflow.query(
            HistoricalCompletionQueryRequest("CASE-1"),
            CorrelationId("correlation:payload"),
        )

    assert caught.value.error.code == "historical_completion_client_finance_readback_invalid"


def test_query_does_not_change_readback_values() -> None:
    orders = _orders()
    workflow, _ = _workflow(orders=orders)

    result = workflow.query(
        HistoricalCompletionQueryRequest("CASE-1"), CorrelationId("correlation:stable")
    )

    assert result.fingerprint
    assert orders.lifecycle_version == 7
    assert replace(orders, lifecycle_version=7) == orders
