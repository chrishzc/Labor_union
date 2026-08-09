from datetime import date

import pytest

from domains.client_finance.client_refund_reversal import (
    ClientFinanceCorrectionType,
    ClientRefundPurpose,
)
from domains.finance_import.correction import (
    CorrectionAllocation,
    FinanceImportCorrectionCandidate,
    FinanceOwningDomain,
)
from domains.finance_import.planning import FinanceClassificationType
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.money import MoneyNTD
from subsystems.client_finance.client_refund_reversal_workflow import (
    ClientRefundReversalSelection,
)
from infrastructure.mysql.finance_import_owning_domain_composite import (
    _subsidy_payout_selection,
)


def _selection() -> ClientRefundReversalSelection:
    return ClientRefundReversalSelection(
        "C-1",
        ClientFinanceCorrectionType.REFUND,
        ClientRefundPurpose.SUBSIDY_RETURN,
        bank_fact_identities=("1",),
        obligation_identities=("subsidy:C-1",),
    )


def _candidate() -> FinanceImportCorrectionCandidate:
    return FinanceImportCorrectionCandidate(
        "finance-import-row:1",
        "finance-import-batch:1",
        FinanceClassificationType.CLIENT_SUBSIDY_RETURN,
        FinanceOwningDomain.CLIENT_FINANCE,
        MoneyNTD(6000),
        (CorrectionAllocation("subsidy:C-1", MoneyNTD(6000)),),
        "reviewed by test",
        ("bank-statement:line-1",),
        PreviewFingerprint("a" * 64),
    )


def _facts(*, allocated=0, completed_on=date(2026, 1, 31), occurred_on=date(2026, 3, 15)):
    return {
        "due_date": date(2026, 3, 15),
        "actual_end_date": completed_on,
        "transaction_date": occurred_on,
        "entitled_amount_ntd": 6000,
        "allocated_amount_ntd": allocated,
    }


def test_unallocated_first_quarter_subsidy_payout_becomes_union_advance():
    result = _subsidy_payout_selection(_Connection(_facts()), _candidate(), _selection())

    assert result.refund_purpose is ClientRefundPurpose.SUBSIDY_ADVANCE


def test_fully_allocated_subsidy_payout_remains_normal_subsidy_return():
    result = _subsidy_payout_selection(_Connection(_facts(allocated=6000)), _candidate(), _selection())

    assert result.refund_purpose is ClientRefundPurpose.SUBSIDY_RETURN


def test_partial_government_allocation_never_auto_nets_a_client_payout():
    with pytest.raises(ValueError, match="subsidy_advance_settlement_ambiguous"):
        _subsidy_payout_selection(_Connection(_facts(allocated=5000)), _candidate(), _selection())


def test_advance_before_fixed_due_date_is_blocked():
    with pytest.raises(ValueError, match="subsidy_advance_not_due"):
        _subsidy_payout_selection(
            _Connection(_facts(occurred_on=date(2026, 3, 14))), _candidate(), _selection()
        )


class _Connection:
    def __init__(self, row):
        self._row = row

    def cursor(self):
        return _Cursor(self._row)


class _Cursor:
    def __init__(self, row):
        self._row = row

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return None

    def execute(self, _sql, _parameters):
        return None

    def fetchone(self):
        return self._row
