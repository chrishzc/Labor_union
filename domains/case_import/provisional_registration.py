"""Pure root-fact rules for a LINE customer registration before case issuance."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Mapping

from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.validation import require_canonical_text, require_positive_integer


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


@dataclass(frozen=True, slots=True)
class ProvisionalRegistrationCandidate:
    line_user_id: str
    client_payload: Mapping[str, str | int | None]
    beclass_payload: Mapping[str, str | Mapping[str, Any] | None]
    payload_fingerprint: PreviewFingerprint


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
    survey_details = _survey_details(intent.survey_details)
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
    return {key: _optional(value, key) for key, value in values.items()}


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
