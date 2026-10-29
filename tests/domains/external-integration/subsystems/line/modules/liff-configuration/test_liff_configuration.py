"""LIFF runtime, edits and rollback share one versioned owner, with zero file effects."""
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
import pytest

from api.dependencies import admin_auth
from api.routes import line_system_config as routes
from domains.line.canonical_payload import canonical_line_payload_json
from domains.line.configuration import LineConfigurationKind as K, LineConfigurationSnapshot, LineConfigurationRevisionConflict
from domains.line.identities import LineConfigurationRevision
from shared_kernel.identities import ActorContext, CorrelationId, IdempotencyKey
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.line.configuration_application import LineConfigurationApplication
from subsystems.line.configuration_contracts import LineConfigurationHistoryEntry, LineConfigurationCommandOutcome


def definition():
    return json.loads(Path('config/liff_settings.json').read_text(encoding='utf-8'))


class Repository:
    def __init__(self):
        self.versions = {1: canonical_line_payload_json(definition())}
        self.revision = 1
        self.error = None

    def get(self, kind):
        assert kind == K.LIFF
        if self.error: raise self.error
        return LineConfigurationSnapshot(kind, LineConfigurationRevision(self.revision), self.versions[self.revision])

    def apply(self, command):
        if command.candidate.before_revision.value != self.revision:
            raise RuntimeError('line_configuration_revision_conflict')
        self.revision += 1
        self.versions[self.revision] = command.candidate.definition_json
        return SimpleNamespace(outcome=LineConfigurationCommandOutcome.CREATED, snapshot=self.get(K.LIFF))

    def history(self, kind):
        assert kind == K.LIFF
        return tuple(LineConfigurationHistoryEntry(LineConfigurationRevision(r), datetime(2026, 10, 25, tzinfo=timezone.utc), 'admin:1', '測試異動') for r in sorted(self.versions, reverse=True))

    def get_revision(self, kind, revision):
        assert kind == K.LIFF
        raw = self.versions.get(revision.value)
        return None if raw is None else LineConfigurationSnapshot(kind, revision, raw)


class Unit:
    def __init__(self, repository):
        self.configurations = repository
        self.commits = 0
        self.audit = SimpleNamespace(append=lambda _item: None)

    def __enter__(self): return self
    def __exit__(self, *args): return False
    def commit(self): self.commits += 1


@pytest.fixture
def context(monkeypatch):
    repo = Repository(); unit = Unit(repo)
    owner = LineConfigurationApplication(lambda: unit)
    monkeypatch.setattr(routes, 'get_line_configuration_application', lambda: owner)
    def no_file(*args, **kwargs): raise AssertionError('LIFF must not use file configuration')
    for name in ('read_config', 'write_config', 'config_revision'):
        monkeypatch.setattr(routes, name, no_file)
    app = FastAPI()
    principal = AdminPrincipal(1, 'isolated', '隔離人員', 'system_admin')
    for dependency in (admin_auth.require_line_viewer, admin_auth.require_line_manager):
        app.dependency_overrides[dependency] = lambda: principal
    @app.middleware('http')
    async def actor(request, call_next):
        request.state.admin_principal = principal
        return await call_next(request)
    app.include_router(routes.public_router); app.include_router(routes.router)
    with TestClient(app) as http:
        yield http, repo, unit, owner


def test_runtime_and_management_read_database_without_file_fallback(context):
    http, repo, unit, _ = context
    d = definition(); d['pages']['gateway']['title'] = '資料庫專用入口'
    repo.versions[1] = canonical_line_payload_json(d)
    runtime = http.get('/api/config/liff/runtime?page=gateway')
    assert runtime.status_code == 200 and runtime.headers['etag'] == '"1"'
    assert runtime.json()['page']['title'] == '資料庫專用入口'
    assert http.get('/api/config/liff').json() == d
    assert http.get('/api/config/liff/state').json()['revision'] == '1'
    assert unit.commits == 0


