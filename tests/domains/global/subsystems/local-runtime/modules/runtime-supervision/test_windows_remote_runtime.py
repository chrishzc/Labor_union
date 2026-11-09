"""
File: test_windows_remote_runtime.py
Description: 驗證 Windows 遠端靜態入口前綴隔離、授權探測、二進位串流、Gzip 與靜態快取資格透傳。
"""
import json
import httpx
import pytest
from starlette.testclient import TestClient

from scripts.build_react_admin_artifact import build_artifact
from infrastructure.runtime.react_admin_artifact import (
    ASSET_ELIGIBILITY_HEADER,
    PRIVATE_IMMUTABLE_CACHE_CONTROL,
    validate_react_admin_artifact,
)
from scripts import windows_remote_runtime as remote


@pytest.fixture
def artifact(tmp_path):
    source = tmp_path / 'source'
    source.mkdir()
    (source / 'index.html').write_text(
        '<div id="root"></div><script src="/test/app.js"></script>', encoding='utf-8',
    )
    (source / 'app.js').write_text('console.log("remote")', encoding='utf-8')
    output = tmp_path / 'artifact'
    build_artifact(output, source=source)
    return validate_react_admin_artifact(output, workspace_root=remote.ROOT)


def test_prefix_static_and_private_paths_never_reach_api(artifact):
    calls = []

    def api(request):
        calls.append(request.url.path)
        return httpx.Response(401, stream=httpx.ByteStream(b''))

    app = remote.create_gateway(artifact, transport=httpx.MockTransport(api))
    with TestClient(app, base_url='http://127.0.0.1:5173') as client:
        assert client.get('/test', follow_redirects=False).headers['location'] == '/test/'
        assert '<div id="root"></div>' in client.get('/test/').text
        assert client.get('/test/app.js').status_code == 200
        assert client.get('/admin/').content == client.get('/test/').content
        assert client.get('/admin/artifact-manifest.json').content == client.get('/test/artifact-manifest.json').content
        assert client.get('/admin/', headers={'host': 'chrishzc.com'}).status_code == 404
        for path in ('/', '/testing', '/api/v1/admin/auth/me', '/internal',
                     '/test/internal/v1/runtime', '/test/docs', '/test/.env',
                     '/test/src/main.tsx', '/test/api/v1/admin/auth/development-session'):
            assert client.get(path).status_code == 404, path
        assert client.get('/test/', headers={'host': 'attacker.example'}).status_code == 403
        assert client.post('/test/api/v1/orders', headers={'origin': 'https://attacker.example'}).status_code == 403
        assert client.get('/test/api/v1/admin/auth/me').status_code == 401
    assert calls == ['/api/v1/admin/auth/me', '/api/v1/admin/auth/me']


def test_api_upload_query_and_binary_download_keep_prefix_and_session(artifact):
    calls = []

    def api(request):
        if request.url.path == '/api/v1/admin/auth/me':
            return httpx.Response(401)
        calls.append((request.url, dict(request.headers), request.read()))
        return httpx.Response(409 if request.url.path.endswith('/apply') else 200,
                              headers={'content-type': 'application/pdf',
                                       'content-disposition': 'attachment; filename="report.pdf"'},
                              stream=httpx.ByteStream(b'%PDF-remote\x00\xff'))

    app = remote.create_gateway(artifact, transport=httpx.MockTransport(api))
    with TestClient(app, base_url='https://chrishzc.com') as client:
        response = client.post('/test/api/v1/imports/apply?mode=preview&name=a%2Fb',
                               content=b'upload\x00data', headers={
                                   'authorization': 'Bearer synthetic-session',
                                   'origin': 'https://chrishzc.com',
                                   'idempotency-key': 'synthetic-key',
                                   'x-forwarded-for': '203.0.113.99',
                                   'cf-access-authenticated-user-email': 'untrusted@example.invalid',
                               })
        assert response.status_code == 409
        assert response.content == b'%PDF-remote\x00\xff'
        assert response.headers['content-disposition'].endswith('"report.pdf"')
        assert response.headers['cache-control'] == 'no-store'
    url, headers, body = calls[0]
    assert url.host == '127.0.0.1' and url.path == '/api/v1/imports/apply'
    assert url.query == b'mode=preview&name=a%2Fb'
    assert body == b'upload\x00data'
    assert headers['authorization'] == 'Bearer synthetic-session'
    assert headers['idempotency-key'] == 'synthetic-key'
    assert 'x-forwarded-for' not in headers
    assert 'cf-access-authenticated-user-email' not in headers


