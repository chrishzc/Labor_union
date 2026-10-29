"""
File: nas_apps.py
Description: 組合獨立管理端與公開 LINE 路由應用介面。
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI


@asynccontextmanager
async def _management_lifespan(_):
    from api.dependencies.knowledge_retrieval import ensure_builtin_knowledge_catalog
    ensure_builtin_knowledge_catalog()
    yield


def management_app():
    from api.main import app
    from api.routes.nas_setup import attach_setup
    from api.routes.private_line_media import router as private_line_media_router
    from api.routes.nas_line_operations import private_router as private_line_operations_router
    app.router.lifespan_context = _management_lifespan
    if not getattr(app.state, "private_line_media_attached", False):
        app.include_router(private_line_media_router)
        app.state.private_line_media_attached = True
    if not getattr(app.state, "private_line_operations_attached", False):
        app.include_router(private_line_operations_router)
        app.state.private_line_operations_attached = True
    return attach_setup(app)


@asynccontextmanager
async def _line_lifespan(_):
    from subsystems.line.runtime_cutover import validate_line_api_runtime, validate_line_worker_runtime
    import os
    validate_line_api_runtime(os.environ)
    validate_line_worker_runtime(os.environ)
    yield


def line_app():
    from api.line_webhook_boundary import canonical_line_webhook
    from api.routes import (
        line_identity, line_order_change, line_staff_self_service,
        line_media_proxy, private_operations, line_system_config, client_profile,
    )
    from api.routes.nas_line_operations import public_router as line_operations_router
    app = FastAPI(title="LINE public service", docs_url=None, redoc_url=None, openapi_url=None,
                  lifespan=_line_lifespan)
    app.add_api_route("/webhook/line", canonical_line_webhook, methods=["POST"])
    app.include_router(line_identity.page_router)
    app.include_router(line_order_change.page_router)
    for route in line_system_config.public_router.routes:
        if route.path == "/api/config/liff/runtime":
            app.router.routes.append(route)
    # Website-session identity administration stays on the management entry.
    for route in line_identity.public_router.routes:
        if "/admin/" not in route.path:
            app.router.routes.append(route)
    for router in (line_order_change.router, line_staff_self_service.router,
                   line_media_proxy.router, client_profile.router, line_operations_router):
        app.include_router(router)
    for route in private_operations.router.routes:
        if route.path in {"/internal/v1/runtime/check", "/internal/v1/runtime/line/run-once"}:
            app.router.routes.append(route)

    @app.get("/health", include_in_schema=False)
    def health():
        return {"status": "ok"}
    return app
