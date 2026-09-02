"""Read immutable Historical Orders adoption source evidence without replaying import logic."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal, Protocol

from shared_kernel.validation import require_canonical_text


HistoricalPairingResolution = Literal[
    "evidence_only",
    "assignment_candidate",
    "assignment_reused",
]
EvidenceAvailability = Literal["available", "unavailable"]


@dataclass(frozen=True, slots=True)
class HistoricalAdoptionPairedStaffEvidence:
    caregiver_ordinal: int
    masked_staff_name: str
    staff_id: int
    resolution: HistoricalPairingResolution
    source_start_date: date | None
    source_end_date: date | None
    assignment_id: int | None


@dataclass(frozen=True, slots=True)
class HistoricalOrderAdoptionEvidence:
    case_no: str
    receipt_id: int
    receipt_identity: str
    source_identity: str
    source_fingerprint: str
    preview_fingerprint: str
    evidence_owner: str
    historical_source_status: str | None
    operational_baseline_step: int | None
    source_start_date: date | None
    source_end_date: date | None
    source_period_availability: EvidenceAvailability
    paired_staff: tuple[HistoricalAdoptionPairedStaffEvidence, ...]
    paired_staff_availability: EvidenceAvailability


class HistoricalOrderAdoptionEvidenceRepository(Protocol):
    def fetch_latest_adopted(
        self,
        case_no: str,
    ) -> HistoricalOrderAdoptionEvidence | None: ...


class HistoricalOrderAdoptionEvidenceNotFound(LookupError):
    pass


def query_historical_order_adoption_evidence(
    repository: HistoricalOrderAdoptionEvidenceRepository,
    case_no: str,
) -> HistoricalOrderAdoptionEvidence:
    canonical_case_no = require_canonical_text(case_no, "case_no", 50)
    evidence = repository.fetch_latest_adopted(canonical_case_no)
    if evidence is None:
        raise HistoricalOrderAdoptionEvidenceNotFound(
            "historical_order_adoption_evidence_not_found"
        )
    if evidence.case_no != canonical_case_no:
        raise ValueError("historical_order_adoption_evidence_case_mismatch")
    if evidence.receipt_id <= 0:
        raise ValueError("historical_order_adoption_evidence_receipt_invalid")
    if evidence.operational_baseline_step is not None and not (
        1 <= evidence.operational_baseline_step <= 11
    ):
        raise ValueError("historical_order_adoption_evidence_baseline_step_invalid")
    if (
        evidence.source_start_date is not None
        and evidence.source_end_date is not None
        and evidence.source_start_date > evidence.source_end_date
    ):
        raise ValueError("historical_order_adoption_evidence_period_invalid")
    return evidence


__all__ = [
    "EvidenceAvailability",
    "HistoricalAdoptionPairedStaffEvidence",
    "HistoricalOrderAdoptionEvidence",
    "HistoricalOrderAdoptionEvidenceNotFound",
    "HistoricalOrderAdoptionEvidenceRepository",
    "HistoricalPairingResolution",
    "query_historical_order_adoption_evidence",
]
