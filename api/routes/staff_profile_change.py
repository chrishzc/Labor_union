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
from domains.staff.retirement import StaffLifecycleState
from infrastructure.mysql.line_unit_of_work import open_line_unit_of_work
from infrastructure.redis.staff_profile_change_staging import StaffProfileStagingConflict, StaffProfileStagingUnavailable
from shared_kernel.identities import ActorContext
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


class Submission(StaffLiffRequest):
    submission_id: UUID
    basis: EditBasis
    profile: ContactChanges | None = None
    bank: BankReplacement | None = None
    relations: dict[RelationKey, Annotated[list[RelationEdit], Field(max_length=40)]] | None = None
    transportation: list[Annotated[str, Field(min_length=1, max_length=50)]] | None = Field(default=None, max_length=30)
    matching: MatchingChanges | None = None


class ReviewDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: int = Field(ge=1)
    action: Literal["approve", "reject"]


@router.post(f"{_LIFF}/query")
def query_form(body: StaffLiffRequest):
    staff_id = _bound_staff_id(body)
    with _translate_errors(), staff_profile_change_application() as (application, lifecycle):
        _require_active(lifecycle, staff_id)
        return BaseResponse(data=application.form(staff_id))


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
        return BaseResponse(data=_review(staff_profile_change_staging().get(application_id)))


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
            return BaseResponse(data=_review(item))
        operation = item["operation_id"]
        change = restore_staff_profile_change(item["staff_id"], item["content"])
        try:
            with staff_profile_change_application() as (application, _):
                application.apply(change, UUID(operation), ActorContext(item["actor"]), "")
        except ValueError:
            # Owner validation has failed inside the rolled-back transaction.
            staging.decide(application_id, "conflict", operation_id=operation)
            raise StaffProfileChangeConflict from None
        item = staging.decide(application_id, "complete", operation_id=operation)
        return BaseResponse(data=_review(item))


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


@contextmanager
def _translate_errors():
    try:
        yield
    except (StaffProfileStagingConflict, StaffProfileChangeConflict, StaffProfileMutationConflict,
            StaffBankAccountConflict):
        raise typed_http_error(409, "conflict", "staff_profile_change_stale",
                               "資料或申請已更新，請重新讀取。", "staff-profile-change") from None
    except LookupError:
        raise typed_http_error(404, "not_found", "staff_profile_request_not_found",
                               "找不到此申請，或申請已到期。", "staff-profile-change") from None
    except ValueError:
        raise typed_http_error(422, "validation", "staff_profile_change_invalid",
                               "請核對異動欄位與格式。更換收款帳戶須已有主要帳戶。", "staff-profile-change") from None
    except StaffProfileStagingUnavailable:
        raise typed_http_error(503, "unavailable", "staff_profile_change_unavailable",
                               "暫時無法讀取或保存申請，請稍後重試。", "staff-profile-change", retryable=True) from None
