"""
File: case_import.py
Description: 定義 Case Import 根事實、來源指紋與候選不變量。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from enum import StrEnum

from domains.bootstrap.case_architecture import (
    BootstrapDomainError,
    BootstrapPresence,
    CaseArchitectureBootstrapCandidate,
    CaseArchitectureBootstrapFacts,
    CaseArchitectureBootstrapIntent,
    CaseRootFacts,
    RatePolicyFacts,
    build_case_architecture_bootstrap_candidate,
)
from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.validation import (
    require_canonical_text,
    require_positive_integer,
)

_CASE_NUMBER_MAXIMUM_LENGTH = 50
_ATTRIBUTE_NAME_MAXIMUM_LENGTH = 64
_ALLOWED_CLIENT_ATTRIBUTES = frozenset(
    {
        "address",
        "admin_notes",
        "baby_info",
        "case_no",
        "city",
        "created_at",
        "delivery_type",
        "due_month",
        "gender",
        "identity_status",
        "ip_address",
        "line_id",
        "name",
        "notes",
        "phone",
        "reject_reason",
        "residence_type",
        "seq_num",
        "service_days",
        "service_start_date",
        "service_time",
        "service_type",
    }
)


class CaseImportIssue(StrEnum):
    INVALID_ROOT_FACTS = "invalid_case_import_root_facts"
    DUPLICATE_CASE = "case_import_duplicate"
    BOOTSTRAP_BLOCKED = "case_import_bootstrap_blocked"
    PROVISIONAL_REGISTRATION_NOT_FOUND = "provisional_registration_not_found"
    PROVISIONAL_REGISTRATION_NOT_SUBMITTED = "provisional_registration_not_submitted"
    PROVISIONAL_REGISTRATION_IDENTITY_MISMATCH = "provisional_registration_identity_mismatch"


class HcmIdentityResolution(StrEnum):
    NEW = "new"
    EXISTING_MATCH = "existing_match"
    CONFLICT = "conflict"
    AMBIGUOUS = "ambiguous"


class CaseImportDomainError(ValueError):
    def __init__(self, issue: CaseImportIssue, message: str) -> None:
        super().__init__(message)
        self.issue = issue


@dataclass(frozen=True, slots=True)
class ClientImportAttribute:
    name: str
    value: str | int | date | datetime | None

    def __post_init__(self) -> None:
        require_canonical_text(
            self.name,
            "client attribute name",
            _ATTRIBUTE_NAME_MAXIMUM_LENGTH,
        )
        if self.name not in _ALLOWED_CLIENT_ATTRIBUTES:
            _raise_invalid(f"client attribute {self.name} is not importable")
        if isinstance(self.value, bool):
            _raise_invalid(f"client attribute {self.name} has invalid type")
        if self.value is not None and not isinstance(
            self.value,
            (str, int, date, datetime),
        ):
            _raise_invalid(f"client attribute {self.name} has invalid type")


@dataclass(frozen=True, slots=True)
class ImportedOrderRootFacts:
    case_no: str
    service_days: int
    service_hours_per_day: int
    planned_start_date: date
    planned_end_date: date
    service_start_time: time
    service_end_time: time
    service_end_day_offset: int
    requires_cooking: bool | None

    def __post_init__(self) -> None:
        _validate_case_no(self.case_no)
        require_positive_integer(self.service_days, "service days")
        require_positive_integer(
            self.service_hours_per_day,
            "service hours per day",
        )
        _require_exact_type(self.planned_start_date, date, "planned start date")
        _require_exact_type(self.planned_end_date, date, "planned end date")
        _require_exact_type(self.service_start_time, time, "service start time")
        _require_exact_type(self.service_end_time, time, "service end time")
        if self.service_end_day_offset not in {0, 1}:
            _raise_invalid("service end day offset must be zero or one")
        if self.requires_cooking is not None and not isinstance(
            self.requires_cooking, bool
        ):
            _raise_invalid("requires cooking must be bool or None")
        if self.planned_end_date < self.planned_start_date:
            _raise_invalid("planned service interval is inverted")


@dataclass(frozen=True, slots=True)
class CaseImportIntent:
    case_no: str
    client_attributes: tuple[ClientImportAttribute, ...]
    order: ImportedOrderRootFacts
    bootstrap: CaseArchitectureBootstrapIntent
    provisional_registration_id: int | None = None

    def __post_init__(self) -> None:
        _validate_case_no(self.case_no)
        if not isinstance(self.client_attributes, tuple):
            raise TypeError("client attributes must be a tuple")
        _validate_attributes(self.case_no, self.client_attributes)
        if self.order.case_no != self.case_no:
            _raise_invalid("order root facts belong to another case")
        if self.bootstrap.case_no != self.case_no:
            _raise_invalid("bootstrap intent belongs to another case")
        if self.provisional_registration_id is not None:
            require_positive_integer(self.provisional_registration_id, "provisional registration id")


@dataclass(frozen=True, slots=True)
class ProvisionalRegistrationFacts:
    registration_id: int
    line_user_id: str
    status: str
    client_id: int | None
    beclass_record_id: int | None
    beclass_query_no: str | None
    has_open_conflict: bool


@dataclass(frozen=True, slots=True)
class CaseImportFacts:
    case_exists: bool
    payroll_rate_policy: RatePolicyFacts | None
    provisional_registration: ProvisionalRegistrationFacts | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.case_exists, bool):
            raise TypeError("case existence must be bool")


@dataclass(frozen=True, slots=True)
class HcmIdentityFacts:
    case_client_ids: tuple[int, ...]
    ip_name_client_ids: tuple[int, ...]
    order_exists: bool


def resolve_hcm_identity(facts: HcmIdentityFacts) -> HcmIdentityResolution:
    if len(facts.case_client_ids) > 1 or len(facts.ip_name_client_ids) > 1:
        return HcmIdentityResolution.AMBIGUOUS
    if not facts.case_client_ids and not facts.ip_name_client_ids and not facts.order_exists:
        return HcmIdentityResolution.NEW
    if facts.order_exists and not facts.case_client_ids:
        return HcmIdentityResolution.CONFLICT
    if facts.case_client_ids == facts.ip_name_client_ids:
        return HcmIdentityResolution.EXISTING_MATCH
    return HcmIdentityResolution.CONFLICT


@dataclass(frozen=True, slots=True)
class CaseImportCandidate:
    case_no: str
    client_attributes: tuple[ClientImportAttribute, ...]
    order: ImportedOrderRootFacts
    bootstrap: CaseArchitectureBootstrapCandidate
    source_fingerprint: PreviewFingerprint
    fingerprint: PreviewFingerprint
    provisional_registration: ProvisionalRegistrationFacts | None = None


# Kept cohesive so source and bootstrap fingerprints describe one candidate.
def build_case_import_candidate(
    facts: CaseImportFacts,
    intent: CaseImportIntent,
) -> CaseImportCandidate:
    if facts.case_exists:
        raise CaseImportDomainError(
            CaseImportIssue.DUPLICATE_CASE,
            "The case already exists and cannot be imported again.",
        )
    bootstrap = _build_bootstrap_candidate(facts, intent)
    _validate_provisional_registration(facts.provisional_registration, intent)
    source_fingerprint = fingerprint_case_import_source(intent)
    fingerprint = fingerprint_payload(
        {
            "source_fingerprint": source_fingerprint.value,
            "bootstrap_fingerprint": bootstrap.fingerprint.value,
        }
    )
    return CaseImportCandidate(
        intent.case_no,
        intent.client_attributes,
        intent.order,
        bootstrap,
        source_fingerprint,
        fingerprint,
        facts.provisional_registration,
    )


def fingerprint_case_import_source(intent: CaseImportIntent) -> PreviewFingerprint:
    return fingerprint_payload(_source_payload(intent))


def _validate_provisional_registration(registration, intent) -> None:
    if intent.provisional_registration_id is None:
        return
    if registration is None or registration.registration_id != intent.provisional_registration_id:
        raise CaseImportDomainError(CaseImportIssue.PROVISIONAL_REGISTRATION_NOT_FOUND, "Provisional registration was not found.")
    if registration.status != "submitted":
        raise CaseImportDomainError(CaseImportIssue.PROVISIONAL_REGISTRATION_NOT_SUBMITTED, "Provisional registration is not submitted.")
    if registration.client_id is None or registration.beclass_record_id is None or registration.beclass_query_no is not None or registration.has_open_conflict:
        raise CaseImportDomainError(CaseImportIssue.PROVISIONAL_REGISTRATION_IDENTITY_MISMATCH, "Provisional registration cannot be safely issued.")
    if _required_attribute(intent.client_attributes, "line_id") != registration.line_user_id:
        raise CaseImportDomainError(CaseImportIssue.PROVISIONAL_REGISTRATION_IDENTITY_MISMATCH, "Case import LINE identity differs from provisional registration.")


# Kept cohesive so the synthetic version-zero root cannot drift across helpers.
def _build_bootstrap_candidate(facts, intent):
    order = intent.order
    bootstrap_facts = CaseArchitectureBootstrapFacts(
        CaseRootFacts(
            order.case_no,
            0,
            order.planned_start_date,
            order.service_days,
            order.service_hours_per_day,
            _required_attribute(intent.client_attributes, "identity_status"),
        ),
        facts.payroll_rate_policy,
        BootstrapPresence(),
    )
    try:
        return build_case_architecture_bootstrap_candidate(
            bootstrap_facts,
            intent.bootstrap,
        )
    except BootstrapDomainError as error:
        raise CaseImportDomainError(
            CaseImportIssue.BOOTSTRAP_BLOCKED,
            str(error),
        ) from error


def _validate_attributes(case_no, attributes) -> None:
    names = tuple(item.name for item in attributes)
    if names != tuple(sorted(set(names))):
        _raise_invalid("client attributes must be sorted and unique")
    if _required_attribute(attributes, "case_no") != case_no:
        _raise_invalid("client root facts belong to another case")
    for name in ("created_at", "identity_status", "name", "service_time"):
        _required_attribute(attributes, name)


def _required_attribute(attributes, name):
    value = next((item.value for item in attributes if item.name == name), None)
    if value is None or (isinstance(value, str) and not value.strip()):
        _raise_invalid(f"client attribute {name} is required")
    return value


def _source_payload(intent):
    return {
        "case_no": intent.case_no,
        "client_attributes": tuple(
            {
                "name": item.name,
                "value": _canonical_value(item.value),
            }
            for item in intent.client_attributes
        ),
        "order": _order_payload(intent.order),
        "bootstrap": _bootstrap_payload(intent.bootstrap),
        "provisional_registration_id": intent.provisional_registration_id,
    }


def _order_payload(order):
    return {
        "service_days": order.service_days,
        "service_hours_per_day": order.service_hours_per_day,
        "planned_start_date": order.planned_start_date.isoformat(),
        "planned_end_date": order.planned_end_date.isoformat(),
        "service_start_time": order.service_start_time.isoformat(),
        "service_end_time": order.service_end_time.isoformat(),
        "service_end_day_offset": order.service_end_day_offset,
        "requires_cooking": order.requires_cooking,
    }


def _bootstrap_payload(bootstrap):
    terms = bootstrap.client_payment_terms
    return {
        "client_policy_version": terms.policy_version,
        "client_hourly_rate_ntd": terms.client_hourly_rate.amount,
        "deposit_service_days": terms.deposit_service_days,
        "deposit_due_date": terms.deposit_due_date.isoformat(),
        "first_payment_due_date": terms.first_payment_due_date.isoformat(),
        "payroll_policy_version": bootstrap.payroll_policy_version,
    }


def _canonical_value(value):
    if isinstance(value, (date, datetime, time)):
        return value.isoformat()
    return value


def _validate_case_no(case_no) -> None:
    require_canonical_text(
        case_no,
        "case number",
        _CASE_NUMBER_MAXIMUM_LENGTH,
    )


def _require_exact_type(value, expected_type, name) -> None:
    if type(value) is not expected_type:
        _raise_invalid(f"{name} has invalid type")


def _raise_invalid(message) -> None:
    raise CaseImportDomainError(CaseImportIssue.INVALID_ROOT_FACTS, message)


__all__ = [
    "CaseImportCandidate",
    "CaseImportDomainError",
    "CaseImportFacts",
    "CaseImportIntent",
    "CaseImportIssue",
    "ClientImportAttribute",
    "ImportedOrderRootFacts",
    "HcmIdentityFacts",
    "HcmIdentityResolution",
    "ProvisionalRegistrationFacts",
    "build_case_import_candidate",
    "fingerprint_case_import_source",
    "resolve_hcm_identity",
]
