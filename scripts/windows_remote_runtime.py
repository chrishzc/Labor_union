"""
File: windows_remote_runtime.py
Description: 提供已驗證 Windows 遠端 React 靜態介面（含 Gzip 與靜態快取資格透傳）及同源 API 代理。
"""
from __future__ import annotations

import argparse
from contextlib import asynccontextmanager
import os
from pathlib import Path
import uuid

import httpx
from starlette.applications import Starlette
from starlette.background import BackgroundTask
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import PlainTextResponse, RedirectResponse, StreamingResponse
from starlette.routing import Mount, Route

try:
    from api.middleware.compression import ResponseCompressionMiddleware
except ImportError:
    from starlette.middleware.gzip import GZipMiddleware as ResponseCompressionMiddleware
from infrastructure.runtime.react_admin_artifact import (
    ReactAdminStaticApplication, validate_react_admin_artifact,
)

ROOT = Path(__file__).resolve().parents[1]
LEGACY_PREFIX = '/test'
ADMIN_PREFIX = '/admin'
PREFIX = os.environ.get('WINDOWS_REMOTE_PREFIX') or LEGACY_PREFIX
if PREFIX not in {LEGACY_PREFIX, ADMIN_PREFIX}:
    raise ValueError('WINDOWS_REMOTE_PREFIX must be /test or /admin')
_STAFF_WEB_PROFILE_PATH = '/line-staff-web-profile'
_HOP_HEADERS = frozenset({
    'connection', 'keep-alive', 'proxy-authenticate', 'proxy-authorization',
    'te', 'trailer', 'transfer-encoding', 'upgrade',
})


def _read_env_file() -> dict[str, str]:
    env_file = ROOT / '.env'
    if not env_file.is_file():
        return {}
    results = {}
    try:
        for line in env_file.read_text(encoding='utf-8').splitlines():
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            key, _, val = line.partition('=')
            key = key.strip()
            val = val.strip().strip("'\"")
            results[key] = val
    except Exception:
        pass
    return results


def _configured_public_origins() -> set[str]:
    origins = set()
    file_env = _read_env_file()
    env_public = os.environ.get('PUBLIC_ORIGIN') or file_env.get('PUBLIC_ORIGIN', '')
    if env_public.strip():
        origins.add(env_public.strip().rstrip('/'))
    env_allowed = os.environ.get('ALLOWED_ORIGINS') or file_env.get('ALLOWED_ORIGINS', '')
    if env_allowed.strip():
        for item in env_allowed.split(','):
            item = item.strip().rstrip('/')
            if item:
                origins.add(item)
    origins.add('https://chrishzc.com')
    return origins


def _configured_allowed_hostnames() -> set[str]:
    hostnames = {'127.0.0.1', 'localhost', 'chrishzc.com'}
    for origin in _configured_public_origins():
        try:
            parsed = httpx.URL(origin)
            if parsed.host:
                hostnames.add(parsed.host.lower())
        except Exception:
            pass
    file_env = _read_env_file()
    line_url = os.environ.get('LINE_PUBLIC_BASE_URL') or file_env.get('LINE_PUBLIC_BASE_URL', '')
    if line_url.strip():
        try:
            parsed = httpx.URL(line_url.strip())
            if parsed.host:
                hostnames.add(parsed.host.lower())
        except Exception:
            pass
    return hostnames


def _forward_headers(headers):
    excluded = _HOP_HEADERS | {
        value.strip().lower() for value in headers.get('connection', '').split(',')
    }
    return {
        key: value for key, value in headers.items()
        if key.lower() not in excluded | {'host', 'forwarded', 'content-length'}
        and not key.lower().startswith(('x-forwarded-', 'cf-access-', 'x-react-admin-'))
    }


def _proxy_timeout() -> httpx.Timeout:
    raw = os.environ.get('WINDOWS_REMOTE_PROXY_TIMEOUT_SECONDS', '').strip()
    try:
        seconds = max(10.0, float(raw)) if raw else 120.0
    except ValueError:
        seconds = 120.0
    return httpx.Timeout(connect=10.0, read=seconds, write=seconds, pool=10.0)


