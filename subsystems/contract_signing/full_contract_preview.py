"""Bounded Full Contract Query/Preview composition over typed owner projections.

This module deliberately does not calculate business facts. It selects the
approved static template, validates every mapped field against a typed owner
projection, and returns cell values for the existing browser print view.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
import hashlib
import json
from pathlib import Path
from typing import Protocol

from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.clock import BusinessClock, SystemBusinessClock
from shared_kernel.validation import require_canonical_text, require_positive_integer
from subsystems.contract_signing.template_catalog import (
    approved_template_mapping_path,
    load_approved_template,
    mapping_is_applicable,
)


class ContractPreviewScope(StrEnum):
    CLIENT = "client"
    STAFF = "staff"


class FullContractPreviewError(RuntimeError):
    def __init__(self, code: str, message: str, *, not_found: bool = False) -> None:
        self.code = code
        self.not_found = not_found
        self.category = "not_found" if not_found else "domain_blocked"
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class FullContractOwnerProjection:
    case_no: str
    scope: ContractPreviewScope
    assignment_id: int | None
    facts: Mapping[str, object]
    owner_fingerprints: Mapping[str, str]

    def __post_init__(self) -> None:
        require_canonical_text(self.case_no, "case number", 50)
        if not isinstance(self.scope, ContractPreviewScope):
            raise TypeError("contract preview scope is invalid")
        if self.scope is ContractPreviewScope.STAFF:
            require_positive_integer(self.assignment_id, "assignment id")
        elif self.assignment_id is not None:
            raise ValueError("client preview must not contain assignment id")
        if not isinstance(self.facts, Mapping):
            raise TypeError("contract preview facts must be a mapping")
        if not isinstance(self.owner_fingerprints, Mapping):
            raise TypeError("contract owner fingerprints must be a mapping")


class FullContractProjectionRepository(Protocol):
    def load_client_projection(self, case_no: str) -> FullContractOwnerProjection | None: ...

    def load_staff_projection(
        self, case_no: str, assignment_id: int
    ) -> FullContractOwnerProjection | None: ...


@dataclass(frozen=True, slots=True)
class FullContractPreviewResult:
    case_no: str
    scope: ContractPreviewScope
    assignment_id: int | None
    template_key: str
    template_version: str
    template_sha256: str
    mapping_sha256: str
    owner_fingerprints: Mapping[str, str]
    field_values: Mapping[str, object | None]
    blockers: tuple[str, ...]
    preview_fingerprint: PreviewFingerprint

    @property
    def ready_to_print(self) -> bool:
        return not self.blockers


class FullContractPreviewApplication:
    """Query and zero-write Preview for exact client/staff contract targets."""

    def __init__(
        self,
        repository: FullContractProjectionRepository,
        clock: BusinessClock | None = None,
    ) -> None:
        self._repository = repository
        self._clock = clock or SystemBusinessClock()

    def preview_client(self, case_no: str) -> FullContractPreviewResult:
        projection = self._repository.load_client_projection(case_no)
        return self._preview(projection, ContractPreviewScope.CLIENT, None)

    def preview_staff(
        self, case_no: str, assignment_id: int
    ) -> FullContractPreviewResult:
        projection = self._repository.load_staff_projection(case_no, assignment_id)
        return self._preview(projection, ContractPreviewScope.STAFF, assignment_id)

    def _preview(
        self,
        projection: FullContractOwnerProjection | None,
        scope: ContractPreviewScope,
        assignment_id: int | None,
    ) -> FullContractPreviewResult:
        if projection is None:
            raise FullContractPreviewError(
                "contract_preview_target_not_found",
                "找不到指定契約預覽對象。",
                not_found=True,
            )
        if projection.scope is not scope or projection.assignment_id != assignment_id:
            raise FullContractPreviewError(
                "contract_preview_target_mismatch",
                "契約預覽對象身分不一致。",
            )
        template_key = (
            "contract_client_copy"
            if scope is ContractPreviewScope.CLIENT
            else "contract_staff_service"
        )
        try:
            template = load_approved_template(template_key)
        except Exception:
            raise FullContractPreviewError(
                "contract_preview_template_unavailable",
                "核准契約模板目前無法使用。",
            ) from None
        # Contract Signing owns only this command snapshot date; all business
        # values remain in the typed owner projection.
        facts = dict(projection.facts)
        snapshot_date = self._clock.today()
        facts["contract_signed_date"] = snapshot_date
        facts["__today__"] = snapshot_date
        mapping_path = approved_template_mapping_path(template_key)
        blockers = _mapping_blockers(template_key, mapping_path, facts)
        field_values = _mapped_field_values(mapping_path, facts)
        fingerprint = fingerprint_payload(
            {
                "case_no": projection.case_no,
                "scope": scope.value,
                "assignment_id": assignment_id,
                "template_key": template.template_key,
                "template_sha256": template.template_sha256,
                "mapping_sha256": template.mapping_sha256,
                "owner_fingerprints": dict(sorted(projection.owner_fingerprints.items())),
                "command_snapshot_date": snapshot_date.isoformat(),
                "blockers": list(blockers),
                "field_values": field_values,
            }
        )
        return FullContractPreviewResult(
            case_no=projection.case_no,
            scope=scope,
            assignment_id=assignment_id,
            template_key=template.template_key,
            template_version=template.mapping_sha256,
            template_sha256=template.template_sha256,
            mapping_sha256=template.mapping_sha256,
            owner_fingerprints=dict(sorted(projection.owner_fingerprints.items())),
            field_values=field_values,
            blockers=tuple(blockers),
            preview_fingerprint=fingerprint,
        )


def _mapping_fields(mapping_path: Path) -> Mapping[str, object] | None:
    try:
        mapping = json.loads(mapping_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    fields = mapping.get("param_mappings") if isinstance(mapping, dict) else None
    return fields if isinstance(fields, dict) else None


def _mapped_field_values(
    mapping_path: Path, facts: Mapping[str, object]
) -> dict[str, object | None]:
    fields = _mapping_fields(mapping_path)
    if fields is None:
        return {}
    values: dict[str, object | None] = {}
    for cell, descriptor in fields.items():
        if not isinstance(cell, str) or not isinstance(descriptor, dict):
            continue
        key = descriptor.get("db_key")
        if descriptor.get("status") == "not_applicable":
            values[cell] = None
        elif isinstance(key, str) and key:
            values[cell] = facts.get(key)
    return values


def _mapping_blockers(
    template_key: str, mapping_path: Path, facts: Mapping[str, object]
) -> tuple[str, ...]:
    fields = _mapping_fields(mapping_path)
    if fields is None:
        return ("contract_pdf_mapping_invalid",)
    blockers: set[str] = set()
    for descriptor in fields.values():
        if not isinstance(descriptor, dict):
            blockers.add("contract_pdf_mapping_invalid")
            continue
        key = descriptor.get("db_key")
        status = descriptor.get("status")
        requiredness = descriptor.get("requiredness")
        if status == "not_applicable":
            # Legacy funding-split cells are intentionally blank in the
            # current owner model. They never require a manual value.
            if requiredness in {"optional", "conditional"}:
                continue
            blockers.add("contract_pdf_required_mapping_unresolved")
            continue
        if status in {"pending", "unresolved"}:
            # Conditional legacy cells only participate when the current
            # typed owner says that the section applies.  An absent optional
            # section must not make an otherwise complete PDF unusable.
            if requiredness == "optional" or (
                requiredness == "conditional"
                and not mapping_is_applicable(descriptor, facts)
            ):
                continue
            blockers.add("contract_pdf_required_mapping_unresolved")
            continue
        if not isinstance(key, str) or not key:
            blockers.add("contract_pdf_required_mapping_unresolved")
            continue
        if requiredness not in {"required", "conditional", "optional"}:
            blockers.add("contract_pdf_required_mapping_unresolved")
            continue
        applicable = requiredness == "required" or (
            requiredness == "conditional" and mapping_is_applicable(descriptor, facts)
        )
        if applicable and (key not in facts or facts.get(key) is None):
            blockers.add("contract_pdf_required_mapping_missing")
    return tuple(sorted(blockers))


def projection_fingerprint(values: Mapping[str, object]) -> str:
    """Build a stable owner fingerprint from already-typed scalar projections."""
    payload = json.dumps(values, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


__all__ = [
    "ContractPreviewScope",
    "FullContractOwnerProjection",
    "FullContractPreviewApplication",
    "FullContractPreviewError",
    "FullContractPreviewResult",
    "FullContractProjectionRepository",
    "projection_fingerprint",
]
