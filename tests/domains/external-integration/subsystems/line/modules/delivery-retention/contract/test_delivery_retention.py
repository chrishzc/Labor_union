"""Six-calendar-month boundaries and atomic retention of confirmed deliveries."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from domains.line.delivery import LineDeliveryStatus
from domains.line.identities import LineDeliveryTaskId
from subsystems.line.delivery_retention import (
    LineDeliveryRetentionApplication, LineDeliveryRetentionFacts, delivery_retention_cutoff,
)

UTC = timezone.utc
NOW = datetime(2026, 11, 18, 1, 2, 3, 456789, tzinfo=UTC)
CUTOFF = datetime(2026, 5, 18, 1, 2, 3, 456789, tzinfo=UTC)


def facts(**changes):
    original = LineDeliveryRetentionFacts(LineDeliveryTaskId(7), LineDeliveryStatus.SENT,
        CUTOFF-timedelta(days=1), False, None, 1, (CUTOFF-timedelta(days=1),),
        None, ('provider_accepted',), False)
    return replace(original, **changes)


@pytest.mark.parametrize(('now','expected'), [
    (NOW,CUTOFF),
    (datetime(2026,8,31,16,tzinfo=UTC),datetime(2026,2,28,16,tzinfo=UTC)),
    (datetime(2026,8,30,16,tzinfo=UTC),datetime(2026,2,27,16,tzinfo=UTC)),
    (datetime(2024,8,31,7,tzinfo=UTC),datetime(2024,2,29,7,tzinfo=UTC)),
    (datetime(2026,1,31,7,tzinfo=UTC),datetime(2025,7,31,7,tzinfo=UTC)),
])
def test_six_month_cutoff_uses_taipei_calendar_and_clamps_month_end(now,expected):
    assert delivery_retention_cutoff(now) == expected


def test_naive_clock_is_rejected():
    with pytest.raises(ValueError,match='timezone-aware'):
        delivery_retention_cutoff(NOW.replace(tzinfo=None))


@pytest.mark.parametrize('changes', [
    {'updated_at':CUTOFF},
    {'updated_at':CUTOFF+timedelta(seconds=1)},
    {'status':LineDeliveryStatus.PENDING},
    {'status':LineDeliveryStatus.PROCESSING},
    {'status':LineDeliveryStatus.RETRYABLE_FAILED},
    {'status':LineDeliveryStatus.FAILED},
    {'has_lease':True},
    {'error_code':'line_reply_outcome_uncertain'},
    {'latest_attempt_error_code':'line_reply_outcome_uncertain'},
    {'completed_attempts':2},
    {'attempt_completed_at':(CUTOFF,)},
    {'intent_statuses':('scheduled',)},
    {'intent_statuses':('cancelled',)},
    {'expired':True},
])
def test_unfinished_recent_uncertain_or_incomplete_readback_is_preserved(changes):
    assert not facts(**changes).eligible(CUTOFF)


def test_confirmed_sent_and_cancelled_without_intents_can_expire():
    assert facts().eligible(CUTOFF)
    assert facts(status=LineDeliveryStatus.CANCELLED,intent_statuses=('cancelled',)).eligible(CUTOFF)
    assert facts(completed_attempts=0,attempt_completed_at=(),intent_statuses=()).eligible(CUTOFF)


class Unit:
    def __init__(self, task_facts):
        self.facts = task_facts
        self.events=[]
        self.saved={}
        self.snapshots=[]
        self.commits=0
        self.delivery_tasks=SimpleNamespace(retention_candidates=self.candidates,
            retention_facts=lambda _:self.facts,expire_retention_details=self.expire)
        self.receipts=SimpleNamespace(get=lambda key,**_:self.saved.get(key.value),append=self.append)
        self.audit=SimpleNamespace(append=lambda intent:self.events.append(('audit',intent)))

    def candidates(self,cutoff,limit):
        assert cutoff==CUTOFF and limit==25
        return (self.facts.task_id,)

    def append(self,receipt,*,result_snapshot):
        self.events.append(('receipt',receipt))
        self.saved[receipt.key.value]=receipt
        self.snapshots.append(result_snapshot)

    def expire(self,current,key):
        assert key.value in self.saved
        self.events.append(('expire',current.task_id.value))
        self.facts=replace(current,expired=True)

    def __enter__(self):return self
    def __exit__(self,*_):return False
    def commit(self):self.commits+=1


def test_receipt_precedes_mutation_and_rerun_is_noop_without_provider():
    unit=Unit(facts())
    app=LineDeliveryRetentionApplication(lambda:unit,lambda:NOW,'synthetic-worker')
    assert app.run_once()==1
    assert [event[0] for event in unit.events]==['receipt','expire','audit']
    assert unit.commits==1
    snapshot=unit.snapshots[0]
    assert snapshot=={'task_id':7,'cutoff':'2026-05-18 01:02:03.456789','expired_at':NOW.isoformat()}
    assert next(iter(unit.saved.values())).result_reference=='line-delivery-retention:7'
    assert app.run_once()==0
    assert unit.commits==1


def test_fresh_read_conflict_skips_without_receipt_or_commit():
    unit=Unit(facts(status=LineDeliveryStatus.PROCESSING))
    assert LineDeliveryRetentionApplication(lambda:unit,lambda:NOW,'synthetic').run_once()==0
    assert not unit.events and not unit.saved and unit.commits==0


def test_existing_receipt_with_uncleared_details_is_not_silently_overwritten():
    unit=Unit(facts());unit.saved['line-delivery-retention:7']=object()
    with pytest.raises(RuntimeError,match='receipt_conflict'):
        LineDeliveryRetentionApplication(lambda:unit,lambda:NOW,'synthetic').run_once()
    assert not unit.events and unit.commits==0


@pytest.mark.parametrize('limit',[0,26])
def test_batch_bounds(limit):
    with pytest.raises(ValueError):
        LineDeliveryRetentionApplication(lambda:None,lambda:NOW,'synthetic',batch_size=limit)


def test_canonical_worker_registers_retention_with_original_uow_and_no_provider_calls(monkeypatch):
    from api.dependencies import line_worker_operation
    unit=Unit(facts())
    monkeypatch.setattr(line_worker_operation,'open_line_unit_of_work',lambda:unit)
    monkeypatch.setattr(line_worker_operation,'_required_access_token',lambda:'synthetic-unused-token')
    workers=line_worker_operation._additional_workers('synthetic-retention',lambda:NOW,
        SimpleNamespace(materialize=lambda _:b''),object())
    assert isinstance(workers['delivery_retention'],LineDeliveryRetentionApplication)
    assert workers['delivery_retention'].run_once()==1
    assert unit.commits==1
