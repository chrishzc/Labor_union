"""Pure staff unavailability rules for matching and calendar availability."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from enum import StrEnum

from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.validation import (
    require_canonical_text,
    require_nonnegative_integer,
    require_positive_integer,
)

_REASON_MAXIMUM_LENGTH = 500


class StaffAvailabilityAction(StrEnum):
    CREATE_LONG_LEAVE = "create_long_leave"
    CREATE_PAUSE = "create_pause"
    END_PAUSE = "end_pause"
    CANCEL = "cancel"


class StaffUnavailabilityKind(StrEnum):
    LONG_LEAVE = "long_leave"
    PAUSED_SERVICE = "paused_service"


class StaffAvailabilityBlockStatus(StrEnum):
    EFFECTIVE = "effective"
    CANCELLED = "cancelled"


class StaffAvailabilityErrorCode(StrEnum):
    INVALID_INTENT = "invalid_staff_availability_intent"
    STAFF_NOT_FOUND = "staff_availability_staff_not_found"
    BLOCK_NOT_FOUND = "staff_availability_block_not_found"
    OVERLAP = "staff_unavailability_overlap"
    ASSIGNMENT_CONFLICT = "staff_unavailability_assignment_conflict"
    WAITING_LOCK_CONFLICT = "staff_unavailability_waiting_lock_conflict"
    BUFFER_CONFLICT = "staff_unavailability_buffer_conflict"
    STALE = "staff_availability_stale"
    IDEMPOTENCY_CONFLICT = "staff_availability_idempotency_conflict"
    TRANSACTION_FAILED = "staff_availability_transaction_failed"


class StaffAvailabilityDomainError(ValueError):
    def __init__(
        self,
        code: StaffAvailabilityErrorCode,
        blockers: tuple[str, ...] = (),
    ) -> None:
        self.code = code
        self.blockers = blockers or (code.value,)
        super().__init__(code.value)


@dataclass(frozen=True, slots=True)
class StaffAvailabilityIntent:
    action: StaffAvailabilityAction
    staff_id: int
    reason: str
    start_date: date | None = None
    end_date: date | None = None
    block_id: int | None = None
    resume_date: date | None = None

    def __post_init__(self) -> None:
        _validate_intent_identity(self)
        _validate_intent_shape(self)


@dataclass(frozen=True, slots=True)
class StaffUnavailabilityBlock:
    block_id: int
    staff_id: int
    kind: StaffUnavailabilityKind
    start_date: date
    end_date: date | None
    status: StaffAvailabilityBlockStatus
    reason: str

    def __post_init__(self) -> None:
        require_positive_integer(self.block_id, "availability block id")
        require_positive_integer(self.staff_id, "availability block staff id")
        _require_date(self.start_date, "availability block start date")
        _require_optional_date(self.end_date, "availability block end date")
        require_canonical_text(self.reason, "availability block reason", _REASON_MAXIMUM_LENGTH)
        _validate_block_dates(self.kind, self.start_date, self.end_date)


@dataclass(frozen=True, slots=True)
class StaffAvailabilityConflict:
    source_kind: str
    source_identity: str
    start_date: date
    end_date: date

    def __post_init__(self) -> None:
        require_canonical_text(self.source_kind, "conflict source kind", 100)
        require_canonical_text(self.source_identity, "conflict source identity", 191)
        _require_date(self.start_date, "conflict start date")
        _require_date(self.end_date, "conflict end date")
        if self.end_date < self.start_date:
            raise ValueError("conflict interval is inverted")


@dataclass(frozen=True, slots=True)
class StaffAvailabilityFacts:
    staff_id: int
    aggregate_version: int
    blocks: tuple[StaffUnavailabilityBlock, ...]
    conflicts: tuple[StaffAvailabilityConflict, ...]
    target_block: StaffUnavailabilityBlock | None = None

    def __post_init__(self) -> None:
        require_positive_integer(self.staff_id, "availability facts staff id")
        require_nonnegative_integer(self.aggregate_version, "staff availability version")
        _validate_fact_ownership(self)


@dataclass(frozen=True, slots=True)
class StaffAvailabilityCandidate:
    kind: StaffUnavailabilityKind
    start_date: date
    end_date: date | None
    status: StaffAvailabilityBlockStatus


@dataclass(frozen=True, slots=True)
class StaffAvailabilityPreview:
    staff_id: int
    action: StaffAvailabilityAction
    source_version: int
    target_block: StaffUnavailabilityBlock | None
    candidate: StaffAvailabilityCandidate | None
    blockers: tuple[str, ...]
    can_apply: bool
    preview_fingerprint: PreviewFingerprint


def build_staff_availability_preview(
    intent: StaffAvailabilityIntent,
    facts: StaffAvailabilityFacts,
) -> StaffAvailabilityPreview:
    if facts.staff_id != intent.staff_id:
        raise StaffAvailabilityDomainError(StaffAvailabilityErrorCode.INVALID_INTENT)
    target = _required_target(intent, facts.target_block)
    candidate = _candidate(intent, target)
    blockers = _blockers(intent, facts)
    fingerprint = fingerprint_payload(_preview_payload(intent, facts, target, candidate, blockers))
    return StaffAvailabilityPreview(
        intent.staff_id,
        intent.action,
        facts.aggregate_version,
        target,
        candidate,
        blockers,
        not blockers,
        fingerprint,
    )


def _validate_intent_identity(intent: StaffAvailabilityIntent) -> None:
    if not isinstance(intent.action, StaffAvailabilityAction):
        raise TypeError("staff availability action is invalid")
    require_positive_integer(intent.staff_id, "staff availability staff id")
    require_canonical_text(intent.reason, "staff availability reason", _REASON_MAXIMUM_LENGTH)


def _validate_intent_shape(intent: StaffAvailabilityIntent) -> None:
    validators = {
        StaffAvailabilityAction.CREATE_LONG_LEAVE: _validate_create_long_leave,
        StaffAvailabilityAction.CREATE_PAUSE: _validate_create_pause,
        StaffAvailabilityAction.END_PAUSE: _validate_end_pause,
        StaffAvailabilityAction.CANCEL: _validate_cancel,
    }
    validators[intent.action](intent)


def _validate_create_long_leave(intent: StaffAvailabilityIntent) -> None:
    _require_date(intent.start_date, "long leave start date")
    _require_date(intent.end_date, "long leave end date")
    _require_absent_command_fields(intent, ("block_id", "resume_date"))
    _validate_block_dates(StaffUnavailabilityKind.LONG_LEAVE, intent.start_date, intent.end_date)


def _validate_create_pause(intent: StaffAvailabilityIntent) -> None:
    _require_date(intent.start_date, "pause start date")
    _require_absent_command_fields(intent, ("end_date", "block_id", "resume_date"))


def _validate_end_pause(intent: StaffAvailabilityIntent) -> None:
    require_positive_integer(intent.block_id, "pause block id")
    _require_date(intent.resume_date, "pause resume date")
    _require_absent_command_fields(intent, ("start_date", "end_date"))


def _validate_cancel(intent: StaffAvailabilityIntent) -> None:
    require_positive_integer(intent.block_id, "cancel block id")
    _require_absent_command_fields(intent, ("start_date", "end_date", "resume_date"))


def _require_absent_command_fields(intent, field_names) -> None:
    if any(getattr(intent, name) is not None for name in field_names):
        raise StaffAvailabilityDomainError(StaffAvailabilityErrorCode.INVALID_INTENT)


def _required_target(intent, target):
    if intent.action in {StaffAvailabilityAction.CREATE_LONG_LEAVE, StaffAvailabilityAction.CREATE_PAUSE}:
        return None
    if target is None or target.block_id != intent.block_id or target.staff_id != intent.staff_id:
        raise StaffAvailabilityDomainError(StaffAvailabilityErrorCode.BLOCK_NOT_FOUND)
    if target.status is not StaffAvailabilityBlockStatus.EFFECTIVE:
        raise StaffAvailabilityDomainError(StaffAvailabilityErrorCode.BLOCK_NOT_FOUND)
    return target


def _candidate(intent, target):
    if intent.action is StaffAvailabilityAction.CREATE_LONG_LEAVE:
        return StaffAvailabilityCandidate(
            StaffUnavailabilityKind.LONG_LEAVE,
            intent.start_date,
            intent.end_date,
            StaffAvailabilityBlockStatus.EFFECTIVE,
        )
    if intent.action is StaffAvailabilityAction.CREATE_PAUSE:
        return StaffAvailabilityCandidate(
            StaffUnavailabilityKind.PAUSED_SERVICE,
            intent.start_date,
            None,
            StaffAvailabilityBlockStatus.EFFECTIVE,
        )
    if intent.action is StaffAvailabilityAction.END_PAUSE:
        return _ended_pause_candidate(intent, target)
    return None


def _ended_pause_candidate(intent, target):
    if target.kind is not StaffUnavailabilityKind.PAUSED_SERVICE or target.end_date is not None:
        raise StaffAvailabilityDomainError(StaffAvailabilityErrorCode.INVALID_INTENT)
    end_date = intent.resume_date - timedelta(days=1)
    if end_date < target.start_date:
        raise StaffAvailabilityDomainError(StaffAvailabilityErrorCode.INVALID_INTENT)
    return StaffAvailabilityCandidate(target.kind, target.start_date, end_date, target.status)


def _blockers(intent, facts):
    if intent.action not in {StaffAvailabilityAction.CREATE_LONG_LEAVE, StaffAvailabilityAction.CREATE_PAUSE}:
        return ()
    return tuple(sorted({_conflict_blocker(item) for item in facts.conflicts}))


def _conflict_blocker(conflict):
    return (
        f"{conflict.source_kind}:{conflict.source_identity}:"
        f"{conflict.start_date.isoformat()}:{conflict.end_date.isoformat()}"
    )


def error_code_for_blockers(blockers: tuple[str, ...]) -> StaffAvailabilityErrorCode:
    kinds = {value.split(":", 1)[0] for value in blockers}
    if "assignment" in kinds:
        return StaffAvailabilityErrorCode.ASSIGNMENT_CONFLICT
    if "waiting_lock" in kinds:
        return StaffAvailabilityErrorCode.WAITING_LOCK_CONFLICT
    if "buffer" in kinds:
        return StaffAvailabilityErrorCode.BUFFER_CONFLICT
    return StaffAvailabilityErrorCode.OVERLAP


def _preview_payload(intent, facts, target, candidate, blockers):
    return {
        "contract_version": "staff-availability-v1",
        "intent": _intent_payload(intent),
        "source_version": facts.aggregate_version,
        "target": _block_payload(target),
        "candidate": _candidate_payload(candidate),
        "blockers": blockers,
    }


def _intent_payload(intent):
    return {
        "action": intent.action.value,
        "staff_id": intent.staff_id,
        "reason": intent.reason,
        "start_date": _date_text(intent.start_date),
        "end_date": _date_text(intent.end_date),
        "block_id": intent.block_id,
        "resume_date": _date_text(intent.resume_date),
    }


def _block_payload(block):
    if block is None:
        return None
    return {
        "block_id": block.block_id,
        "staff_id": block.staff_id,
        "kind": block.kind.value,
        "start_date": block.start_date.isoformat(),
        "end_date": _date_text(block.end_date),
        "status": block.status.value,
        "reason": block.reason,
    }


def _candidate_payload(candidate):
    if candidate is None:
        return None
    return {
        "kind": candidate.kind.value,
        "start_date": candidate.start_date.isoformat(),
        "end_date": _date_text(candidate.end_date),
        "status": candidate.status.value,
    }


def _validate_fact_ownership(facts):
    if any(block.staff_id != facts.staff_id for block in facts.blocks):
        raise ValueError("availability block belongs to another staff")
    if facts.target_block is not None and facts.target_block.staff_id != facts.staff_id:
        raise ValueError("target availability block belongs to another staff")


def _validate_block_dates(kind, start_date, end_date):
    if end_date is not None and end_date < start_date:
        raise StaffAvailabilityDomainError(StaffAvailabilityErrorCode.INVALID_INTENT)
    if kind is StaffUnavailabilityKind.LONG_LEAVE and end_date is None:
        raise StaffAvailabilityDomainError(StaffAvailabilityErrorCode.INVALID_INTENT)


def _require_date(value, label):
    if type(value) is not date:
        raise TypeError(f"{label} must be a date")


def _require_optional_date(value, label):
    if value is not None:
        _require_date(value, label)


def _date_text(value):
    return value.isoformat() if value is not None else None


__all__ = [
    "StaffAvailabilityAction",
    "StaffAvailabilityBlockStatus",
    "StaffAvailabilityCandidate",
    "StaffAvailabilityConflict",
    "StaffAvailabilityDomainError",
    "StaffAvailabilityErrorCode",
    "StaffAvailabilityFacts",
    "StaffAvailabilityIntent",
    "StaffAvailabilityPreview",
    "StaffUnavailabilityBlock",
    "StaffUnavailabilityKind",
    "build_staff_availability_preview",
    "error_code_for_blockers",
]
