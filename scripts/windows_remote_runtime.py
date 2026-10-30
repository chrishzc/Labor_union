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

from api.middleware.compression import ResponseCompressionMiddleware
from infrastructure.runtime.react_admin_artifact import (
    ReactAdminStaticApplication, validate_react_admin_artifact,
)

ROOT = Path(__file__).resolve().parents[1]
PREFIX = '/test'
PUBLIC_ORIGIN = 'https://chrishzc.com'
_HOP_HEADERS = frozenset({
    'connection', 'keep-alive', 'proxy-authenticate', 'proxy-authorization',
    'te', 'trailer', 'transfer-encoding', 'upgrade',
})


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

    static_app = ResponseCompressionMiddleware(
        ReactAdminStaticApplication(artifact), minimum_size=1024, compresslevel=5,
    )
    app = Starlette(lifespan=lifespan, routes=[
        Route(PREFIX, redirect, methods=['GET', 'HEAD']),
        Route(PREFIX + '/api/{path:path}', proxy,
              methods=['GET', 'HEAD', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS']),
        Mount(PREFIX, app=static_app),
        # The same immutable /test build is available locally at the familiar
        # /admin URL. Its absolute /test assets/API still use this same gateway.
        Route('/admin', lambda _: RedirectResponse('/admin/', status_code=307)),
        Mount('/admin', app=static_app),
    ])

    async def boundary(request: Request, call_next):
        if request.url.hostname not in {'127.0.0.1', 'localhost', 'chrishzc.com'}:
            return PlainTextResponse('Forbidden', status_code=403)
        if (request.url.path == '/admin' or request.url.path.startswith('/admin/')) and (
            request.url.hostname not in {'127.0.0.1', 'localhost'}
        ):
            return PlainTextResponse('Not Found', status_code=404)
        origin = request.headers.get('origin')
        if origin and origin != PUBLIC_ORIGIN and origin not in {
            f'http://127.0.0.1:{request.url.port}', f'http://localhost:{request.url.port}',
        }:
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
    print('Windows remote artifact ready: https://chrishzc.com/test/')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
