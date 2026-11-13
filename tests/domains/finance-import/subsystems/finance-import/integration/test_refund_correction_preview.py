"""Refund corrections must run the owner check before Preview or any Apply write."""
from unittest.mock import Mock

import pytest

from domains.finance_import.correction import ClientRefundCorrectionPreview, CorrectionAllocation, CorrectionTargetObligation, FinanceImportCorrectionFacts, FinanceImportCorrectionSelection, FinanceOwningDomain, build_finance_import_correction_candidate
from shared_kernel.fingerprints import PreviewFingerprint
from domains.finance_import.planning import FinanceClassificationType
from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
from shared_kernel.money import MoneyNTD
from subsystems.finance_import.correction_workflow import FinanceImportCorrectionWorkflow, FinanceImportCorrectionWorkflowError, FinanceImportCorrectionApplyRequest


@pytest.mark.parametrize('kind,code', [
    (kind, code) for kind in (FinanceClassificationType.CLIENT_REFUND, FinanceClassificationType.CLIENT_SUBSIDY_RETURN)
    for code in ('bank_currency_not_twd', 'bank_transaction_date_missing', 'refund_requires_exact_settlement', 'allocation_exceeds_obligation')
] + [(FinanceClassificationType.CLIENT_REFUND, code) for code in ('client_refund_recipient_account_ambiguous', 'client_refund_recipient_account_mismatch')]
  + [(FinanceClassificationType.CLIENT_SUBSIDY_RETURN, code) for code in ('subsidy_advance_not_due', 'due_date_missing')])
def test_preview_and_fresh_apply_reject_same_owner_reason_before_writes(kind, code):
    selection = FinanceImportCorrectionSelection('finance-import-row:1', kind, ('refund:case',), '', ('source:1',))
    facts = FinanceImportCorrectionFacts('finance-import-batch:1', 1, 0, 1, MoneyNTD(12000), True,
        (CorrectionTargetObligation('refund:case', FinanceOwningDomain.CLIENT_FINANCE, MoneyNTD(12000)),))
    repository = Mock()
    repository.load.return_value = facts
    repository.find_correction_receipt.return_value = None
    port = Mock()
    port.preview_client_refund.return_value = ClientRefundCorrectionPreview(('refund:case',),
        (CorrectionAllocation('refund:case', MoneyNTD(12000)),), MoneyNTD(0), MoneyNTD(0), PreviewFingerprint('c'*64))
    unit = Mock()
    unit.__enter__ = Mock(return_value=unit)
    unit.__exit__ = Mock(return_value=False)
    workflow = FinanceImportCorrectionWorkflow(repository, port, lambda: unit)
    valid = workflow.preview(selection, CorrelationId('before-change'))
    port.preview_client_refund.side_effect = ValueError(code)
    with pytest.raises(FinanceImportCorrectionWorkflowError) as preview:
        workflow.preview(selection, CorrelationId('blocked-preview'))
    request = FinanceImportCorrectionApplyRequest(selection, ExpectedVersion(1), ExpectedVersion(0), ExpectedVersion(1),
        valid.fingerprint, IdempotencyKey('original-command'), ActorContext('synthetic'), CorrelationId('fresh-apply'))
    with pytest.raises(FinanceImportCorrectionWorkflowError) as applied:
        workflow.correct_and_post(request)
    assert preview.value.error.code == applied.value.error.code == code
    assert preview.value.error.domain_blockers == applied.value.error.domain_blockers == (code,)
    repository.append_manual_classification.assert_not_called()
    repository.append_reconciliation_receipt.assert_not_called()
    repository.save_correction_receipt.assert_not_called()
    port.post.assert_not_called()
    unit.commit.assert_not_called()


