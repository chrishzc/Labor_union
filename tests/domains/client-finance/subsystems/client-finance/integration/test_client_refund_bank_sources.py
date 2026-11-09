"""Canonical original bank references must reach the refund owner's guard."""
from copy import deepcopy
from datetime import date
import pytest

from domains.client_finance.client_refund_reversal import (
    ClientRefundBankFact, ClientRefundObligation, ClientRefundPurpose, build_client_refund_candidate,
)
from infrastructure.mysql.client_refund_reversal_repository import _refund_bank_facts, _verify_taishin_subsidy_cases, _query_outgoing_bank_facts, _single_refund_recipient_account
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

    candidate = build_client_refund_candidate("CASE", (bank,), (obligation,), ClientRefundPurpose.SUBSIDY_RETURN,
                                              allow_partial_refund_recovery=amount < 11900)

    assert candidate.amount == MoneyNTD(amount)
    assert candidate.transfer_fee == MoneyNTD(fee)
    assert sum(item.amount.amount for item in candidate.allocations) == allocated


@pytest.mark.parametrize('memo,case_no,eligible', [
    ('HC115003', '115000003', True),
    ('HC115003', '115000004', False),
    ('HC115003 HC115004', '115000003', False),
    ('合成月嫂甲 HC115003', '115000003', False),
    ('無識別資料', '115000003', False),
])
def test_taishin_subsidy_revalidates_memo_case_and_name_priority_without_account(memo, case_no, eligible):
    class Cursor:
        def execute(self, statement, params=()):
            if 'FROM staff WHERE' in statement:
                self.rows = [{'name': '合成月嫂甲'}]
            elif 'FROM client_legacy_virtual_accounts' in statement:
                self.rows = [{'case_no': '115000003'}]
            else:
                raise AssertionError(statement)

        def fetchall(self):
            return self.rows

    row = {'id': 16, 'format_id': 'taishin', 'memo': memo, 'resolved_counterparty_account': None,
           'direction': 'outgoing', 'debit': 12000, 'credit': 0,
           'effective_classification_type': 'client_subsidy_return', 'reconciliation_status': 'pending',
           'transaction_date': date(2026, 11, 2), 'ledger_entry_id': None, 'currency': 'TWD'}
    rows = _verify_taishin_subsidy_cases(Cursor(), (row,))
    facts = _refund_bank_facts(rows, case_no, ClientRefundPurpose.SUBSIDY_RETURN, None)
    assert facts[0].eligible is eligible
    targets = _query_outgoing_bank_facts(rows, ({'obligation_identity': 'subsidy:test'},), ClientRefundPurpose.SUBSIDY_RETURN, case_no)
    assert bool(targets) is eligible
    assert 'taishin_memo_case_no' not in row and row['resolved_counterparty_account'] is None


def test_account_based_refund_cannot_use_another_obligations_snapshot_for_missing_account():
    with pytest.raises(ValueError, match='client_refund_recipient_account_ambiguous'):
        _single_refund_recipient_account(({'bank_account': 'synthetic-account'}, {'bank_account': None}))


