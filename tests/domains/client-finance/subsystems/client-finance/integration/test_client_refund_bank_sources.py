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


@pytest.mark.parametrize("amount,partial,fee,allocated", [
    (1000, False, 0, 1000), (1000, True, 0, 1000),
    (970, False, 30, 1000), (970, True, 0, 970),
    (900, False, 100, 1000), (900, True, 0, 900),
    (899, True, 0, 899), (300, True, 0, 300),
])
def test_explicit_partial_refund_preserves_unpaid_balance_instead_of_inventing_a_fee(
    amount, partial, fee, allocated,
):
    bank = ClientRefundBankFact("partial-source", "CASE", MoneyNTD(amount), "2026-11-06")
    obligation = ClientRefundObligation("refund:CASE", "CASE", MoneyNTD(1000), "refund")

    result = build_client_refund_candidate(
        "CASE", (bank,), (obligation,), allow_partial_refund_recovery=partial,
    )

    assert result.amount.amount == amount
    assert result.entries[0].amount.amount == amount
    assert result.transfer_fee.amount == fee
    assert sum(item.amount.amount for item in result.allocations) == allocated
    assert 1000 - allocated == (1000 - amount if partial else 0)


@pytest.mark.parametrize("amount,partial,error", [
    (899, False, "refund_requires_exact_settlement"),
    (1100, False, "allocation_exceeds_obligation"),
    (1100, True, "allocation_exceeds_obligation"),
])
def test_partial_refund_intent_does_not_remove_other_amount_blockers(amount, partial, error):
    bank = ClientRefundBankFact("blocked-source", "CASE", MoneyNTD(amount), "2026-11-06")
    obligation = ClientRefundObligation("refund:CASE", "CASE", MoneyNTD(1000), "refund")
    with pytest.raises(ValueError, match=error):
        build_client_refund_candidate(
            "CASE", (bank,), (obligation,), allow_partial_refund_recovery=partial,
        )
