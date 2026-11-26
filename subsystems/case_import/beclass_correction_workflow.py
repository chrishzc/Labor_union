"""Case Import-owned Query/Preview/Apply for Client BeClass effective corrections."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Callable, Protocol

from domains.case_import.beclass_correction import normalize_beclass_changes
from domains.orders.lifecycle import OrderLifecycleStatus
from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
from subsystems.client_finance.pricing_configuration import HistoricalBirthCorrectionPreview


_COMMAND_FAMILY = "client_beclass_correction/v1"


def allows_manual_beclass_source(order_status: object) -> bool:
    try:
        OrderLifecycleStatus(str(order_status))
    except ValueError:
        return False
    return True


class BeClassBirthCountCorrectionMode(StrEnum):
    STANDARD = "standard"
    LOCKED = "locked"
    HISTORICAL_SERVICE_COMPLETED = "historical_service_completed"


def beclass_birth_count_correction_mode(
    order_status: str, *, service_data_locked: bool,
) -> BeClassBirthCountCorrectionMode:
    if order_status == OrderLifecycleStatus.HISTORICAL_SERVICE_COMPLETED:
        return BeClassBirthCountCorrectionMode.HISTORICAL_SERVICE_COMPLETED
    if service_data_locked or order_status in {
        OrderLifecycleStatus.IN_SERVICE,
        OrderLifecycleStatus.COMPLETED,
        OrderLifecycleStatus.CANCELLED,
        OrderLifecycleStatus.HISTORICAL_IN_SERVICE,
        OrderLifecycleStatus.HISTORICAL_ACCOUNTING_COMPLETED,
    }:
        return BeClassBirthCountCorrectionMode.LOCKED
    return BeClassBirthCountCorrectionMode.STANDARD


class BeClassCorrectionNotFound(LookupError):
    pass


class BeClassCorrectionConflict(ValueError):
    pass


class BeClassCorrectionBlocked(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class BeClassCorrectionSnapshot:
    beclass_record_id: int | None
    case_no: str
    version: int
    original: Mapping[str, str | bool | int | float | None]
    effective: Mapping[str, str | bool | int | float | None]
    source_kind: str = "imported"
    birth_count_correction_mode: BeClassBirthCountCorrectionMode = BeClassBirthCountCorrectionMode.STANDARD


@dataclass(frozen=True, slots=True)
class BeClassCorrectionPreview:
    beclass_record_id: int | None
    case_no: str
    current_version: int
    before: Mapping[str, str | bool | int | float | None]
    after: Mapping[str, str | bool | int | float | None]
    preview_fingerprint: PreviewFingerprint
    historical_pricing: HistoricalBirthCorrectionPreview | None = None


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
    accounting_pending: tuple[str, ...] = ()


class BeClassCorrectionRepository(Protocol):
    def load(self, case_no: str, *, for_update: bool) -> Mapping[str, Any] | None: ...
    def claim(self, *, case_no: str, key: IdempotencyKey, command_fingerprint: PreviewFingerprint, correlation_id: CorrelationId) -> None: ...
    def load_receipt(self, key: IdempotencyKey, *, for_update: bool) -> Mapping[str, Any] | None: ...
    def persist(self, *, snapshot: BeClassCorrectionSnapshot, after: Mapping[str, str | bool | int | float | None], actor: ActorContext, reason: str, key: IdempotencyKey, correlation_id: CorrelationId) -> tuple[int, int, int]: ...
    def save_receipt(self, *, key: IdempotencyKey, command_fingerprint: PreviewFingerprint, preview_fingerprint: PreviewFingerprint, actor: ActorContext, reason: str, result: Mapping[str, Any]) -> None: ...


class BeClassFinancialSyncPort(Protocol):
    def preview_historical(
        self,
        *,
        case_no: str,
        before_birth_count: str | None,
        after_birth_count: str,
        for_update: bool,
    ) -> HistoricalBirthCorrectionPreview: ...

    def apply_historical(
        self,
        *,
        preview: HistoricalBirthCorrectionPreview,
        actor: ActorContext,
        reason: str,
        idempotency_key: IdempotencyKey,
    ) -> None: ...

    def apply(
        self,
        *,
        case_no: str,
        correction_event_id: int,
        actor: ActorContext,
        reason: str,
        idempotency_key: IdempotencyKey,
        correlation_id: CorrelationId,
    ) -> None: ...

    def sync_refund_recipient_snapshots(self, *, case_no: str) -> int: ...


class BeClassCorrectionWorkflow:
    def __init__(self, repository: BeClassCorrectionRepository, unit_of_work_factory: Callable[[], Any], financial_sync: BeClassFinancialSyncPort | None = None) -> None:
        self._repository = repository
        self._unit_of_work_factory = unit_of_work_factory
        self._financial_sync = financial_sync

    def query(self, case_no: str) -> BeClassCorrectionSnapshot:
        return _snapshot(self._require_row(self._repository.load(_case_no(case_no), for_update=False)))

    def preview(self, case_no: str, changes: Mapping[str, object], expected_version: ExpectedVersion) -> BeClassCorrectionPreview:
        snapshot = self.query(case_no)
        return self.preview_from_snapshot(
            snapshot, normalize_beclass_changes(changes), expected_version, for_update=False
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
            preview = self.preview_from_snapshot(snapshot, normalized, expected_version, for_update=True)
            if preview.preview_fingerprint != preview_fingerprint:
                raise BeClassCorrectionConflict("beclass_correction_stale_preview")
            if preview.historical_pricing is not None:
                self._require_financial_sync().apply_historical(
                    preview=preview.historical_pricing,
                    actor=actor,
                    reason=clean_reason,
                    idempotency_key=idempotency_key,
                )
            effective_after = {**snapshot.effective, **normalized}
            beclass_record_id, resulting_version, correction_event_id = self._repository.persist(
                snapshot=snapshot,
                after=effective_after,
                actor=actor,
                reason=clean_reason,
                key=idempotency_key,
                correlation_id=correlation_id,
            )
            if preview.historical_pricing is None and _birth_count_changed(snapshot, normalized):
                self._require_financial_sync().apply(
                    case_no=identity,
                    correction_event_id=correction_event_id,
                    actor=actor,
                    reason=clean_reason,
                    idempotency_key=idempotency_key,
                    correlation_id=correlation_id,
                )
            if _refund_account_touched(normalized) and self._financial_sync is not None and hasattr(self._financial_sync, "sync_refund_recipient_snapshots"):
                self._financial_sync.sync_refund_recipient_snapshots(case_no=identity)
            result: dict[str, object] = {
                "beclass_record_id": beclass_record_id,
                "case_no": identity,
                "resulting_version": resulting_version,
                "changed_fields": sorted(normalized),
            }
            if preview.historical_pricing is not None:
                result["accounting_pending"] = preview.historical_pricing.impact.pending
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

    def preview_from_snapshot(
        self,
        snapshot: BeClassCorrectionSnapshot,
        normalized: Mapping[str, str | bool | int | float | None],
        expected_version: ExpectedVersion,
        *,
        for_update: bool,
    ) -> BeClassCorrectionPreview:
        if snapshot.version != expected_version.value:
            raise BeClassCorrectionConflict("beclass_correction_stale_version")
        historical_pricing = None
        before = {field: snapshot.effective.get(field) for field in normalized}
        mode = snapshot.birth_count_correction_mode
        review_existing_twins = (
            mode is BeClassBirthCountCorrectionMode.HISTORICAL_SERVICE_COMPLETED
            and normalized == {"multi_birth_count": "雙胞胎"}
        )
        if _birth_count_changed(snapshot, normalized) or review_existing_twins:
            if mode is BeClassBirthCountCorrectionMode.LOCKED:
                raise BeClassCorrectionBlocked("beclass_multi_birth_count_locked_after_service_start")
            if mode is BeClassBirthCountCorrectionMode.HISTORICAL_SERVICE_COMPLETED:
                if normalized.keys() != {"multi_birth_count"}:
                    raise BeClassCorrectionBlocked("historical_birth_correction_requires_separate_command")
                before_birth_count = before["multi_birth_count"]
                after_birth_count = normalized["multi_birth_count"]
                if not isinstance(after_birth_count, str):
                    raise ValueError("beclass_multi_birth_count_invalid")
                historical_pricing = self._require_financial_sync().preview_historical(
                    case_no=snapshot.case_no,
                    before_birth_count=before_birth_count if isinstance(before_birth_count, str) else None,
                    after_birth_count=after_birth_count,
                    for_update=for_update,
                )
        fingerprint_facts = {
            "family": _COMMAND_FAMILY,
            "record_id": snapshot.beclass_record_id,
            "version": snapshot.version,
            "before": before,
            "after": normalized,
        }
        if historical_pricing is not None:
            fingerprint_facts["historical_pricing"] = historical_pricing.fingerprint.value
        return BeClassCorrectionPreview(
            snapshot.beclass_record_id,
            snapshot.case_no,
            snapshot.version,
            before,
            normalized,
            fingerprint_payload(fingerprint_facts),
            historical_pricing,
        )

    def _require_financial_sync(self) -> BeClassFinancialSyncPort:
        if self._financial_sync is None:
            raise RuntimeError("beclass_financial_sync_required")
        return self._financial_sync

    @staticmethod
    def _require_row(row: Mapping[str, Any] | None) -> Mapping[str, Any]:
        if row is None:
            raise BeClassCorrectionNotFound("beclass_record_not_found")
        return row


def _snapshot(row: Mapping[str, Any]) -> BeClassCorrectionSnapshot:
    original = dict(row["original"])
    effective = {**original, **dict(row.get("corrections") or {})}
    source_kind = str(row.get("source_kind") or "imported")
    record_id = int(row["beclass_record_id"]) if row.get("beclass_record_id") is not None else None
    if source_kind not in {"imported", "admin_manual"}:
        raise ValueError("beclass_source_kind_invalid")
    if record_id is None and source_kind != "admin_manual":
        raise ValueError("beclass_manual_source_invalid")
    return BeClassCorrectionSnapshot(
        record_id,
        str(row["case_no"]),
        int(row.get("aggregate_version") or 0),
        original,
        effective,
        source_kind,
        BeClassBirthCountCorrectionMode(row["birth_count_correction_mode"]),
    )


def _birth_count_changed(
    snapshot: BeClassCorrectionSnapshot,
    normalized: Mapping[str, str | bool | int | float | None],
) -> bool:
    return (
        "multi_birth_count" in normalized
        and normalized["multi_birth_count"]
        != snapshot.effective.get("multi_birth_count")
    )


def _refund_account_touched(
    normalized: Mapping[str, str | bool | int | float | None],
) -> bool:
    return "refund_bank_code" in normalized or "refund_account_no" in normalized


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
        tuple(str(item) for item in result.get("accounting_pending", ())),
    )


def _case_no(value: str) -> str:
    identity = str(value or "").strip()
    if not identity or len(identity) > 50:
        raise ValueError("case_no_invalid")
    return identity


__all__ = [
    "BeClassCorrectionConflict",
    "BeClassCorrectionBlocked",
    "BeClassCorrectionNotFound",
    "BeClassCorrectionPreview",
    "BeClassCorrectionReceipt",
    "BeClassCorrectionSnapshot",
    "BeClassCorrectionWorkflow",
    "allows_manual_beclass_source",
    "BeClassBirthCountCorrectionMode",
    "beclass_birth_count_correction_mode",
]
