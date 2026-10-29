from datetime import date

import pytest

from domains.client_finance.client_refund_reversal import (
    ClientFinanceCorrectionType,
    ClientRefundPurpose,
)
from domains.client_finance.subsidy_advance import subsidy_payout_is_advance
from subsystems.client_finance.client_refund_reversal_workflow import (
    ClientRefundReversalSelection,
)
from infrastructure.mysql.client_refund_reversal_repository import _load_subsidy_payout_funding


def _selection() -> ClientRefundReversalSelection:
    return ClientRefundReversalSelection(
        "C-1",
        ClientFinanceCorrectionType.REFUND,
        ClientRefundPurpose.SUBSIDY_RETURN,
        bank_fact_identities=("1",),
        obligation_identities=("subsidy:C-1",),
    )


def _facts(*, completed_on=date(2026, 1, 31)):
    return {
        "due_date": date(2026, 3, 15),
        "service_end_date": completed_on,
        "amount_due_ntd": 6000,
    }


def _funding(covered=(), *, paid_on=date(2026, 3, 15)):
    cursor = _Cursor(_facts(), covered)
    return _load_subsidy_payout_funding(cursor, _selection(), ({'transaction_date': paid_on},), False)


def test_uncovered_period_subsidy_payout_becomes_union_advance():
    assert subsidy_payout_is_advance(_funding(), 6000) is True


def test_covered_period_payout_remains_normal_subsidy_return():
    assert subsidy_payout_is_advance(_funding(({'id': 7},)), 6000) is False


def test_ambiguous_period_coverage_never_auto_nets_a_client_payout():
    with pytest.raises(ValueError, match="subsidy_advance_settlement_ambiguous"):
        _funding(({'id': 7}, {'id': 8}))


def test_partial_legacy_allocation_requires_review_instead_of_splitting_the_payout():
    from dataclasses import replace
    with pytest.raises(ValueError, match="subsidy_advance_settlement_ambiguous"):
        subsidy_payout_is_advance(replace(_funding(), allocated_at_payment_ntd=5000), 6000)


def test_advance_before_fixed_due_date_is_blocked():
    with pytest.raises(ValueError, match="subsidy_advance_not_due"):
        subsidy_payout_is_advance(_funding(paid_on=date(2026, 3, 14)), 6000)


class _Cursor:
    def __init__(self, row, covered):
        self._row = row
        self._covered = covered

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return None

    def execute(self, sql, parameters):
        if 'government_subsidy_period_members' in sql:
            assert 'entry.paid_on<=%s' in sql
            assert 'reversal.paid_on<=%s' in sql
            assert parameters[0] == 'C-1'

    def fetchone(self):
        return self._row

    def fetchall(self):
        return self._covered
