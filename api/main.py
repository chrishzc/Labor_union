"""
File: main.py
Description: 掛載 FastAPI 管理、業務、LINE 與 Access Control API router。
"""

import asyncio
import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from api.exception_handlers import CorrelationBoundaryMiddleware, install_typed_error_handlers
from api.middleware.compression import ResponseCompressionMiddleware
from api.middleware.performance import ApiPerformanceMiddleware
from api.routes import (
    admin_audit,
    admin_auth,
    admin_entry_targets,
    account_center,
    anomaly_recovery,
    anomaly_registry,
    import_warning_tracking,
    assignment_plan,
    assignment_schedule_rest_dates,
    beclass_import_review,
    client_beclass_import,
    case_architecture_bootstrap,
    client_deposit_reversal,
    client_receipt_reconciliation,
    client_refund_reversal,
    contract_signing,
    client_payments,
    clients,
    contracts,
    controlled_files,
    data_browser_admin,
    finance_import,
    hcm_import,
    historical_order_adoption,
    staff_historical_workbook,
    finance_reports,
    operations_reports,
    financial_adjustment,
    government_subsidy,
    holidays,
    leave_substitution,
    line_admin,
    line_configurations,
    line_notification_rules,
    staff_service_day_media,
    staff_service_day_logs,
    line_identity,
    line_staff_self_service,
    line_mobile_admin,
    line_media_assets,
    line_identity_management,
    customer_service,
    line_order_groups,
    line_rich_menus,
    line_reviews,
    runtime_health,
    line_system_config,
    line_tasks,
    knowledge_retrieval,
    match_records,
    matches,
    candidate_contact_pool,
    multi_caregiver_case_assignments,
    multi_caregiver_schedule,
    multi_caregiver_schedule_read,
    caregiver_segment_availability,
    caregiver_availability_locks,
    capability_grants,
    order_actual_start,
    order_auto_completion,
    order_cancellation,
    order_contract_completion,
    order_reopen,
    order_schedule_calculation,
    service_date_confirmation,
    matching_schedule_confirmation,
    matching_coordination,
    order_terms,
    orders,
    orders_card_projection,
    orders_stage_projection,
    payroll,
    payroll_rebuild,
    private_operations,
    schedule,
    jobs,
    scheduling_current,
    scheduling_eligibility_collision,
    staff_matching_preferences,
    staff_retirement,
    staff,
    staff_qualification_master,
    staff_availability,
    staff_monthly_schedule,
    staff_payout,
    staff_payments,
    staff_leave_intake,
    staff_leave_management,
    system_status,
)






from api.schemas.base import BaseResponse
from api.dependencies.line_runtime import line_webhook_runtime_mode
from infrastructure.runtime.react_admin_artifact import (
    ReactAdminArtifactRuntime,
    ReactAdminStaticApplication,
    load_react_admin_runtime_from_environment,
)
from line.line_bot import router as line_router
from subsystems.access.authentication_session import record_admin_audit


PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")
REACT_ADMIN_RUNTIME = load_react_admin_runtime_from_environment(
    workspace_root=PROJECT_ROOT
)


def mount_react_admin_static(
    application: FastAPI,
    runtime: ReactAdminArtifactRuntime | None,
) -> bool:
    """Mount the validated active artifact and its private health provider once."""
    if runtime is None:
        return False
    application.state.react_admin_artifact_health = runtime.health_attestation
    application.mount(
        "/admin",
        ReactAdminStaticApplication(runtime.active),
        name="react-admin",
    )
    return True


def _allowed_origins() -> list[str]:
    configured = os.getenv("ALLOWED_ORIGINS", "").strip()
    if configured:
        return [origin.strip() for origin in configured.split(",") if origin.strip()]
    return ["http://localhost:8501", "http://127.0.0.1:8501"]


@asynccontextmanager
async def lifespan(_: FastAPI):
    line_webhook_runtime_mode()
    yield


app = FastAPI(
    title="Labor Union Webhook & API",
    description="LINE, LIFF and labor union administration API",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins(),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=[
        "Accept",
        "Authorization",
        "Content-Type",
        "If-Match",
        "If-None-Match",
        "Idempotency-Key",
        "X-Preview-Fingerprint",
        "X-Correlation-ID",
    ],
    expose_headers=["X-Correlation-ID", "Retry-After", "WWW-Authenticate"],
)
app.add_middleware(
    ResponseCompressionMiddleware,
    minimum_size=1024,
    compresslevel=5,
)
app.add_middleware(ApiPerformanceMiddleware)
app.add_middleware(CorrelationBoundaryMiddleware)
install_typed_error_handlers(app)


@app.get("/static/bind.html", include_in_schema=False)
def redirect_retired_static_bind(request: Request) -> RedirectResponse:
    """Keep old bookmarks usable without exposing the retired direct-writer page."""
    query = request.url.query
    target = f"/line-identity?{query}" if query else "/line-identity"
    return RedirectResponse(target, status_code=307)


app.mount("/static", StaticFiles(directory="line/static"), name="static")

