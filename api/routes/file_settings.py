"""Root-only transfer settings; the current storage path is a read-only projection."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field

from api.dependencies.admin_auth import require_persisted_admin
from api.error_contracts import typed_http_error
from api.schemas.base import BaseResponse
from infrastructure.runtime.file_transfer_settings import FileSettingsError, file_settings_view, save_file_settings
from subsystems.access.authentication_session import AdminPrincipal

router = APIRouter(prefix="/api/v1/storage/settings", tags=["File Settings"])


def require_file_settings_admin(principal: AdminPrincipal = Depends(require_persisted_admin)):
    if principal.id is None or not principal.is_root:
        raise typed_http_error(403, "forbidden", "file_settings_forbidden", "僅 root 管理員可調整檔案設定。", "file-settings")
    return principal


class FileSettingsView(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: int
    photo_max_bytes: int
    resume_max_bytes: int
    timeout_seconds: int
    container_root: str | None


class SaveFileSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    expected_version: int = Field(ge=0)
    photo_max_bytes: int = Field(gt=0, le=9007199254740991)
    resume_max_bytes: int = Field(gt=0, le=9007199254740991)
    timeout_seconds: int = Field(ge=0, le=2147483)


def _call(operation):
    try:
        return BaseResponse[FileSettingsView](data=FileSettingsView(**operation()))
    except FileSettingsError as error:
        conflict = error.code in {"file_settings_stale", "file_settings_busy"}
        raise typed_http_error(409 if conflict else 503, "conflict" if conflict else "unavailable", error.code,
            "設定已變更或正在儲存，請重新讀取後確認。" if conflict else "設定目前無法讀寫；未確認儲存結果，請重新讀取。",
            "file-settings", retryable=False) from None
    except ValueError:
        raise typed_http_error(422, "validation", "file_settings_invalid", "請填寫有效的檔案容量及等待秒數。", "file-settings") from None


@router.get("", response_model=BaseResponse[FileSettingsView])
def read_settings(principal=Depends(require_file_settings_admin)):
    return _call(file_settings_view)


@router.put("", response_model=BaseResponse[FileSettingsView])
def update_settings(body: SaveFileSettings, principal=Depends(require_file_settings_admin)):
    return _call(lambda: save_file_settings(**body.model_dump()))
