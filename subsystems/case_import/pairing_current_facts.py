"""Case Import-owned current facts for exact HCM/Client BeClass pairing."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from shared_kernel.validation import require_canonical_text, require_nonnegative_integer

CASE_PAIRING_ANOMALY_OWNER_DOMAIN = "case_import"
CASE_PAIRING_ANOMALY_OWNER_ROOT_TYPE = "case_pairing_current_fact"


class CasePairingCurrentIssueCode(StrEnum):
    HCM_COUNTERPART_MISSING = "BECLASS-001"
    BECLASS_COUNTERPART_MISSING = "IMPORT-003"


class CasePairingCurrentFactReason(StrEnum):
    COUNTERPART_MISSING = "counterpart_missing"
    COUNTERPART_AMBIGUOUS = "counterpart_ambiguous"
    MAPPING_CONFLICT = "mapping_conflict"
    OWNER_READBACK_INCOMPLETE = "owner_readback_incomplete"


@dataclass(frozen=True, slots=True)
class HcmCounterpartCurrentFact:
    case_no: str
    owner_snapshot_token: str
    owner_version: int
    authoritative_complete: bool
    counterpart_count: int
    accepted_mapping_consistent: bool

    def __post_init__(self) -> None:
        _validate_common(self.case_no, self.owner_snapshot_token, self.owner_version, self.authoritative_complete)
        require_nonnegative_integer(self.counterpart_count, "counterpart count")
        _bool(self.accepted_mapping_consistent)

    @property
    def unresolved_reason_codes(self):
        return _reasons(self.authoritative_complete, self.counterpart_count, self.accepted_mapping_consistent)

    @property
    def predicate_active(self) -> bool:
        return bool(self.unresolved_reason_codes)


@dataclass(frozen=True, slots=True)
class BeClassCounterpartCurrentFact:
    entity_kind: str
    review_item_id: str
    owner_snapshot_token: str
    owner_version: int
    authoritative_complete: bool
    counterpart_count: int
    accepted_mapping_consistent: bool

    def __post_init__(self) -> None:
        _validate_common(self.entity_kind, self.owner_snapshot_token, self.owner_version, self.authoritative_complete)
        require_canonical_text(self.review_item_id, "review item id", 191)
        require_nonnegative_integer(self.counterpart_count, "counterpart count")
        _bool(self.accepted_mapping_consistent)

    @property
    def unresolved_reason_codes(self):
        return _reasons(self.authoritative_complete, self.counterpart_count, self.accepted_mapping_consistent)

    @property
    def predicate_active(self) -> bool:
        return bool(self.unresolved_reason_codes)


CasePairingCurrentFact = HcmCounterpartCurrentFact | BeClassCounterpartCurrentFact


@dataclass(frozen=True, slots=True)
class CasePairingAnomalyRecheckRequest:
    definition_code: CasePairingCurrentIssueCode
    subject_ids: tuple[str, ...]
    owner_root_ids: tuple[str, ...]
    owner_version: int
    owner_snapshot_token: str
    intent_identity: str

    def __post_init__(self) -> None:
        if not self.subject_ids or self.subject_ids != tuple(sorted(set(self.subject_ids))):
            raise ValueError("case pairing recheck subjects must be sorted and unique")
        if not self.owner_root_ids or self.owner_root_ids != tuple(sorted(set(self.owner_root_ids))):
            raise ValueError("case pairing recheck roots must be sorted and unique")
        for value in (*self.subject_ids, *self.owner_root_ids):
            require_canonical_text(value, "case pairing recheck identity", 191)
        require_nonnegative_integer(self.owner_version, "owner version")
        require_canonical_text(self.owner_snapshot_token, "owner snapshot token", 191)
        require_canonical_text(self.intent_identity, "recheck intent identity", 191)


def hcm_counterpart_recheck(case_no: str, version: int, token: str, identity: str):
    require_canonical_text(case_no, "case number", 50)
    return CasePairingAnomalyRecheckRequest(CasePairingCurrentIssueCode.HCM_COUNTERPART_MISSING, (case_no,), ("case:" + case_no,), version, token, identity)


def beclass_counterpart_recheck(entity_kind: str, review_item_id: str, version: int, token: str, identity: str):
    require_canonical_text(entity_kind, "entity kind", 50)
    require_canonical_text(review_item_id, "review item id", 191)
    return CasePairingAnomalyRecheckRequest(CasePairingCurrentIssueCode.BECLASS_COUNTERPART_MISSING, (entity_kind + ":" + review_item_id,), ("review:" + review_item_id,), version, token, identity)


def _reasons(complete, count, consistent):
    reasons = []
    if not complete:
        reasons.append(CasePairingCurrentFactReason.OWNER_READBACK_INCOMPLETE)
    if count == 0:
        reasons.append(CasePairingCurrentFactReason.COUNTERPART_MISSING)
    elif count > 1:
        reasons.append(CasePairingCurrentFactReason.COUNTERPART_AMBIGUOUS)
    elif not consistent:
        reasons.append(CasePairingCurrentFactReason.MAPPING_CONFLICT)
    return tuple(reasons)


def _validate_common(identity, token, version, complete):
    require_canonical_text(identity, "case pairing identity", 191)
    require_canonical_text(token, "owner snapshot token", 191)
    require_nonnegative_integer(version, "owner version")
    _bool(complete)


def _bool(value):
    if type(value) is not bool:
        raise TypeError("case pairing current-fact flags must be bool")


__all__ = [name for name in globals() if name.startswith("Case") or name.startswith("Hcm") or name.startswith("BeClass") or name.startswith("CASE_") or name.endswith("_recheck")]
