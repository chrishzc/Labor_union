"""Canonical original bank references must reach the refund owner's guard."""
from copy import deepcopy
from datetime import date
import pytest

from domains.client_finance.client_refund_reversal import (
    ClientRefundBankFact, ClientRefundObligation, ClientRefundPurpose, build_client_refund_candidate,
)
from infrastructure.mysql.client_refund_reversal_repository import _refund_bank_facts
from shared_kernel.money import MoneyNTD


@pytest.mark.parametrize('format_id,reference_key,reference,account,eligible', [
    ('legacy', 'transaction_reference', '0000007004', None, True),
    ('legacy', 'transaction_reference', '0000007005', None, False),
    ('legacy', 'transaction_reference', None, '0000007004', True),
    ('legacy', 'transaction_reference', '0000007004', '0000007005', False),
    ('sinopac', '交易參考編號', '0000007004', None, True),
    ('taishin', 'transaction_reference', None, '0000007004', True),
])
def test_partial_refund_checks_the_complete_source_account_without_changing_bank_facts(
    format_id, reference_key, reference, account, eligible,
):
    row = {'id':16, 'format_id':format_id, 'bank_references':{reference_key:reference},
           'resolved_counterparty_account':account, 'direction':'outgoing', 'debit':200,
           'credit':0, 'effective_classification_type':'client_refund', 'reconciliation_status':'pending',
           'transaction_date':date(2026,11,2), 'ledger_entry_id':None, 'currency':'TWD'}
    original = deepcopy(row)
    facts = _refund_bank_facts((row,), 'CASE', ClientRefundPurpose.CUSTOMER_REFUND, '0000007004')
    obligation = ClientRefundObligation('refund:CASE', 'CASE', MoneyNTD(1000), 'refund')
    assert facts[0].eligible is eligible
    if eligible:
        candidate = build_client_refund_candidate('CASE', facts, (obligation,), allow_partial_refund_recovery=True)
        assert candidate.amount.amount == 200
        assert sum(item.amount.amount for item in candidate.allocations) == 200
    else:
        with pytest.raises(ValueError, match='bank_fact_not_eligible'):
            build_client_refund_candidate('CASE', facts, (obligation,), allow_partial_refund_recovery=True)
    assert row == original


@pytest.mark.parametrize(("amount", "fee", "allocated"), [
    (12000, 0, 12000),
    (11900, 100, 12000),
    (11899, 0, 11899),
])
def test_subsidy_return_fee_preserves_bank_amount_and_settles_only_within_threshold(amount, fee, allocated):
    bank = ClientRefundBankFact("16", "CASE", MoneyNTD(amount), "2026-11-02", True)
    obligation = ClientRefundObligation("return:CASE", "CASE", MoneyNTD(12000), "subsidy_return")

    candidate = build_client_refund_candidate("CASE", (bank,), (obligation,), ClientRefundPurpose.SUBSIDY_RETURN)

    assert candidate.amount == MoneyNTD(amount)
    assert candidate.transfer_fee == MoneyNTD(fee)
    assert sum(item.amount.amount for item in candidate.allocations) == allocated
