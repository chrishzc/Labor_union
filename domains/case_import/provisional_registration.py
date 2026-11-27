"""
File: provisional_registration.py
Description: 定義 LINE 客戶臨時登記根事實與閉鎖驗證規則，強制胎數僅收單胞胎或雙胞胎。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Literal, Mapping

from domains.case_import.beclass_correction import VALID_MULTI_BIRTH_COUNTS
from domains.case_import.cooking_requirement import CookingRequirementDomainError, normalize_cooking_requirement
from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from domains.case_import.refund_account import refund_fields_from_survey
from domains.case_import.registration_details import HOLIDAY_DOUBLE_PAY_SURVEY_FIELD, normalize_holiday_double_pay, normalize_id_number, INGREDIENT_PURCHASE_SURVEY_FIELD, normalize_ingredient_purchase
from shared_kernel.validation import require_canonical_text, require_positive_integer


_LIFF_REQUIRED_CARE_TEXT_KEYS = (
    "服務時間內是否有其他寶寶",
    "哺乳方式：",
    "5媽咪有無過敏體質：",
    "特殊照護時應注意事項：",
    "月子餐點調理喜好/飲食習慣：",
    "呈上題，若遇無法媒合到葷食服務人員時，是否可以接受蛋奶素服務人員？",
    "2．餐飲含酒比例：",
    "餐點喜忌備註：",
    "透天服務樓層方式(會加收樓層費)",
    "提供服務人員轎車停車位",
)
_LIFF_CARE_EXCLUSIVE_CHOICES = {
    "洗澡水準備：": "不需另外準備",
    "可以接受中藥補品：□茶飲 □藥飲 □藥膳": "無法接受中藥補品",
    "3．料理用油：(可接受種類)": "不適用",
    "烹煮工具": "無上述設備",
}


def has_valid_liff_care_answers(survey: Mapping[str, object]) -> bool:
    for key in _LIFF_REQUIRED_CARE_TEXT_KEYS:
        answer = survey.get(key)
        if not isinstance(answer, str) or not answer.strip():
            return False
    for key, exclusive_choice in _LIFF_CARE_EXCLUSIVE_CHOICES.items():
        answer = survey.get(key)
        if not isinstance(answer, str):
            return False
        choices = {choice.strip() for choice in answer.split(",")} - {""}
        if not choices or (exclusive_choice in choices and len(choices) > 1):
            return False
    try:
        normalize_cooking_requirement(survey)
    except CookingRequirementDomainError:
        return False
    return True


class ProvisionalRegistrationIssue(StrEnum):
    INVALID_ROOT_FACTS = "provisional_registration_invalid_root_facts"


class ProvisionalRegistrationDomainError(ValueError):
    def __init__(self, issue: ProvisionalRegistrationIssue, message: str) -> None:
        super().__init__(message)
        self.issue = issue


@dataclass(frozen=True, slots=True)
class ProvisionalRegistrationIntent:
    line_user_id: str
    name: str
    phone: str
    expected_date: str
    service_days: int
    address: str
    gender: str | None
    email: str | None
    birth_date: str | None
    tel: str | None
    ext: str | None
    city: str | None
    zip_code: str | None
    id_number: str | None
    liff_config_revision: str | None
    survey_details: Mapping[str, Any]
    registration_kind: Literal["subsidy", "non_citizen"] = "subsidy"
    service_start_date: str | None = None
    service_time: str | None = None
    residence_type: str | None = None
    delivery_type: str | None = None
    service_type: str | None = None
    baby_info: str | None = None
    notes: str | None = None
    line_id: str | None = None
    passbook_image_id: str | None = None


@dataclass(frozen=True, slots=True)
class ProvisionalRegistrationCandidate:
    line_user_id: str
    client_payload: Mapping[str, str | int | None]
    beclass_payload: Mapping[str, str | Mapping[str, Any] | None]
    payload_fingerprint: PreviewFingerprint

    @property
    def registration_kind(self) -> str:
        metadata = self.beclass_payload["survey_details"].get("_liff_meta", {})
        return metadata.get("registration_kind", "subsidy")


def build_provisional_registration_candidate(
    intent: ProvisionalRegistrationIntent,
) -> ProvisionalRegistrationCandidate:
    line_user_id = _required(intent.line_user_id, "line user id", 100)
    name = _required(intent.name, "name", 100)
    phone = _phone(intent.phone)
    expected_date = _required(intent.expected_date, "expected date", 100)
    address = _required(intent.address, "address", 255)
    service_days = _service_days(intent.service_days)
    passbook_image_id = intent.passbook_image_id
    if intent.registration_kind == "subsidy" or passbook_image_id is not None:
        passbook_image_id = _required(passbook_image_id, "passbook image", 128)
    optional = _optional_payload(intent)
    survey_details = dict(_survey_details(intent.survey_details))
    survey_details["特殊計費:胎數"] = _required_multi_birth_count(survey_details)
    try:
        purchase = normalize_ingredient_purchase(survey_details.get(INGREDIENT_PURCHASE_SURVEY_FIELD))
        if purchase is None:
            raise ValueError("ingredient_purchase_required")
    except ValueError:
        raise ProvisionalRegistrationDomainError(
            ProvisionalRegistrationIssue.INVALID_ROOT_FACTS, "代購食材須選擇需月嫂代購(實報實銷)或自行準備。"
        ) from None
    survey_details[INGREDIENT_PURCHASE_SURVEY_FIELD] = purchase
    if HOLIDAY_DOUBLE_PAY_SURVEY_FIELD in survey_details:
        try:
            survey_details[HOLIDAY_DOUBLE_PAY_SURVEY_FIELD] = normalize_holiday_double_pay(
                survey_details[HOLIDAY_DOUBLE_PAY_SURVEY_FIELD]
            )
        except ValueError:
            raise ProvisionalRegistrationDomainError(
                ProvisionalRegistrationIssue.INVALID_ROOT_FACTS, "三節假日雙薪意願須選擇是、否或未填。"
            ) from None
    client = {
        "name": name,
        "phone": phone,
        "address": address,
        "service_days": service_days,
        "due_month": expected_date,
        "line_user_id": line_user_id,
        "gender": optional["gender"],
        "city": optional["city"],
    }
    beclass = {
        "name": name,
        "email": optional["email"],
        "birth_date": optional["birth_date"],
        "phone": phone,
        "tel": optional["tel"],
        "ext": optional["ext"],
        "city": optional["city"],
        "zip_code": optional["zip_code"],
        "address": address,
        "survey_details": _enriched_survey(
            survey_details,
            expected_date,
            service_days,
            optional["id_number"],
            optional["gender"],
            optional["liff_config_revision"],
        ),
    }
    try:
        beclass.update(refund_fields_from_survey(survey_details))
    except ValueError as error:
        raise ProvisionalRegistrationDomainError(ProvisionalRegistrationIssue.INVALID_ROOT_FACTS, str(error)) from None
    if intent.registration_kind not in {"subsidy", "non_citizen"}:
        raise ProvisionalRegistrationDomainError(
            ProvisionalRegistrationIssue.INVALID_ROOT_FACTS, "registration kind is invalid"
        )
    if intent.registration_kind == "non_citizen":
        from domains.case_import.non_citizen_registration import non_citizen_client_fields
        try:
            client.update(non_citizen_client_fields(intent))
        except (ValueError, TypeError) as error:
            raise ProvisionalRegistrationDomainError(
                ProvisionalRegistrationIssue.INVALID_ROOT_FACTS, str(error)
            ) from error
        if client["baby_info"] != survey_details["特殊計費:胎數"]:
            raise ProvisionalRegistrationDomainError(
                ProvisionalRegistrationIssue.INVALID_ROOT_FACTS,
                "baby_info must match multi_birth_count",
            )
        beclass["survey_details"]["_liff_meta"].update(
            page="non_citizen_registration", registration_kind="non_citizen"
        )
    if passbook_image_id is not None:
        beclass["survey_details"]["_liff_meta"]["passbook_image_id"] = passbook_image_id
    return ProvisionalRegistrationCandidate(
        line_user_id,
        client,
        beclass,
        fingerprint_payload({"client": client, "beclass": beclass}),
    )


def _required(value: object, field_name: str, maximum_length: int) -> str:
    try:
        return require_canonical_text(value, field_name, maximum_length)
    except ValueError as error:
        raise ProvisionalRegistrationDomainError(
            ProvisionalRegistrationIssue.INVALID_ROOT_FACTS,
            f"{field_name} is required",
        ) from error


def _phone(value: str) -> str:
    normalized = value.replace(" ", "").replace("-", "")
    if len(normalized) > 20 or not normalized:
        raise ProvisionalRegistrationDomainError(
            ProvisionalRegistrationIssue.INVALID_ROOT_FACTS, "phone is invalid"
        )
    return normalized


def _service_days(value: int) -> int:
    try:
        return require_positive_integer(value, "service days")
    except ValueError as error:
        raise ProvisionalRegistrationDomainError(
            ProvisionalRegistrationIssue.INVALID_ROOT_FACTS,
            "service days is invalid",
        ) from error


def _optional_payload(intent: ProvisionalRegistrationIntent) -> dict[str, str | None]:
    values = {
        "gender": intent.gender,
        "email": intent.email,
        "birth_date": intent.birth_date,
        "tel": intent.tel,
        "ext": intent.ext,
        "city": intent.city,
        "zip_code": intent.zip_code,
        "id_number": intent.id_number,
        "liff_config_revision": intent.liff_config_revision,
    }
    normalized = {key: _optional(value, key) for key, value in values.items()}
    normalized["id_number"] = _optional_id_number(intent.id_number)
    return normalized


def _optional_id_number(value: str | None) -> str | None:
    try:
        return normalize_id_number(value)
    except ValueError:
        raise ProvisionalRegistrationDomainError(
            ProvisionalRegistrationIssue.INVALID_ROOT_FACTS, "id_number is invalid",
        ) from None


def _optional(value: str | None, field_name: str) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    if len(normalized) > 255:
        raise ProvisionalRegistrationDomainError(
            ProvisionalRegistrationIssue.INVALID_ROOT_FACTS,
            f"{field_name} exceeds maximum length",
        )
    return normalized


def _required_multi_birth_count(survey_details: Mapping[str, Any]) -> str:
    value = survey_details.get("特殊計費:胎數")
    if not isinstance(value, str) or not value.strip():
        raise ProvisionalRegistrationDomainError(
            ProvisionalRegistrationIssue.INVALID_ROOT_FACTS,
            "multi_birth_count is required",
        )
    normalized = value.strip()
    if normalized not in VALID_MULTI_BIRTH_COUNTS:
        raise ProvisionalRegistrationDomainError(
            ProvisionalRegistrationIssue.INVALID_ROOT_FACTS,
            "multi_birth_count is invalid",
        )
    return normalized


def _survey_details(value: Mapping[str, Any]) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ProvisionalRegistrationDomainError(
            ProvisionalRegistrationIssue.INVALID_ROOT_FACTS,
            "survey details is invalid",
        )
    try:
        fingerprint_payload(dict(value))
    except (TypeError, ValueError) as error:
        raise ProvisionalRegistrationDomainError(
            ProvisionalRegistrationIssue.INVALID_ROOT_FACTS,
            "survey details is invalid",
        ) from error
    return dict(value)


def _enriched_survey(survey, expected_date, service_days, id_number, gender, revision):
    return {
        **survey,
        "預產期": expected_date,
        "預計服務天數": service_days,
        "身分證字號": id_number,
        "性別": gender,
        "資料來源": "LINE 原生表單",
        "_liff_meta": {"page": "registration", "config_revision": revision},
    }


__all__ = [
    "ProvisionalRegistrationCandidate",
    "ProvisionalRegistrationDomainError",
    "ProvisionalRegistrationIntent",
    "ProvisionalRegistrationIssue",
    "build_provisional_registration_candidate",
    "has_valid_liff_care_answers",
]