@pytest.mark.parametrize('status', [200, 404, 500])
def test_startup_refuses_bypass_or_unavailable_api(artifact, status):
    app = remote.create_gateway(artifact, transport=httpx.MockTransport(lambda _: httpx.Response(status)))
    with pytest.raises(RuntimeError, match='authenticated API'):
        with TestClient(app):
            pass


def test_factory_refuses_inherited_bypass_before_loading_artifact(monkeypatch):
    monkeypatch.setenv('ACCESS_CONTROL_PROFILE', 'local_bypass')
    monkeypatch.setenv('ENABLE_ADMIN_AUTH', 'false')
    with pytest.raises(RuntimeError, match='refuses development'):
        remote.create_app()


@pytest.mark.parametrize('method', ['GET', 'HEAD'])
@pytest.mark.parametrize('mount', ['/test', '/admin'])
@pytest.mark.parametrize('extension,original,replacement', [
    ('js', b'export const version = 1;\n', b'export const version = 2;\n'),
    ('css', b'body { color: black; }\n', b'body { color: white; }\n'),
])
def test_equal_size_asset_corruption_after_gateway_start_is_not_served_or_cached(
    tmp_path, method, mount, extension, original, replacement,
):
    source = tmp_path / 'source'
    (source / 'assets').mkdir(parents=True)
    (source / '.vite').mkdir()
    relative = f'assets/app-a1b2c3d4.{extension}'
    (source / 'index.html').write_text('<div id="root"></div>', encoding='utf-8')
    (source / relative).write_bytes(original)
    (source / '.vite/manifest.json').write_text(
        json.dumps({'entry': {'file': relative}}), encoding='utf-8',
    )
    output = tmp_path / 'artifact'
    build_artifact(output, source=source)
    validated = validate_react_admin_artifact(output, workspace_root=remote.ROOT)
    app = remote.create_gateway(validated, transport=httpx.MockTransport(lambda _: httpx.Response(401)))
    with TestClient(app, base_url='http://127.0.0.1:5173') as client:
        original_response = client.request(method, f'{mount}/{relative}')
        assert original_response.status_code == 200
        assert original_response.headers['cache-control'] == PRIVATE_IMMUTABLE_CACHE_CONTROL
        assert len(original) == len(replacement)
        (output / relative).write_bytes(replacement)
        rejected = client.request(method, f'{mount}/{relative}')
        assert rejected.status_code == 404
        assert rejected.headers['cache-control'] == 'no-store'
        assert ASSET_ELIGIBILITY_HEADER.lower() not in rejected.headers
        assert replacement not in rejected.content


def test_static_assets_above_threshold_are_gzip_compressed_across_test_and_admin_mounts(tmp_path):
    source = tmp_path / 'gzip_source'
    assets = source / 'assets'
    assets.mkdir(parents=True)
    (source / '.vite').mkdir(parents=True)
    bundle_text = 'export const workbenchLabel = "產後照護排班與帳務管理平台";\n' * 80
    (source / 'index.html').write_text(
        '<div id="root"></div><script type="module" src="/test/assets/index-a1b2c3d4.js"></script>',
        encoding='utf-8',
    )
    (assets / 'index-a1b2c3d4.js').write_text(bundle_text, encoding='utf-8', newline='\n')
    (source / '.vite/manifest.json').write_text(
        json.dumps({'index.html': {'file': 'assets/index-a1b2c3d4.js', 'isEntry': True}}),
        encoding='utf-8',
    )
    output = tmp_path / 'gzip_artifact'
    build_artifact(output, source=source)
    validated = validate_react_admin_artifact(output, workspace_root=remote.ROOT)

    app = remote.create_gateway(validated, transport=httpx.MockTransport(lambda _: httpx.Response(401)))
    raw_size = len(bundle_text.encode('utf-8'))
    with TestClient(app, base_url='http://127.0.0.1:5173') as client:
        for mount in ('/test/assets/index-a1b2c3d4.js', '/admin/assets/index-a1b2c3d4.js'):
            response = client.get(mount, headers={'Accept-Encoding': 'gzip'})
            assert response.status_code == 200
            assert response.headers.get('content-encoding') == 'gzip'
            assert int(response.headers['content-length']) < raw_size
            assert response.text == bundle_text
            assert response.headers['cache-control'] == PRIVATE_IMMUTABLE_CACHE_CONTROL
            assert response.headers[ASSET_ELIGIBILITY_HEADER].startswith(
                f'v1;artifact={validated.artifact_digest};sha256='
            )


