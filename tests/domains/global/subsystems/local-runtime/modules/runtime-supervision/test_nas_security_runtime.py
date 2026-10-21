"""Offline deployment boundaries; no container or database is started here."""
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[7]


def test_previous_ui_toolchain_update_preserves_historical_application_sources(tmp_path):
    import json
    from scripts.package_nas_preview import _use_patched_previous_ui_toolchain
    for folder, version in [("ui_react", "4.1.11"), ("previous_ui", "3.2.7")]:
        target = tmp_path / folder
        target.mkdir()
        (target / "package.json").write_text(json.dumps({
            "dependencies": {"react": "19.2.8"},
            "devDependencies": {"vitest": version, "happy-dom": version, "vite": "8.2.0"},
        }), encoding="utf-8")
        (target / "package-lock.json").write_text(json.dumps({"packages": {
            "node_modules/react": {"version": "19.2.8"},
            "node_modules/vitest": {"version": version, "dev": True},
        }}), encoding="utf-8")
        (target / "App.tsx").write_text(folder, encoding="utf-8")
    _use_patched_previous_ui_toolchain(tmp_path)
    for name in ("package.json", "package-lock.json"):
        assert (tmp_path / "previous_ui" / name).read_bytes() == (tmp_path / "ui_react" / name).read_bytes()
    assert (tmp_path / "previous_ui/App.tsx").read_text() == "previous_ui"


def test_previous_ui_toolchain_rejects_transitive_runtime_version_changes(tmp_path):
    import json
    from scripts.package_nas_preview import _use_patched_previous_ui_toolchain
    for folder, version in [("ui_react", "2"), ("previous_ui", "1")]:
        target = tmp_path / folder
        target.mkdir()
        (target / "package.json").write_text('{}', encoding="utf-8")
        (target / "package-lock.json").write_text(json.dumps({"packages": {
            "node_modules/runtime": {"version": version},
        }}), encoding="utf-8")
    original = (tmp_path / "previous_ui/package-lock.json").read_bytes()
    with pytest.raises(ValueError, match="historical frontend runtime lock differs"):
        _use_patched_previous_ui_toolchain(tmp_path)
    assert (tmp_path / "previous_ui/package-lock.json").read_bytes() == original


@pytest.mark.parametrize("section", ["dependencies", "devDependencies"])
def test_previous_ui_toolchain_rejects_unrelated_dependency_changes(tmp_path, section):
    import json
    from scripts.package_nas_preview import _use_patched_previous_ui_toolchain
    for folder, version in [("ui_react", "2"), ("previous_ui", "1")]:
        target = tmp_path / folder
        target.mkdir()
        (target / "package.json").write_text(json.dumps({section: {"unrelated": version}}), encoding="utf-8")
        (target / "package-lock.json").write_text(version, encoding="utf-8")
    before = {path: path.read_bytes() for path in (tmp_path / "previous_ui").iterdir()}
    with pytest.raises(ValueError, match="historical frontend dependencies differ"):
        _use_patched_previous_ui_toolchain(tmp_path)
    assert {path: path.read_bytes() for path in before} == before


@pytest.mark.parametrize('name', [
    '.env', 'ui_react/.env.production', 'config/app.env', 'config/credentials.json',
    'config/tokens/token', 'config/verifiers.json', 'config/service_account_live.json',
    'config/private.pem', 'ui_react/.npmrc',
    'config/certificate-maintenance/transactions/fixture/candidate/db-key',
])
def test_build_source_filter_rejects_live_settings_and_credentials(name):
    from scripts.package_nas_preview import include_source
    assert not include_source(name)
    assert include_source('scripts/nas_security_runtime.py')


