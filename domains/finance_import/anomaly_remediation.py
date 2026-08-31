"""Finance Import-owned current facts for ``IMPORT-006``.

The Anomalies projection is derived state.  This module is deliberately free of
database and anomaly-workflow dependencies: it defines the facts Finance Import
can prove and the predicate that a consumer may use after a fresh read.

Two repair paths are intentionally distinct:

* a correct immutable source with a stale derived projection is repaired by a
  deterministic same-batch rebuild; and
* a human-confirmed bad source is never rewritten.  It requires an explicitly
  recorded, completed successor batch with exact immutable lineage.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.validation import (
    require_canonical_text,
    require_nonnegative_integer,
)

_IDENTITY_MAXIMUM_LENGTH = 191


class FinanceImportIntegrityRepairPath(StrEnum):
    """The only supported dispositions for an IMPORT-006 owner fact."""

    DERIVED_REBUILD = "derived_rebuild"
    SOURCE_CORRECTION = "source_correction"
    STRUCTURAL_AMBIGUITY = "structural_ambiguity"


class FinanceImportIntegrityReason(StrEnum):
    OWNER_READBACK_INCOMPLETE = "owner_readback_incomplete"
    INTEGRITY_INCONSISTENT = "integrity_inconsistent"
    PROJECTION_INCONSISTENT = "projection_inconsistent"
    SOURCE_CORRECTION_REQUIRED = "source_correction_required"
    SUCCESSOR_NOT_UNIQUE = "successor_not_unique"
    SUCCESSOR_NOT_COMPLETED = "successor_not_completed"
    SUCCESSOR_NOT_FRESH = "successor_not_fresh"
    SUCCESSOR_INCOMPLETE = "successor_incomplete"
    STRUCTURAL_AMBIGUITY = "structural_ambiguity"


def _identity(value: str, field_name: str) -> str:
    return require_canonical_text(value, field_name, _IDENTITY_MAXIMUM_LENGTH)


def _batch_identity(value: str, field_name: str = "batch identity") -> str:
    value = _identity(value, field_name)
    prefix = "finance-import-batch:"
    raw = value.removeprefix(prefix)
    if not value.startswith(prefix) or not raw.isdecimal() or int(raw) <= 0:
        raise ValueError(f"{field_name} is invalid")
    return value


@dataclass(frozen=True, slots=True)
class FinanceImportSourceCorrectionLineage:
    """Immutable source-correction relation recorded by the owner Apply.

    Missing values deliberately mean that the correction is not terminal.  No
    identifier, version, or completion flag is inferred from a filename,
    amount, name, similarity, timestamp, receipt, or outbox event.
    """

    original_batch_identity: str
    original_batch_version: int
    corrected_successor_batch_identity: str | None = None
    corrected_successor_version: int | None = None
    successor_unique: bool = False
    successor_completed: bool = False
    successor_fresh_verified: bool = False
    successor_covers_all_current_problems: bool = False
    accepted_in_owner_uow: bool = False

    def __post_init__(self) -> None:
        _batch_identity(self.original_batch_identity, "original batch identity")
        require_nonnegative_integer(self.original_batch_version, "original batch version")
        if self.corrected_successor_batch_identity is not None:
            _batch_identity(
                self.corrected_successor_batch_identity,
                "corrected successor batch identity",
            )
            if self.corrected_successor_batch_identity == self.original_batch_identity:
                raise ValueError("source correction successor must be a new batch")
        if self.corrected_successor_version is not None:
            require_nonnegative_integer(
                self.corrected_successor_version,
                "corrected successor batch version",
            )
        for value, field_name in (
            (self.successor_unique, "successor unique"),
            (self.successor_completed, "successor completed"),
            (self.successor_fresh_verified, "successor fresh verified"),
            (self.successor_covers_all_current_problems, "successor coverage"),
            (self.accepted_in_owner_uow, "accepted in owner unit of work"),
        ):
            if type(value) is not bool:
                raise TypeError(f"{field_name} must be bool")
        if self.corrected_successor_batch_identity is None and self.corrected_successor_version is not None:
            raise ValueError("successor version requires successor identity")
        if self.corrected_successor_batch_identity is not None and self.corrected_successor_version is None:
            raise ValueError("successor identity requires successor version")

    @property
    def terminal(self) -> bool:
        return bool(
            self.corrected_successor_batch_identity
            and self.corrected_successor_version is not None
            and self.successor_unique
            and self.successor_completed
            and self.successor_fresh_verified
            and self.successor_covers_all_current_problems
            and self.accepted_in_owner_uow
        )

    @property
    def unresolved_reason_codes(self) -> tuple[FinanceImportIntegrityReason, ...]:
        reasons: list[FinanceImportIntegrityReason] = []
        if self.corrected_successor_batch_identity is None:
            reasons.append(FinanceImportIntegrityReason.SOURCE_CORRECTION_REQUIRED)
        if not self.successor_unique:
            reasons.append(FinanceImportIntegrityReason.SUCCESSOR_NOT_UNIQUE)
        if not self.successor_completed:
            reasons.append(FinanceImportIntegrityReason.SUCCESSOR_NOT_COMPLETED)
        if not self.successor_fresh_verified:
            reasons.append(FinanceImportIntegrityReason.SUCCESSOR_NOT_FRESH)
        if not self.successor_covers_all_current_problems:
            reasons.append(FinanceImportIntegrityReason.SUCCESSOR_INCOMPLETE)
        if not self.accepted_in_owner_uow:
            reasons.append(FinanceImportIntegrityReason.SOURCE_CORRECTION_REQUIRED)
        return tuple(dict.fromkeys(reasons))


@dataclass(frozen=True, slots=True)
class FinanceImportSourceCorrectionApplyRequest:
    """Closed Apply input for a corrected-source successor batch.

    The application layer must execute this request in the same owner UoW that
    accepts the successor batch.  This value contains no editable bank facts;
    those are supplied by the newly ingested immutable successor batch.
    """

    original_batch_identity: str
    expected_original_batch_version: int
    corrected_successor_batch_identity: str
    corrected_successor_batch_version: int
    actor: str
    reason: str
    evidence_reference: str

    def __post_init__(self) -> None:
        _batch_identity(self.original_batch_identity, "original batch identity")
        _batch_identity(
            self.corrected_successor_batch_identity,
            "corrected successor batch identity",
        )
        if self.original_batch_identity == self.corrected_successor_batch_identity:
            raise ValueError("source correction successor must be a new batch")
        require_nonnegative_integer(
            self.expected_original_batch_version,
            "expected original batch version",
        )
        require_nonnegative_integer(
            self.corrected_successor_batch_version,
            "corrected successor batch version",
        )
        _identity(self.actor, "source correction actor")
        require_canonical_text(self.reason, "source correction reason", 500)
        _identity(self.evidence_reference, "source correction evidence reference")


@dataclass(frozen=True, slots=True)
class FinanceImportSourceCorrectionIntent:
    """Explicit ingestion input for a corrected-source successor batch."""

    original_batch_identity: str
    original_batch_version: int
    reason: str
    evidence_reference: str

    def __post_init__(self) -> None:
        _batch_identity(self.original_batch_identity, "original batch identity")
        require_nonnegative_integer(self.original_batch_version, "original batch version")
        require_canonical_text(self.reason, "source correction reason", 500)
        _identity(self.evidence_reference, "source correction evidence reference")


def build_source_correction_lineage(
    request: FinanceImportSourceCorrectionApplyRequest,
    *,
    successor_unique: bool,
    successor_completed: bool,
    successor_fresh_verified: bool,
    successor_covers_all_current_problems: bool,
    accepted_in_owner_uow: bool,
) -> FinanceImportSourceCorrectionLineage:
    """Create the exact immutable relation after successor Apply verification."""

    if not isinstance(request, FinanceImportSourceCorrectionApplyRequest):
        raise TypeError("Finance Import source correction Apply request is required")
    return FinanceImportSourceCorrectionLineage(
        request.original_batch_identity,
        request.expected_original_batch_version,
        request.corrected_successor_batch_identity,
        request.corrected_successor_batch_version,
        successor_unique,
        successor_completed,
        successor_fresh_verified,
        successor_covers_all_current_problems,
        accepted_in_owner_uow,
    )


@dataclass(frozen=True, slots=True)
class FinanceImportIntegrityCounts:
    """Bounded root counts used to derive the IMPORT-006 predicate."""

    expected_occurrence_count: int
    occurrence_count: int
    distinct_canonical_count: int
    non_pending_inconsistent_count: int = 0
    partial_batch_count: int = 0

    def __post_init__(self) -> None:
        for value, field_name in (
            (self.expected_occurrence_count, "expected occurrence count"),
            (self.occurrence_count, "occurrence count"),
            (self.distinct_canonical_count, "distinct canonical count"),
            (self.non_pending_inconsistent_count, "non-pending inconsistent count"),
            (self.partial_batch_count, "partial batch count"),
        ):
            require_nonnegative_integer(value, field_name)
        if self.distinct_canonical_count > self.occurrence_count:
            raise ValueError("distinct canonical count exceeds occurrence count")

    @property
    def missing_occurrence_count(self) -> int:
        return max(self.expected_occurrence_count - self.occurrence_count, 0)

    @property
    def unexpected_occurrence_count(self) -> int:
        return max(self.occurrence_count - self.expected_occurrence_count, 0)

    @property
    def duplicate_occurrence_count(self) -> int:
        return self.occurrence_count - self.distinct_canonical_count

    @property
    def integrity_inconsistent_count(self) -> int:
        return (
            self.missing_occurrence_count
            + self.unexpected_occurrence_count
            + self.duplicate_occurrence_count
            + self.non_pending_inconsistent_count
            + self.partial_batch_count
        )


@dataclass(frozen=True, slots=True)
class FinanceImportIntegrityOwnerFact:
    """Fresh Finance Import fact consumed by the IMPORT-006 projection."""

    batch_identity: str
    batch_version: int
    owner_snapshot_token: str
    authoritative_complete: bool
    integrity_inconsistent_count: int
    canonical_roots_valid: bool = True
    projection_consistent: bool = True
    repair_path: FinanceImportIntegrityRepairPath = FinanceImportIntegrityRepairPath.DERIVED_REBUILD
    source_correction: FinanceImportSourceCorrectionLineage | None = None

    def __post_init__(self) -> None:
        _batch_identity(self.batch_identity)
        require_nonnegative_integer(self.batch_version, "batch version")
        _identity(self.owner_snapshot_token, "owner snapshot token")
        if type(self.authoritative_complete) is not bool:
            raise TypeError("authoritative complete must be bool")
        require_nonnegative_integer(
            self.integrity_inconsistent_count,
            "integrity inconsistent count",
        )
        if type(self.canonical_roots_valid) is not bool or type(self.projection_consistent) is not bool:
            raise TypeError("Finance Import integrity flags must be bool")
        if not isinstance(self.repair_path, FinanceImportIntegrityRepairPath):
            raise TypeError("Finance Import repair path is invalid")
        if self.source_correction is not None:
            if not isinstance(self.source_correction, FinanceImportSourceCorrectionLineage):
                raise TypeError("Finance Import source correction lineage is invalid")
            if self.source_correction.original_batch_identity != self.batch_identity:
                raise ValueError("source correction original batch mismatch")
            if self.source_correction.original_batch_version != self.batch_version:
                raise ValueError("source correction original version mismatch")
        if self.repair_path is FinanceImportIntegrityRepairPath.SOURCE_CORRECTION and self.source_correction is None:
            raise ValueError("source correction path requires immutable lineage")

    @property
    def owner_version(self) -> int:
        """Compatibility name used by generic owner-snapshot composition."""

        return self.batch_version

    @property
    def source_version(self) -> int:
        """The anomaly source version is always the Finance batch version."""

        return self.batch_version

    @property
    def batch_id(self) -> int:
        """Numeric identity for bounded SQL/current-issue adapters."""

        return int(self.batch_identity.removeprefix("finance-import-batch:"))

    @property
    def unresolved_reason_codes(self) -> tuple[FinanceImportIntegrityReason, ...]:
        reasons: list[FinanceImportIntegrityReason] = []
        if not self.authoritative_complete:
            reasons.append(FinanceImportIntegrityReason.OWNER_READBACK_INCOMPLETE)
        source_terminal = (
            self.repair_path is FinanceImportIntegrityRepairPath.SOURCE_CORRECTION
            and self.source_correction is not None
            and self.source_correction.terminal
        )
        # The original bad source remains immutable historical evidence.  Once
        # its explicitly linked successor has passed every terminal check, that
        # old inconsistency is no longer a current issue.
        if not source_terminal:
            if self.integrity_inconsistent_count > 0 or not self.canonical_roots_valid:
                reasons.append(FinanceImportIntegrityReason.INTEGRITY_INCONSISTENT)
            if not self.projection_consistent:
                reasons.append(FinanceImportIntegrityReason.PROJECTION_INCONSISTENT)
        if self.repair_path is FinanceImportIntegrityRepairPath.STRUCTURAL_AMBIGUITY:
            reasons.append(FinanceImportIntegrityReason.STRUCTURAL_AMBIGUITY)
        if self.repair_path is FinanceImportIntegrityRepairPath.SOURCE_CORRECTION:
            assert self.source_correction is not None
            reasons.extend(self.source_correction.unresolved_reason_codes)
        return tuple(dict.fromkeys(reasons))

    @property
    def predicate_active(self) -> bool:
        return bool(self.unresolved_reason_codes)

    @property
    def repair_is_deterministic_rebuild(self) -> bool:
        return self.repair_path is FinanceImportIntegrityRepairPath.DERIVED_REBUILD and self.canonical_roots_valid


def build_finance_import_integrity_owner_fact(
    batch_identity: str,
    batch_version: int,
    owner_snapshot_token: str,
    counts: FinanceImportIntegrityCounts,
    *,
    authoritative_complete: bool = True,
    canonical_roots_valid: bool = True,
    projection_consistent: bool = True,
    repair_path: FinanceImportIntegrityRepairPath = FinanceImportIntegrityRepairPath.DERIVED_REBUILD,
    source_correction: FinanceImportSourceCorrectionLineage | None = None,
) -> FinanceImportIntegrityOwnerFact:
    if not isinstance(counts, FinanceImportIntegrityCounts):
        raise TypeError("Finance Import integrity counts are required")
    return FinanceImportIntegrityOwnerFact(
        batch_identity,
        batch_version,
        owner_snapshot_token,
        authoritative_complete,
        counts.integrity_inconsistent_count,
        canonical_roots_valid,
        projection_consistent,
        repair_path,
        source_correction,
    )


def finance_import_integrity_predicate(fact: FinanceImportIntegrityOwnerFact) -> bool:
    """Return the current owner predicate; never consult alert workflow state."""

    if not isinstance(fact, FinanceImportIntegrityOwnerFact):
        raise TypeError("Finance Import integrity owner fact is required")
    return fact.predicate_active


def finance_import_integrity_fingerprint(fact: FinanceImportIntegrityOwnerFact) -> PreviewFingerprint:
    """Build a deterministic fingerprint for one fresh owner snapshot."""

    if not isinstance(fact, FinanceImportIntegrityOwnerFact):
        raise TypeError("Finance Import integrity owner fact is required")
    lineage = fact.source_correction
    payload = {
        "batch_identity": fact.batch_identity,
        "batch_version": fact.batch_version,
        "owner_snapshot_token": fact.owner_snapshot_token,
        "authoritative_complete": fact.authoritative_complete,
        "integrity_inconsistent_count": fact.integrity_inconsistent_count,
        "canonical_roots_valid": fact.canonical_roots_valid,
        "projection_consistent": fact.projection_consistent,
        "repair_path": fact.repair_path.value,
        "source_correction": None
        if lineage is None
        else {
            "original_batch_identity": lineage.original_batch_identity,
            "original_batch_version": lineage.original_batch_version,
            "corrected_successor_batch_identity": lineage.corrected_successor_batch_identity,
            "corrected_successor_version": lineage.corrected_successor_version,
            "successor_unique": lineage.successor_unique,
            "successor_completed": lineage.successor_completed,
            "successor_fresh_verified": lineage.successor_fresh_verified,
            "successor_covers_all_current_problems": lineage.successor_covers_all_current_problems,
            "accepted_in_owner_uow": lineage.accepted_in_owner_uow,
        },
    }
    return fingerprint_payload(payload)


# Names used by owner-specific current-fact consumers.
__all__ = [
    "FinanceImportIntegrityCounts",
    "FinanceImportIntegrityOwnerFact",
    "FinanceImportIntegrityReason",
    "FinanceImportIntegrityRepairPath",
    "FinanceImportSourceCorrectionApplyRequest",
    "FinanceImportSourceCorrectionIntent",
    "FinanceImportSourceCorrectionLineage",
    "build_source_correction_lineage",
    "build_finance_import_integrity_owner_fact",
    "finance_import_integrity_fingerprint",
    "finance_import_integrity_predicate",
]