@pytest.mark.parametrize('mutation', ['replace', 'theme', 'page', 'create', 'update', 'delete'])
def test_every_existing_write_route_updates_database_revision(context, mutation):
    http, repo, unit, _ = context
    d = definition()
    extra = {'id':'custom_note','label':'補充說明','type':'text','order':100,'system_field':False}
    d['pages']['registration']['fields'].append(extra)
    repo.versions[1] = canonical_line_payload_json(d)
    if mutation == 'replace':
        d['pages']['bind']['title'] = '新版綁定'; method, path, payload = 'put', '', d
    elif mutation == 'theme':
        payload = dict(d['theme'], primary_color='#123456'); method, path = 'put', '/theme'
    elif mutation == 'page':
        payload = dict(d['pages']['gateway'], title='新版服務入口'); method, path = 'put', '/pages/gateway'
    elif mutation == 'create':
        payload = dict(extra, id='another_note'); method, path = 'post', '/pages/registration/fields'
    elif mutation == 'update':
        payload = dict(extra, label='新版欄位'); method, path = 'put', '/pages/registration/fields/custom_note'
    else:
        payload = None; method, path = 'delete', '/pages/registration/fields/custom_note'
    response = http.request(method, '/api/config/liff'+path, json=payload, headers={'If-Match':'"1"'})
    assert response.status_code in (200, 201, 204), response.text
    assert repo.revision == 2 and unit.commits == 1
    assert repo.versions[1] != repo.versions[2]
    fresh = http.get('/api/config/liff/state').json()
    assert fresh['revision'] == '2' and fresh['config'] == json.loads(repo.versions[2])


def test_stale_write_and_concurrent_apply_are_conflicts(context, monkeypatch):
    http, repo, unit, owner = context
    response = http.put('/api/config/liff/theme', json=definition()['theme'], headers={'If-Match':'99'})
    assert response.status_code == 409 and unit.commits == 0
    original = owner.apply
    def race(**kwargs):
        repo.versions[2] = repo.versions[1]; repo.revision = 2
        return original(**kwargs)
    monkeypatch.setattr(owner, 'apply', race)
    response = http.put('/api/config/liff/theme', json=definition()['theme'], headers={'If-Match':'1'})
    assert response.status_code == 409 and unit.commits == 0


@pytest.mark.parametrize('failure', ['missing', 'invalid', 'unavailable'])
def test_runtime_missing_invalid_or_unavailable_is_503(context, failure):
    http, repo, unit, _ = context
    if failure == 'missing': repo.revision = 0; repo.versions[0] = '{}'
    elif failure == 'invalid': repo.versions[1] = '{}'
    else: repo.error = RuntimeError('database unavailable')
    for path in ('/api/config/liff', '/api/config/liff/runtime?page=bind', '/api/config/liff/state'):
        assert http.get(path).status_code == 503
    assert unit.commits == 0


def test_disabled_or_missing_page_is_not_available(context):
    http, repo, unit, _ = context
    d=definition();d['pages']['gateway']['enabled']=False;repo.versions[1]=canonical_line_payload_json(d)
    assert http.get('/api/config/liff/runtime?page=gateway').status_code == 404
    assert http.get('/api/config/liff/runtime?page=unknown').status_code == 404
    assert unit.commits == 0


def test_history_and_rollback_append_revision_and_preserve_prior_versions(context):
    http, repo, unit, _ = context
    old = repo.versions[1]
    payload = dict(definition()['pages']['gateway'], title='修改後入口')
    assert http.put('/api/config/liff/pages/gateway', json=payload, headers={'If-Match':'1'}).status_code == 200
    second = repo.versions[2]
    history = http.get('/api/config/liff/history').json()['items']
    assert [row['revision'] for row in history] == ['2', '1']
    assert all('config' not in row for row in history)
    response = http.post('/api/config/liff/rollback/1',json={'reason':'還原驗證'},headers={'If-Match':'2'})
    assert response.status_code == 200 and response.json()['revision']=='3', response.text
    assert repo.versions[1] == old and repo.versions[2] == second
    assert json.loads(repo.versions[3]) == json.loads(old)
    assert http.post('/api/config/liff/rollback/old-file-hash',json={},headers={'If-Match':'3'}).status_code == 404


def test_generic_owner_rejects_invalid_liff_shape_before_commit(context):
    _, repo, unit, owner = context
    actor=ActorContext('admin:1',permission_scope=('line.config.manage',))
    with pytest.raises(ValueError):
        owner.apply(kind=K.LIFF, expected_revision=LineConfigurationRevision(1),definition={},actor=actor,
            reason='invalid',idempotency_key=IdempotencyKey('invalid-liff'),correlation_id=CorrelationId('invalid-liff'))
    assert repo.revision == 1 and unit.commits == 0


