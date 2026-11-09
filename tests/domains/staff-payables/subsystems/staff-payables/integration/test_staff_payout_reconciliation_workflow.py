from __future__ import annotations

import pytest

from domains.staff_payables.reconciliation import (
    OutgoingBankFact,
    StaffPayableFacts,
    StaffPayableStatus,
    StaffPayoutEventType,
    StaffPrimaryBankAccount,
)
from shared_kernel.errors import ErrorCategory
from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
from shared_kernel.money import MoneyNTD
from subsystems.staff_payables.payout_reconciliation import (
    StaffPayoutApplyRequest,
    StaffPayoutReconciliationError,
    StaffPayoutReconciliationFacts,
    StaffPayoutReconciliationWorkflow,
    StaffPayoutSelection,
    StoredStaffPayoutReceipt,
)


class _UnitOfWork:
    def __init__(self):
        self.committed = False

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def commit(self):
        self.committed = True


class _Repository:
    def __init__(self, facts):
        self.facts = facts
        self.receipt = None
        self.calls = []

    def load(self, selection, *, for_update):
        assert selection.obligation_identities == ("obligation:1",)
        self.calls.append(("load", for_update))
        return self.facts

    def find_receipt(self, _key):
        self.calls.append(("find",))
        return self.receipt

    def append_events(self, candidate):
        self.calls.append(("events", len(candidate.events)))

    def append_obligation_links(self, candidate):
        self.calls.append(("links", len(candidate.obligation_links)))

    def update_payable_projection(self, _selection, version, status):
        self.calls.append(("projection", version, status))

    def append_outbox(self, _candidate):
        self.calls.append(("outbox",))

    def save_receipt(self, _key, receipt):
        self.calls.append(("receipt",))
        self.receipt = receipt


def _facts(version=4):
    return StaffPayoutReconciliationFacts(
        version,
        8,
        (OutgoingBankFact("bank:1", 7, MoneyNTD(500), "account:7"),),
        (StaffPrimaryBankAccount("account:7", 7),),
        (StaffPayableFacts("obligation:1", 7, MoneyNTD(500)),),
    )


def _selection():
    return StaffPayoutSelection(StaffPayoutEventType.PAYOUT, ("bank:1",), ("obligation:1",))


def _request(preview, *, version=4, key="payout-1"):
    return StaffPayoutApplyRequest(
        _selection(), ExpectedVersion(version), ExpectedVersion(8), preview.fingerprint,
        IdempotencyKey(key), ActorContext("admin"), "Record exact staff payout.",
        CorrelationId("staff-payout-test"),
    )


@pytest.mark.parametrize('total,portion,cash,fee,status', [
    (18000, 18000, 17935, 65, StaffPayableStatus.COMPLETED),
    (30000, 18000, 17935, 65, StaffPayableStatus.PARTIALLY_PAID),
    (30000, 12000, 11970, 30, StaffPayableStatus.PARTIALLY_PAID),
    (30000, 18000, 18000, 0, StaffPayableStatus.PARTIALLY_PAID),
])
def test_fee_settles_only_selected_funding_portion_and_preserves_other_portion(total, portion, cash, fee, status):
    from dataclasses import replace
    facts = replace(_facts(), bank_facts=(OutgoingBankFact('bank:1', 7, MoneyNTD(cash), 'account:7'),),
        obligations=(StaffPayableFacts('obligation:1', 7, MoneyNTD(total), installment_limit=MoneyNTD(portion)),))
    repository = _Repository(facts)
    workflow = StaffPayoutReconciliationWorkflow(repository, _UnitOfWork)
    preview = workflow.preview(_selection(), CorrelationId('funding-fee'))
    assert preview.candidate.bank_total.amount == cash
    assert preview.candidate.obligation_total.amount == portion
    assert preview.candidate.transfer_fee.amount == fee
    assert sum(link.allocated_amount.amount for link in preview.candidate.obligation_links) == portion
    assert preview.candidate.resulting_status is status
    receipt = workflow.apply(_request(preview))
    assert receipt.resulting_status is status
    before = list(repository.calls)
    assert workflow.apply(_request(preview)) == receipt
    assert repository.calls == [*before, ('find',)]