def create_gateway(artifact, *, api_port: int = 8000, transport=None, prefix: str = PREFIX) -> Starlette:
    """Compose transport only; the canonical API retains authentication and writers."""
    if not 1 <= api_port <= 65535:
        raise ValueError('Invalid loopback API port')
    if prefix not in {LEGACY_PREFIX, ADMIN_PREFIX}:
        raise ValueError('Windows management path must be /test or /admin')
    api_origin = f'http://127.0.0.1:{api_port}'

    @asynccontextmanager
    async def lifespan(app):
        async with httpx.AsyncClient(
            base_url=api_origin, transport=transport, trust_env=False, timeout=_proxy_timeout(),
        ) as client:
            # No token means this must reject before accessing business data.
            response = await client.get('/api/v1/admin/auth/me')
            if response.status_code != 401:
                raise RuntimeError('Remote entry requires an authenticated API (expected 401)')
            app.state.api_client = client
            yield

    async def proxy(request: Request) -> PlainTextResponse | StreamingResponse:
        incoming_prefix = '/' + request.url.path.split('/', 2)[1]
        path = request.url.path.removeprefix(incoming_prefix)
        if path == '/api/v1/admin/auth/development-session':
            return PlainTextResponse('Not Found', status_code=404, headers={'Cache-Control': 'no-store'})
        query = request.scope.get('query_string', b'').decode('ascii')
        url = httpx.URL(path, query=query.encode('ascii'))
        client = request.app.state.api_client
        upstream_headers = _forward_headers(request.headers)
        if path == '/api/v1/admin/setup':
            # The gateway already validated Host and Origin. Replace forwarded
            # input with this endpoint's facts for the loopback API's origin check.
            upstream_headers['host'] = request.headers['host']
            upstream_headers['x-forwarded-proto'] = request.url.scheme
        # The canonical profile page declares GET only.
        profile_head = request.method == 'HEAD' and path == _STAFF_WEB_PROFILE_PATH
        try:
            upstream = client.build_request(
                'GET' if profile_head else request.method, url, headers=upstream_headers,
                content=request.stream(),
            )
            response = await client.send(upstream, stream=True)
        except httpx.HTTPError:
            return PlainTextResponse('API unavailable', status_code=502, headers={'Cache-Control': 'no-store'})
        headers = _forward_headers(response.headers)
        location = headers.get('location', '')
        if location.startswith('/api/'):
            headers['location'] = incoming_prefix + location
        headers['cache-control'] = 'no-store'
        return StreamingResponse(
            iter(()) if profile_head else response.aiter_raw(),
            status_code=response.status_code, headers=headers,
            background=BackgroundTask(response.aclose),
        )

    async def redirect(request):
        target = prefix + '/'
        if request.url.query:
            target += '?' + request.url.query
        return RedirectResponse(target, status_code=307, headers={'Cache-Control': 'no-store'})

    async def root_redirect(request: Request):
        if request.url.hostname in {'127.0.0.1', 'localhost', 'chrishzc.com'}:
            return PlainTextResponse('Not Found', status_code=404, headers={'Cache-Control': 'no-store'})
        return RedirectResponse('/admin/', status_code=307, headers={'Cache-Control': 'no-store'})

    async def local_staff_web_profile_redirect(request: Request) -> RedirectResponse:
        target = prefix + _STAFF_WEB_PROFILE_PATH
        if request.url.query:
            target += '?' + request.url.query
        return RedirectResponse(target, status_code=307, headers={'Cache-Control': 'no-store'})

    static_app = ResponseCompressionMiddleware(
        ReactAdminStaticApplication(artifact), minimum_size=1024, compresslevel=5,
    )
    routes = [
        Route('/', root_redirect, methods=['GET', 'HEAD']),
        Route(_STAFF_WEB_PROFILE_PATH, local_staff_web_profile_redirect, methods=['GET', 'HEAD']),
    ]
    api_methods = ['GET', 'HEAD', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS']
    if prefix == ADMIN_PREFIX:
        routes.extend([
            Route(LEGACY_PREFIX, redirect, methods=['GET', 'HEAD']),
            Route(LEGACY_PREFIX + '/', redirect, methods=['GET', 'HEAD']),
            Route(LEGACY_PREFIX + _STAFF_WEB_PROFILE_PATH, proxy, methods=['GET', 'HEAD']),
            Route(LEGACY_PREFIX + '/static/staff_web_profile.js', proxy, methods=['GET', 'HEAD']),
            Route(LEGACY_PREFIX + '/api/{path:path}', proxy, methods=api_methods),
        ])
    routes.extend([
        Route(prefix, redirect, methods=['GET', 'HEAD']),
        Route(prefix + _STAFF_WEB_PROFILE_PATH, proxy, methods=['GET', 'HEAD']),
        Route(prefix + '/static/staff_web_profile.js', proxy, methods=['GET', 'HEAD']),
        Route(prefix + '/api/{path:path}', proxy, methods=api_methods),
        Mount(prefix, app=static_app),
    ])
    if prefix == LEGACY_PREFIX:
        # Preserve the local shortcut while the legacy artifact is active.
        routes.extend([
            Route(ADMIN_PREFIX, lambda _: RedirectResponse(ADMIN_PREFIX + '/', status_code=307,
                  headers={'Cache-Control': 'no-store'}), methods=['GET', 'HEAD']),
            Mount(ADMIN_PREFIX, app=static_app),
        ])
    app = Starlette(lifespan=lifespan, routes=routes)

    async def boundary(request: Request, call_next):
        allowed_hosts = _configured_allowed_hostnames()
        if request.url.hostname not in allowed_hosts:
            return PlainTextResponse('Forbidden', status_code=403, headers={'Cache-Control': 'no-store'})
        if request.url.hostname == 'chrishzc.com':
            public_prefixes = (ADMIN_PREFIX, LEGACY_PREFIX) if prefix == ADMIN_PREFIX else (LEGACY_PREFIX,)
            if not any(request.url.path == item or request.url.path.startswith(item + '/')
                       for item in public_prefixes):
                return PlainTextResponse('Not Found', status_code=404, headers={'Cache-Control': 'no-store'})
        if request.url.path == _STAFF_WEB_PROFILE_PATH and request.url.hostname not in {'127.0.0.1', 'localhost'}:
            return PlainTextResponse('Not Found', status_code=404, headers={'Cache-Control': 'no-store'})
        origin = request.headers.get('origin')
        if origin:
            allowed_origins = _configured_public_origins()
            port = request.url.port
            loopbacks = {
                f'http://127.0.0.1:{port}',
                f'http://localhost:{port}',
                'http://127.0.0.1:5173',
                'http://localhost:5173',
            }
            if origin not in allowed_origins and origin not in loopbacks:
                return PlainTextResponse('Forbidden', status_code=403, headers={'Cache-Control': 'no-store'})
        return await call_next(request)

    app.add_middleware(BaseHTTPMiddleware, dispatch=boundary)
    return app


def create_app() -> Starlette:
    if (os.environ.get('ACCESS_CONTROL_PROFILE') != 'production'
            or os.environ.get('ENABLE_ADMIN_AUTH') != 'true'):
        raise RuntimeError('Remote entry refuses development authentication profiles')
    artifact = validate_react_admin_artifact(
        Path(os.environ['WINDOWS_REMOTE_ARTIFACT_DIR']), workspace_root=ROOT,
    )
    return create_gateway(artifact, api_port=int(os.environ.get('WINDOWS_REMOTE_API_PORT', '8000')))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepare', action='store_true', required=True)
    parser.add_argument('--output-file', type=Path, required=True)
    args = parser.parse_args()
    # Build in a fresh ignored directory; existing artifacts and .env stay intact.
    os.environ['VITE_PUBLIC_PATH_PREFIX'] = PREFIX
    os.environ['VITE_ACCESS_CONTROL_PROFILE'] = 'production'
    os.environ['WINDOWS_REMOTE_BUILD'] = '1'
    from scripts.build_react_admin_artifact import build_artifact
    output = ROOT / 'scratch' / 'windows-remote' / ('artifact-' + uuid.uuid4().hex)
    build_artifact(output, run_frontend_build=True)
    args.output_file.write_text(str(output), encoding='utf-8')
    custom_origins = [o for o in _configured_public_origins() if 'chrishzc' not in o]
    display_origin = custom_origins[0] if custom_origins else 'https://chrishzc.com'
    print(f'Windows remote artifact ready: {display_origin.rstrip("/")}{PREFIX}/')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
