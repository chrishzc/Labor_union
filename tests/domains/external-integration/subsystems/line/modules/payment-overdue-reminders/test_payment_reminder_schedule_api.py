"""Schedule HTTP contract: authenticated, versioned, and closed to extra controls."""
from dataclasses import asdict
import json
from types import SimpleNamespace
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.dependencies.admin_auth import require_admin
from api.routes import line_payment_reminder_settings as route
from api.routes.line_payment_overdue_reminders import router as overdue_router
from domains.line.configuration import LineConfigurationKind,LineConfigurationSnapshot,LineConfigurationRevisionConflict
from domains.line.canonical_payload import canonical_line_payload_json
from domains.line.identities import LineConfigurationRevision
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.line.payment_reminder_schedule import PaymentReminderSchedule


@pytest.fixture
def http(monkeypatch):
    definition={'timezone':'Asia/Taipei','schedules':[],'unrelated_setting':{'preserved':True}}
    state=SimpleNamespace(revision=2,definition=definition,writes=0,receipts={})
    def get(kind,actor):
        assert kind is LineConfigurationKind.MESSAGE_SCHEDULES
        return LineConfigurationSnapshot(kind,LineConfigurationRevision(state.revision),canonical_line_payload_json(state.definition))
    def apply(**command):
        if command['expected_revision'].value!=state.revision:
            raise LineConfigurationRevisionConflict('stale')
        state.definition=command['definition'];state.revision+=1;state.writes+=1
        snapshot=get(command['kind'],command['actor'])
        state.receipts[command['idempotency_key'].value]=snapshot
        return SimpleNamespace(snapshot=snapshot)
    monkeypatch.setattr(route,'get_line_configuration_application',lambda:SimpleNamespace(get=get,apply=apply,get_applied=lambda kind,key,actor:state.receipts.get(key.value)))
    principal=AdminPrincipal(1,'synthetic','測試人員','system_admin')
    app=FastAPI();app.include_router(overdue_router)
    app.dependency_overrides[require_admin]=lambda:principal
    with TestClient(app) as client:
        yield client,state,app


def body(**changes):
    return {'expected_revision':2,'schedule':{**asdict(PaymentReminderSchedule()),**changes},'idempotency_key':'synthetic-operation'}


def test_get_is_readonly_and_save_preserves_unrelated_configuration(http):
    client,state,_=http
    view=client.get('/api/v1/line/payment-overdue-reminders/schedule')
    assert view.status_code==200 and view.json()['data']['followup_after_hours']==24
    assert state.writes==0
    result=client.put('/api/v1/line/payment-overdue-reminders/schedule',json=body(first_time='11:30'))
    assert result.status_code==200 and result.json()['data']['revision']==3
    assert result.json()['data']['schedule']['first_time']=='11:30'
    assert state.definition['unrelated_setting']=={'preserved':True}
    assert state.writes==1
    stale=client.put('/api/v1/line/payment-overdue-reminders/schedule',json=body())
    assert stale.status_code==409 and state.writes==1
    assert stale.json()['detail']['error']['category']=='conflict'


@pytest.mark.parametrize('change',[{'overdue_time':'24:00'},{'first_time':'9:00'},{'deposit_mode':'unknown'},{'followup_limit':2},{'followup_after_hours':12},{'recipient':'group'}])
def test_invalid_time_or_effect_expansion_is_rejected_before_writer(http,change):
    client,state,_=http
    result=client.put('/api/v1/line/payment-overdue-reminders/schedule',json=body(**change))
    assert result.status_code==422 and state.writes==0


def test_read_only_account_cannot_save(http):
    client,state,app=http
    app.dependency_overrides[require_admin]=lambda:AdminPrincipal(2,'reader','唯讀人員','read_only',capabilities=frozenset())
    assert client.get('/api/v1/line/payment-overdue-reminders/schedule').status_code==403
    assert client.put('/api/v1/line/payment-overdue-reminders/schedule',json=body()).status_code==403
    assert state.writes==0


def test_same_save_operation_replays_its_result_without_another_revision(http):
    client,state,_=http
    request=body(first_time='11:30')
    first=client.put('/api/v1/line/payment-overdue-reminders/schedule',json=request)
    assert first.status_code==200
    replay=client.put('/api/v1/line/payment-overdue-reminders/schedule',json=request)
    assert replay.status_code==200 and replay.json()==first.json() and state.writes==1
    changed=client.put('/api/v1/line/payment-overdue-reminders/schedule',json=body(first_time='12:00'))
    assert changed.status_code==409 and state.writes==1


def test_noncanonical_operation_key_is_validation_error_not_server_error(http):
    client,state,_=http
    request=body();request['idempotency_key']=' '
    assert client.put('/api/v1/line/payment-overdue-reminders/schedule',json=request).status_code==422 and state.writes==0