@pytest.mark.parametrize('fee', [0, 30, 100])
@pytest.mark.parametrize('kind,partial', [(FinanceClassificationType.CLIENT_REFUND, False), (FinanceClassificationType.CLIENT_REFUND, True), (FinanceClassificationType.CLIENT_SUBSIDY_RETURN, False), (FinanceClassificationType.CLIENT_SUBSIDY_RETURN, True)])
def test_customer_refund_correction_adopts_the_owner_fee_and_allocation(fee, kind, partial):
    from domains.client_finance.client_refund_reversal import ClientRefundBankFact, ClientRefundObligation, ClientRefundPurpose, build_client_refund_candidate
    purpose = ClientRefundPurpose.SUBSIDY_RETURN if kind is FinanceClassificationType.CLIENT_SUBSIDY_RETURN else ClientRefundPurpose.CUSTOMER_REFUND
    owner = build_client_refund_candidate('CASE', (ClientRefundBankFact('1', 'CASE', MoneyNTD(12000-fee), '2026-11-08'),),
        (ClientRefundObligation('refund:case', 'CASE', MoneyNTD(12000), 'subsidy_return' if purpose is ClientRefundPurpose.SUBSIDY_RETURN else 'refund'),), purpose, allow_partial_refund_recovery=partial)
    projection = ClientRefundCorrectionPreview(('refund:case',),
        tuple(CorrectionAllocation(item.obligation_identity, item.amount) for item in owner.allocations),
        owner.transfer_fee, MoneyNTD(0), owner.fingerprint)
    selection = FinanceImportCorrectionSelection('finance-import-row:1', kind, ('refund:case',), '', ('source:1',), allow_partial_refund_recovery=partial)
    facts = FinanceImportCorrectionFacts('finance-import-batch:1', 0, 0, 0, MoneyNTD(12000-fee), True,
        (CorrectionTargetObligation('refund:case', FinanceOwningDomain.CLIENT_FINANCE, MoneyNTD(12000)),))
    candidate = build_finance_import_correction_candidate(selection, facts, refund_preview=projection)
    assert candidate.bank_amount.amount == 12000-fee
    assert sum(item.amount.amount for item in candidate.allocations) == 12000
    assert candidate.refund_preview.transfer_fee.amount == fee
    assert candidate.refund_preview.remaining_amount.amount == 0


@pytest.mark.parametrize('kind', [FinanceClassificationType.CLIENT_REFUND, FinanceClassificationType.CLIENT_SUBSIDY_RETURN])
def test_changed_owner_preview_fails_as_typed_conflict_before_any_writer(kind):
    from dataclasses import replace
    from shared_kernel.errors import ErrorCategory
    selection = FinanceImportCorrectionSelection('finance-import-row:1', kind, ('refund:case',), '', ('source:1',))
    facts = FinanceImportCorrectionFacts('finance-import-batch:1', 0, 0, 0, MoneyNTD(12000), True,
        (CorrectionTargetObligation('refund:case', FinanceOwningDomain.CLIENT_FINANCE, MoneyNTD(12000)),))
    projection = ClientRefundCorrectionPreview(('refund:case',), (CorrectionAllocation('refund:case', MoneyNTD(12000)),), MoneyNTD(0), MoneyNTD(0), PreviewFingerprint('c'*64))
    repository = Mock(); repository.load.return_value = facts; repository.find_correction_receipt.return_value = None
    port = Mock();port.preview_client_refund.return_value = projection
    unit = Mock();unit.__enter__=Mock(return_value=unit);unit.__exit__=Mock(return_value=False)
    workflow = FinanceImportCorrectionWorkflow(repository, port, lambda: unit)
    preview = workflow.preview(selection, CorrelationId('before'))
    port.preview_client_refund.return_value = replace(projection, fingerprint=PreviewFingerprint('d'*64))
    request = FinanceImportCorrectionApplyRequest(selection, ExpectedVersion(0), ExpectedVersion(0), ExpectedVersion(0), preview.fingerprint, IdempotencyKey('same-command'), ActorContext('synthetic'), CorrelationId('after'))
    with pytest.raises(FinanceImportCorrectionWorkflowError) as raised:workflow.correct_and_post(request)
    assert raised.value.error.category is ErrorCategory.CONFLICT
    assert raised.value.error.code == 'stale_preview'
    repository.append_manual_classification.assert_not_called();port.post.assert_not_called();unit.commit.assert_not_called()


