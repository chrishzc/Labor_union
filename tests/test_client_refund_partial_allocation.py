from domains.client_finance.client_refund_reversal import (
    ClientRefundBankFact,
    ClientRefundObligation,
    ClientRefundPurpose,
    build_client_refund_candidate,
)
from infrastructure.mysql.client_refund_reversal_repository import (
    _settle_refund_obligations,
)
from shared_kernel.money import MoneyNTD


def _bank(amount: int) -> ClientRefundBankFact:
    return ClientRefundBankFact("bank-1", "C-1", MoneyNTD(amount), "2026-08-03")


def _obligation(identity: str, amount: int) -> ClientRefundObligation:
    return ClientRefundObligation(identity, "C-1", MoneyNTD(amount), "refund")


def test_partial_refund_allocates_bank_payment_without_forcing_full_settlement() -> None:
    candidate = build_client_refund_candidate("C-1", (_bank(300),), (_obligation("refund-1", 500),))

    assert candidate.amount == MoneyNTD(300)
    assert candidate.allocations[0].amount == MoneyNTD(300)
    assert candidate.affected_obligations == ("refund-1",)
    assert candidate.entries[0].entry_type == "refund"


def test_subsidy_return_uses_its_own_ledger_entry_type() -> None:
    obligation = ClientRefundObligation("subsidy-1", "C-1", MoneyNTD(500), "subsidy_return")

    candidate = build_client_refund_candidate(
        "C-1", (_bank(300),), (obligation,), ClientRefundPurpose.SUBSIDY_RETURN
    )

    assert candidate.entries[0].entry_type == "subsidy_return"


def test_union_subsidy_advance_uses_a_distinct_ledger_entry_type() -> None:
    obligation = ClientRefundObligation("subsidy-1", "C-1", MoneyNTD(500), "subsidy_return")

    candidate = build_client_refund_candidate(
        "C-1", (_bank(300),), (obligation,), ClientRefundPurpose.SUBSIDY_ADVANCE
    )

    assert candidate.entries[0].entry_type == "subsidy_advance"


def test_refund_larger_than_selected_payable_obligations_is_rejected() -> None:
    try:
        build_client_refund_candidate("C-1", (_bank(501),), (_obligation("refund-1", 500),))
    except ValueError as error:
        assert str(error) == "allocation_exceeds_obligation"
    else:
        raise AssertionError("over-refund must be rejected")


def test_projection_decrements_partial_refund_and_only_settles_exact_remainder() -> None:
    candidate = build_client_refund_candidate("C-1", (_bank(300),), (_obligation("refund-1", 500),))
    cursor = _UpdateCursor()

    _settle_refund_obligations(cursor, candidate, {"refund-1": 300}, 8)

    params = cursor.calls[0][1]
    assert params == (300, 300, 8, "refund-1", "C-1", 300)
    assert "amount_due_ntd=amount_due_ntd-%s" in cursor.calls[0][0]
    assert "CASE WHEN amount_due_ntd-%s=0 THEN 'settled' ELSE 'open' END" in cursor.calls[0][0]


class _UpdateCursor:
    rowcount = 1

    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    def execute(self, sql, params) -> None:
        self.calls.append((sql, params))
