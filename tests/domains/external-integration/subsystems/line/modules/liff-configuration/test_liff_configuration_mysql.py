"""Native versioned LIFF routes; localhost disposable database and no workers."""
from copy import deepcopy
import json
import os
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from api.dependencies import admin_auth
from api.routes import line_system_config as routes
from domains.line.configuration import LineConfigurationKind as K
from domains.line.identities import LineConfigurationRevision
from infrastructure.mysql import mysql_adapter
from infrastructure.mysql.line_unit_of_work import open_line_unit_of_work
from shared_kernel.identities import ActorContext, CorrelationId, IdempotencyKey
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.line.configuration_application import LineConfigurationApplication

pytestmark=pytest.mark.skipif(not os.getenv('LINE_SETTINGS_TEST_DB'), reason='explicit localhost disposable database required')
ACTOR=ActorContext('system:isolated-liff-settings',permission_scope=('line.config.manage','line.config.read'))


@pytest.fixture
def native(monkeypatch):
    target=os.environ['LINE_SETTINGS_TEST_DB']
    assert target.startswith('lu_test_') and mysql_adapter.DB_CONFIG['database']==target
    assert os.getenv('APP_ENV')=='development' and mysql_adapter.DB_CONFIG['host'] in ('localhost','127.0.0.1')
    owner=LineConfigurationApplication(open_line_unit_of_work)
    current=owner.get(K.LIFF,ACTOR)
    definition=json.loads(Path('config/liff_settings.json').read_text(encoding='utf-8'))
    owner.apply(kind=K.LIFF,expected_revision=current.revision,definition=definition,actor=ACTOR,
        reason='isolated LIFF fixture',idempotency_key=IdempotencyKey(uuid4().hex),correlation_id=CorrelationId(uuid4().hex))
    monkeypatch.setattr(routes,'get_line_configuration_application',lambda:owner)
    def no_file(*args,**kwargs):raise AssertionError('file access is forbidden')
    for name in ('read_config','write_config','config_revision'):monkeypatch.setattr(routes,name,no_file)
    app=FastAPI();principal=AdminPrincipal(1,'isolated-settings','隔離設定人員','system_admin')
    for dep in (admin_auth.require_line_viewer,admin_auth.require_line_manager):app.dependency_overrides[dep]=lambda:principal
    @app.middleware('http')
    async def actor(request,call_next):
        request.state.admin_principal=principal
        return await call_next(request)
    app.include_router(routes.router);app.include_router(routes.public_router)
    with TestClient(app) as http:yield http,owner


def effects():
    c=mysql_adapter.get_connection()
    try:
        with c.cursor() as cur:
            result={}
            for name in ('line_delivery_tasks','line_rich_menu_publication_tasks','line_notification_source_events'):
                cur.execute('SELECT COUNT(*) n FROM '+name);result[name]=cur.fetchone()['n']
            return result
    finally:c.close()


def test_native_save_readback_conflict_history_and_rollback(native):
    http,owner=native;baseline=effects()
    state=http.get('/api/config/liff/state').json();revision=state['revision'];old=state['config']
    changed=deepcopy(old['pages']['gateway']);changed['title']='資料庫版本驗證 '+uuid4().hex[:6]
    response=http.put('/api/config/liff/pages/gateway',json=changed,headers={'If-Match':revision})
    assert response.status_code==200,response.text
    assert http.get('/api/config/liff/runtime?page=gateway').json()['page']['title']==changed['title']
    assert http.get('/api/config/liff').json()['pages']['gateway']['title']==changed['title']
    saved=http.get('/api/config/liff/state').json();assert int(saved['revision'])==int(revision)+1
    stale=http.put('/api/config/liff/pages/gateway',json=changed,headers={'If-Match':revision})
    assert stale.status_code==409
    history=http.get('/api/config/liff/history').json()['items']
    assert history[0]['revision']==saved['revision'] and history[1]['revision']==revision
    response=http.post('/api/config/liff/rollback/'+revision,json={'reason':'還原'},headers={'If-Match':saved['revision']})
    assert response.status_code==200,response.text
    assert response.json()['config']==old
    assert int(response.json()['revision'])==int(revision)+2
    assert json.loads(owner.get_revision(K.LIFF,LineConfigurationRevision(int(saved['revision'])),ACTOR).definition_json)['pages']['gateway']['title']==changed['title']
    assert effects()==baseline


def test_native_theme_and_field_lifecycle_are_shared_by_runtime(native):
    http,_=native;baseline=effects()
    def revision():return http.get('/api/config/liff/state').json()['revision']
    theme=http.get('/api/config/liff').json()['theme'];theme['primary_color']='#123456'
    assert http.put('/api/config/liff/theme',json=theme,headers={'If-Match':revision()}).status_code==200
    assert http.get('/api/config/liff/runtime?page=bind').json()['theme']['primary_color']=='#123456'
    field={'id':'native_note','label':'資料庫補充欄位','type':'text','order':100,'system_field':False}
    assert http.post('/api/config/liff/pages/registration/fields',json=field,headers={'If-Match':revision()}).status_code==201
    field['label']='更新後欄位'
    assert http.put('/api/config/liff/pages/registration/fields/native_note',json=field,headers={'If-Match':revision()}).status_code==200
    assert any(f['label']=='更新後欄位' for f in http.get('/api/config/liff/runtime?page=registration').json()['page']['fields'])
    assert http.delete('/api/config/liff/pages/registration/fields/native_note',headers={'If-Match':revision()}).status_code==204
    assert all(f['id']!='native_note' for f in http.get('/api/config/liff/runtime?page=registration').json()['page']['fields'])
    assert effects()==baseline


def test_retired_customer_settings_native_clear_history_and_zero_effect(native):
    http,owner=native;baseline=effects()
    before=owner.get(K.CUSTOMER_SERVICE,ACTOR)
    result=owner.apply(kind=K.CUSTOMER_SERVICE,expected_revision=before.revision,definition={},actor=ACTOR,
        reason='retired settings isolated clear',idempotency_key=IdempotencyKey(uuid4().hex),correlation_id=CorrelationId(uuid4().hex))
    assert result.snapshot.definition_json=='{}'
    assert result.snapshot.revision.value==before.revision.value+1
    assert owner.get_revision(K.CUSTOMER_SERVICE,result.snapshot.revision,ACTOR)==result.snapshot
    with pytest.raises(ValueError,match='retired'):
        owner.preview(K.CUSTOMER_SERVICE,result.snapshot.revision,{'settings':{'auto_assign':True}},ACTOR)
    assert http.get('/api/config/customer-service').status_code==410
    assert http.put('/api/config/customer-service',json={'settings':{'auto_assign':True}}).status_code==410
    assert owner.get(K.CUSTOMER_SERVICE,ACTOR)==result.snapshot and effects()==baseline