@pytest.mark.parametrize('kind', [FinanceClassificationType.CLIENT_REFUND, FinanceClassificationType.CLIENT_SUBSIDY_RETURN])
def test_owner_change_after_import_preflight_blocks_the_formal_refund_writer(monkeypatch, kind):
    import infrastructure.mysql.finance_import_owning_domain_composite as adapter
    from shared_kernel.errors import ErrorCategory

    selection = FinanceImportCorrectionSelection('finance-import-row:1', kind, ('refund:case',), '', ('source:1',))
    facts = FinanceImportCorrectionFacts('finance-import-batch:1', 0, 0, 0, MoneyNTD(11970), True,
        (CorrectionTargetObligation('refund:case', FinanceOwningDomain.CLIENT_FINANCE, MoneyNTD(12000)),))
    projection = ClientRefundCorrectionPreview(('refund:case',),
        (CorrectionAllocation('refund:case', MoneyNTD(12000)),), MoneyNTD(30), MoneyNTD(0), PreviewFingerprint('c'*64))
    candidate = build_finance_import_correction_candidate(selection, facts, refund_preview=projection)
    repository = Mock()
    workflow = Mock()
    workflow.preview.return_value = Mock(fingerprint=PreviewFingerprint('d'*64))
    monkeypatch.setattr(adapter, '_client_refund_selection' if kind is FinanceClassificationType.CLIENT_REFUND else '_client_subsidy_return_selection', lambda *args: object())
    monkeypatch.setattr(adapter, 'MySqlClientRefundReversalRepository', lambda *args: repository)
    monkeypatch.setattr(adapter, 'ClientRefundReversalWorkflow', lambda *args: workflow)

    composite = adapter.MySqlFinanceImportOwningDomainComposite(object())
    with pytest.raises(FinanceImportCorrectionWorkflowError) as raised:
        post = composite._post_client_refund if kind is FinanceClassificationType.CLIENT_REFUND else composite._post_client_subsidy_return
        post(candidate, Mock(correlation_id=CorrelationId('changed-owner')))
    assert raised.value.error.category is ErrorCategory.CONFLICT
    assert raised.value.error.code == 'stale_preview'
    repository.bind_apply_request.assert_not_called()
    workflow.apply.assert_not_called()
    if kind is FinanceClassificationType.CLIENT_REFUND:
        repository.clear_apply_request.assert_called_once()


def test_refund_preview_delegates_planned_classification_without_bank_mutation(monkeypatch):
    import infrastructure.mysql.client_refund_reversal_repository as adapter
    from domains.client_finance.client_refund_reversal import ClientFinanceCorrectionType, ClientRefundPurpose
    from subsystems.client_finance.client_refund_reversal_workflow import ClientRefundReversalSelection
    bank = {'id': 1, 'format_id': 'legacy', 'transaction_date': '2026-10-20', 'debit': 12000, 'credit': 0,
        'currency': 'TWD', 'direction': 'outgoing', 'effective_classification_type': 'non_business_review',
        'resolved_counterparty_account': 'synthetic-account', 'reconciliation_status': 'pending', 'ledger_entry_id': None}
    obligation = {'obligation_identity': 'refund:case', 'case_no': 'CASE', 'amount_due_ntd': 12000,
        'obligation_type': 'refund', 'bank_account': 'synthetic-account'}
    monkeypatch.setattr(adapter, '_load_refund_bank_rows', lambda *args: (bank,))
    monkeypatch.setattr(adapter, '_load_refund_obligation_rows', lambda *args: (obligation,))
    repo = adapter.MySqlClientRefundReversalRepository(object(), preview_refund_classification='client_refund')
    selection = ClientRefundReversalSelection('CASE', ClientFinanceCorrectionType.REFUND, ClientRefundPurpose.CUSTOMER_REFUND,
        bank_fact_identities=('1',), obligation_identities=('refund:case',))
    facts = repo._load_refund(object(), selection, False)
    assert facts['bank_facts'][0].eligible
    assert bank['effective_classification_type'] == 'non_business_review'
    with pytest.raises(ValueError, match='preview_only_repository'):
        repo.load(selection, for_update=True)


@pytest.mark.parametrize('field,value,code', [
    ('transaction_date', None, 'bank_transaction_date_missing'),
    ('currency', 'USD', 'bank_currency_not_twd'),
    ('resolved_counterparty_account', 'other-synthetic-account', 'client_refund_recipient_account_mismatch'),
])
def test_refund_owner_preserves_specific_source_failure_in_preview_and_apply(monkeypatch, field, value, code):
    import infrastructure.mysql.client_refund_reversal_repository as adapter
    from domains.client_finance.client_refund_reversal import ClientFinanceCorrectionType, ClientRefundPurpose
    from subsystems.client_finance.client_refund_reversal_workflow import ClientRefundReversalSelection
    row = {'id': 1, 'format_id': 'legacy', 'transaction_date': '2026-10-20', 'debit': 12000, 'credit': 0,
        'currency': 'TWD', 'resolved_counterparty_account': 'synthetic-account'}
    row[field] = value
    monkeypatch.setattr(adapter, '_load_refund_bank_rows', lambda *args: (row,))
    monkeypatch.setattr(adapter, '_load_refund_obligation_rows', lambda *args: ({'bank_account': 'synthetic-account'},))
    selection = ClientRefundReversalSelection('CASE', ClientFinanceCorrectionType.REFUND, ClientRefundPurpose.CUSTOMER_REFUND,
        bank_fact_identities=('1',), obligation_identities=('refund:case',))
    for locked in (False, True):
        with pytest.raises(ValueError, match=code):
            adapter.MySqlClientRefundReversalRepository(object())._load_refund(object(), selection, locked)