def test_preview_apply_persists_ledger_projection_outbox_and_receipt():
    repository = _Repository(_facts())
    unit_of_work = _UnitOfWork()
    workflow = StaffPayoutReconciliationWorkflow(repository, lambda: unit_of_work)

    preview = workflow.preview(_selection(), CorrelationId("preview"))
    receipt = workflow.apply(_request(preview))

    assert receipt.staff_payables_version == 5
    assert receipt.bank_facts_version == 8
    assert receipt.resulting_status is StaffPayableStatus.COMPLETED
    assert repository.calls == [
        ("load", False), ("find",), ("load", True), ("events", 1),
        ("links", 1), ("projection", 5, StaffPayableStatus.COMPLETED),
        ("outbox",), ("receipt",),
    ]
    assert unit_of_work.committed is True


def test_apply_replays_matching_command_without_new_write():
    repository = _Repository(_facts())
    workflow = StaffPayoutReconciliationWorkflow(repository, _UnitOfWork)
    preview = workflow.preview(_selection(), CorrelationId("preview"))
    request = _request(preview)
    first = workflow.apply(request)
    repository.calls.clear()

    assert workflow.apply(request) == first
    assert repository.calls == [("find",)]


@pytest.mark.parametrize('amounts,cash,chosen,blocked,fee', [
    ((6000,7000),5000,(0,),True,0),
    ((12000,),12000,(0,),False,0),
    ((12000,12000),12000,(1,),False,0),
    ((7000,5000),11970,(0,1),False,30),
])
def test_sinopac_synthetic_owner_preview_apply_and_replay_match_the_selected_payment(amounts,cash,chosen,blocked,fee):
    all_obligations=tuple(StaffPayableFacts(f'obligation:{i}',7,MoneyNTD(amount)) for i,amount in enumerate(amounts))
    facts=StaffPayoutReconciliationFacts(4,8,(OutgoingBankFact('bank:1',7,MoneyNTD(cash),'account:7'),),
        (StaffPrimaryBankAccount('account:7',7),),tuple(all_obligations[i] for i in chosen))
    selection=StaffPayoutSelection(StaffPayoutEventType.PAYOUT,('bank:1',),tuple(sorted(item.obligation_identity for item in facts.obligations)))
    class Repository:
        def __init__(self): self.receipts={};self.events=[];self.links=[];self.version=4;self.commits=0
        def load(self,selection,*,for_update): return facts
        def find_receipt(self,key): return self.receipts.get(key.value)
        def append_events(self,candidate): self.events.extend(candidate.events)
        def append_obligation_links(self,candidate): self.links.extend(candidate.obligation_links)
        def update_payable_projection(self,selection,version,status): self.version=version
        def append_outbox(self,candidate): pass
        def save_receipt(self,key,stored): self.receipts[key.value]=stored
    repo=Repository()
    class Unit:
        def __enter__(self): return self
        def __exit__(self,*args): return False
        def commit(self): repo.commits+=1
    workflow=StaffPayoutReconciliationWorkflow(repo,Unit)
    correlation=CorrelationId('synthetic-sinopac')
    if blocked:
        from shared_kernel.fingerprints import PreviewFingerprint
        with pytest.raises(StaffPayoutReconciliationError) as preview:workflow.preview(selection,correlation)
        request=StaffPayoutApplyRequest(selection,ExpectedVersion(4),ExpectedVersion(8),PreviewFingerprint('a'*64),
            IdempotencyKey('blocked-sinopac'),ActorContext('synthetic'),'合成不足額',correlation)
        with pytest.raises(StaffPayoutReconciliationError) as applied:workflow.apply(request)
        assert preview.value.error.code==applied.value.error.code=='staff_payout_amount_mismatch'
        assert repo.events==repo.links==[] and repo.commits==0
        return
    preview=workflow.preview(selection,correlation)
    assert repo.events==repo.links==[]
    assert preview.candidate.transfer_fee.amount==fee
    assert preview.candidate.bank_total.amount==cash
    request=StaffPayoutApplyRequest(selection,ExpectedVersion(4),ExpectedVersion(8),preview.fingerprint,
        IdempotencyKey('synthetic-sinopac'),ActorContext('synthetic'),'合成月嫂核銷',correlation)
    receipt=workflow.apply(request)
    assert repo.events==list(preview.candidate.events)
    assert repo.links==list(preview.candidate.obligation_links)
    assert len(repo.events)==1 and repo.events[0].amount.amount==cash
    assert sum(item.allocated_amount.amount for item in repo.links)==sum(amounts[i] for i in chosen)
    assert receipt.resulting_status is StaffPayableStatus.COMPLETED
    assert workflow.apply(request)==receipt
    assert len(repo.events)==1 and repo.commits==1 and repo.version==5
    assert {item.obligation_identity for item in repo.links}==set(selection.obligation_identities)