@pytest.mark.parametrize('changes,obligations,code', [
    ({'transaction_date':None},[{'bank_account':None}],'bank_transaction_date_missing'),
    ({'currency':'USD'},[{'bank_account':None}],'bank_currency_not_twd'),
    ({},[],'outgoing_client_refund_no_open_obligation'),
    ({},[{'bank_account':None}],'client_refund_recipient_account_ambiguous'),
    ({},[{'bank_account':'0000007004'},{'bank_account':'0000007005'}],'client_refund_recipient_account_ambiguous'),
    ({'bank_references':{}},[{'bank_account':'0000007004'}],'client_refund_source_account_missing'),
    ({'bank_references':{'交易參考編號':'0000007005'}},[{'bank_account':'0000007004'}],'client_refund_recipient_account_mismatch'),
])
def test_sinopac_refund_source_failures_are_identical_in_owner_preview_and_fresh_apply(monkeypatch,changes,obligations,code):
    from unittest.mock import MagicMock
    from domains.client_finance.client_refund_reversal import ClientFinanceCorrectionType
    import infrastructure.mysql.client_refund_reversal_repository as adapter
    from subsystems.client_finance.client_refund_reversal_workflow import ClientRefundReversalWorkflow, ClientRefundReversalSelection, ClientRefundReversalApplyRequest, ClientRefundReversalError
    from shared_kernel.identities import ActorContext,CorrelationId,ExpectedVersion,IdempotencyKey
    from shared_kernel.fingerprints import PreviewFingerprint
    row={'id':97,'format_id':'sinopac','transaction_date':date(2026,10,20),'currency':'TWD','debit':12000,
         'bank_references':{'交易參考編號':'0000007004'},**changes}
    before=deepcopy(row)
    monkeypatch.setattr(adapter,'_case_exists',lambda *args:True)
    monkeypatch.setattr(adapter,'_load_account_version',lambda *args,**kwargs:4)
    monkeypatch.setattr(adapter,'_load_refund_bank_rows',lambda *args:(row,))
    monkeypatch.setattr(adapter,'_load_refund_obligation_rows',lambda *args:tuple(obligations))
    repo=adapter.MySqlClientRefundReversalRepository(MagicMock())
    repo.find_receipt=lambda *args:None
    repo.append_ledger_entries=MagicMock()
    unit=MagicMock(); unit.__enter__.return_value=unit
    workflow=ClientRefundReversalWorkflow(repo,lambda:unit)
    selection=ClientRefundReversalSelection('SYNTHETIC',ClientFinanceCorrectionType.REFUND,bank_fact_identities=('97',),obligation_identities=('refund:synthetic',))
    with pytest.raises(ClientRefundReversalError) as preview:workflow.preview(selection,CorrelationId('preview'))
    request=ClientRefundReversalApplyRequest(selection,ExpectedVersion(4),PreviewFingerprint('a'*64),IdempotencyKey('blocked'),ActorContext('synthetic'),'verify',CorrelationId('apply'))
    with pytest.raises(ClientRefundReversalError) as applied:workflow.apply(request)
    assert preview.value.error.code==applied.value.error.code==code
    repo.append_ledger_entries.assert_not_called()
    unit.commit.assert_not_called()
    assert row==before
    # Automatic resolution must preserve the same real owner rejection before posting.
    import infrastructure.mysql.finance_import_owning_domain_composite as posting
    from domains.finance_import.planning import CanonicalFinanceImportRow,FinanceClassificationType,FinanceImportDisposition
    connection=MagicMock()
    connection.cursor.return_value.__enter__.return_value.fetchone.return_value={'format_id':'sinopac','currency':row['currency']}
    monkeypatch.setattr(posting,'_sinopac_outgoing_case_info',lambda *args:(True,'SYNTHETIC',row['transaction_date']))
    monkeypatch.setattr(posting,'_load_client_refund_targets',lambda *args:({'case_no':'SYNTHETIC','obligation_identity':'refund:synthetic','due_date':date(2026,10,15),'amount_due_ntd':12000},))
    monkeypatch.setattr(posting,'MySqlClientRefundReversalRepository',lambda *args:repo)
    monkeypatch.setattr(posting,'_client_refund_selection',lambda *args:selection)
    candidate=CanonicalFinanceImportRow('finance-import-row:97',0,MoneyNTD(12000),FinanceClassificationType.CLIENT_REFUND,
        FinanceImportDisposition.BUSINESS_PENDING,PreviewFingerprint('c'*64),target_identities=('client:7',),
        evidence=('sinopac_unique_client_refund_account_in_transaction_reference',))
    pending=posting._resolve_client_refund(connection,candidate)
    assert pending.disposition is FinanceImportDisposition.BUSINESS_PENDING
    assert pending.pending_reason==code
    assert pending.available_actions==('resolve_owning_domain_target',)
