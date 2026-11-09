"""Same-case rejected source diagnostics must not widen eligible receipt facts."""
from copy import deepcopy
from datetime import date

import pytest

from api.schemas.client_receipt_reconciliation import ClientReceiptQueryView
from infrastructure.mysql.client_receipt_reconciliation_repository import _query_bank_facts, _query_bank_fact_blockers, _query_candidate_bank_rows


def bank(**changes):
    return {'id': 1, 'format_id': 'sinopac', 'direction': 'incoming', 'credit': 12000, 'debit': 0,
        'classification_type': 'client_receipt', 'reconciliation_status': 'pending', 'transaction_date': date(2026, 11, 8),
        'currency': 'TWD', 'ledger_entry_id': None, 'resolved_virtual_account_case_no': 'CASE',
        'dedup_fingerprint': 'a' * 64, **changes}


@pytest.mark.parametrize('changes,codes', [
    ({'transaction_date': None}, ('bank_transaction_date_missing',)),
    ({'currency': 'USD'}, ('bank_currency_not_twd',)),
    ({'transaction_date': None, 'currency': 'USD'}, ('bank_transaction_date_missing', 'bank_currency_not_twd')),
])
def test_rejected_sources_remain_ineligible_but_return_actual_same_case_causes(changes, codes):
    row = bank(**changes);before = deepcopy(row)
    assert _query_bank_facts((row,), 'CASE') == ()
    assert _query_bank_fact_blockers((row,), 'CASE') == ({'finance_import_row_id': 1, 'codes': codes},)
    assert row == before


def test_other_case_rejected_sources_do_not_leak_into_the_diagnostics():
    rows = (bank(transaction_date=None, resolved_virtual_account_case_no='OTHER'),
        bank(id=2, currency='USD', resolved_virtual_account_case_no=None))
    assert _query_bank_fact_blockers(rows, 'CASE') == ()


@pytest.mark.parametrize('currency', [None, 'TWD', 'NTD'])
def test_valid_receipt_sources_and_existing_currency_rules_stay_eligible(currency):
    rows = (bank(currency=currency),)
    assert len(_query_bank_facts(rows, 'CASE')) == 1
    assert _query_bank_fact_blockers(rows, 'CASE') == ()


def test_candidate_query_can_return_date_and_currency_rejections_without_writes():
    class Cursor:
        def execute(self, sql, params):
            assert sql.startswith('SELECT ')
            assert 'fir.transaction_date IS NOT NULL' not in sql
            assert "fir.currency IN ('TWD','NTD')" not in sql
            assert "fir.reconciliation_status='pending'" in sql
            assert 'ledger.id IS NULL' in sql
            assert params == ('CASE',)

        def fetchall(self):
            return (bank(transaction_date=None), bank(id=2, currency='USD'))

    rows = _query_candidate_bank_rows(Cursor(), 'CASE')
    view = ClientReceiptQueryView.model_validate({'case_no': 'CASE', 'account_version': 0, 'bank_facts': [], 'obligations': [],
        'bank_fact_blockers': _query_bank_fact_blockers(rows, 'CASE')})
    assert [item.codes for item in view.bank_fact_blockers] == [['bank_transaction_date_missing'], ['bank_currency_not_twd']]


@pytest.mark.parametrize('changes,code', [
    ({'transaction_date':None},'bank_transaction_date_missing'),
    ({'currency':'USD'},'bank_currency_not_twd'),
])
def test_preview_and_fresh_apply_return_the_same_source_cause_without_writes(monkeypatch, changes, code):
    from unittest.mock import MagicMock
    import infrastructure.mysql.client_receipt_reconciliation_repository as module
    from shared_kernel.fingerprints import PreviewFingerprint
    from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
    from subsystems.client_finance.reconciliation_workflow import ReconciliationSelection, ClientReconciliationWorkflow, ClientReconciliationApplyRequest
    source = bank(**changes); before = deepcopy(source)
    monkeypatch.setattr(module,'_load_account_version',lambda *args,**kwargs:0)
    monkeypatch.setattr(module,'_load_selected_bank_rows',lambda *args,**kwargs:(source,))
    monkeypatch.setattr(module,'_load_selected_obligations',lambda *args,**kwargs:())
    repository = module.MySqlClientReceiptReconciliationRepository(MagicMock())
    repository.find_receipt = lambda key: None
    repository.append_ledger_entries = MagicMock()
    unit = MagicMock()
    workflow = ClientReconciliationWorkflow(repository,lambda:unit)
    selection = ReconciliationSelection('CASE',None,('1',),('first',))
    with pytest.raises(ValueError,match=code): workflow.preview(selection)
    request = ClientReconciliationApplyRequest(selection,ExpectedVersion(0),PreviewFingerprint('a'*64),
        IdempotencyKey('blocked'),ActorContext('synthetic'),'合成來源拒絕',CorrelationId('blocked'))
    with pytest.raises(ValueError,match=code): workflow.apply(request)
    repository.append_ledger_entries.assert_not_called()
    unit.commit.assert_not_called()
    assert source == before
