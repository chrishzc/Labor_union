"""
File: provisional_registration.py
Description: 定義 LINE 客戶臨時登記根事實與閉鎖驗證規則，強制胎數僅收單胞胎或雙胞胎。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import re
from typing import Any, Literal, Mapping

from domains.case_import.beclass_correction import VALID_MULTI_BIRTH_COUNTS
from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from domains.case_import.refund_account import refund_fields_from_survey
from shared_kernel.validation import require_canonical_text, require_positive_integer


_FULLWIDTH_ASCII_TRANSLATION = str.maketrans(
    {chr(codepoint): chr(codepoint - 0xFEE0) for codepoint in range(0xFF01, 0xFF5F)}
)
HOLIDAY_DOUBLE_PAY_SURVEY_FIELD = "三節假日是否願意支付雙倍薪水"


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
    optional = _optional_payload(intent)
    survey_details = dict(_survey_details(intent.survey_details))
    survey_details["特殊計費:胎數"] = _required_multi_birth_count(survey_details)
    if (
        HOLIDAY_DOUBLE_PAY_SURVEY_FIELD in survey_details
        and survey_details[HOLIDAY_DOUBLE_PAY_SURVEY_FIELD] not in ("是", "否")
    ):
        raise ProvisionalRegistrationDomainError(
            ProvisionalRegistrationIssue.INVALID_ROOT_FACTS, "三節假日雙倍薪水意願須選擇是或否。"
        )
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
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    candidate = normalized.translate(_FULLWIDTH_ASCII_TRANSLATION).upper()
    if not re.fullmatch(r"[A-Z][0-9]{9}", candidate):
        raise ProvisionalRegistrationDomainError(
            ProvisionalRegistrationIssue.INVALID_ROOT_FACTS,
            "id_number is invalid",
        )
    return candidate


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
]