def test_private_api_certificates_include_strict_chain_identifiers(tmp_path, monkeypatch):
    from cryptography import x509
    from scripts import nas_security_runtime as runtime
    monkeypatch.setattr(runtime, "CA", tmp_path / "ca")
    monkeypatch.setattr(runtime, "API_TLS", tmp_path / "tls")
    def write(path, value, mode=0o400):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(value)
    monkeypatch.setattr(runtime, "_write", write)
    runtime._prepare_api_tls()
    ca = x509.load_pem_x509_certificate((runtime.CA / "ca.pem").read_bytes())
    identifier = ca.extensions.get_extension_for_class(x509.SubjectKeyIdentifier).value.digest
    assert ca.extensions.get_extension_for_class(x509.KeyUsage).value.key_cert_sign
    for service in ("management-api", "line-api"):
        cert = x509.load_pem_x509_certificate((runtime.API_TLS / service / "server-cert.pem").read_bytes())
        assert cert.extensions.get_extension_for_class(x509.AuthorityKeyIdentifier).value.key_identifier == identifier
        assert x509.oid.ExtendedKeyUsageOID.SERVER_AUTH in cert.extensions.get_extension_for_class(x509.ExtendedKeyUsage).value
        assert cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value.get_values_for_type(x509.DNSName) == [service]


def test_line_composition_has_necessary_liff_pages_but_no_admin_or_approval_routes():
    from api.nas_apps import line_app
    paths = line_app().openapi()["paths"]
    for path in ("/webhook/line", "/line-profile-update", "/line-order-update", "/line-staff-baby-log",
                 "/api/v1/line/identity/registration/apply", "/api/v1/line/client-profile/apply",
                 "/api/v1/line/staff-self-service/service-day-logs/apply"):
        assert path in paths
    assert not any("/admin/" in path or path.startswith(("/setup", "/api/v1/client-profile/requests")) for path in paths)


def test_compose_separates_database_credentials_and_machine_tokens():
    compose = yaml.safe_load((ROOT / "deployment/nas/compose.yaml").read_text(encoding="utf-8"))
    services = compose["services"]
    assert "bootstrap:/etc/mysql/conf.d:ro" in services["db"]["volumes"]
    assert "default-character-set=utf8mb4" in (ROOT / "deployment/nas/mysql-client.cnf").read_text(encoding="utf-8")
    for service in services.values():
        assert "ports" not in service
        assert 'build' not in service
    management_network = services['management-api']['networks']['management-egress']
    assert management_network['ipv4_address'].startswith('${NAS_PROXY_API_IP:?')
    edge = compose['networks']['management-egress']
    assert edge['driver'] == 'bridge'
    assert edge['ipam']['config'][0]['subnet'].startswith('${NAS_PROXY_SUBNET:?')
    assert all('management-egress' not in service.get('networks', {})
               for name, service in services.items() if name != 'management-api')
    public_mounts = {mount.split(":", 1)[0] if isinstance(mount, str) else mount['source']
                     for mount in services["line-api"]["volumes"]}
    assert "line-db" in public_mounts
    assert not public_mounts.intersection({"settings", "access-db", "maintenance-db", "management-db", "mysql-secrets"})
    assert not any('controlled-files' in mount or 'app-data' in mount or 'knowledge' in mount for mount in public_mounts)
    assert 'line-media-token:/run/line-media-proxy:ro' in services['line-api']['volumes']
    assert services['line-api']['environment']['LINE_MEDIA_API_BASE_URL'] == 'https://management-api:8443'
    assert 'line-media-control' in services['line-api']['networks']
    assert 'line-media-control' in services['management-api']['networks']
    assert services['management-api']['environment']['FILE_SETTINGS_PATH'] == '/data/file-settings.json'
    assert 'line-media-token:/workers/line-media-proxy' in services['initialize']['volumes']
    for worker in ("durable-worker", "knowledge-worker", "incident-worker", "runtime-monitor", "line-worker"):
        mounts = services[worker]["volumes"]
        assert len([mount for mount in mounts if "token:/run/worker:ro" in mount]) == 1
        assert not any("-db:" in mount or "mysql-secrets:" in mount for mount in mounts)
        assert services[worker]["environment"]["INTERNAL_SERVICE_AUTH_MODE"] == "nas_service_token"
    assert services["line-worker"]["command"][-1] == "--check"
    assert services["line-worker"]["restart"] == "no"
    assert services['line-worker']['profiles'] == ['line-check']
    assert services['cloudflared']['networks'] == ['line-control', 'tunnel-egress']
    assert not services['cloudflared']['volumes'][-1].startswith('settings:')


