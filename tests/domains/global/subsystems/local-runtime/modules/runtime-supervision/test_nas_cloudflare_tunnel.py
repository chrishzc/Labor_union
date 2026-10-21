"""Explicit proxy trust and the source-only GUI Tunnel handoff contract."""
import asyncio
import json
from pathlib import Path
import zipfile

import httpx
import pytest
import yaml
from fastapi import FastAPI, Request
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from scripts import nas_appliance
from scripts.package_nas_preview import prepare_operations

ROOT = Path(__file__).resolve().parents[7]


@pytest.fixture
def routing(monkeypatch):
    original = Path.read_text
    def read(path, *args, **kwargs):
        if str(path).replace('\\', '/') == '/proc/net/route':
            return 'Iface Destination Gateway Flags\neth0 00000000 01FA1FAC 0003\n'
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'read_text', read)
    monkeypatch.delenv('NAS_TRUSTED_PROXY_IPS', raising=False)


def test_original_DSM_gateway_and_loopback_trust_are_preserved(routing):
    assert set(nas_appliance._trusted_proxies().split(',')) == {'127.0.0.1', '172.31.250.1'}


def test_tunnel_adds_only_its_explicit_addresses(routing, monkeypatch):
    monkeypatch.setenv('NAS_TRUSTED_PROXY_IPS', '172.31.251.2, 172.31.252.2')
    assert set(nas_appliance._trusted_proxies().split(',')) == {
        '127.0.0.1', '172.31.250.1', '172.31.251.2', '172.31.252.2'}


@pytest.mark.parametrize('value', ['*', '0.0.0.0', '::', '172.31.251.0/29', 'proxy.example.com', '224.0.0.1', '172.31.251.2,'])
def test_invalid_proxy_trust_fails_closed_without_echoing_input(routing, monkeypatch, value):
    monkeypatch.setenv('NAS_TRUSTED_PROXY_IPS', value)
    with pytest.raises(ValueError) as caught:
        nas_appliance._trusted_proxies()
    assert value not in str(caught.value)


@pytest.mark.parametrize('peer,scheme,client', [
    ('172.31.251.2', 'https', '203.0.113.10'),
    ('172.31.250.1', 'https', '203.0.113.10'),
    ('172.31.251.4', 'http', '172.31.251.4'),
])
def test_forwarded_headers_only_affect_known_proxy_sources(routing, monkeypatch, peer, scheme, client):
    monkeypatch.setenv('NAS_TRUSTED_PROXY_IPS', '172.31.251.2')
    app = FastAPI()
    @app.get('/probe')
    async def probe(request: Request):
        return {'scheme': request.url.scheme, 'client': request.client.host}
    guarded = ProxyHeadersMiddleware(app, trusted_hosts=nas_appliance._trusted_proxies())
    async def check():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=guarded, client=(peer, 4000)),
                                    base_url='http://admin.example.invalid') as session:
            response = await session.get('/probe', headers={'X-Forwarded-Proto': 'https', 'X-Forwarded-For': '203.0.113.10'})
            assert response.json() == {'scheme': scheme, 'client': client}
    asyncio.run(check())


def test_connector_has_no_database_credentials_business_files_or_host_ports():
    model = yaml.safe_load((ROOT / 'deployment/nas/compose.yaml').read_text(encoding='utf-8'))
    connector = model['services']['cloudflared']
    assert connector['command'] == ['tunnel', '--no-autoupdate', 'run', '--token-file', '/run/cloudflare/token']
    assert connector['user'] == '65532:65532'
    assert connector['read_only'] is True
    assert set(connector['networks']) == {'management-tunnel', 'line-tunnel', 'tunnel-egress'}
    assert connector['volumes'][-1] == 'private-ca:/run/private-ca:ro'
    assert connector['volumes'][0]['target'] == '/run/cloudflare/token'
    assert connector['volumes'][0]['read_only'] is True
    assert len(connector['volumes']) == 2
    for name in ['management-tunnel', 'line-tunnel']:
        assert model['networks'][name]['internal'] is True
        expected = {'cloudflared', 'management-api' if name == 'management-tunnel' else 'line-api'}
        assert {service for service, config in model['services'].items() if name in config.get('networks', {})} == expected
    assert all(not config.get('ports') and not config.get('build') for config in model['services'].values())


def test_passing_handoff_contains_only_allowlisted_files_and_preserves_startup_modes(tmp_path):
    report = tmp_path / 'synthetic-validation.json'
    report.write_text(json.dumps({'local_required_status': 'passed', 'required_failed': 0}))
    directory = tmp_path / 'delivery'
    result = prepare_operations(directory, report)
    assert result['image_build'] == 'not_run'
    with zipfile.ZipFile(directory.with_suffix('.zip')) as archive:
        assert archive.testzip() is None
        names = set(archive.namelist())
        assert names == {'compose.yaml','compose.with-tunnel.yaml','README.md','CLOUDFLARE.md','CERTIFICATES.md',
                         'SQL-BACKUPS.md','OPERATIONS.md','maintain-certificates.sh','backup-database.sh',
                         'nas_appliance.py','nas_certificate_maintenance.py','env-additions.example','validation.json','SHA256SUMS'}
        assert '.env' not in names and 'token' not in names and 'credentials.json' not in names
        base = yaml.safe_load(archive.read('compose.yaml'))
        active = yaml.safe_load(archive.read('compose.with-tunnel.yaml'))
        for service in ['line-api','cloudflared']:
            base['services'][service].pop('profiles')
        assert active == base
        assert active['services']['line-worker']['profiles'] == ['line-check']
        assert archive.read('nas_appliance.py') == (ROOT / 'scripts/nas_appliance.py').read_bytes()


def test_handoff_refuses_to_publish_before_required_tests_pass(tmp_path):
    report = tmp_path / 'failed.json'
    report.write_text(json.dumps({'local_required_status': 'failed', 'required_failed': 1}))
    with pytest.raises(ValueError, match='validation must pass'):
        prepare_operations(tmp_path / 'delivery', report)
    assert not (tmp_path / 'delivery').exists()
