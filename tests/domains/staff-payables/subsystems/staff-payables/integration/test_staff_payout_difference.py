from __future__ import annotations

import pytest
from pathlib import Path

from domains.staff_payables.reconciliation import (
    OutgoingBankFact,
    StaffPayableFacts,
    StaffPayableStatus,
    StaffPayoutDifferenceMode,
    StaffPayoutEventType,
    StaffPrimaryBankAccount,
    build_staff_payout_candidate,
    build_staff_payout_difference_candidate,
)
from shared_kernel.identities import CorrelationId
from shared_kernel.money import MoneyNTD
from subsystems.staff_payables.payout_reconciliation import (
    StaffPayoutReconciliationFacts,
    StaffPayoutReconciliationWorkflow,
    StaffPayoutSelection,
)


def _bank(amount: int) -> OutgoingBankFact:
    return OutgoingBankFact("bank:1", 7, MoneyNTD(amount), "account:7")


def _payable() -> StaffPayableFacts:
    return StaffPayableFacts("obligation:1", 7, MoneyNTD(20_000))


def _accounts() -> tuple[StaffPrimaryBankAccount, ...]:
    return (StaffPrimaryBankAccount("account:7", 7),)


def test_general_payout_remains_exact_only():
    with pytest.raises(ValueError, match="staff_payout_amount_mismatch"):
        build_staff_payout_candidate((_bank(18_500),), (_payable(),))


def test_underpayment_keeps_remaining_obligation_without_recovery():
    candidate = build_staff_payout_difference_candidate(
        (_bank(18_500),), (_payable(),), StaffPayoutDifferenceMode.UNDERPAYMENT,
        bank_accounts=_accounts(), require_primary_account_owner=True,
    )

    assert candidate.resulting_status is StaffPayableStatus.PARTIALLY_PAID
    assert candidate.bank_total == MoneyNTD(18_500)
    assert candidate.obligation_total == MoneyNTD(20_000)
    assert candidate.allocations[0].amount == MoneyNTD(18_500)
    assert candidate.recovery is None


def test_overpayment_records_full_outflow_and_separate_recovery():
    candidate = build_staff_payout_difference_candidate(
        (_bank(21_000),), (_payable(),), StaffPayoutDifferenceMode.OVERPAYMENT,
        bank_accounts=_accounts(), require_primary_account_owner=True,
    )

    assert candidate.events[0].amount == MoneyNTD(21_000)
    assert candidate.obligation_links[0].allocated_amount == MoneyNTD(20_000)
    assert candidate.resulting_status is StaffPayableStatus.RECOVERY_REQUIRED
    assert candidate.recovery is not None
    assert candidate.recovery.original_amount == MoneyNTD(1_000)
    assert candidate.recovery.source_bank_fact_identities == ("bank:1",)


class _DifferenceRepository:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def load(self, _selection, *, for_update):
        self.calls.append(f"load:{for_update}")
        return StaffPayoutReconciliationFacts(
            4, 8, (_bank(21_000),), _accounts(), (_payable(),),
        )

    def find_receipt(self, _key):
        return None

    def append_events(self, _candidate):
        self.calls.append("events")

    def append_obligation_links(self, _candidate):
        self.calls.append("links")

    def append_overpayment_recovery(self, _candidate):
        self.calls.append("recovery")

    def update_payable_projection(self, _selection, _version, _status):
        self.calls.append("projection")

    def append_outbox(self, _candidate):
        self.calls.append("outbox")

    def save_receipt(self, _key, _receipt):
        self.calls.append("receipt")


def test_difference_preview_exposes_overpayment_recovery():
    workflow = StaffPayoutReconciliationWorkflow(_DifferenceRepository(), lambda: _UnitOfWork())
    selection = StaffPayoutSelection(
        StaffPayoutEventType.PAYOUT, ("bank:1",), ("obligation:1",),
        difference_mode=StaffPayoutDifferenceMode.OVERPAYMENT,
    )

    preview = workflow.preview(selection, CorrelationId("staff-difference-preview"))

    assert preview.candidate.recovery is not None
    assert preview.candidate.recovery.original_amount == MoneyNTD(1_000)


class _UnitOfWork:
    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def commit(self):
        return None


def test_difference_source_links_are_immutable() -> None:
    sql = Path("db/schema_parts/174_staff_payout_difference_source.sql").read_text(encoding="utf-8")

    assert "trg_staff_payout_difference_sources_before_update" in sql
    assert "trg_staff_payout_difference_source_rows_before_update" in sql
    assert "trg_staff_payout_difference_source_obligations_before_update" in sql


def test_staff_overpayment_recovery_delete_trigger_has_a_complete_mysql_header() -> None:
    sql = Path("db/schema_parts/168_staff_payout_difference_recovery.sql").read_text(encoding="utf-8")

    trigger = sql.split("CREATE TRIGGER trg_staff_overpayment_recoveries_before_delete", 1)[1]
    assert "BEFORE DELETE ON staff_overpayment_recoveries" in trigger.split(";", 1)[0]

    event_trigger = sql.split("CREATE TRIGGER trg_staff_overpayment_recovery_events_before_delete", 1)[1]
    assert "BEFORE DELETE ON staff_overpayment_recovery_events" in event_trigger.split(";", 1)[0]
