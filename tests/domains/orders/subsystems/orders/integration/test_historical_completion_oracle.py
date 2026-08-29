"""
File: test_historical_completion_oracle.py
Description: 驗證歷史案件完成 Subsystem oracle 的 terminal、缺根與不可用語意。
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date

import pytest

from subsystems.orders.historical_completion_oracle import (
    CompletionOwner,
    CompletionReferral,
    HistoricalCompletionFacts,
    HistoricalCompletionState,
    HistoricalOrdersCompletionReadback,
    HistoricalSettlementReadback,
    HistoricalSettlementSourceVersion,
    SettlementSourceKind,
    evaluate_historical_completion,
)
from domains.orders.lifecycle import OrderLifecycleStatus


def _orders(**changes):
    facts = HistoricalOrdersCompletionReadback(
        case_no="CASE-1",
        lifecycle_version=7,
        canonical_status=OrderLifecycleStatus.COMPLETED,
        completion_lineage_identity="orders-completion:CASE-1:v7",
        actual_start_date=date(2026, 8, 1),
        official_service_fact_identity="assignment-service:CASE-1:v3",
        official_service_dates=(date(2026, 8, 1), date(2026, 8, 2)),
        required_service_day_count=2,
        service_time_tuple_complete=True,
    )
    return replace(facts, **changes)


def _settlement(owner, **changes):
    staff_sources = tuple(sorted((
        HistoricalSettlementSourceVersion(SettlementSourceKind.PAYROLL_CASE_ACCOUNT, "CASE-1", 4),
        HistoricalSettlementSourceVersion(SettlementSourceKind.STAFF_BANK_FACT, "bank:1", 1),
        HistoricalSettlementSourceVersion(SettlementSourceKind.STAFF_OBLIGATION, "obligation:1", 2),
        HistoricalSettlementSourceVersion(SettlementSourceKind.STAFF_OBLIGATION_EVENT, "event:1", 2),
        HistoricalSettlementSourceVersion(SettlementSourceKind.STAFF_PAYABLE_ACCOUNT, "staff:1", 3),
        HistoricalSettlementSourceVersion(SettlementSourceKind.STAFF_PAYABLE_PROJECTION, "obligation:1", 3),
        HistoricalSettlementSourceVersion(SettlementSourceKind.STAFF_PAYOUT_ALLOCATION, "allocation:1", 1),
        HistoricalSettlementSourceVersion(SettlementSourceKind.STAFF_PAYOUT_EVENT, "payout:1", 1),
    )))
    facts = HistoricalSettlementReadback(
        case_no="CASE-1",
        owner=owner,
        aggregate_version=4 if owner is CompletionOwner.CLIENT_FINANCE else None,
        settlement_lineage_identity=f"{owner.value}:settlement:CASE-1:v4",
        obligation_count=2,
        open_obligation_count=0,
        allocation_lineage_identity=f"{owner.value}:allocation:CASE-1:v4",
        source_versions=staff_sources if owner is CompletionOwner.STAFF_PAYABLES else (),
    )
    return replace(facts, **changes)


def _facts(**changes):
    return HistoricalCompletionFacts(
        case_no="CASE-1",
        orders=changes.pop("orders", _orders()),
        client_finance=changes.pop("client_finance", _settlement(CompletionOwner.CLIENT_FINANCE)),
        staff_payables=changes.pop("staff_payables", _settlement(CompletionOwner.STAFF_PAYABLES)),
    )


def test_all_owner_terminal_roots_are_required_for_step_11() -> None:
    result = evaluate_historical_completion(_facts())

    assert result.state is HistoricalCompletionState.COMPLETED
    assert result.step_11_completed
    assert result.missing_roots == ()
    assert result.owner_versions == (("orders", 7), ("client_finance", 4))
    assert result.owner_source_versions == _settlement(CompletionOwner.STAFF_PAYABLES).source_versions


@pytest.mark.parametrize(
    ("changes", "code", "referral"),
    [
        ({"canonical_status": OrderLifecycleStatus.COMPLETED, "completion_lineage_identity": None}, "orders_completion_lineage_missing", CompletionReferral.ORDERS_COMPLETION),
        ({"actual_start_date": None}, "orders_actual_start_missing", CompletionReferral.ORDERS_ACTUAL_START),
        ({"official_service_dates": (date(2026, 8, 1),)}, "scheduling_service_dates_incomplete", CompletionReferral.SCHEDULING_SERVICE_FACTS),
        ({"service_time_tuple_complete": False}, "scheduling_service_time_missing", CompletionReferral.SCHEDULING_SERVICE_FACTS),
    ],
)
def test_each_missing_completion_root_is_actionable(changes, code, referral) -> None:
    result = evaluate_historical_completion(_facts(orders=_orders(**changes)))

    assert result.state is HistoricalCompletionState.BLOCKED
    issue = next(item for item in result.missing_roots if item.code == code)
    assert issue.referral is referral
    assert issue.field_path
    assert issue.message


def test_known_scheduling_integrity_gap_keeps_exact_owner_referral() -> None:
    result = evaluate_historical_completion(
        _facts(
            orders=_orders(
                official_service_fact_identity=None,
                integrity_blockers=("scheduling.aggregate_missing",),
            )
        )
    )

    assert result.state is HistoricalCompletionState.BLOCKED
    issue = next(
        item for item in result.missing_roots
        if item.code == "scheduling_integrity_blocked:scheduling.aggregate_missing"
    )
    assert issue.owner is CompletionOwner.SCHEDULING
    assert issue.referral is CompletionReferral.SCHEDULING_SERVICE_FACTS
    assert "orders_readback_unavailable" not in {
        item.code for item in result.missing_roots
    }


def test_status_only_completed_does_not_clear_missing_lineage() -> None:
    result = evaluate_historical_completion(_facts(orders=_orders(completion_lineage_identity=None)))

    assert not result.step_11_completed
    assert "orders_completion_lineage_missing" in {item.code for item in result.missing_roots}


def test_finance_and_staff_are_independent_terminal_predicates() -> None:
    result = evaluate_historical_completion(
        _facts(client_finance=_settlement(CompletionOwner.CLIENT_FINANCE, open_obligation_count=1))
    )

    assert result.state is HistoricalCompletionState.BLOCKED
    assert {item.code for item in result.missing_roots} == {"client_finance_settlement_open"}


def test_unavailable_owner_readback_is_not_reported_as_completed() -> None:
    result = evaluate_historical_completion(
        _facts(staff_payables=_settlement(CompletionOwner.STAFF_PAYABLES, readback_available=False))
    )

    assert result.state is HistoricalCompletionState.UNAVAILABLE
    assert "staff_payables_readback_unavailable" in {item.code for item in result.missing_roots}


def test_open_recovery_source_is_lineage_not_a_step_11_blocker() -> None:
    staff = _settlement(
        CompletionOwner.STAFF_PAYABLES,
        source_versions=tuple(sorted(
            _settlement(CompletionOwner.STAFF_PAYABLES).source_versions
            + (
                HistoricalSettlementSourceVersion(SettlementSourceKind.STAFF_OVERPAYMENT_RECOVERY, "recovery:1", 3),
                HistoricalSettlementSourceVersion(SettlementSourceKind.STAFF_OVERPAYMENT_RECOVERY_EVENT, "recovery:1:10", 10),
            )
        )),
    )

    result = evaluate_historical_completion(_facts(staff_payables=staff))

    assert result.step_11_completed
    assert any(
        item.kind is SettlementSourceKind.STAFF_OVERPAYMENT_RECOVERY
        for item in result.owner_source_versions
    )


def test_case_identity_mismatch_is_rejected_before_evaluation() -> None:
    with pytest.raises(ValueError, match="case identity"):
        HistoricalCompletionFacts(
            "CASE-1",
            _orders(case_no="CASE-2"),
            _settlement(CompletionOwner.CLIENT_FINANCE),
            _settlement(CompletionOwner.STAFF_PAYABLES),
        )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("orders", {}, "Orders completion readback"),
        ("client_finance", [], "Client Finance completion readback"),
        ("staff_payables", "invalid", "Staff Payables completion readback"),
    ],
)
def test_completion_facts_reject_malformed_operands_with_typed_error(
    field, value, message
) -> None:
    changes = {field: value}

    with pytest.raises(TypeError, match=message):
        _facts(**changes)


def test_result_fingerprint_is_stable_for_same_owner_readbacks() -> None:
    first = evaluate_historical_completion(_facts())
    second = evaluate_historical_completion(_facts())

    assert first.fingerprint == second.fingerprint
    assert first.canonical_payload == second.canonical_payload


def test_result_fingerprint_covers_material_settlement_lineage() -> None:
    first = evaluate_historical_completion(_facts())
    changed_staff = _settlement(
        CompletionOwner.STAFF_PAYABLES,
        settlement_lineage_identity="staff_payables:settlement:CASE-1:changed",
    )
    second = evaluate_historical_completion(_facts(staff_payables=changed_staff))

    assert first.fingerprint != second.fingerprint


def test_result_fingerprint_covers_material_orders_roots() -> None:
    first = evaluate_historical_completion(_facts())
    changed = evaluate_historical_completion(
        _facts(orders=_orders(actual_start_date=date(2026, 8, 2)))
    )

    assert first.fingerprint != changed.fingerprint


def test_incomplete_staff_source_vector_is_unavailable() -> None:
    staff = _settlement(CompletionOwner.STAFF_PAYABLES)
    incomplete = replace(
        staff,
        source_versions=tuple(
            item for item in staff.source_versions
            if item.kind is not SettlementSourceKind.STAFF_PAYABLE_PROJECTION
        ),
    )

    result = evaluate_historical_completion(_facts(staff_payables=incomplete))

    assert result.state is HistoricalCompletionState.UNAVAILABLE


def test_maximum_length_integrity_blocker_is_reported_without_overflow() -> None:
    staff = _settlement(
        CompletionOwner.STAFF_PAYABLES,
        integrity_blockers=("x" * 191,),
    )

    result = evaluate_historical_completion(_facts(staff_payables=staff))

    assert result.state is HistoricalCompletionState.BLOCKED
    issue = next(item for item in result.missing_roots if item.field_path == "staff_payables.integrity")
    assert len(issue.code) <= 191
    assert len(issue.message) <= 191
    assert "fingerprint" in issue.message
