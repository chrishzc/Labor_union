"""LIFF self-service intake and admin decisions for one atomic Staff change."""
from contextlib import contextmanager
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Path
from pydantic import BaseModel, ConfigDict, Field, SecretStr

from api.dependencies.admin_auth import admin_actor_context, require_registry_writer
from api.dependencies.staff_profile_change import staff_profile_change_application, staff_profile_change_staging
from api.error_contracts import typed_http_error
from api.routes.line_staff_self_service import _required_staff, _verified_line_user_id
from api.schemas.base import BaseResponse
from api.schemas.line_staff_self_service import StaffLiffRequest
from api.schemas.staff_matching_preferences import IntegerRangePreferenceInput, IntegerSetPreferenceInput
from api.schemas.staff_web_profile import WebProfilePhotoInput
from domains.staff.retirement import StaffLifecycleState
from domains.staff.web_profile import WebProfileConflict
from infrastructure.file.storage_layout import StorageLayoutError
from infrastructure.runtime.file_transfer_settings import FileSettingsError
from infrastructure.mysql.line_unit_of_work import open_line_unit_of_work
from infrastructure.redis.registration_connection import RegistrationRedisConfigurationError
from infrastructure.redis.staff_profile_change_staging import StaffProfileStagingConflict, StaffProfileStagingUnavailable
from shared_kernel.identities import ActorContext
from subsystems.controlled_files.contracts import ControlledFileStorageError
from subsystems.controlled_files.workflow import ControlledFileWorkflowError
from subsystems.staff.bank_account_workflow import StaffBankAccountConflict
from subsystems.staff.profile_change_approval import StaffProfileChangeConflict, restore_staff_profile_change
from subsystems.staff.profile_workflow import StaffProfileMutationConflict


router = APIRouter(tags=["Staff profile change requests"])
_LIFF = "/api/v1/line/staff-self-service/profile-change"
_ADMIN = "/api/v1/admin/staff-profile-change-requests"


class ContactChanges(BaseModel):
    model_config = ConfigDict(extra="forbid")
    phone: str | None = Field(default=None, max_length=20)
    tel: str | None = Field(default=None, max_length=20)
    tel_ext: str | None = Field(default=None, max_length=10)
    email: str | None = Field(default=None, max_length=100)
    city: str | None = Field(default=None, max_length=50)
    zip_code: str | None = Field(default=None, max_length=10)
    address: str | None = Field(default=None, max_length=255)
    emergency_contact_name: str | None = Field(default=None, max_length=100)
    emergency_contact_phone: str | None = Field(default=None, max_length=30)


class BankReplacement(BaseModel):
    model_config = ConfigDict(extra="forbid")
    bank_code: str = Field(pattern=r"^\d{3}$")
    branch_code: str = Field(pattern=r"^\d{4}$")
    account_no: SecretStr = Field(min_length=6, max_length=20)