def test_gui_default_and_optional_stages_are_separate():
    compose = yaml.safe_load((ROOT / 'deployment/nas/compose.yaml').read_text(encoding='utf-8'))
    services = compose['services']
    assert {name for name, service in services.items() if not service.get('profiles')} == {
        'initialize', 'db', 'configure-security', 'redis', 'management-api'}
    for stage in ['durable', 'knowledge', 'incident', 'monitor', 'line', 'tunnel', 'line-check']:
        selected = {name for name, service in services.items() if not service.get('profiles') or stage in service['profiles']}
        assert ('line-worker' in selected) == (stage == 'line-check')
        for name in selected:
            assert set(services[name].get('depends_on', {})) <= selected
    for name in ['initialize', 'management-api', 'line-api']:
        for mount in services[name]['volumes']:
            if isinstance(mount, dict):
                assert mount['bind']['create_host_path'] is False


def test_ds220_compatibility_preserves_the_existing_internal_data_network():
    compose = yaml.safe_load((ROOT / 'deployment/nas/compose.yaml').read_text(encoding='utf-8'))
    assert all('cpus' not in service for service in compose['services'].values())
    assert compose['networks']['data'] == {
        'external': True,
        'name': '${COMPOSE_PROJECT_NAME:?請保留現有專案名稱}_data',
    }
    # Unsupported quotas must not return through the optional Tunnel overlay.
    tunnel = yaml.safe_load((ROOT / 'deployment/nas/compose.tunnel.yaml').read_text(encoding='utf-8'))
    assert all('cpus' not in service for service in tunnel['services'].values())


def test_management_certificate_covers_nas_address_without_changing_private_line_identity(tmp_path, monkeypatch):
    from cryptography import x509
    from scripts import nas_security_runtime as runtime
    monkeypatch.setenv('NAS_BIND_IP', '192.168.50.10')
    monkeypatch.setenv('NAS_MANAGEMENT_HOSTNAME', 'union-nas.example.com')
    monkeypatch.setattr(runtime, 'CA', tmp_path/'ca')
    monkeypatch.setattr(runtime, 'API_TLS', tmp_path/'tls')
    def write(path, value, mode=0o400):
        path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(value)
    monkeypatch.setattr(runtime, '_write', write)
    runtime._prepare_api_tls()
    cert = x509.load_pem_x509_certificate((runtime.API_TLS/'management-api/server-cert.pem').read_bytes())
    san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    assert san.get_values_for_type(x509.DNSName) == ['management-api', 'union-nas.example.com']
    assert [str(ip) for ip in san.get_values_for_type(x509.IPAddress)] == ['192.168.50.10']
    line = x509.load_pem_x509_certificate((runtime.API_TLS/'line-api/server-cert.pem').read_bytes())
    assert line.extensions.get_extension_for_class(x509.SubjectAlternativeName).value.get_values_for_type(x509.DNSName) == ['line-api']


