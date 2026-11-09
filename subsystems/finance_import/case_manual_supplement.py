"""Typed manual-source command; delegates financial effects to owning workflows."""
from __future__ import annotations
from dataclasses import asdict, dataclass
from datetime import date
from typing import Protocol
from shared_kernel.fingerprints import fingerprint_payload
from shared_kernel.validation import require_canonical_text, require_positive_integer


class ManualSupplementConflict(ValueError):
    """The operation key belongs to another immutable command."""


@dataclass(frozen=True)
class ManualSupplementCommand:
    case_no: str
    bank: str
    direction: str
    target_item: str
    amount_ntd: int
    transaction_date: str
    reason: str | None
    actor: str
    settlement_mode: str = "exact"


@dataclass(frozen=True)
class ManualSupplementResult:
    case_no: str
    row_id: int
    entry_id: int
    direction: str
    target_item: str
    amount_ntd: int
    reconciled: bool


class ManualSupplementPort(Protocol):
    def lock_case(self, case_no: str) -> None: ...
    def reserve_or_replay(self, key: str, digest: str) -> ManualSupplementResult | None: ...
    def reconcile(self, command: ManualSupplementCommand, key: str, digest: str) -> ManualSupplementResult: ...


class CaseManualSupplementService:
    """Caller owns the outer commit: source, child writer and receipt."""

    def __init__(self, repository: ManualSupplementPort):
        self.repository = repository

    def execute(self, case_no, bank, direction, target_item, amount_ntd,
                transaction_date, reason, idempotency_key, actor, settlement_mode="exact"):
        if bank not in {"sinopac", "taishin"}:
            raise ValueError("invalid_manual_bank")
        if direction not in {"client_receipt", "staff_salary", "client_refund", "government_subsidy"}:
            raise ValueError("invalid_manual_direction")
        if settlement_mode not in {"exact", "partial", "overage"}:
            raise ValueError("invalid_manual_settlement_mode")
        require_positive_integer(amount_ntd, "manual amount")
        for value, label, maximum in ((case_no, "case", 191), (target_item, "target", 191),
                                      (actor, "actor", 100), (idempotency_key, "key", 191)):
            require_canonical_text(value, label, maximum)
        if date.fromisoformat(transaction_date).isoformat() != transaction_date:
            raise ValueError("invalid_manual_transaction_date")
        if reason is not None:
            require_canonical_text(reason, "reason", 500, allow_empty=True)
        command = ManualSupplementCommand(case_no, bank, direction, target_item, amount_ntd,
                                          transaction_date, reason, actor, settlement_mode)
        digest = fingerprint_payload(asdict(command)).value
        replay = self.repository.reserve_or_replay(idempotency_key, digest)
        if replay is not None:
            return replay
        self.repository.lock_case(case_no)
        return self.repository.reconcile(command, idempotency_key, digest)
