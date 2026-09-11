"""Staff-owned Query/Preview/Apply workflow for personal and contact facts."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Callable, Protocol

from domains.staff.profile import STAFF_PROFILE_FIELDS, normalize_staff_profile_changes
from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey


_COMMAND_FAMILY = "staff_profile_change/v1"


class StaffProfileMutationNotFound(LookupError):
    pass


class StaffProfileMutationConflict(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class StaffProfileSnapshot:
    staff_id: int
    version: int
    values: Mapping[str, str | None]


@dataclass(frozen=True, slots=True)
class StaffProfileMutationPreview:
    staff_id: int
    current_version: int
    before: Mapping[str, str | None]
    after: Mapping[str, str | None]
    preview_fingerprint: PreviewFingerprint


@dataclass(frozen=True, slots=True)
class StaffProfileMutationReceipt:
    staff_id: int
    resulting_version: int
    changed_fields: tuple[str, ...]
    preview_fingerprint: PreviewFingerprint
    idempotency_key: IdempotencyKey
    replayed: bool
    readback: StaffProfileSnapshot


class StaffProfileMutationRepository(Protocol):
    def load(self, staff_id: int, *, for_update: bool) -> Mapping[str, Any] | None: ...
    def claim(self, *, staff_id: int, key: IdempotencyKey, command_fingerprint: PreviewFingerprint, correlation_id: CorrelationId) -> None: ...
    def load_receipt(self, key: IdempotencyKey, *, for_update: bool) -> Mapping[str, Any] | None: ...
    def persist(self, *, snapshot: StaffProfileSnapshot, changes: Mapping[str, str | None], actor: ActorContext, reason: str, key: IdempotencyKey, correlation_id: CorrelationId) -> int: ...
    def save_receipt(self, *, key: IdempotencyKey, command_fingerprint: PreviewFingerprint, preview_fingerprint: PreviewFingerprint, actor: ActorContext, reason: str, result: Mapping[str, Any]) -> None: ...


class StaffProfileMutationWorkflow:
    def __init__(self, repository: StaffProfileMutationRepository, unit_of_work_factory: Callable[[], Any]) -> None:
        self._repository = repository
        self._unit_of_work_factory = unit_of_work_factory

    def query(self, staff_id: int) -> StaffProfileSnapshot:
        return _snapshot(self._require(self._repository.load(_staff_id(staff_id), for_update=False)))

    def preview(self, staff_id: int, changes: Mapping[str, object], expected_version: ExpectedVersion) -> StaffProfileMutationPreview:
        snapshot = self.query(staff_id)
        normalized = normalize_staff_profile_changes(changes)
        return self._preview(snapshot, normalized, expected_version)

    def apply(
        self,
        staff_id: int,
        changes: Mapping[str, object],
        expected_version: ExpectedVersion,
        preview_fingerprint: PreviewFingerprint,
        idempotency_key: IdempotencyKey,
        actor: ActorContext,
        reason: str,
        correlation_id: CorrelationId,
    ) -> StaffProfileMutationReceipt:
        identity = _staff_id(staff_id)
        normalized = normalize_staff_profile_changes(changes)
        clean_reason = reason.strip()
        if not clean_reason:
            raise ValueError("staff_profile_reason_required")
        command_fingerprint = fingerprint_payload({
            "family": _COMMAND_FAMILY,
            "staff_id": identity,
            "changes": normalized,
            "expected_version": expected_version.value,
            "preview_fingerprint": preview_fingerprint.value,
            "actor": actor.actor_id,
            "reason": clean_reason,
        })
        with self._unit_of_work_factory() as unit_of_work:
            self._repository.claim(
                staff_id=identity,
                key=idempotency_key,
                command_fingerprint=command_fingerprint,
                correlation_id=correlation_id,
            )
            replay = self._repository.load_receipt(idempotency_key, for_update=True)
            if replay is not None:
                if str(replay["request_fingerprint"]) != command_fingerprint.value:
                    raise StaffProfileMutationConflict("idempotency_mismatch")
                fresh = _snapshot(self._require(self._repository.load(identity, for_update=False)))
                unit_of_work.commit()
                return _receipt(replay["result"], preview_fingerprint, idempotency_key, True, fresh)
            snapshot = _snapshot(self._require(self._repository.load(identity, for_update=True)))
            preview = self._preview(snapshot, normalized, expected_version)
            if preview.preview_fingerprint != preview_fingerprint:
                raise StaffProfileMutationConflict("staff_profile_stale_preview")
            resulting_version = self._repository.persist(
                snapshot=snapshot,
                changes=normalized,
                actor=actor,
                reason=clean_reason,
                key=idempotency_key,
                correlation_id=correlation_id,
            )
            result = {
                "staff_id": identity,
                "resulting_version": resulting_version,
                "changed_fields": sorted(normalized),
            }
            self._repository.save_receipt(
                key=idempotency_key,
                command_fingerprint=command_fingerprint,
                preview_fingerprint=preview_fingerprint,
                actor=actor,
                reason=clean_reason,
                result=result,
            )
            unit_of_work.commit()
            fresh = _snapshot(self._require(self._repository.load(identity, for_update=False)))
            return _receipt(result, preview_fingerprint, idempotency_key, False, fresh)

    @staticmethod
    def _preview(snapshot: StaffProfileSnapshot, changes: Mapping[str, str | None], expected_version: ExpectedVersion) -> StaffProfileMutationPreview:
        if snapshot.version != expected_version.value:
            raise StaffProfileMutationConflict("staff_profile_stale_version")
        before = {field: snapshot.values.get(field) for field in changes}
        after = {field: changes[field] for field in changes}
        return StaffProfileMutationPreview(
            snapshot.staff_id,
            snapshot.version,
            before,
            after,
            fingerprint_payload({
                "family": _COMMAND_FAMILY,
                "staff_id": snapshot.staff_id,
                "version": snapshot.version,
                "before": before,
                "after": after,
            }),
        )

    @staticmethod
    def _require(row: Mapping[str, Any] | None) -> Mapping[str, Any]:
        if row is None:
            raise StaffProfileMutationNotFound("staff_profile_not_found")
        return row


def _snapshot(row: Mapping[str, Any]) -> StaffProfileSnapshot:
    return StaffProfileSnapshot(
        int(row["staff_id"]),
        int(row.get("staff_profile_version") or 0),
        {field: _value(row.get(field)) for field in STAFF_PROFILE_FIELDS},
    )


def _value(value: Any) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return str(value.isoformat())
    return str(value)


def _receipt(result: Mapping[str, Any], preview: PreviewFingerprint, key: IdempotencyKey, replayed: bool, readback: StaffProfileSnapshot) -> StaffProfileMutationReceipt:
    return StaffProfileMutationReceipt(
        int(result["staff_id"]),
        int(result["resulting_version"]),
        tuple(str(item) for item in result["changed_fields"]),
        preview,
        key,
        replayed,
        readback,
    )


def _staff_id(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError("staff_id_invalid")
    return value


__all__ = [
    "StaffProfileMutationConflict",
    "StaffProfileMutationNotFound",
    "StaffProfileMutationPreview",
    "StaffProfileMutationReceipt",
    "StaffProfileMutationWorkflow",
    "StaffProfileSnapshot",
]