@pytest.fixture
def isolated_initializer(tmp_path, monkeypatch):
    from scripts import compact_fresh_schema, nas_security_runtime as runtime
    from subsystems.line.configuration_store import CONFIG_FILES
    monkeypatch.setattr(compact_fresh_schema, 'load_compact_plan', lambda: {})
    for name in ['SETTINGS', 'LINE_SETTINGS', 'PROFILES_ROOT', 'WORKERS', 'API_TLS', 'CA', 'DB_CA', 'LINE_CONFIG']:
        path = tmp_path/name; path.mkdir(); monkeypatch.setattr(runtime, name, path)
    roots = tuple(tmp_path/name for name in ['files', 'media', 'knowledge'])
    for root in roots: root.mkdir()
    monkeypatch.setattr(runtime, 'FILE_ROOTS', roots)
    for name in ['DATA', 'BOOTSTRAP', 'SERVER_TLS']:
        path = tmp_path/name; path.mkdir(); monkeypatch.setattr(runtime.nas_appliance, name, path)
    def base_initialize():
        (runtime.SETTINGS/'app.env').write_text('CONTRACT_DOCUMENT_ARCHIVE_ROOT=/data/contracts\n', encoding='utf-8')
        (runtime.nas_appliance.SERVER_TLS/'ca.pem').write_bytes(b'isolated-db-ca-copy-fixture')
    monkeypatch.setattr(runtime.nas_appliance, 'initialize', base_initialize)
    # The offline fixture supplies container-only assets explicitly. It must not
    # depend on /opt or /app existing on the developer's operating system.
    assets = tmp_path/'assets'
    config_assets = assets/'config'
    config_assets.mkdir(parents=True)
    for filename in CONFIG_FILES.values():
        (config_assets/filename).write_text('{"fixture":"' + filename + '"}', encoding='utf-8')
    def container_asset_path(value):
        if value == '/opt/nas/init/mysql-client.cnf':
            return ROOT/'deployment/nas/mysql-client.cnf'
        if value == '/app/config':
            return config_assets
        return Path(value)
    monkeypatch.setattr(runtime, 'Path', container_asset_path)
    ownership = []
    monkeypatch.setattr(runtime.os, 'chown', lambda path, uid, gid: ownership.append((Path(path), uid, gid)), raising=False)
    monkeypatch.setattr(runtime, '_test_ownership', ownership, raising=False)
    for name in ['NAS_BIND_IP', 'NAS_MANAGEMENT_HOSTNAME']:
        monkeypatch.delenv(name, raising=False)
    return runtime


@pytest.mark.parametrize('root_index', [0, 1, 2])
def test_nonempty_file_roots_stop_before_any_initialization(isolated_initializer, root_index, monkeypatch):
    runtime = isolated_initializer
    existing = runtime.FILE_ROOTS[root_index]/'existing-file'
    existing.write_bytes(b'preserve-user-data')
    mode = existing.stat().st_mode
    monkeypatch.setattr(runtime.nas_appliance, 'initialize', lambda: pytest.fail('must not initialize existing data'))
    with pytest.raises(ValueError, match='refusing to overwrite'):
        runtime.initialize()
    assert existing.read_bytes() == b'preserve-user-data' and existing.stat().st_mode == mode
    assert not list(runtime.SETTINGS.iterdir())


@pytest.mark.parametrize('name,value', [('NAS_BIND_IP', '0.0.0.0'), ('NAS_BIND_IP', 'not-an-ip'),
                                      ('NAS_MANAGEMENT_HOSTNAME', 'https://nas:18443')])
def test_invalid_management_address_stops_before_creating_secrets(isolated_initializer, monkeypatch, name, value):
    runtime = isolated_initializer
    monkeypatch.setenv(name, value)
    monkeypatch.setattr(runtime.nas_appliance, 'initialize', lambda: pytest.fail('must validate first'))
    with pytest.raises(ValueError): runtime.initialize()
    assert not list(runtime.SETTINGS.iterdir())


