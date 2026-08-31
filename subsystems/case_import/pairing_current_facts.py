"""Case Import-owned current facts for exact HCM/Client BeClass pairing."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from shared_kernel.validation import require_canonical_text, require_nonnegative_integer

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


__all__ = [name for name in globals() if name.startswith("Case") or name.startswith("Hcm") or name.startswith("BeClass")]
