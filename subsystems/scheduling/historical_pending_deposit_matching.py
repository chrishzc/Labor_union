"""Typed Scheduling port for adopting a historical pending-deposit match."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from shared_kernel.validation import require_canonical_text


@dataclass(frozen=True, slots=True)
class HistoricalPendingDepositMatchCommand:
    case_no: str
    staff_id: int
    actor: str
    source_identity: str

    def __post_init__(self) -> None:
        require_canonical_text(self.case_no, "case number", 50)
        if isinstance(self.staff_id, bool) or not isinstance(self.staff_id, int) or self.staff_id <= 0:
            raise ValueError("historical matching staff id must be positive")
        require_canonical_text(self.actor, "historical matching actor", 100)
        require_canonical_text(self.source_identity, "historical source identity", 191)


@dataclass(frozen=True, slots=True)
class HistoricalPendingDepositMatchReceipt:
    case_no: str
    plan_id: int
    plan_version: int
    staff_id: int
    created: bool

    def __post_init__(self) -> None:
        require_canonical_text(self.case_no, "case number", 50)
        for value, name in (
            (self.plan_id, "historical matching plan id"),
            (self.plan_version, "historical matching plan version"),
            (self.staff_id, "historical matching staff id"),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{name} must be positive")
        if not isinstance(self.created, bool):
            raise TypeError("historical matching created flag must be bool")


class HistoricalPendingDepositMatchingPort(Protocol):
    """Write one formal proposed Matching plan in the caller-owned UoW."""

    def ensure_pending_deposit_match(
        self,
        command: HistoricalPendingDepositMatchCommand,
    ) -> HistoricalPendingDepositMatchReceipt: ...


__all__ = [
    "HistoricalPendingDepositMatchCommand",
    "HistoricalPendingDepositMatchReceipt",
    "HistoricalPendingDepositMatchingPort",
]
