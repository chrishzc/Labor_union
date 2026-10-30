"""Authenticated transport for the local Windows NAS backup schedule only."""
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field

from api.dependencies.admin_auth import require_admin, require_persisted_admin
from api.error_contracts import typed_http_error
from api.schemas.base import BaseResponse
from scripts.nas_database_maintenance import MaintenanceBlocked, ScheduleConflict, backup_status, configure_daily_backup
from subsystems.access.authentication_session import AdminPrincipal

router = APIRouter(prefix="/api/v1/system/database-backup", tags=["Database Backup"])


class LastBackupResult(BaseModel):
    status: Literal["passed", "failed"]
    time: str
    message: str | None = None


class BackupStatus(BaseModel):
    configured: bool
    enabled: bool
    time: str
    version: int
    last_backup: str | None
    last_result: LastBackupResult | None


class SaveBackupSchedule(BaseModel):
    model_config = ConfigDict(extra="forbid")
    time: str = Field(pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    expected_version: int = Field(ge=0)


@router.get("", response_model=BaseResponse[BackupStatus])
def read_backup_status(_: AdminPrincipal = Depends(require_admin)):
    return BaseResponse(data=BackupStatus(**backup_status()))


@router.put("/schedule", response_model=BaseResponse[BackupStatus])
def save_backup_schedule(body: SaveBackupSchedule, _: AdminPrincipal = Depends(require_persisted_admin)):
    try:
        configure_daily_backup(body.time, expected_version=body.expected_version)
    except ScheduleConflict as error:
        raise typed_http_error(409, "conflict", "backup_schedule_stale", str(error), "nas-backup-schedule") from None
    except MaintenanceBlocked as error:
        raise typed_http_error(409, "domain_blocked", "backup_schedule_unavailable", str(error), "nas-backup-schedule") from None
    except Exception:
        raise typed_http_error(503, "unavailable", "backup_schedule_unavailable", "備份時間暫時無法儲存，請通知維護人員。", "nas-backup-schedule") from None
    return BaseResponse(data=BackupStatus(**backup_status()))
