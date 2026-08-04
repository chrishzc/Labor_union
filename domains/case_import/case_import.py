"""Pure candidate rules for importing one negotiated case."""

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
        if self.planned_end_date < self.planned_start_date:
            _raise_invalid("planned service interval is inverted")


@dataclass(frozen=True, slots=True)
class CaseImportIntent:
    case_no: str
    client_attributes: tuple[ClientImportAttribute, ...]
    order: ImportedOrderRootFacts
    bootstrap: CaseArchitectureBootstrapIntent

    def __post_init__(self) -> None:
        _validate_case_no(self.case_no)
        if not isinstance(self.client_attributes, tuple):
            raise TypeError("client attributes must be a tuple")
        _validate_attributes(self.case_no, self.client_attributes)
        if self.order.case_no != self.case_no:
            _raise_invalid("order root facts belong to another case")
        if self.bootstrap.case_no != self.case_no:
            _raise_invalid("bootstrap intent belongs to another case")


@dataclass(frozen=True, slots=True)
class CaseImportFacts:
    case_exists: bool
    payroll_rate_policy: RatePolicyFacts | None

    def __post_init__(self) -> None:
        if not isinstance(self.case_exists, bool):
            raise TypeError("case existence must be bool")


@dataclass(frozen=True, slots=True)
class CaseImportCandidate:
    case_no: str
    client_attributes: tuple[ClientImportAttribute, ...]
    order: ImportedOrderRootFacts
    bootstrap: CaseArchitectureBootstrapCandidate
    source_fingerprint: PreviewFingerprint
    fingerprint: PreviewFingerprint


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
    source_fingerprint = fingerprint_payload(_source_payload(intent))
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
    )


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
    "build_case_import_candidate",
]