def test_api_proxy_strips_internal_asset_eligibility_headers_and_forces_no_store(artifact):
    seen_request_headers = {}

    def api(request):
        if request.url.path == '/api/v1/admin/auth/me':
            return httpx.Response(401)
        seen_request_headers.update(dict(request.headers))
        return httpx.Response(
            200,
            headers={
                'content-type': 'text/javascript',
                'cache-control': PRIVATE_IMMUTABLE_CACHE_CONTROL,
                ASSET_ELIGIBILITY_HEADER: f'v1;artifact={"a" * 64};sha256={"b" * 64}',
            },
            stream=httpx.ByteStream(b'export const secret = 1;\n'),
        )

    app = remote.create_gateway(artifact, transport=httpx.MockTransport(api))
    with TestClient(app, base_url='https://chrishzc.com') as client:
        response = client.get(
            '/test/api/v1/assets/index-a1b2c3d4.js',
            headers={ASSET_ELIGIBILITY_HEADER: f'v1;artifact={"c" * 64};sha256={"d" * 64}'},
        )
    assert ASSET_ELIGIBILITY_HEADER.lower() not in seen_request_headers
    assert response.status_code == 200
    assert response.headers['cache-control'] == 'no-store'
    assert ASSET_ELIGIBILITY_HEADER.lower() not in response.headers


def test_custom_allowed_origins_and_domain_routing(artifact, monkeypatch):
    monkeypatch.setenv('ALLOWED_ORIGINS', 'https://admin.union-example.org.tw,http://localhost:5173')
    app = remote.create_gateway(artifact, transport=httpx.MockTransport(lambda _: httpx.Response(401)))
    with TestClient(app, base_url='https://admin.union-example.org.tw') as client:
        # Custom domain can access /admin/ directly
        admin_resp = client.get('/admin/')
        assert admin_resp.status_code == 200
        assert '<div id="root"></div>' in admin_resp.text
        # Root redirects to /admin/ on custom domain
        root_resp = client.get('/', follow_redirects=False)
        assert root_resp.status_code == 307
        assert root_resp.headers['location'] == '/admin/'
        # Unauthorized foreign host is blocked with 403
        unauthorized = client.get('/admin/', headers={'host': 'unauthorized.invalid'})
        assert unauthorized.status_code == 403


def test_root_setup_preserves_validated_origin_and_replaces_forwarded_input(artifact):
    calls = []
    def api(request):
        if request.url.path.endswith('/auth/me'):
            return httpx.Response(401)
        calls.append(request)
        return httpx.Response(200, headers={'content-type': 'application/json'},
                              stream=httpx.ByteStream(b'{"required":true}'))
    app = remote.create_gateway(artifact, transport=httpx.MockTransport(api))
    with TestClient(app, base_url='https://chrishzc.com') as client:
        response = client.get('/test/api/v1/admin/setup', headers={
            'origin': 'https://chrishzc.com', 'x-forwarded-proto': 'http',
            'x-forwarded-host': 'attacker.example',
        })
        assert response.json() == {'required': True}
    assert calls[0].headers['host'] == 'chrishzc.com'
    assert calls[0].headers['origin'] == 'https://chrishzc.com'
    assert calls[0].headers['x-forwarded-proto'] == 'https'
    assert 'x-forwarded-host' not in calls[0].headers
