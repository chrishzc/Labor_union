"""Exact-case acknowledgement keeps owner facts intact and rejects changed replay."""
from datetime import datetime, timezone
from types import SimpleNamespace
import pytest
from shared_kernel.identities import ActorContext, IdempotencyKey
from subsystems.line.capabilities import LineCapability
from subsystems.line.identity_management_application import LineIdentityManagementApplication

class Unit:
    def __init__(self):
        self.saved={};self.snapshots=[];self.audits=[];self.commits=0;self.scope=None
        self.identity_management=SimpleNamespace(lock_customer_reminder_subject=self.lock)
        self.receipts=SimpleNamespace(get=lambda key,**kw:self.saved.get(key.value),append=self.append)
        self.audit=SimpleNamespace(append=self.audits.append)
    def lock(self,identity,case):
        self.scope=(identity,case)
        return self.scope==(7,'SYNTH-CASE')
    def append(self,receipt,**kw):
        self.saved[receipt.key.value]=receipt;self.snapshots.append(kw['result_snapshot'])
    def __enter__(self):return self
    def __exit__(self,*args):return False
    def commit(self):self.commits+=1

def setup():
    unit=Unit()
    app=LineIdentityManagementApplication(lambda:unit,lambda:datetime(2026,11,17,tzinfo=timezone.utc))
    actor=ActorContext('synthetic-admin',(LineCapability.IDENTITY_BINDING_MANAGE.value,))
    return app,unit,actor

def test_exact_scope_reason_audit_and_same_key_replay():
    app,unit,actor=setup();key=IdempotencyKey('dismiss-synthetic')
    assert app.dismiss_customer_binding_reminder(7,'SYNTH-CASE','已核對誤報',key,actor) is False
    assert app.dismiss_customer_binding_reminder(7,'SYNTH-CASE','已核對誤報',key,actor) is True
    assert unit.commits==1 and len(unit.audits)==1
    assert next(iter(unit.saved.values())).result_reference=='binding-reminder-dismissed:customer:7:SYNTH-CASE'
    assert unit.snapshots[0]['reason']=='已核對誤報'
    assert unit.snapshots[0]['actor_id']=='synthetic-admin'
    with pytest.raises(RuntimeError,match='idempotency_conflict'):
        app.dismiss_customer_binding_reminder(7,'SYNTH-CASE','換原因',key,actor)
    assert unit.commits==1

def test_wrong_case_has_no_receipt_or_commit():
    app,unit,actor=setup()
    with pytest.raises(LookupError):app.dismiss_customer_binding_reminder(7,'OTHER','誤報',IdempotencyKey('wrong'),actor)
    assert not unit.saved and unit.commits==0

def test_empty_reason_and_readonly_actor_cannot_dismiss():
    app,unit,actor=setup()
    with pytest.raises(ValueError):app.dismiss_customer_binding_reminder(7,'SYNTH-CASE','  ',IdempotencyKey('empty'),actor)
    with pytest.raises(PermissionError):app.dismiss_customer_binding_reminder(7,'SYNTH-CASE','誤報',IdempotencyKey('denied'),ActorContext('viewer'))
    assert not unit.saved and unit.commits==0
