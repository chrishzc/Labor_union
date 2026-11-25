"""
File: nas_apps.py
Description: 組合獨立管理端與公開 LINE 路由應用介面，支援壓縮與連線池釋放。
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from api.middleware.compression import ResponseCompressionMiddleware


@asynccontextmanager
async def _management_lifespan(_):
    from api.dependencies.admin_auth import ensure_development_line_configuration
    from api.dependencies.knowledge_retrieval import ensure_builtin_knowledge_catalog
    from infrastructure.mysql.mysql_adapter import close_connection_pools
    from infrastructure.mysql.nas_mutations import ensure_nas_procedures
    from infrastructure.mysql.mysql_adapter import get_connection
    try:
        _conn = get_connection()
        try:
            ensure_nas_procedures(_conn)
        finally:
            _conn.close()
    except Exception:
        pass
    ensure_builtin_knowledge_catalog()
    ensure_development_line_configuration()
    from api.dependencies.registration_runtime import registration_maintenance_runtime
    try:
        with registration_maintenance_runtime():
            yield
    finally:
        close_connection_pools()


def management_app():
    from api.main import app
    app.router.lifespan_context = _management_lifespan
    return app


@asynccontextmanager
async def _line_lifespan(_):
    from subsystems.line.runtime_cutover import validate_line_api_runtime, validate_line_worker_runtime
    from infrastructure.mysql.mysql_adapter import close_connection_pools
    import os
    validate_line_api_runtime(os.environ)
    validate_line_worker_runtime(os.environ)
    try:
        yield
    finally:
        close_connection_pools()


def line_app():
    from fastapi import APIRouter
    from api.line_webhook_boundary import canonical_line_webhook
    from api.routes import (
        line_candidate_contact, line_deposit_payment, line_feedback, line_identity,
        line_mobile_admin, line_mobile_staff_leave_coordination, line_order_change,
        line_service_help, line_staff_self_service, line_system_config,
        line_table_images, matches, notification_task_actions, private_operations,
        staff_leave_intake,
    )
    app = FastAPI(title="LINE public service", docs_url=None, redoc_url=None, openapi_url=None,
                  lifespan=_line_lifespan)
    app.include_router(line_table_images.router)
    app.add_middleware(ResponseCompressionMiddleware, minimum_size=1024, compresslevel=5)
    app.add_api_route("/webhook/line", canonical_line_webhook, methods=["POST"])
    app.include_router(line_identity.page_router)
    for route in line_system_config.public_router.routes:
        if route.path == "/api/config/liff/runtime":
            app.router.routes.append(route)
    # Website-session identity administration stays on the management entry.
    for route in line_identity.public_router.routes:
        if "/admin/" not in route.path:
            app.router.routes.append(route)
    postponement_prefix = "/api/v1/line/staff-self-service/leave-results"
    postponement_paths = {f"{postponement_prefix}/{step}" for step in ("cases", "preview", "propose")}
    postponement_operations = APIRouter()
    postponement_operations.routes.extend(
        route for route in staff_leave_intake.router.routes if route.path in postponement_paths
    )
    app.add_api_route(
        f"{postponement_prefix}/submit", staff_leave_intake.submit_leave_result,
        methods=["POST"], include_in_schema=False,
    )
    for router in (
        line_order_change.router,
        line_staff_self_service.router,
        line_deposit_payment.router,
        line_service_help.public_router,
        line_feedback.router,
        line_mobile_admin.router,
        line_mobile_staff_leave_coordination.router,
        notification_task_actions.mobile_router,
        matches.resume_router,
        postponement_operations,
        line_candidate_contact.page_router,
        line_deposit_payment.page_router,
        line_service_help.page_router,
        line_mobile_admin.page_router,
        matches.resume_page_router,
    ):
        app.include_router(router)
    for route in private_operations.router.routes:
        if route.path in {"/internal/v1/runtime/check", "/internal/v1/runtime/line/run-once"}:
            app.router.routes.append(route)

    @app.get("/health", include_in_schema=False)
    def health():
        return {"status": "ok"}
    return app