def test_fresh_initializer_prepares_photo_identity_and_public_ca_without_overwriting_on_reentry(isolated_initializer):
    import hashlib
    import json
    from infrastructure.runtime.worker_credentials import SERVICES
    runtime = isolated_initializer
    runtime.initialize()
    registry = json.loads((runtime.WORKERS/'api/verifiers.json').read_text())
    assert set(registry['services']) == set(SERVICES)
    assert (runtime.WORKERS/'line-media-proxy/token').is_file()
    assert (runtime.nas_appliance.DATA/'management-api-ca.crt').read_bytes() == (runtime.CA/'ca.pem').read_bytes()
    assert (runtime.nas_appliance.BOOTSTRAP/'00-client-charset.cnf').read_bytes() == (ROOT/'deployment/nas/mysql-client.cnf').read_bytes()
    assert all((folder, 1000, -1) in runtime._test_ownership for folder in runtime.FILE_ROOTS)
    before = {str(path): hashlib.sha256(path.read_bytes()).hexdigest()
              for path in runtime.SETTINGS.parent.rglob('*') if path.is_file()}
    runtime.initialize()
    after = {str(path): hashlib.sha256(path.read_bytes()).hexdigest()
             for path in runtime.SETTINGS.parent.rglob('*') if path.is_file()}
    assert before == after


def test_tunnel_routes_only_to_public_api_and_denies_private_operations():
    rules = yaml.safe_load((ROOT / "deployment/nas/cloudflared.example.yaml").read_text(encoding="utf-8"))["ingress"]
    assert rules[0]["path"] == "^/internal(/|$)" and rules[0]["service"] == "http_status:404"
    assert rules[1]["service"] == "https://line-api:8443"
    assert rules[1]["originRequest"]["noTLSVerify"] is False
    assert rules[-1] == {"service": "http_status:404"}


def test_stale_compact_schema_stops_before_initialization(monkeypatch):
    from scripts import compact_fresh_schema, nas_security_runtime
    def stale(): raise ValueError("stale schema")
    monkeypatch.setattr(compact_fresh_schema, "load_compact_plan", stale)
    monkeypatch.setattr(nas_security_runtime.nas_appliance, "initialize",
                        lambda: pytest.fail("initializer must not write with a stale baseline"))
    with pytest.raises(ValueError, match="stale schema"):
        nas_security_runtime.initialize()


@pytest.mark.parametrize("service,profiles", [("line-api", [(None, "line")]),
    ("management-api", [(None, "management"), ("access", "access"), ("maintenance", "maintenance")])])
def test_api_start_verifies_only_its_own_profiles_against_canonical_inventory(service, profiles, monkeypatch):
    from scripts import compact_fresh_schema, nas_security_runtime
    from infrastructure.mysql import mysql_adapter, nas_permissions
    from types import SimpleNamespace
    checks, launches = [], []
    inventory = {"tables": {"clients", "orders"}, "views": set()}
    monkeypatch.setattr(nas_security_runtime, "dotenv_values", lambda _: {})
    monkeypatch.setattr(nas_security_runtime.nas_appliance, "_drop_privileges", lambda: None)
    monkeypatch.setattr(nas_security_runtime.nas_appliance, "_trusted_proxies", lambda: "127.0.0.1")
    monkeypatch.setattr(nas_security_runtime.nas_test_runtime, "require_login_mode", lambda: None)
    monkeypatch.setattr(compact_fresh_schema, "load_compact_plan", lambda: {"expected": inventory})
    monkeypatch.setattr(mysql_adapter, "get_connection", lambda profile=None: SimpleNamespace(profile=profile, close=lambda: None))
    def verify(connection, profile, database, **expected):
        assert database == nas_security_runtime.nas_test_runtime.DATABASE
        assert expected == {"expected_tables": inventory["tables"], "expected_views": inventory["views"]}
        checks.append((connection.profile, profile))
    monkeypatch.setattr(nas_permissions, "verify_runtime_permissions", verify)
    monkeypatch.setattr(nas_security_runtime.os, "execvp", lambda executable, args: launches.append(args))
    nas_security_runtime.serve(service)
    assert checks == profiles
    assert "--ssl-certfile" in launches[0] and "--ssl-keyfile" in launches[0]
    assert launches[0][3] == ("api.nas_apps:line_app" if service == "line-api" else "api.nas_apps:management_app")
