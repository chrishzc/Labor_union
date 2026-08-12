"""
================================================================================
檔案名稱: api/main.py
功能說明: FastAPI 主程序，掛載 LINE、LIFF、管理介面與其他後端 API；LINE Worker 由獨立程序管理
================================================================================
"""

import asyncio
import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from api.middleware.compression import ResponseCompressionMiddleware
from api.middleware.performance import ApiPerformanceMiddleware
from api.routes import (
    admin_audit,
    admin_auth,
    anomaly_recovery,
    anomaly_registry,
    assignment_plan,
    assignment_schedule_rest_dates,
    beclass_import_review,
    case_architecture_bootstrap,
    client_deposit_reversal,
    client_receipt_reconciliation,
    client_refund_reversal,
    contract_signing,
    client_payments,
    clients,
    contracts,
    data_browser_admin,
    finance_import,
    finance_reports,
    financial_adjustment,
    government_subsidy,
    holidays,
    leave_substitution,
    line_admin,
    line_configurations,
    line_identity,
    line_staff_self_service,
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
    matches,`r`n    candidate_contact_pool,
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
    order_terms,
    orders,
    payroll,
    payroll_rebuild,
    schedule,
    jobs,
    scheduling_current,
    staff,
    staff_monthly_schedule,
    staff_payout,
    staff_payments,
    system_status,
)






from api.schemas.base import BaseResponse
from api.dependencies.line_runtime import line_webhook_runtime_mode
from line.line_bot import router as line_router
from subsystems.access.authentication_session import record_admin_audit
from subsystems.access.security_audit_retention_worker import (
    start_security_audit_retention_worker,
    stop_security_audit_retention_worker,
)
from subsystems.anomalies.outbox_worker import (
    start_architecture_outbox_worker,
    stop_architecture_outbox_worker,
)


PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")


def _allowed_origins() -> list[str]:
    configured = os.getenv("ALLOWED_ORIGINS", "").strip()
    if configured:
        return [origin.strip() for origin in configured.split(",") if origin.strip()]
    return ["http://localhost:8501", "http://127.0.0.1:8501"]


def _background_workers_enabled() -> bool:
    read_only = os.getenv("PRESERVE_DATA_REHEARSAL_READ_ONLY", "false")
    return read_only.strip().lower() != "true"


@asynccontextmanager
async def lifespan(_: FastAPI):
    line_webhook_runtime_mode()
    if not _background_workers_enabled():
        yield
        return
    architecture_worker_task = start_architecture_outbox_worker()
    security_audit_worker_task = start_security_audit_retention_worker()
    try:
        yield
    finally:
        await stop_security_audit_retention_worker(security_audit_worker_task)
        await stop_architecture_outbox_worker(architecture_worker_task)


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
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(
    ResponseCompressionMiddleware,
    minimum_size=1024,
    compresslevel=5,
)
app.add_middleware(ApiPerformanceMiddleware)

app.mount("/static", StaticFiles(directory="line/static"), name="static")

# LINE/LIFF/webhook endpoints are a child router of this central application.
app.include_router(line_router)
app.include_router(admin_auth.router)
app.include_router(admin_audit.router)
app.include_router(capability_grants.router)
app.include_router(line_admin.router)
app.include_router(line_configurations.router)
app.include_router(line_tasks.router)
app.include_router(line_rich_menus.router)
app.include_router(line_reviews.router)
app.include_router(line_identity.public_router)
app.include_router(line_identity.review_router)
app.include_router(line_identity.page_router)
app.include_router(line_order_groups.router)
app.include_router(knowledge_retrieval.router)
app.include_router(line_staff_self_service.router)
app.include_router(customer_service.router)
app.include_router(line_identity_management.router)

# Existing administration API routers.
app.include_router(orders.router)
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
app.include_router(assignment_schedule_rest_dates.router)


app.include_router(matches.router)`r`napp.include_router(candidate_contact_pool.router)
app.include_router(match_records.router)

app.include_router(schedule.router)
app.include_router(jobs.router)
app.include_router(scheduling_current.router)
app.include_router(multi_caregiver_case_assignments.router)
app.include_router(multi_caregiver_case_assignments.staff_router)
app.include_router(multi_caregiver_schedule.router)
app.include_router(multi_caregiver_schedule_read.router)
app.include_router(caregiver_segment_availability.router)
app.include_router(caregiver_availability_locks.router)
app.include_router(clients.router)
app.include_router(staff.router)
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
app.include_router(finance_import.router)
app.include_router(beclass_import_review.router)
app.include_router(finance_reports.router)
app.include_router(government_subsidy.router)
app.include_router(anomaly_registry.router)
app.include_router(anomaly_recovery.router)
app.include_router(data_browser_admin.router)
app.include_router(system_status.router)
app.include_router(runtime_health.router)



@app.middleware("http")
async def audit_authenticated_mutations(request: Request, call_next):
    """Persist authenticated management changes without storing request secrets."""
    response = await call_next(request)
    principal = getattr(request.state, "admin_principal", None)
    is_preview = request.url.path.endswith("/preview")
    if principal and request.method in {"POST", "PUT", "PATCH", "DELETE"} and not is_preview:
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
        except Exception as exc:
            print(f"[Admin Audit] Failed to record request: {exc}")
    return response


@app.get("/health", response_model=BaseResponse[dict], tags=["Health"])
def api_health_check():
    return BaseResponse(
        data={"status": "healthy", "service": "Labor Union API"},
        message="API Server is running normally",
    )