def test_system_fields_remain_protected(context):
    http, repo, unit, _=context
    assert http.delete('/api/config/liff/pages/bind/fields/name',headers={'If-Match':'1'}).status_code == 409
    assert repo.revision == 1 and unit.commits == 0


def test_non_citizen_page_and_gateway_are_created_in_one_configuration_version(context):
    http, repo, unit, _ = context
    old = definition()
    old['pages'].pop('non_citizen_registration', None)
    old['pages']['gateway']['actions'] = [a for a in old['pages']['gateway']['actions'] if a['id'] != 'non_citizen_registration']
    repo.versions[1] = canonical_line_payload_json(old)
    assert http.get('/api/config/liff/non-citizen').json()['page'] is None
    result = http.post('/api/config/liff/non-citizen', headers={'If-Match':'1'})
    assert result.status_code == 200, result.text
    assert result.json()['revision'] == '2' and unit.commits == 1
    saved = json.loads(repo.versions[2])
    assert saved['pages']['registration'] == old['pages']['registration']
    assert saved['pages']['gateway']['actions'][:-1] == old['pages']['gateway']['actions']
    assert saved['pages']['gateway']['actions'][-1]['path'] == '/line-non-citizen-registration'
    assert all(field['required'] for field in saved['pages']['non_citizen_registration']['fields'] if field['system_field'])
    assert http.post('/api/config/liff/non-citizen', headers={'If-Match':'2'}).json()['revision'] == '2'
    assert unit.commits == 1


def test_non_citizen_settings_use_revision_and_cannot_disable_required_fields(context):
    http, repo, unit, _ = context
    state = http.get('/api/config/liff/non-citizen').json()
    page = state['page']; page['title'] = '非市民自費服務'
    response = http.put('/api/config/liff/non-citizen', json=page, headers={'If-Match':'1'})
    assert response.status_code == 200 and response.json()['revision'] == '2'
    assert http.get('/api/config/liff/runtime?page=non_citizen_registration').json()['page']['title'] == page['title']
    assert http.put('/api/config/liff/non-citizen', json=page, headers={'If-Match':'1'}).status_code == 409
    next(field for field in page['fields'] if field['id'] == 'service_time')['required'] = False
    assert http.put('/api/config/liff/non-citizen', json=page, headers={'If-Match':'2'}).status_code == 422
    assert repo.revision == 2


def test_history_read_failure_is_503_and_does_not_write(context, monkeypatch):
    http, repo, unit, owner = context
    def unavailable(*args):raise ConnectionError('isolated history unavailable')
    monkeypatch.setattr(owner,'history',unavailable)
    monkeypatch.setattr(owner,'get_revision',unavailable)
    assert http.get('/api/config/liff/history').status_code == 503
    assert http.post('/api/config/liff/rollback/1',json={},headers={'If-Match':'1'}).status_code == 503
    assert repo.revision == 1 and unit.commits == 0


def test_retired_customer_service_routes_cannot_read_or_write_files(context):
    http, repo, unit, owner = context
    assert http.get('/api/config/customer-service').status_code == 410
    assert http.put('/api/config/customer-service', json={'settings': {'auto_assign': True}}).status_code == 410
    assert unit.commits == 0 and repo.revision == 1


def test_retired_customer_service_cannot_be_restored_or_bootstrapped(context):
    _, repo, unit, owner = context
    actor = ActorContext('test', permission_scope=('line.config.manage',))
    with pytest.raises(ValueError, match='retired'):
        owner._validate(unit, K.CUSTOMER_SERVICE, {'settings': {'auto_assign': True}})
    owner._validate(unit, K.CUSTOMER_SERVICE, {})
    assert owner.bootstrap_missing({K.CUSTOMER_SERVICE: {'settings': {'auto_assign': True}}}, actor,
        reason='test', correlation_id=CorrelationId('retired-customer-bootstrap')) == ()
    from subsystems.line.configuration_store import config_path
    with pytest.raises(ValueError, match='Unsupported'):
        config_path('customer_service')
