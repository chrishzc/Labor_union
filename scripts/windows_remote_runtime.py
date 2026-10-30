"""
File: windows_remote_runtime.py
Description: 提供已驗證 Windows 遠端 React 靜態介面（含 Gzip 壓縮）與同源 API 代理。
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
PREFIX = os.environ.get('WINDOWS_REMOTE_PREFIX', '/test')
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
        and not key.lower().startswith(('x-forwarded-', 'cf-access-'))
    }


def create_gateway(artifact, *, api_port: int = 8000, transport=None) -> Starlette:
    """Compose transport only; the canonical API retains authentication and writers."""
    if not 1 <= api_port <= 65535:
        raise ValueError('Invalid loopback API port')
    api_origin = f'http://127.0.0.1:{api_port}'

    @asynccontextmanager
    async def lifespan(app):
        async with httpx.AsyncClient(
            base_url=api_origin, transport=transport, trust_env=False, timeout=60,
        ) as client:
            # No token means this must reject before accessing business data.
            response = await client.get('/api/v1/admin/auth/me')
            if response.status_code != 401:
                raise RuntimeError('Remote entry requires an authenticated API (expected 401)')
            app.state.api_client = client
            yield

    async def proxy(request: Request):
        path = request.url.path.removeprefix(PREFIX)
        if path == '/api/v1/admin/auth/development-session':
            return PlainTextResponse('Not Found', status_code=404)
        query = request.scope.get('query_string', b'').decode('ascii')
        url = httpx.URL(path, query=query.encode('ascii'))
        client = request.app.state.api_client
        try:
            upstream = client.build_request(
                request.method, url, headers=_forward_headers(request.headers),
                content=request.stream(),
            )
            response = await client.send(upstream, stream=True)
        except httpx.HTTPError:
            return PlainTextResponse('API unavailable', status_code=502)
        headers = _forward_headers(response.headers)
        location = headers.get('location', '')
        if location.startswith('/api/'):
            headers['location'] = PREFIX + location
        headers['cache-control'] = 'no-store'
        return StreamingResponse(
            response.aiter_raw(), status_code=response.status_code, headers=headers,
            background=BackgroundTask(response.aclose),
        )

    async def redirect(request):
        return RedirectResponse(PREFIX + '/', status_code=307)

    async def root_redirect(request: Request):
        if request.url.hostname in {'127.0.0.1', 'localhost', 'chrishzc.com'}:
            return PlainTextResponse('Not Found', status_code=404)
        return RedirectResponse('/admin/', status_code=307)

    static_app = ResponseCompressionMiddleware(
        ReactAdminStaticApplication(artifact), minimum_size=1024, compresslevel=5,
    )
    routes = [
        Route('/', root_redirect, methods=['GET', 'HEAD']),
        Route(PREFIX, redirect, methods=['GET', 'HEAD']),
        Route(PREFIX + '/api/{path:path}', proxy,
              methods=['GET', 'HEAD', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS']),
        Mount(PREFIX, app=static_app),
        # The same immutable /test build is available locally at the familiar
        # /admin URL. Its absolute /test assets/API still use this same gateway.
        Route('/admin', lambda _: RedirectResponse('/admin/', status_code=307)),
        Mount('/admin', app=static_app),
    ]
    app = Starlette(lifespan=lifespan, routes=routes)

    async def boundary(request: Request, call_next):
        allowed_hosts = _configured_allowed_hostnames()
        if request.url.hostname not in allowed_hosts:
            return PlainTextResponse('Forbidden', status_code=403)
        if request.url.hostname == 'chrishzc.com' and not request.url.path.startswith(PREFIX):
            return PlainTextResponse('Not Found', status_code=404)
        if (request.url.path == '/admin' or request.url.path.startswith('/admin/')) and (
            request.url.hostname == 'chrishzc.com'
        ):
            return PlainTextResponse('Not Found', status_code=404)
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
                return PlainTextResponse('Forbidden', status_code=403)
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
