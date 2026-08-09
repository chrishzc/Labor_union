"""Typed outcomes for provisional LINE registration."""

from __future__ import annotations

from dataclasses import dataclass


class ProvisionalRegistrationConflictError(RuntimeError):
    """The LINE identity already owns a different active registration."""


@dataclass(frozen=True, slots=True)
class ProvisionalRegistrationConflict:
    registration_id: int
    conflict_id: int


@dataclass(frozen=True, slots=True)
class ProvisionalRegistrationReceipt:
    registration_id: int
    client_id: int
    beclass_record_id: int
    client_name: str
    replayed: bool
    worker_wakeup_required: bool


__all__ = [
    "ProvisionalRegistrationConflict",
    "ProvisionalRegistrationConflictError",
    "ProvisionalRegistrationReceipt",
]