class RelationEdit(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value: str = Field(min_length=1, max_length=50)
    detail: str | None = Field(default=None, max_length=100)


RelationKey = Literal["service_regions", "service_periods", "rest_schedule", "baby_types", "holiday_availability"]


class MatchingChanges(BaseModel):
    model_config = ConfigDict(extra="forbid")
    preferred_service_days: IntegerRangePreferenceInput | None = None
    daily_service_hours: IntegerSetPreferenceInput | None = None


class EditBasis(BaseModel):
    model_config = ConfigDict(extra="forbid")
    profile: int = Field(ge=0)
    bank: int = Field(ge=0)
    relations: str = Field(pattern=r"^[0-9a-f]{64}$")
    transportation: str = Field(pattern=r"^[0-9a-f]{64}$")
    matching: int = Field(ge=0)


class SubmissionReference(StaffLiffRequest):
    submission_id: UUID


class Submission(SubmissionReference):
    basis: EditBasis
    profile: ContactChanges | None = None
    bank: BankReplacement | None = None
    relations: dict[RelationKey, Annotated[list[RelationEdit], Field(max_length=40)]] | None = None
    transportation: list[Annotated[str, Field(min_length=1, max_length=50)]] | None = Field(default=None, max_length=30)
    matching: MatchingChanges | None = None
    web_contents: list[WebProfilePhotoInput] = Field(default_factory=list, max_length=50)


class ReviewDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: int = Field(ge=1)
    action: Literal["approve", "reject"]


@router.post(f"{_LIFF}/query")
def query_form(body: StaffLiffRequest):
    staff_id = _bound_staff_id(body)
    with _translate_errors(), staff_profile_change_application() as (application, lifecycle):
        _require_active(lifecycle, staff_id)
        form = application.form(staff_id)
        form["applications"] = [_status(item) for item in staff_profile_change_staging().for_staff(staff_id)]
        return BaseResponse(data=form)


@router.post(f"{_LIFF}/submit")
def submit(body: Submission):
    staff_id = _bound_staff_id(body)
    proposed = body.model_dump(
        include={"profile", "relations", "transportation"}, exclude_none=True, exclude_unset=True,
    )
    if body.profile is not None:
        proposed["profile"] = body.profile.model_dump(exclude_unset=True)
    if body.bank is not None:
        proposed["bank"] = {
            "bank_code": body.bank.bank_code, "branch_code": body.bank.branch_code,
            "account_no": body.bank.account_no.get_secret_value(),
        }
    if body.matching is not None:
        proposed["matching"] = {
            key: getattr(body.matching, key).canonical_value()
            for key in body.matching.model_fields_set if getattr(body.matching, key) is not None
        }
    if body.web_contents:
        proposed["web_contents"] = [photo.model_dump(mode="json") for photo in body.web_contents]
    basis = body.basis.model_dump()
    with _translate_errors(), staff_profile_change_application() as (application, lifecycle):
        _require_active(lifecycle, staff_id)
        staging = staff_profile_change_staging()
        submitted = {"basis": basis, "proposed": proposed}
        prior = staging.find_submission(staff_id, body.submission_id, submitted)
        if prior is not None:
            return BaseResponse(data=_status(prior))
        content, review = application.prepare(staff_id, proposed, basis)
        item = staging.submit(staff_id, body.submission_id, submitted, content, review)
    return BaseResponse(data=_status(item))


@router.get(f"{_ADMIN}/{{application_id}}")
def query_review(application_id: Annotated[int, Path(gt=0)], _=Depends(require_registry_writer)):
    with _translate_errors():
        return BaseResponse(data=_approved_review(staff_profile_change_staging().get(application_id)))


@router.post(f"{_ADMIN}/{{application_id}}/decision")
def decide_review(application_id: Annotated[int, Path(gt=0)], body: ReviewDecision,
                  principal=Depends(require_registry_writer)):
    actor = admin_actor_context(principal)
    with _translate_errors():
        staging = staff_profile_change_staging()
        if body.action == "reject":
            item = staging.decide(application_id, "reject", version=body.version, actor=actor.actor_id)
            return BaseResponse(data=_review(item))
        item = staging.decide(application_id, "claim", version=body.version, actor=actor.actor_id)
        if item["status"] == "approved":
            return BaseResponse(data=_approved_review(item))
        operation = item["operation_id"]
        change = restore_staff_profile_change(item["staff_id"], item["content"])
        try:
            with staff_profile_change_application() as (application, _):
                application.apply(change, UUID(operation), ActorContext(item["actor"]), "")
        except (WebProfileConflict, StaffProfileChangeConflict):
            staging.decide(application_id, "conflict", operation_id=operation)
            raise
        except ControlledFileWorkflowError as error:
            if error.retryable:
                raise
            staging.decide(application_id, "conflict", operation_id=operation)
            raise StaffProfileChangeConflict from None
        except (ValueError, LookupError):
            # Owner validation has failed inside the rolled-back transaction.
            staging.decide(application_id, "conflict", operation_id=operation)
            raise StaffProfileChangeConflict from None
        item = staging.decide(application_id, "complete", operation_id=operation)
        return BaseResponse(data=_approved_review(item))


@router.post(f"{_LIFF}/submission-status")
def query_submission_status(body: SubmissionReference):
    staff_id = _bound_staff_id(body)
    with _translate_errors():
        item = staff_profile_change_staging().status_for_submission(staff_id, body.submission_id)
        return BaseResponse(data=_status(item) if item is not None else {"status": "not_received"})


@router.post(f"{_LIFF}/{{application_id}}/status")
def query_own_status(application_id: Annotated[int, Path(gt=0)], body: StaffLiffRequest):
    staff_id = _bound_staff_id(body)
    with _translate_errors():
        item = staff_profile_change_staging().get(application_id, include_content=False)
        if item["staff_id"] != staff_id:
            raise LookupError("staff_profile_request_not_found")
        return BaseResponse(data=_status(item))


def _bound_staff_id(body):
    identity = _verified_line_user_id(body)
    with open_line_unit_of_work() as unit_of_work:
        subject = _required_staff(unit_of_work.customer_service.staff_subject(identity.value))
    return int(subject["staff_id"])


def _require_active(lifecycle, staff_id):
    if lifecycle.load(staff_id, lock=False).state != StaffLifecycleState.ACTIVE:
        raise typed_http_error(403, "forbidden", "staff_profile_change_inactive",
                               "目前無法以此月嫂身分申請異動。", "staff-profile-change")


def _status(item):
    return {key: item[key] for key in ("id", "status", "version")}


def _review(item):
    return {**_status(item), "staff_id": item["staff_id"], "changes": item.get("review")}


def _approved_review(item):
    result = _review(item)
    if item["status"] == "approved" and item.get("has_web_contents"):
        with staff_profile_change_application() as (application, _):
            receipt = application.web_profile.repository.approval(UUID(item["operation_id"]), item["staff_id"])
            if receipt is None:
                raise StaffProfileStagingUnavailable
            result["publications"] = receipt
    return result


@contextmanager
def _translate_errors():
    try:
        yield
    except (StaffProfileStagingConflict, StaffProfileChangeConflict, StaffProfileMutationConflict,
            StaffBankAccountConflict):
        raise typed_http_error(409, "conflict", "staff_profile_change_stale",
                               "資料或申請已更新，請重新讀取。", "staff-profile-change") from None
    except WebProfileConflict as error:
        messages = {
            "staff_web_template_other_has_multiple": "此項目仍有人員有多張照片。每人保留最多一張後，才能改為「其他」。",
            "staff_web_operation_mismatch": "這次發布的操作編號已用於另一筆內容，請重新讀取後再操作。",
        }
        raise typed_http_error(409, "conflict", str(error),
                               messages.get(str(error), "照片或模板已更新，請重新讀取。"), "staff-web-profile") from None
    except LookupError as error:
        if str(error) == "staff_web_staff_not_found":
            raise typed_http_error(404, "not_found", "staff_web_staff_not_found",
                                   "找不到此月嫂。", "staff-web-profile") from None
        raise typed_http_error(404, "not_found", "staff_profile_request_not_found",
                               "找不到此申請，或申請已到期。", "staff-profile-change") from None
    except ValueError as error:
        code = str(error)
        if code.startswith("staff_web_"):
            messages = {
                "staff_web_expiry_required": "「其他」項目必須填寫有效到期日。",
                "staff_web_other_single_photo": "「其他」類別的每個項目只能提交一張照片。",
                "staff_web_photo_too_large": "照片超過系統的單檔大小上限，請縮小後重新選擇。",
                "staff_web_photo_heif_unsupported": "目前無法上傳 HEIC 或 HEIF，請轉存為 JPEG 或 PNG 再選擇。",
                "staff_web_photo_format_invalid": "系統無法讀取這張照片。請選擇可開啟的單張 JPEG、PNG 或 WebP。",
            }
            message = messages.get(code, "請核對照片、模板項目與日期。")
            raise typed_http_error(422, "validation", code, message, "staff-web-profile") from None
        raise typed_http_error(422, "validation", "staff_profile_change_invalid",
                               "請核對異動欄位與格式。", "staff-profile-change") from None
    except (StaffProfileStagingUnavailable, RegistrationRedisConfigurationError):
        raise typed_http_error(503, "unavailable", "staff_profile_change_unavailable",
                               "暫時無法讀取或保存申請，請稍後重試。", "staff-profile-change", retryable=True) from None
    except ControlledFileWorkflowError as error:
        if error.retryable:
            raise typed_http_error(503, "unavailable", error.code,
                                   "照片服務暫時無法使用，請稍後重試。", "staff-web-profile", retryable=True) from None
        status, kind = (409, "conflict") if error.code in {
            "idempotency_mismatch", "controlled_file_already_registered", "stale_preview", "stale_staging_version",
        } else (422, "validation")
        raise typed_http_error(status, kind, error.code,
                               "照片未通過驗證，請重新選擇檔案。", "staff-web-profile") from None
    except (ControlledFileStorageError, FileSettingsError) as error:
        raise typed_http_error(503, "unavailable", error.code,
                               "照片儲存暫時無法使用，請稍後重試。", "staff-web-profile", retryable=True) from None
    except StorageLayoutError:
        raise typed_http_error(503, "unavailable", "staff_web_storage_layout_unavailable",
                               "照片儲存暫時無法使用，請稍後重試。", "staff-web-profile", retryable=True) from None
