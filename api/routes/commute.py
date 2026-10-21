"""Admin-only manual Google motorcycle routes and shared usage accounting."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterator, Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, Path, Response
from pydantic import BaseModel, ConfigDict, Field

from api.dependencies.admin_auth import require_system_admin
from api.dependencies.jobs import immutable_admin_job_actor
from api.error_contracts import typed_http_error
from api.schemas.base import BaseResponse
from infrastructure.http.google_routes import GoogleRoutesProvider
from infrastructure.mysql.commute_query_repository import MySqlCommuteRepository
from infrastructure.mysql.mysql_adapter import get_connection
from shared_kernel.durable_job_queue import DurableJobCommand, DurableJobStateConflict
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.jobs.contracts import DurableJobCommandConflict
from subsystems.scheduling.commute_query import COMMAND_TYPE, RECONCILIATION_TYPE, CommuteApplication, CommuteError

router = APIRouter(prefix="/api/v1", tags=["Manual motorcycle commute"])


class ManualQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_key: str = Field(pattern=r"^[a-z0-9][a-z0-9._:-]{0,119}$")


class Reconciliation(ManualQuery):
    month: str = Field(pattern=r"^\d{4}-\d{2}$")
    count: int = Field(strict=True, ge=0)
    through: datetime


class UsageView(BaseModel):
    billing_month: str
    billing_timezone: Literal["America/Los_Angeles"]
    configured: bool
    free_limit: int
    local_requests: int
    estimated_billable: int
    uncertain_requests: int
    free_used: int
    free_remaining: int
    paid_requests: int
    estimated_cost_usd: str
    verified_count: int | None
    verified_through: str | None
    verified_at: str | None


class RouteView(BaseModel):
    case_no: str
    staff_id: int
    event_key: str
    status: Literal["ready", "no_route", "failed", "unknown", "already_requested"]
    distance_meters: int | None
    duration_seconds: float | None
    queried_at: str
    message: str


class HistoryRecordView(BaseModel):
    record_id: str
    queried_at: str
    staff_id: int
    staff_name: str | None
    status: Literal["succeeded", "failed", "unknown"]
    message: str


class HistoryView(BaseModel):
    case_no: str
    records: list[HistoryRecordView] = Field(max_length=50)


def get_commute_application() -> Iterator[CommuteApplication]:
    connection = get_connection()
    try:
        yield CommuteApplication(MySqlCommuteRepository(connection), connection, GoogleRoutesProvider())
    finally:
        connection.close()


def _error(error):
    if isinstance(error, CommuteError):
        return typed_http_error(error.status, "unavailable" if error.status == 503 else "validation" if error.status == 422 else "not_found" if error.status == 404 else "domain_blocked",
            error.code, error.message, "manual-commute")
    return typed_http_error(409, "conflict", "commute_command_conflict", "操作識別已用於其他查詢，請重新讀取畫面。", "manual-commute")


@router.get("/scheduling/commute-usage", response_model=BaseResponse[UsageView])
def get_usage(response: Response, principal: AdminPrincipal = Depends(require_system_admin),
              application: CommuteApplication = Depends(get_commute_application)):
    response.headers["Cache-Control"] = "no-store"
    return BaseResponse(data=application.monthly_usage(datetime.now(timezone.utc)))


@router.post("/orders/{case_no}/caregivers/{staff_id}/commute", response_model=BaseResponse[RouteView])
def query_commute(body: ManualQuery, response: Response,
                  case_no: str = Path(min_length=1, max_length=50), staff_id: int = Path(gt=0),
                  principal: AdminPrincipal = Depends(require_system_admin),
                  application: CommuteApplication = Depends(get_commute_application)):
    response.headers["Cache-Control"] = "no-store"
    actor = immutable_admin_job_actor(principal, "manual-commute")
    command = DurableJobCommand(str(uuid4()), f"commute:{body.event_key}", COMMAND_TYPE, 1,
        dict(case_no=case_no, staff_id=staff_id, event_key=body.event_key), actor, "manual-commute", max_attempts=1)
    try:
        return BaseResponse(data=application.query(command, datetime.now(timezone.utc)))
    except (CommuteError, DurableJobCommandConflict, DurableJobStateConflict) as error:
        raise _error(error) from None


@router.get("/orders/{case_no}/commute-history", response_model=BaseResponse[HistoryView])
def get_commute_history(response: Response, case_no: str = Path(min_length=1, max_length=50),
                        principal: AdminPrincipal = Depends(require_system_admin),
                        application: CommuteApplication = Depends(get_commute_application)):
    response.headers["Cache-Control"] = "no-store"
    return BaseResponse(data=application.history(case_no))


@router.post("/scheduling/commute-usage/reconciliation", response_model=BaseResponse[UsageView])
def reconcile_usage(body: Reconciliation, response: Response,
                    principal: AdminPrincipal = Depends(require_system_admin),
                    application: CommuteApplication = Depends(get_commute_application)):
    response.headers["Cache-Control"] = "no-store"
    if body.through.tzinfo is None:
        raise _error(CommuteError("commute_reconciliation_invalid", "報表統計截止時間必須包含時區。", 422))
    command = DurableJobCommand(str(uuid4()), f"commute-billing:{body.event_key}", RECONCILIATION_TYPE, 1,
        dict(month=body.month, count=body.count, through=body.through.astimezone(timezone.utc).isoformat()),
        immutable_admin_job_actor(principal, "commute-billing"), "commute-billing", max_attempts=1)
    now = datetime.now(timezone.utc)
    try:
        application.reconcile(command, now)
    except (CommuteError, DurableJobCommandConflict) as error:
        raise _error(error) from None
    return BaseResponse(data=application.monthly_usage(now))
