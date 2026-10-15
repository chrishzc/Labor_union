"""Validate that an execution candidate exactly realizes one commitment."""

from __future__ import annotations

from dataclasses import dataclass
from collections import Counter
from datetime import date


class CommitmentExecutionMismatch(ValueError):
    """The execution candidate does not preserve the commitment root facts."""


@dataclass(frozen=True, slots=True)
class CommitmentServiceDay:
    staff_id: int
    service_date: date


@dataclass(frozen=True, slots=True)
class ExecutionServiceDay:
    staff_id: int
    service_date: date


def require_exact_commitment_execution(
    commitment_plan_id: int,
    lock_plan_ids: tuple[int, ...],
    commitment_days: tuple[CommitmentServiceDay, ...],
    execution_days: tuple[ExecutionServiceDay, ...],
    *,
    confirmed_days: tuple[ExecutionServiceDay, ...] | None = None,
) -> None:
    """Preserve signed people/volume; a date shift requires current confirmations."""
    if not lock_plan_ids or set(lock_plan_ids) != {commitment_plan_id}:
        raise CommitmentExecutionMismatch("commitment_execution_mismatch")
    signed = _day_identities(commitment_days)
    execution = _day_identities(execution_days)
    if signed == execution:
        return
    if (
        not signed
        or confirmed_days is None
        or execution != _day_identities(confirmed_days)
        or Counter(staff for staff, _ in signed) != Counter(staff for staff, _ in execution)
    ):
        raise CommitmentExecutionMismatch("commitment_execution_mismatch")


def _day_identities(days):
    identities = tuple(sorted((day.staff_id, day.service_date) for day in days))
    if len(identities) != len(set(identities)):
        raise CommitmentExecutionMismatch("commitment_execution_mismatch")
    return identities
