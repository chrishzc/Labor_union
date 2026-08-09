from datetime import date

from domains.government_subsidy.staff_payout_funding import (
    StaffPayoutFundingFacts,
    StaffPayoutFundingState,
    determine_staff_payout_funding_state,
)
from shared_kernel.money import MoneyNTD


def _facts(*, client_payable=0, full_subsidy_order=True, government_allocation=0, union_advance=0):
    return StaffPayoutFundingFacts(
        date(2026, 9, 15),
        MoneyNTD(30_000),
        MoneyNTD(client_payable),
        full_subsidy_order,
        MoneyNTD(government_allocation),
        MoneyNTD(union_advance),
    )


def test_state_machine_keeps_client_and_government_funding_paths_separate():
    assert determine_staff_payout_funding_state(
        _facts(client_payable=1, full_subsidy_order=False), date(2026, 9, 15)
    ) is StaffPayoutFundingState.CLIENT_RECEIPT_REQUIRED
    assert determine_staff_payout_funding_state(
        _facts(government_allocation=30_000), date(2026, 9, 15)
    ) is StaffPayoutFundingState.GOVERNMENT_FUNDED


def test_full_subsidy_due_date_without_government_receipt_enters_union_advance_state():
    assert determine_staff_payout_funding_state(
        _facts(), date(2026, 9, 15)
    ) is StaffPayoutFundingState.UNION_ADVANCE_DUE


def test_partial_or_excess_funding_never_auto_nets_and_requires_review():
    assert determine_staff_payout_funding_state(
        _facts(government_allocation=10_000), date(2026, 9, 15)
    ) is StaffPayoutFundingState.REVIEW_REQUIRED


def test_subsidy_eligible_order_with_a_floor_fee_stays_on_client_receipt_path():
    assert determine_staff_payout_funding_state(
        _facts(client_payable=900, full_subsidy_order=False), date(2026, 9, 15)
    ) is StaffPayoutFundingState.CLIENT_RECEIPT_REQUIRED
    assert determine_staff_payout_funding_state(
        _facts(union_advance=30_001), date(2026, 9, 15)
    ) is StaffPayoutFundingState.REVIEW_REQUIRED