@pytest.mark.parametrize('amounts,fee,due', [((12000,),0,'2026-10-15'),((12000,),30,'2026-10-15'),((12000,),100,'2026-10-15'),((6000,6000),0,'2026-10-15'),((6000,6000),30,'2026-10-15'),((6000,6000),100,'2026-10-15'),((12000,),0,None)])
def test_sinopac_refund_real_owner_and_import_correction_agree_and_replay_once(monkeypatch,amounts,fee,due):
    """CF-03: real workflows/rules/read adapter; persistence is a stateful synthetic double, not MySQL."""
    from copy import deepcopy
    from datetime import date
    from unittest.mock import MagicMock
    import infrastructure.mysql.finance_import_owning_domain_composite as posting
    import infrastructure.mysql.client_refund_reversal_repository as storage
    from domains.client_finance.client_refund_reversal import ClientFinanceCorrectionType
    from subsystems.client_finance.client_refund_reversal_workflow import ClientRefundReversalSelection

    total=sum(amounts); cash=total-fee
    ids=tuple(f'refund:{i}' for i in range(len(amounts)))
    bank={'id':97,'format_id':'sinopac','direction':'outgoing','debit':cash,'credit':0,'currency':'TWD',
          'transaction_date':date(2026,10,20),'bank_references':{'交易參考編號':'0000007004'},
          'effective_classification_type':'client_refund','reconciliation_status':'pending','ledger_entry_id':None}
    before=deepcopy(bank)
    state={'version':4,'remaining':dict(zip(ids,amounts)),'receipts':{},'ledger':[],'allocations':[],'outbox':[]}
    class OwnerRepository(storage.MySqlClientRefundReversalRepository):
        def find_receipt(self,key):return state['receipts'].get(key.value)
        def append_ledger_entries(self,candidate):state['ledger'].extend(candidate.entries)
        def append_allocations(self,candidate):state['allocations'].extend(candidate.allocations)
        def update_projection(self,candidate,version):
            for item in candidate.allocations:state['remaining'][item.obligation_identity]-=item.amount.amount
            state['version']=version;bank['reconciliation_status']='completed';bank['ledger_entry_id']=1
        def append_outbox(self,candidate,version):state['outbox'].append(version)
        def save_receipt(self,key,receipt):state['receipts'][key.value]=receipt
    monkeypatch.setattr(storage,'_case_exists',lambda *args:True)
    monkeypatch.setattr(storage,'_load_account_version',lambda *args,**kwargs:state['version'])
    monkeypatch.setattr(storage,'_load_refund_bank_rows',lambda *args:(bank,))
    monkeypatch.setattr(storage,'_load_refund_obligation_rows',lambda *args:tuple(
        dict(obligation_identity=i,case_no='SYNTHETIC',obligation_type='refund',amount_due_ntd=a,bank_account='0000007004')
        for i,a in state['remaining'].items() if a>0))
    monkeypatch.setattr(posting,'MySqlClientRefundReversalRepository',OwnerRepository)
    owner_selection=ClientRefundReversalSelection('SYNTHETIC',ClientFinanceCorrectionType.REFUND,bank_fact_identities=('97',),obligation_identities=ids)
    monkeypatch.setattr(posting,'_client_refund_selection',lambda *args:owner_selection)
    connection=MagicMock()
    connection.cursor.return_value.__enter__.return_value.fetchone.return_value={'format_id':'sinopac','currency':'TWD'}
    monkeypatch.setattr(posting,'_sinopac_outgoing_case_info',lambda *args:(True,'SYNTHETIC','2026-10-20'))
    monkeypatch.setattr(posting,'_load_client_refund_targets',lambda *args:tuple(
        dict(case_no='SYNTHETIC',obligation_identity=i,due_date=due,amount_due_ntd=a) for i,a in zip(ids,amounts)))
    from domains.finance_import.planning import CanonicalFinanceImportRow,FinanceImportDisposition
    automatic=CanonicalFinanceImportRow('finance-import-row:97',0,MoneyNTD(cash),FinanceClassificationType.CLIENT_REFUND,
        FinanceImportDisposition.BUSINESS_PENDING,PreviewFingerprint('c'*64),target_identities=('client:7',),
        evidence=('sinopac_unique_client_refund_account_in_transaction_reference',))
    ready=posting._resolve_client_refund(connection,automatic)
    if due is None:
        assert ready.disposition is FinanceImportDisposition.BUSINESS_PENDING and ready.pending_reason=='due_date_missing'
    else:
        assert ready.disposition is FinanceImportDisposition.CREATE and ready.target_identities==ids and ready.pending_reason is None
    port=posting.MySqlFinanceImportOwningDomainComposite(connection)
    selection=FinanceImportCorrectionSelection('finance-import-row:97',FinanceClassificationType.CLIENT_REFUND,ids,'',('synthetic-source',))
    facts=FinanceImportCorrectionFacts('finance-import-batch:1',0,0,0,MoneyNTD(cash),True,
        tuple(CorrectionTargetObligation(i,FinanceOwningDomain.CLIENT_FINANCE,MoneyNTD(a)) for i,a in zip(ids,amounts)))
    repo=MagicMock();repo.load.return_value=facts
    receipts={}
    repo.find_correction_receipt.side_effect=lambda key:receipts.get(key.value)
    repo.save_correction_receipt.side_effect=lambda key,value:receipts.update({key.value:value})
    repo.append_alert_resolved_event.return_value=0
    unit=MagicMock();unit.__enter__.return_value=unit
    workflow=FinanceImportCorrectionWorkflow(repo,port,lambda:unit)
    checked=workflow.preview(selection,CorrelationId('preview'))
    assert state['ledger']==[] and bank==before
    assert checked.candidate.bank_amount.amount==cash
    assert checked.candidate.refund_preview.transfer_fee.amount==fee
    assert checked.candidate.refund_preview.remaining_amount.amount==0
    assert sum(a.amount.amount for a in checked.candidate.allocations)==total
    request=FinanceImportCorrectionApplyRequest(selection,ExpectedVersion(0),ExpectedVersion(0),ExpectedVersion(0),checked.fingerprint,
        IdempotencyKey('same-refund-command'),ActorContext('synthetic'),CorrelationId('apply'))
    port.bind_request(request)
    try:
        first=workflow.correct_and_post(request)
        second=workflow.correct_and_post(request)
    finally:port.clear_request()
    assert first==second
    assert len(state['ledger'])==1 and state['ledger'][0].amount.amount==cash
    assert len(state['allocations'])==len(amounts)
    assert all(value==0 for value in state['remaining'].values())
    assert state['version']==5 and len(state['outbox'])==1 and len(state['receipts'])==1
    assert bank['debit']==before['debit'] and bank['bank_references']==before['bank_references']
    repo.append_manual_classification.assert_called_once()
    repo.append_reconciliation_receipt.assert_called_once()
    repo.save_correction_receipt.assert_called_once()
    unit.commit.assert_called_once()


