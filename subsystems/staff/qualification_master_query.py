"""
File: qualification_master_query.py
Description: 提供選定服務人員的資格與可服務期間 typed 唯讀投影。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Protocol

from shared_kernel.validation import require_canonical_text, require_positive_integer


_AVAILABILITY_STATES = frozenset({"available", "unavailable", "unknown", "partial"})
_SECTION_KINDS = frozenset(
    {"skills", "cooking", "certifications", "medical", "validity", "unavailability"}
)
_SECTION_ORDER = (
    "skills",
    "cooking",
    "certifications",
    "medical",
    "validity",
    "unavailability",
)


class QualificationMasterContractError(ValueError):
    """資格主檔來源違反 bounded projection 契約。"""


class StaffQualificationNotFound(LookupError):
    """指定服務人員不存在。"""


@dataclass(frozen=True, slots=True)
class UnavailabilitySourceRecord:
    block_id: int
    kind: str
    start_date: date
    end_date: date | None
    source_version: str | None


@dataclass(frozen=True, slots=True)
class StaffQualificationSourceRecord:
    staff_id: int
    staff_name: str
    staff_source_version: str | None
    special_skills: tuple[str, ...]
    cooking_skills: tuple[tuple[str, str | None], ...]
    massage_certified: bool | None
    unavailability_source_available: bool
    unavailability_source_reason: str
    unavailability_blocks: tuple[UnavailabilitySourceRecord, ...]


@dataclass(frozen=True, slots=True)
class StaffQualificationMasterQuery:
    staff_id: int
    as_of: date

    def __post_init__(self) -> None:
        require_positive_integer(self.staff_id, "staff qualification staff id")
        if type(self.as_of) is not date:
            raise TypeError("staff qualification as_of must be a date")


@dataclass(frozen=True, slots=True)
class QualificationFact:
    code: str
    value: str | bool | None
    source_identity: str
    source_version: str | None
    valid_from: date | None
    valid_until: date | None
    availability: str
    availability_reason: str
    detail: str | None = None

    def __post_init__(self) -> None:
        _require_code(self.code, "qualification fact code")
        _require_code(self.source_identity, "qualification fact source identity")
        _require_code(self.availability_reason, "qualification fact availability reason")
        _require_state(self.availability)
        if self.source_version is not None:
            require_canonical_text(self.source_version, "qualification fact source version", 191)
        if self.detail is not None:
            require_canonical_text(self.detail, "qualification fact detail", 200)
        if self.valid_from is not None and type(self.valid_from) is not date:
            raise TypeError("qualification fact valid_from must be a date")
        if self.valid_until is not None and type(self.valid_until) is not date:
            raise TypeError("qualification fact valid_until must be a date")
        if (
            self.valid_from is not None
            and self.valid_until is not None
            and self.valid_until < self.valid_from
        ):
            raise QualificationMasterContractError("qualification fact validity range is inverted")


@dataclass(frozen=True, slots=True)
class QualificationSection:
    kind: str
    owner: str
    availability: str
    availability_reason: str
    source_identity: str | None
    source_version: str | None
    items: tuple[QualificationFact, ...]

    def __post_init__(self) -> None:
        _require_code(self.kind, "qualification section kind")
        if self.kind not in _SECTION_KINDS:
            raise QualificationMasterContractError("unknown qualification section kind")
        _require_code(self.owner, "qualification section owner")
        _require_code(self.availability_reason, "qualification section availability reason")
        _require_state(self.availability)
        if self.source_identity is not None:
            _require_code(self.source_identity, "qualification section source identity")
        if self.source_version is not None:
            require_canonical_text(self.source_version, "qualification section source version", 191)
        codes = tuple(item.code for item in self.items)
        if len(codes) != len(set(codes)):
            raise QualificationMasterContractError("qualification section contains duplicate fact codes")


@dataclass(frozen=True, slots=True)
class StaffQualificationMaster:
    staff_id: int
    staff_name: str
    as_of: date
    overall_availability: str
    availability_reason: str
    sections: tuple[QualificationSection, ...]

    def __post_init__(self) -> None:
        require_positive_integer(self.staff_id, "staff qualification staff id")
        require_canonical_text(self.staff_name, "staff qualification staff name", 100)
        if type(self.as_of) is not date:
            raise TypeError("staff qualification as_of must be a date")
        _require_state(self.overall_availability)
        _require_code(self.availability_reason, "staff qualification availability reason")
        kinds = tuple(section.kind for section in self.sections)
        if kinds != _SECTION_ORDER or len(kinds) != len(set(kinds)):
            raise QualificationMasterContractError("qualification sections must be unique and ordered")
        if set(kinds) != _SECTION_KINDS:
            raise QualificationMasterContractError("qualification projection must contain all sections")


class StaffQualificationMasterRepository(Protocol):
    def fetch(self, query: StaffQualificationMasterQuery) -> StaffQualificationSourceRecord: ...


class StaffQualificationMasterQueryService:
    """把 repository 的 existing facts 映射成六個明確 bounded sections。"""

    def __init__(self, repository: StaffQualificationMasterRepository) -> None:
        self._repository = repository

    def query(self, request: StaffQualificationMasterQuery) -> StaffQualificationMaster:
        source = self._repository.fetch(request)
        if not isinstance(source, StaffQualificationSourceRecord):
            raise QualificationMasterContractError("repository returned an invalid qualification source")
        return _project(source, request.as_of)


class QualificationMasterQueryApplication:
    """API dependency 使用的最小 query application facade。"""

    def __init__(self, service: StaffQualificationMasterQueryService) -> None:
        self.service = service

    def query(self, request: StaffQualificationMasterQuery) -> StaffQualificationMaster:
        return self.service.query(request)


def _project(source: StaffQualificationSourceRecord, as_of: date) -> StaffQualificationMaster:
    if source.staff_id <= 0:
        raise QualificationMasterContractError("repository returned an invalid staff id")
    if not source.staff_name.strip():
        raise QualificationMasterContractError("repository returned an empty staff name")
    sections = (
        _skills_section(source),
        _cooking_section(source),
        _certifications_section(source),
        _medical_section(),
        _validity_section(),
        _unavailability_section(source),
    )
    has_block = bool(source.unavailability_blocks)
    if has_block:
        overall = "unavailable"
        reason = "effective_staff_unavailability"
    elif not source.unavailability_source_available:
        overall = "unknown"
        reason = "staff_availability_source_not_ready"
    else:
        overall = "available"
        reason = "no_effective_unavailability_for_as_of"
    return StaffQualificationMaster(
        staff_id=source.staff_id,
        staff_name=source.staff_name,
        as_of=as_of,
        overall_availability=overall,
        availability_reason=reason,
        sections=sections,
    )


def _skills_section(source: StaffQualificationSourceRecord) -> QualificationSection:
    items = tuple(
        QualificationFact(
            code=f"special_skill_{index}",
            value=value,
            source_identity=f"staff:{source.staff_id}:special_skills:{index}",
            source_version=source.staff_source_version,
            valid_from=None,
            valid_until=None,
            availability="available",
            availability_reason="staff_special_skill_record",
        )
        for index, value in enumerate(source.special_skills, start=1)
    )
    return QualificationSection(
        kind="skills",
        owner="staff_master",
        availability="available",
        availability_reason="staff_special_skills_empty" if not items else "staff_special_skills_ready",
        source_identity=f"staff:{source.staff_id}:special_skills",
        source_version=source.staff_source_version,
        items=items,
    )


def _cooking_section(source: StaffQualificationSourceRecord) -> QualificationSection:
    items = tuple(
        QualificationFact(
            code=f"cooking_skill_{index}",
            value=skill_name,
            detail=detail,
            source_identity=f"staff_cooking_skills:{source.staff_id}:{index}",
            source_version=None,
            valid_from=None,
            valid_until=None,
            availability="available",
            availability_reason="staff_cooking_skill_record",
        )
        for index, (skill_name, detail) in enumerate(source.cooking_skills, start=1)
    )
    return QualificationSection(
        kind="cooking",
        owner="staff_cooking_skills",
        availability="available",
        availability_reason="staff_cooking_skills_empty" if not items else "staff_cooking_skills_ready",
        source_identity=f"staff_cooking_skills:{source.staff_id}",
        source_version=None,
        items=items,
    )


def _certifications_section(source: StaffQualificationSourceRecord) -> QualificationSection:
    availability = "available" if source.massage_certified is not None else "partial"
    reason = "legacy_massage_certificate_ready" if source.massage_certified is not None else "legacy_certificate_value_missing"
    item = QualificationFact(
        code="massage_certificate",
        value=source.massage_certified,
        source_identity=f"staff:{source.staff_id}:has_massage_cert",
        source_version=source.staff_source_version,
        valid_from=None,
        valid_until=None,
        availability=availability,
        availability_reason=reason,
    )
    return QualificationSection(
        kind="certifications",
        owner="staff_master_legacy_certification",
        availability=availability,
        availability_reason=reason,
        source_identity=f"staff:{source.staff_id}:has_massage_cert",
        source_version=source.staff_source_version,
        items=(item,),
    )


def _medical_section() -> QualificationSection:
    return QualificationSection(
        kind="medical",
        owner="staff_medical_registry",
        availability="unavailable",
        availability_reason="staff_medical_registry_not_provided",
        source_identity=None,
        source_version=None,
        items=(),
    )


def _validity_section() -> QualificationSection:
    return QualificationSection(
        kind="validity",
        owner="qualification_validity_registry",
        availability="unavailable",
        availability_reason="qualification_validity_registry_not_provided",
        source_identity=None,
        source_version=None,
        items=(),
    )


def _unavailability_section(source: StaffQualificationSourceRecord) -> QualificationSection:
    if not source.unavailability_source_available:
        return QualificationSection(
            kind="unavailability",
            owner="scheduling_staff_unavailability",
            availability="unavailable",
            availability_reason=source.unavailability_source_reason,
            source_identity=None,
            source_version=None,
            items=(),
        )
    items = tuple(
        QualificationFact(
            code=f"unavailability_block_{block.block_id}",
            value=block.kind,
            source_identity=f"scheduling_staff_unavailability_blocks:{block.block_id}",
            source_version=block.source_version,
            valid_from=block.start_date,
            valid_until=block.end_date,
            availability="unavailable",
            availability_reason="effective_unavailability_block",
        )
        for block in source.unavailability_blocks
    )
    return QualificationSection(
        kind="unavailability",
        owner="scheduling_staff_unavailability",
        availability="unavailable" if items else "available",
        availability_reason="effective_unavailability_block" if items else "no_effective_unavailability_for_as_of",
        source_identity=f"scheduling_staff_unavailability:{source.staff_id}",
        source_version=None,
        items=items,
    )


def _require_state(value: str) -> None:
    if value not in _AVAILABILITY_STATES:
        raise QualificationMasterContractError("unknown qualification availability state")


def _require_code(value: str, field: str) -> None:
    try:
        require_canonical_text(value, field, 191)
    except (TypeError, ValueError) as error:
        raise QualificationMasterContractError(str(error)) from error


__all__ = [
    "QualificationFact",
    "QualificationMasterContractError",
    "QualificationMasterQueryApplication",
    "QualificationSection",
    "StaffQualificationMaster",
    "StaffQualificationMasterQuery",
    "StaffQualificationMasterQueryService",
    "StaffQualificationMasterRepository",
    "StaffQualificationNotFound",
    "StaffQualificationSourceRecord",
    "UnavailabilitySourceRecord",
]