@pytest.mark.parametrize('amounts,cash,chosen,memo,duplicate_name,error,fee', [
    ((12000,),12000,(0,),'合成月嫂甲',False,None,0),
    ((12000,),11970,(0,),'合成月嫂甲',False,None,30),
    ((12000,),11900,(0,),'合成月嫂甲',False,None,100),
    ((7000,5000),12000,(0,1),'合成月嫂甲 HC115003',False,None,0),
    ((7000,5000),11900,(0,1),'合成月嫂甲 HC115003',False,None,100),
    ((12000,12000),12000,(1,),'合成月嫂甲',False,None,0),
    ((6000,7000),5000,(0,),'合成月嫂甲',False,'staff_payout_amount_mismatch',0),
    ((12000,),12000,(0,),'HC115003',False,'staff_memo_recipient_unconfirmed',0),
    ((12000,),12000,(0,),'合成月嫂甲',True,'staff_memo_recipient_unconfirmed',0),
    ((12000,),12000,(0,),'合成月嫂乙',False,'cross_staff_allocation_forbidden',0),
])
def test_taishin_raw_memo_owner_preview_apply_and_replay_without_accounts(monkeypatch,amounts,cash,chosen,memo,duplicate_name,error,fee):
    """CF/Staff payout acceptance: real owner reader/rules/workflow, synthetic persistence only."""
    from copy import deepcopy
    from datetime import date
    import infrastructure.mysql.staff_payout_repository as storage
    from domains.staff_payables.reconciliation import StaffPayoutEvent,project_staff_payable
    from shared_kernel.fingerprints import PreviewFingerprint
    bank={'id':88,'format_id':'taishin','memo':memo,'transaction_date':date(2026,10,20),'currency':'TWD',
          'direction':'outgoing','debit':cash,'credit':None,'classification_type':'staff_payout',
          'reconciliation_status':'pending','payout_event_id':None,'dedup_fingerprint':'c'*64,
          'resolved_counterparty_account':None,'bank_references':{}}
    before=deepcopy(bank)
    rows=tuple(dict(obligation_identity=f'obligation:{i}',staff_id=7,amount_due_ntd=a) for i,a in enumerate(amounts))
    selected=tuple(rows[i] for i in chosen)
    class Cursor:
        def execute(self,sql,params=()):
            assert sql.startswith('SELECT id,name FROM staff WHERE')
        def fetchall(self):
            return [{'id':7,'name':'合成月嫂甲'},{'id':8,'name':'合成月嫂甲' if duplicate_name else '合成月嫂乙'}]
    class Repository(storage.MySqlStaffPayoutRepository):
        def __init__(self):
            super().__init__(object());self.receipts={};self.events=[];self.links=[];self.version=4;self.commits=0;self.outbox=[]
        def load(self,selection,*,for_update):
            return self._assemble_facts(Cursor(),selection,7,self.version,(bank,),selected,for_update)
        def find_receipt(self,key):return self.receipts.get(key.value)
        def append_events(self,candidate):self.events.extend(candidate.events)
        def append_obligation_links(self,candidate):self.links.extend(candidate.obligation_links)
        def update_payable_projection(self,selection,version,status):
            self.version=version;bank['reconciliation_status']='completed';bank['payout_event_id']=1
        def append_outbox(self,candidate):self.outbox.append(candidate)
        def save_receipt(self,key,stored):self.receipts[key.value]=stored
    repo=Repository()
    def current_events(*args):
        return {link.obligation_identity:(StaffPayoutEvent('event:1',StaffPayoutEventType.PAYOUT,link.allocated_amount),) for link in repo.links}
    monkeypatch.setattr(storage,'_load_obligation_events',current_events)
    monkeypatch.setattr(storage,'_load_blocking_anomalies',lambda *args:{})
    class Unit:
        def __enter__(self):return self
        def __exit__(self,*args):return False
        def commit(self):repo.commits+=1
    workflow=StaffPayoutReconciliationWorkflow(repo,Unit)
    selection=StaffPayoutSelection(StaffPayoutEventType.PAYOUT,('88',),tuple(sorted(row['obligation_identity'] for row in selected)))
    correlation=CorrelationId('synthetic-taishin')
    if error:
        with pytest.raises(StaffPayoutReconciliationError) as preview:workflow.preview(selection,correlation)
        try:
            current_bank_version=repo.load(selection,for_update=False).bank_facts_version
        except ValueError:
            current_bank_version=0
        request=StaffPayoutApplyRequest(selection,ExpectedVersion(4),ExpectedVersion(current_bank_version),PreviewFingerprint('a'*64),
            IdempotencyKey('blocked'),ActorContext('synthetic'),'既存流水重新核對備註',correlation)
        with pytest.raises(StaffPayoutReconciliationError) as applied:workflow.apply(request)
        assert preview.value.error.code==applied.value.error.code==error
        assert repo.events==repo.links==repo.outbox==[] and repo.commits==0 and bank==before
        return
    preview=workflow.preview(selection,correlation)
    assert repo.events==repo.links==[] and bank==before
    assert preview.candidate.transfer_fee.amount==fee and preview.candidate.bank_total.amount==cash
    request=StaffPayoutApplyRequest(selection,ExpectedVersion(preview.staff_payables_version),ExpectedVersion(preview.bank_facts_version),preview.fingerprint,
        IdempotencyKey('same-taishin-command'),ActorContext('synthetic'),'合成台新付款',correlation)
    first=workflow.apply(request)
    second=workflow.apply(request)
    assert first==second and first.resulting_status is StaffPayableStatus.COMPLETED
    assert repo.events==list(preview.candidate.events) and repo.links==list(preview.candidate.obligation_links)
    assert len(repo.events)==1 and repo.events[0].amount.amount==cash
    assert sum(link.allocated_amount.amount for link in repo.links)==sum(amounts[i] for i in chosen)
    projections=storage._obligation_facts(selected,current_events())
    assert all(project_staff_payable(item).balance.amount==0 for item in projections)
    assert repo.commits==1 and len(repo.receipts)==1 and len(repo.outbox)==1 and repo.version==5
    assert bank['debit']==before['debit'] and bank['resolved_counterparty_account'] is None