@pytest.mark.parametrize('covered',[False,True])
@pytest.mark.parametrize('amounts,cash,overage,issue',[
    ((6000,),6000,False,None),((6000,),5970,False,None),((6000,),5900,False,None),
    ((2500,3500),5900,False,None),((6000,),6030,True,None),((2500,3500),6030,True,None),
    ((6000,),6000,False,'date'),((6000,),6000,False,'currency'),((6000,),6000,False,'due'),
    ((6000,),6000,False,'memo_missing'),((6000,),6000,False,'memo_staff'),
    ((6000,),6000,False,'memo_case'),((6000,),6000,False,'early'),
])
def test_taishin_subsidy_real_readers_correction_posting_and_recovery_replay(monkeypatch,covered,amounts,cash,overage,issue):
    """Actual source/funding readers + owner/import workflows; synthetic persistence, not MySQL."""
    from copy import deepcopy
    from datetime import date
    from unittest.mock import MagicMock
    import infrastructure.mysql.finance_import_owning_domain_composite as posting
    import infrastructure.mysql.client_refund_reversal_repository as storage
    from domains.finance_import.planning import CanonicalFinanceImportRow,FinanceImportDisposition
    case='115000003'; ids=tuple(f'subsidy:{i}' for i in range(len(amounts))); total=sum(amounts)
    due=None if issue=='due' else date(2026,3,15)
    memo='合成月嫂甲 HC115003' if issue=='memo_staff' else '無辨識資料' if issue=='memo_missing' else 'HC115004' if issue=='memo_case' else 'HC115003'
    bank={'id':97,'format_id':'taishin','direction':'outgoing','memo':memo,'debit':cash,'credit':0,
          'currency':'USD' if issue=='currency' else 'TWD','transaction_date':None if issue=='date' else date(2026,3,14) if issue=='early' else date(2026,3,15),
          'effective_classification_type':'client_subsidy_return','reconciliation_status':'pending','ledger_entry_id':None,
          'resolved_counterparty_account':None,'bank_references':{}}
    before=deepcopy(bank)
    state={'version':4,'remaining':dict(zip(ids,amounts)),'receipts':{},'ledger':[],'allocations':[],'outbox':[], 'recoveries':[], 'recovery_events':[]}
    def obligations():
        return tuple(dict(obligation_identity=i,case_no=case,obligation_type='subsidy_return',amount_due_ntd=a,
                          due_date=due,service_end_date=date(2026,2,28)) for i,a in state['remaining'].items() if a>0)
    class Cursor:
        def __enter__(self):return self
        def __exit__(self,*args):return False
        def close(self):pass
        def execute(self,sql,params=()):
            if 'FROM finance_import_rows WHERE' in sql:self.rows=(bank,)
            elif 'FROM staff WHERE' in sql:self.rows=({'name':'合成月嫂甲'},)
            elif 'SELECT id,name FROM clients' in sql:self.rows=()
            elif sql=='SELECT case_no FROM orders WHERE case_no=%s FOR UPDATE':self.rows=({'case_no':case},)
            elif 'FROM client_legacy_virtual_accounts' in sql:self.rows=({'case_no':'115000004' if params[0].endswith('115004') else case},)
            elif 'FROM government_subsidy_period_members' in sql:self.rows=({'id':7},) if covered else ()
            elif 'FROM client_obligations' in sql:self.rows=obligations()
            elif sql.startswith('INSERT INTO client_over_refund_recoveries '):state['recoveries'].append(params);self.rows=()
            elif sql.startswith('INSERT INTO client_over_refund_recovery_events '):state['recovery_events'].append(params);self.rows=()
            else:raise AssertionError(sql)
        def fetchone(self):return self.rows[0] if self.rows else None
        def fetchall(self):return self.rows
    class Connection:
        def cursor(self):return Cursor()
    connection=Connection()
    class OwnerRepository(storage.MySqlClientRefundReversalRepository):
        def find_receipt(self,key):return state['receipts'].get(key.value)
        def append_ledger_entries(self,candidate):
            state['ledger'].extend(candidate.entries)
            self._entry_ids.update({entry.identity:1 for entry in candidate.entries})
        def append_allocations(self,candidate):state['allocations'].extend(candidate.allocations)
        def update_projection(self,candidate,version):
            for item in candidate.allocations:state['remaining'][item.obligation_identity]-=item.amount.amount
            state['version']=version;bank['reconciliation_status']='completed';bank['ledger_entry_id']=1
        def append_outbox(self,candidate,version):state['outbox'].append(candidate)
        def save_receipt(self,key,receipt):state['receipts'][key.value]=receipt
    monkeypatch.setattr(storage,'_case_exists',lambda *args:True)
    monkeypatch.setattr(storage,'_load_account_version',lambda *args,**kwargs:state['version'])
    monkeypatch.setattr(storage,'_load_refund_bank_rows',lambda *args:(bank,))
    monkeypatch.setattr(storage,'_load_refund_obligation_rows',lambda *args:obligations())
    monkeypatch.setattr(posting,'MySqlClientRefundReversalRepository',OwnerRepository)
    code={'date':'bank_transaction_date_missing','currency':'bank_currency_not_twd','due':'due_date_missing',
          'memo_missing':'client_subsidy_memo_recipient_unconfirmed','memo_staff':'client_subsidy_memo_staff_matched',
          'memo_case':'client_subsidy_memo_case_mismatch'}.get(issue)
    if issue=='early' and not covered:code='subsidy_advance_not_due'
    # These are existing canonical sources under fresh re-verification, not new
    # imports that classify a missing memo or a staff memo as customer subsidy.
    if issue!='memo_case':
        automatic=CanonicalFinanceImportRow('finance-import-row:97',0,MoneyNTD(cash),FinanceClassificationType.CLIENT_SUBSIDY_RETURN,
            FinanceImportDisposition.BUSINESS_PENDING,PreviewFingerprint('c'*64),evidence=(posting.TAISHIN_CLIENT_SUBSIDY_MEMO_REASON,),pending_reason='due_date_missing')
        result=posting._resolve_client_subsidy_return(connection,automatic)
        if code or overage:
            assert result.pending_reason==(code or 'outgoing_client_refund_amount_mismatch')
            assert result.disposition is FinanceImportDisposition.BUSINESS_PENDING
        else:
            assert result.disposition is FinanceImportDisposition.CREATE and result.pending_reason is None
    selection=FinanceImportCorrectionSelection('finance-import-row:97',FinanceClassificationType.CLIENT_SUBSIDY_RETURN,ids,'',('synthetic-source',),allow_refund_overage_recovery=overage)
    facts=FinanceImportCorrectionFacts('finance-import-batch:1',0,0,0,MoneyNTD(cash),True,
        tuple(CorrectionTargetObligation(i,FinanceOwningDomain.CLIENT_FINANCE,MoneyNTD(a)) for i,a in zip(ids,amounts)))
    repo=MagicMock();repo.load.return_value=facts;receipts={}
    repo.find_correction_receipt.side_effect=lambda key:receipts.get(key.value)
    repo.save_correction_receipt.side_effect=lambda key,value:receipts.update({key.value:value})
    repo.append_alert_resolved_event.return_value=0
    unit=MagicMock();unit.__enter__.return_value=unit
    port=posting.MySqlFinanceImportOwningDomainComposite(connection)
    workflow=FinanceImportCorrectionWorkflow(repo,port,lambda:unit)
    if code:
        with pytest.raises(FinanceImportCorrectionWorkflowError) as preview:workflow.preview(selection,CorrelationId('preview'))
        request=FinanceImportCorrectionApplyRequest(selection,ExpectedVersion(0),ExpectedVersion(0),ExpectedVersion(0),PreviewFingerprint('f'*64),IdempotencyKey('blocked'),ActorContext('synthetic'),CorrelationId('apply'))
        with pytest.raises(FinanceImportCorrectionWorkflowError) as applied:workflow.correct_and_post(request)
        assert preview.value.error.code==applied.value.error.code==code
        assert state['ledger']==state['allocations']==state['recoveries']==[] and bank==before
        repo.append_manual_classification.assert_not_called();unit.commit.assert_not_called()
        return
    checked=workflow.preview(selection,CorrelationId('preview'))
    assert state['ledger']==[] and bank==before
    assert checked.candidate.refund_preview.transfer_fee.amount==max(total-cash,0)
    assert checked.candidate.refund_preview.remaining_amount.amount==0
    request=FinanceImportCorrectionApplyRequest(selection,ExpectedVersion(0),ExpectedVersion(0),ExpectedVersion(0),checked.fingerprint,
        IdempotencyKey('same-taishin-refund'),ActorContext('synthetic'),CorrelationId('apply'))
    port.bind_request(request)
    try:
        first=workflow.correct_and_post(request);second=workflow.correct_and_post(request)
    finally:port.clear_request()
    assert first==second and len(state['ledger'])==1
    assert state['ledger'][0].amount.amount==cash
    assert state['ledger'][0].entry_type==('subsidy_return' if covered else 'subsidy_advance')
    assert len(state['allocations'])==len(ids) and sum(a.amount.amount for a in state['allocations'])==total
    assert all(a==0 for a in state['remaining'].values()) and state['version']==5
    assert len(state['recoveries'])==len(state['recovery_events'])==int(overage)
    if overage:
        assert state['recoveries'][0][5]==cash-total and state['recoveries'][0][4]==ids[0]
        assert state['recovery_events'][0][1]==cash-total
    assert bank['debit']==cash and bank['resolved_counterparty_account'] is None and due==date(2026,3,15)
    assert len(state['receipts'])==1 and len(state['outbox'])==1
    repo.append_manual_classification.assert_called_once();repo.save_correction_receipt.assert_called_once();unit.commit.assert_called_once()
