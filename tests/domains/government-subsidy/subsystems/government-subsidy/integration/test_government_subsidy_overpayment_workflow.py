from domains.government_subsidy.overpayment import GovernmentSubsidyOffsetIntent, GovernmentSubsidyOffsetTarget, GovernmentSubsidyOverpayment, GovernmentSubsidyOverpaymentStatus
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
from shared_kernel.money import MoneyNTD
from subsystems.government_subsidy.overpayment_workflow import GovernmentSubsidyOverpaymentWorkflow, OffsetApplyRequest

class Uow:
 def __enter__(self): return self
 def __exit__(self,*_): return False
 def commit(self): pass
class Repo:
 def __init__(self): self.root=GovernmentSubsidyOverpayment('o','hccg',MoneyNTD(200),'pending_review',1); self.persisted=False
 def load_overpayment(self,*_,**__): return self.root
 def load_offset_targets(self,*_,**__): return (GovernmentSubsidyOffsetTarget(7,1,1,MoneyNTD(200),MoneyNTD(0),'hccg',MoneyNTD(200),True,True),)
 def persist_offset(self,*_): self.persisted=True; return {'ok':True}








def test_apply_reloads_root_and_refuses_stale_preview_before_write():
 repo=Repo(); workflow=GovernmentSubsidyOverpaymentWorkflow(repo,Uow)
 request=OffsetApplyRequest('o',(GovernmentSubsidyOffsetIntent(7,MoneyNTD(100)),),ExpectedVersion(1),PreviewFingerprint('0'*64),IdempotencyKey('key'),ActorContext('admin'), 'reason','evidence',CorrelationId('c'))
 try: workflow.apply_offset(request)
 except ValueError as error: assert str(error)=='government_subsidy_overpayment_preview_stale'
 else: raise AssertionError('stale preview must fail')
 assert repo.persisted is False