@pytest.mark.parametrize('missing_date,currency,code', [(True,'TWD','bank_transaction_date_missing'),(False,'USD','bank_currency_not_twd')])
@pytest.mark.parametrize('bank_format', ['sinopac', 'taishin'])
def test_owner_checks_source_date_and_currency_before_any_payment(monkeypatch,missing_date,currency,code,bank_format):
    from datetime import date
    from shared_kernel.fingerprints import PreviewFingerprint
    from infrastructure.mysql.staff_payout_repository import MySqlStaffPayoutRepository
    bank={'id':88,'format_id':bank_format,'transaction_date':None if missing_date else date(2026,10,20),'currency':currency}
    reader=MySqlStaffPayoutRepository(object())
    repo=_Repository(_facts())
    repo.load=lambda selection,*,for_update:reader._assemble_facts(object(),selection,7,4,(bank,),(),for_update)
    unit=_UnitOfWork()
    workflow=StaffPayoutReconciliationWorkflow(repo,lambda:unit)
    selection=StaffPayoutSelection(StaffPayoutEventType.PAYOUT,('88',),('obligation:0',))
    with pytest.raises(StaffPayoutReconciliationError) as preview:workflow.preview(selection,CorrelationId('preview'))
    request=StaffPayoutApplyRequest(selection,ExpectedVersion(4),ExpectedVersion(0),PreviewFingerprint('a'*64),IdempotencyKey('blocked-date'),ActorContext('synthetic'),'合成來源檢查',CorrelationId('apply'))
    with pytest.raises(StaffPayoutReconciliationError) as applied:workflow.apply(request)
    assert preview.value.error.code==applied.value.error.code==code
    assert repo.calls==[('find',)] and not unit.committed


