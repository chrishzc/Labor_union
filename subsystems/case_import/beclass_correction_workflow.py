"""Case Import-owned Query/Preview/Apply for Client BeClass effective corrections."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Callable, Protocol

from domains.case_import.beclass_correction import normalize_beclass_changes
from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey


_COMMAND_FAMILY = "client_beclass_correction/v1"


class BeClassCorrectionNotFound(LookupError):
    pass


class BeClassCorrectionConflict(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class BeClassCorrectionSnapshot:
    beclass_record_id: int
    case_no: str
    version: int
    original: Mapping[str, str | None]
    effective: Mapping[str, str | None]


@dataclass(frozen=True, slots=True)
class BeClassCorrectionPreview:
    beclass_record_id: int
    case_no: str
    current_version: int
    before: Mapping[str, str | None]
    after: Mapping[str, str | None]
    preview_fingerprint: PreviewFingerprint


@dataclass(frozen=True, slots=True)
class BeClassCorrectionReceipt:
    beclass_record_id: int
    case_no: str
    resulting_version: int
    changed_fields: tuple[str, ...]
    preview_fingerprint: PreviewFingerprint
    idempotency_key: IdempotencyKey
    replayed: bool
    readback: BeClassCorrectionSnapshot


class BeClassCorrectionRepository(Protocol):
    def load(self, case_no: str, *, for_update: bool) -> Mapping[str, Any] | None: ...
    def claim(self, *, case_no: str, key: IdempotencyKey, command_fingerprint: PreviewFingerprint, correlation_id: CorrelationId) -> None: ...
    def load_receipt(self, key: IdempotencyKey, *, for_update: bool) -> Mapping[str, Any] | None: ...
    def persist(self, *, snapshot: BeClassCorrectionSnapshot, after: Mapping[str, str | None], actor: ActorContext, reason: str, key: IdempotencyKey, correlation_id: CorrelationId) -> int: ...
    def save_receipt(self, *, key: IdempotencyKey, command_fingerprint: PreviewFingerprint, preview_fingerprint: PreviewFingerprint, actor: ActorContext, reason: str, result: Mapping[str, Any]) -> None: ...


class BeClassCorrectionWorkflow:
    def __init__(self, repository: BeClassCorrectionRepository, unit_of_work_factory: Callable[[], Any]) -> None:
        self._repository = repository
        self._unit_of_work_factory = unit_of_work_factory

    def query(self, case_no: str) -> BeClassCorrectionSnapshot:
        return _snapshot(self._require_row(self._repository.load(_case_no(case_no), for_update=False)))

    def preview(self, case_no: str, changes: Mapping[str, object], expected_version: ExpectedVersion) -> BeClassCorrectionPreview:
        snapshot = self.query(case_no)
        if snapshot.version != expected_version.value:
            raise BeClassCorrectionConflict("beclass_correction_stale_version")
        normalized = normalize_beclass_changes(changes)
        before = {field: snapshot.effective.get(field) for field in normalized}
        after = {**snapshot.effective, **normalized}
        fingerprint = fingerprint_payload({
            "family": _COMMAND_FAMILY,
            "record_id": snapshot.beclass_record_id,
            "version": snapshot.version,
            "before": before,
            "after": {field: after.get(field) for field in normalized},
        })
        return BeClassCorrectionPreview(
            snapshot.beclass_record_id,
            snapshot.case_no,
            snapshot.version,
            before,
            {field: after.get(field) for field in normalized},
            fingerprint,
        )

    def apply(
        self,
        case_no: str,
        changes: Mapping[str, object],
        expected_version: ExpectedVersion,
        preview_fingerprint: PreviewFingerprint,
        idempotency_key: IdempotencyKey,
        actor: ActorContext,
        reason: str,
        correlation_id: CorrelationId,
    ) -> BeClassCorrectionReceipt:
        identity = _case_no(case_no)
        normalized = normalize_beclass_changes(changes)
        clean_reason = reason.strip()
        if not clean_reason:
            raise ValueError("beclass_correction_reason_required")
        command_fingerprint = fingerprint_payload({
            "family": _COMMAND_FAMILY,
            "case_no": identity,
            "changes": normalized,
            "expected_version": expected_version.value,
            "preview_fingerprint": preview_fingerprint.value,
            "actor": actor.actor_id,
            "reason": clean_reason,
        })
        with self._unit_of_work_factory() as unit_of_work:
            self._repository.claim(
                case_no=identity,
                key=idempotency_key,
                command_fingerprint=command_fingerprint,
                correlation_id=correlation_id,
            )
            replay = self._repository.load_receipt(idempotency_key, for_update=True)
            if replay is not None:
                if str(replay["request_fingerprint"]) != command_fingerprint.value:
                    raise BeClassCorrectionConflict("idempotency_mismatch")
                fresh = _snapshot(self._require_row(self._repository.load(identity, for_update=False)))
                result = replay["result"]
                unit_of_work.commit()
                return _receipt(result, preview_fingerprint, idempotency_key, True, fresh)
            snapshot = _snapshot(self._require_row(self._repository.load(identity, for_update=True)))
            preview = self.preview_from_snapshot(snapshot, normalized, expected_version)
            if preview.preview_fingerprint != preview_fingerprint:
                raise BeClassCorrectionConflict("beclass_correction_stale_preview")
            effective_after = {**snapshot.effective, **normalized}
            resulting_version = self._repository.persist(
                snapshot=snapshot,
                after=effective_after,
                actor=actor,
                reason=clean_reason,
                key=idempotency_key,
                correlation_id=correlation_id,
            )
            result = {
                "beclass_record_id": snapshot.beclass_record_id,
                "case_no": identity,
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
            fresh = _snapshot(self._require_row(self._repository.load(identity, for_update=False)))
            return _receipt(result, preview_fingerprint, idempotency_key, False, fresh)

    def preview_from_snapshot(self, snapshot: BeClassCorrectionSnapshot, normalized: Mapping[str, str | None], expected_version: ExpectedVersion) -> BeClassCorrectionPreview:
        if snapshot.version != expected_version.value:
            raise BeClassCorrectionConflict("beclass_correction_stale_version")
        before = {field: snapshot.effective.get(field) for field in normalized}
        after = {field: normalized[field] for field in normalized}
        return BeClassCorrectionPreview(
            snapshot.beclass_record_id,
            snapshot.case_no,
            snapshot.version,
            before,
            after,
            fingerprint_payload({
                "family": _COMMAND_FAMILY,
                "record_id": snapshot.beclass_record_id,
                "version": snapshot.version,
                "before": before,
                "after": after,
            }),
        )

    @staticmethod
    def _require_row(row: Mapping[str, Any] | None) -> Mapping[str, Any]:
        if row is None:
            raise BeClassCorrectionNotFound("beclass_record_not_found")
        return row


def _snapshot(row: Mapping[str, Any]) -> BeClassCorrectionSnapshot:
    original = dict(row["original"])
    effective = {**original, **dict(row.get("corrections") or {})}
    return BeClassCorrectionSnapshot(
        int(row["beclass_record_id"]),
        str(row["case_no"]),
        int(row.get("aggregate_version") or 0),
        original,
        effective,
    )


def _receipt(result: Mapping[str, Any], preview: PreviewFingerprint, key: IdempotencyKey, replayed: bool, readback: BeClassCorrectionSnapshot) -> BeClassCorrectionReceipt:
    return BeClassCorrectionReceipt(
        int(result["beclass_record_id"]),
        str(result["case_no"]),
        int(result["resulting_version"]),
        tuple(str(item) for item in result["changed_fields"]),
        preview,
        key,
        replayed,
        readback,
    )


def _case_no(value: str) -> str:
    identity = str(value or "").strip()
    if not identity or len(identity) > 50:
        raise ValueError("case_no_invalid")
    return identity


__all__ = [
    "BeClassCorrectionConflict",
    "BeClassCorrectionNotFound",
    "BeClassCorrectionPreview",
    "BeClassCorrectionReceipt",
    "BeClassCorrectionSnapshot",
    "BeClassCorrectionWorkflow",
]
