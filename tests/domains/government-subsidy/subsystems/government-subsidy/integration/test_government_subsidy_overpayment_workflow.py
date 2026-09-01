from domains.government_subsidy.overpayment import GovernmentRecipientSnapshot, GovernmentSubsidyOffsetIntent, GovernmentSubsidyOffsetTarget, GovernmentSubsidyOverpayment, GovernmentSubsidyOverpaymentStatus
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
from shared_kernel.money import MoneyNTD
from subsystems.government_subsidy.overpayment_workflow import GovernmentSubsidyOverpaymentWorkflow, OffsetApplyRequest, ReturnApplyRequest, ReturnReconciliationApplyRequest, ReturnReconciliationWithExcessApplyRequest

class Uow:
 def __enter__(self): return self
 def __exit__(self,*_): return False
 def commit(self): pass
class Repo:
 def __init__(self): self.root=GovernmentSubsidyOverpayment('o','hccg',MoneyNTD(200),'pending_review',1); self.persisted=False
 def load_overpayment(self,*_,**__): return self.root
 def load_offset_targets(self,*_,**__): return (GovernmentSubsidyOffsetTarget(7,1,1,MoneyNTD(200),MoneyNTD(0),'hccg',MoneyNTD(200),True,True),)
 def persist_offset(self,*_): self.persisted=True; return {'ok':True}


class ReturnRepo:
 def __init__(self): self.root=GovernmentSubsidyOverpayment('o','hccg',MoneyNTD(200),GovernmentSubsidyOverpaymentStatus.PENDING_REVIEW,1); self.lock_values=[]; self.persisted=None
 def load_overpayment(self,*_,**__): return self.root
 def load_return_recipient(self, due_date, evidence_reference, *, lock):
  self.lock_values.append(lock)
  return GovernmentRecipientSnapshot('hccg','新竹市政府','004','****1234','f'*64,'2026-08-01',due_date,evidence_reference)
 def persist_return(self, request, candidate, recipient): self.persisted=(request,candidate,recipient); return {'ok':True}


class ReconciliationRepo:
 def __init__(self): self.persisted=False
 def load_overpayment(self, *_args, **_kwargs):
  return GovernmentSubsidyOverpayment('o','hccg',MoneyNTD(200),GovernmentSubsidyOverpaymentStatus.RETURN_PAYABLE,2)
 def load_return_reconciliation_context(self, *_args, **_kwargs):
  from domains.government_subsidy.ledger import GovernmentBankFact, GovernmentSubsidyBankDirection
  return (GovernmentSubsidyOverpayment('o','hccg',MoneyNTD(200),GovernmentSubsidyOverpaymentStatus.RETURN_PAYABLE,2), ('return:o', MoneyNTD(200), 1), GovernmentBankFact(7,'bank-7',GovernmentSubsidyBankDirection.OUTGOING,'government_subsidy',MoneyNTD(200),__import__('datetime').date(2026,7,1)))
 def persist_return_reconciliation(self, *_): self.persisted=True; return {'reconciled':True}


class ExcessReconciliationRepo:
 def __init__(self): self.persisted=False; self.lock_values=[]
 def load_overpayment(self, *_args, **_kwargs):
  self.lock_values.append(_kwargs.get('lock'))
  return GovernmentSubsidyOverpayment('o','hccg',MoneyNTD(200),GovernmentSubsidyOverpaymentStatus.RETURN_PAYABLE,2)
 def load_return_reconciliation_context(self, *_args, **_kwargs):
  self.lock_values.append(_kwargs.get('lock'))
  from domains.government_subsidy.ledger import GovernmentBankFact, GovernmentSubsidyBankDirection
  return (GovernmentSubsidyOverpayment('o','hccg',MoneyNTD(200),GovernmentSubsidyOverpaymentStatus.RETURN_PAYABLE,2), ('return:o', MoneyNTD(200), 1), GovernmentBankFact(8,'bank-8',GovernmentSubsidyBankDirection.OUTGOING,'government_subsidy',MoneyNTD(250),__import__('datetime').date(2026,7,1)))
 def persist_return_reconciliation_with_excess(self, request, candidate): self.persisted=(request,candidate); return {'recovery_identity':candidate.recovery_identity,'excess_amount_ntd':candidate.excess_amount_ntd.amount}


def test_apply_reloads_root_and_refuses_stale_preview_before_write():
 repo=Repo(); workflow=GovernmentSubsidyOverpaymentWorkflow(repo,Uow)
 request=OffsetApplyRequest('o',(GovernmentSubsidyOffsetIntent(7,MoneyNTD(100)),),ExpectedVersion(1),PreviewFingerprint('0'*64),IdempotencyKey('key'),ActorContext('admin'), 'reason','evidence',CorrelationId('c'))
 try: workflow.apply_offset(request)
 except ValueError as error: assert str(error)=='government_subsidy_overpayment_preview_stale'
 else: raise AssertionError('stale preview must fail')
 assert repo.persisted is False


def test_return_apply_reloads_government_account_snapshot_under_lock():
 repo=ReturnRepo(); workflow=GovernmentSubsidyOverpaymentWorkflow(repo,Uow)
 preview=workflow.preview_return('o','2026-09-05','notice-1')
 request=ReturnApplyRequest('o','2026-09-05','notice-1',ExpectedVersion(1),preview.fingerprint,IdempotencyKey('return-key'),ActorContext('admin'),'reason',CorrelationId('c'))
 assert workflow.apply_return(request)=={'ok':True}
 assert repo.lock_values==[False,True]
 assert repo.persisted[2].account_display=='****1234'


def test_return_reconciliation_accepts_an_earlier_bank_statement_date():
 repo=ReconciliationRepo(); workflow=GovernmentSubsidyOverpaymentWorkflow(repo,Uow)
 preview=workflow.preview_return_reconciliation('o',7)
 request=ReturnReconciliationApplyRequest('o',7,ExpectedVersion(2),preview.fingerprint,IdempotencyKey('reconcile-key'),ActorContext('admin'),'reason','evidence',CorrelationId('c'))
 assert workflow.apply_return_reconciliation(request)=={'reconciled':True}
 assert repo.persisted is True


def test_excess_return_reconciliation_uses_dedicated_owner_operation():
 repo=ExcessReconciliationRepo(); workflow=GovernmentSubsidyOverpaymentWorkflow(repo,Uow)
 preview=workflow.preview_return_reconciliation_with_excess('o',8)
 request=ReturnReconciliationWithExcessApplyRequest('o',8,ExpectedVersion(2),preview.fingerprint,IdempotencyKey('excess-reconcile-key'),ActorContext('admin'),'over-return','statement',CorrelationId('c'))
 assert workflow.apply_return_reconciliation_with_excess(request)=={'recovery_identity':'government-overpayment-return-excess:bank-8','excess_amount_ntd':50}
 assert repo.persisted[1].lawful_amount_ntd == MoneyNTD(200)
 assert repo.lock_values == [False, True, True]