@pytest.mark.parametrize('operation', ['preview', 'apply'])
def test_unconfirmed_memo_identity_is_a_typed_blocker_before_any_payment_write(operation):
    repository = _Repository(_facts())
    unit = _UnitOfWork()
    workflow = StaffPayoutReconciliationWorkflow(repository, lambda: unit)
    preview = workflow.preview(_selection(), CorrelationId('preview'))
    repository.calls.clear()

    def unconfirmed(_selection, *, for_update):
        raise ValueError('staff_memo_recipient_unconfirmed')

    repository.load = unconfirmed
    with pytest.raises(StaffPayoutReconciliationError) as raised:
        if operation == 'preview':
            workflow.preview(_selection(), CorrelationId('unconfirmed'))
        else:
            workflow.apply(_request(preview))
    assert raised.value.error.category is ErrorCategory.DOMAIN_BLOCKED
    assert raised.value.error.code == 'staff_memo_recipient_unconfirmed'
    assert not unit.committed
    assert repository.calls == ([] if operation == 'preview' else [('find',)])


def test_apply_rejects_stale_version_before_persistence():
    stale_preview = StaffPayoutReconciliationWorkflow(_Repository(_facts(4)), _UnitOfWork).preview(_selection(), CorrelationId("preview"))
    repository = _Repository(_facts(5))
    workflow = StaffPayoutReconciliationWorkflow(repository, _UnitOfWork)

    with pytest.raises(StaffPayoutReconciliationError) as raised:
        workflow.apply(_request(stale_preview, version=4))

    assert raised.value.error.category is ErrorCategory.CONFLICT
    assert raised.value.error.code == "staff_payable_candidate_stale"
    assert repository.calls == [("find",), ("load", True)]


def test_apply_rejects_another_command_for_existing_idempotency_key():
    repository = _Repository(_facts())
    workflow = StaffPayoutReconciliationWorkflow(repository, _UnitOfWork)
    preview = workflow.preview(_selection(), CorrelationId("preview"))
    request = _request(preview)
    receipt = workflow.apply(request)
    repository.receipt = StoredStaffPayoutReceipt(
        workflow._find_replay.__self__._repository.receipt.command_fingerprint, receipt
    )
    different = StaffPayoutApplyRequest(
        request.selection, request.expected_staff_payables_version,
        request.expected_bank_facts_version, request.preview_fingerprint,
        request.idempotency_key, request.actor, "Different reason.", request.correlation_id,
    )

    with pytest.raises(StaffPayoutReconciliationError) as raised:
        workflow.apply(different)

    assert raised.value.error.category is ErrorCategory.IDEMPOTENCY_MISMATCH