# LINE/LIFF/webhook endpoints are a child router of this central application.
app.include_router(line_router)
app.include_router(admin_auth.router)
app.include_router(account_center.router)
app.include_router(admin_audit.router)
app.include_router(capability_grants.router)
app.include_router(line_admin.router)
app.include_router(line_configurations.router)
app.include_router(line_notification_rules.router)
app.include_router(staff_service_day_media.router)
app.include_router(staff_service_day_logs.router)
app.include_router(line_tasks.router)
app.include_router(line_rich_menus.router)
app.include_router(line_media_assets.router)
app.include_router(line_reviews.router)
app.include_router(line_identity.public_router)
app.include_router(line_identity.review_router)
app.include_router(line_identity.page_router)
app.include_router(line_order_groups.router)
app.include_router(knowledge_retrieval.router)
app.include_router(line_staff_self_service.router)
app.include_router(staff_leave_intake.router)
app.include_router(staff_leave_management.router)
app.include_router(line_mobile_admin.router)
app.include_router(line_mobile_admin.page_router)
app.include_router(customer_service.router)
app.include_router(customer_service.escalation_router)
app.include_router(line_identity_management.router)

# Existing administration API routers.
app.include_router(orders.router)
app.include_router(orders_card_projection.router)
app.include_router(orders_stage_projection.router)
app.include_router(case_architecture_bootstrap.router)
app.include_router(order_terms.router)
app.include_router(order_contract_completion.router)
app.include_router(contract_signing.router)
app.include_router(order_actual_start.router)
app.include_router(order_auto_completion.router)
app.include_router(order_cancellation.router)
app.include_router(order_reopen.router)
app.include_router(assignment_plan.router)
app.include_router(leave_substitution.router)
app.include_router(order_schedule_calculation.router)
app.include_router(service_date_confirmation.router)
app.include_router(matching_schedule_confirmation.router)
app.include_router(matching_coordination.router)
app.include_router(assignment_schedule_rest_dates.router)


app.include_router(matches.router)
app.include_router(candidate_contact_pool.router)
app.include_router(match_records.router)

app.include_router(schedule.router)
app.include_router(jobs.router)
app.include_router(scheduling_current.router)
app.include_router(scheduling_eligibility_collision.router)
app.include_router(staff_matching_preferences.router)
app.include_router(multi_caregiver_case_assignments.router)
app.include_router(multi_caregiver_case_assignments.staff_router)
app.include_router(multi_caregiver_schedule.router)
app.include_router(multi_caregiver_schedule_read.router)
app.include_router(caregiver_segment_availability.router)
app.include_router(caregiver_availability_locks.router)
app.include_router(clients.router)
app.include_router(staff.router)
app.include_router(staff_qualification_master.router)
app.include_router(staff_retirement.router)
app.include_router(staff_availability.router)
app.include_router(staff_monthly_schedule.router)

app.include_router(holidays.router)
app.include_router(line_system_config.router)
app.include_router(line_system_config.public_router)
app.include_router(client_payments.router)
app.include_router(client_deposit_reversal.router)
app.include_router(client_receipt_reconciliation.router)
app.include_router(client_refund_reversal.router)
app.include_router(financial_adjustment.router)
app.include_router(staff_payout.router)
app.include_router(payroll.router)
app.include_router(payroll_rebuild.router)
app.include_router(staff_payments.router)
app.include_router(contracts.router)
app.include_router(controlled_files.router)
app.include_router(finance_import.router)
app.include_router(hcm_import.router)
app.include_router(client_beclass_import.router)
app.include_router(historical_order_adoption.router)
app.include_router(staff_historical_workbook.router)
app.include_router(beclass_import_review.router)
app.include_router(finance_reports.router)
app.include_router(operations_reports.router)
app.include_router(government_subsidy.router)
app.include_router(anomaly_registry.router)
app.include_router(anomaly_recovery.router)
app.include_router(import_warning_tracking.router)
app.include_router(data_browser_admin.router)
app.include_router(system_status.router)
app.include_router(runtime_health.router)
app.include_router(private_operations.router)
app.include_router(admin_entry_targets.router)



@app.middleware("http")
async def audit_authenticated_mutations(request: Request, call_next):
    """Persist authenticated management changes without storing request secrets."""
    response = await call_next(request)
    principal = getattr(request.state, "admin_principal", None)
    is_preview = request.url.path.endswith("/preview")
    is_entry_target_apply = (
        request.method == "POST" and request.url.path == "/api/v1/admin/entry-targets/apply"
    )
    uses_control_plane_receipt = is_entry_target_apply and (
        getattr(request.state, "audit_persistence", None) == "admin_entry_target_control_plane"
        or response.status_code >= 400
    )
    if (
        principal
        and request.method in {"POST", "PUT", "PATCH", "DELETE"}
        and not is_preview
        and not uses_control_plane_receipt
    ):
        try:
            await asyncio.to_thread(
                record_admin_audit,
                principal=principal,
                action=getattr(request.state, "audit_action", "api.mutation"),
                request_path=request.url.path,
                http_method=request.method,
                result_status=response.status_code,
                ip_address=request.client.host if request.client else None,
                resource_type=getattr(request.state, "audit_resource_type", None),
                resource_id=getattr(request.state, "audit_resource_id", None),
                details=getattr(request.state, "audit_details", None),
            )
        except Exception:
            print("[Admin Audit] Failed to record request")
    return response


@app.get("/health", response_model=BaseResponse[dict], tags=["Health"])
def api_health_check():
    return BaseResponse(
        data={"status": "healthy", "service": "Labor Union API"},
        message="API Server is running normally",
    )


mount_react_admin_static(app, REACT_ADMIN_RUNTIME)
