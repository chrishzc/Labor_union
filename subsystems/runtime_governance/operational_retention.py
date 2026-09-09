"""Positive-registry operational retention Query, Preview, Apply and worker policy."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from typing import Callable, Literal, Protocol

from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload


POLICY_REVISION = "operational-retention.v1"
RETENTION_DAYS = 30
DEFAULT_BATCH_SIZE = 250
MAX_BATCH_SIZE = 500

RetentionMode = Literal["expired", "capacity"]
RetentionOutcome = Literal["completed", "partial", "capacity_unrelieved"]


class RetentionError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        category: str = "validation",
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.category = category
        self.retryable = retryable


@dataclass(frozen=True, slots=True)
class RetentionCandidate:
    identity: str
    version: str
    occurred_at_utc: datetime
    estimated_bytes: int

    def __post_init__(self) -> None:
        if not self.identity or not self.version:
            raise ValueError("retention candidate identity and version are required")
        if self.occurred_at_utc.tzinfo is None:
            raise ValueError("retention candidate time must be timezone-aware")
        if self.estimated_bytes < 0:
            raise ValueError("retention candidate bytes cannot be negative")


@dataclass(frozen=True, slots=True)
class RetentionSourceSnapshot:
    source_id: str
    label: str
    storage_kind: Literal["database", "files"]
    classification: Literal["eligible", "blocked-unclassified"]
    current_logical_bytes: int
    eligible_count: int
    expired_count: int
    oldest_eligible_at_utc: datetime | None
    estimated_reclaimable_bytes: int
    high_water_bytes: int | None
    low_water_bytes: int | None
    capacity_status: Literal["normal", "high", "unconfigured", "unavailable"]
    blocked_reason: str | None = None
    last_run_at_utc: datetime | None = None
    last_outcome: str | None = None


@dataclass(frozen=True, slots=True)
class RetentionPreview:
    policy_revision: str
    source_id: str
    mode: RetentionMode
    reason: str
    previewed_at_utc: datetime
    cutoff_at_utc: datetime
    batch_size: int
    candidate_count: int
    estimated_reclaimable_bytes: int
    current_logical_bytes: int
    target_low_water_bytes: int | None
    preview_fingerprint: PreviewFingerprint
    candidates: tuple[RetentionCandidate, ...]


@dataclass(frozen=True, slots=True)
class RetentionDeleteResult:
    deleted_count: int
    deleted_logical_bytes: int
    failed_count: int = 0
    error_code: str | None = None


@dataclass(frozen=True, slots=True)
class RetentionReceipt:
    idempotency_key: str
    source_id: str
    mode: RetentionMode
    policy_revision: str
    preview_fingerprint: str
    outcome: RetentionOutcome
    candidate_count: int
    deleted_count: int
    failed_count: int
    deleted_logical_bytes: int
    started_at_utc: datetime
    finished_at_utc: datetime
    correlation_id: str
    error_code: str | None
    replayed: bool = False


@dataclass(frozen=True, slots=True)
class RetentionIntent:
    idempotency_key: str
    source_id: str
    mode: RetentionMode
    reason: str
    policy_revision: str
    previewed_at_utc: datetime
    cutoff_at_utc: datetime
    batch_size: int
    preview_fingerprint: str
    candidates: tuple[RetentionCandidate, ...]
    actor_id: str
    correlation_id: str
    started_at_utc: datetime


class RetentionSource(Protocol):
    source_id: str

    def snapshot(self, now: datetime, retention_days: int) -> RetentionSourceSnapshot: ...

    def candidates(
        self,
        *,
        cutoff_at_utc: datetime,
        limit: int,
    ) -> tuple[RetentionCandidate, ...]: ...

    def delete(self, candidates: tuple[RetentionCandidate, ...]) -> RetentionDeleteResult: ...

    def rotate_oversized(self, now: datetime) -> int: ...


class RetentionEvidenceStore(Protocol):
    def terminal_receipt(self, idempotency_key: str) -> RetentionReceipt | None: ...

    def pending_intent(self, idempotency_key: str) -> RetentionIntent | None: ...

    def append_intent(self, intent: RetentionIntent) -> None: ...

    def append_terminal(self, receipt: RetentionReceipt, actor_id: str) -> None: ...

    def latest_by_source(self) -> dict[str, tuple[datetime, str]]: ...


class OperationalRetentionApplication:
    def __init__(
        self,
        sources: tuple[RetentionSource, ...],
        evidence_store: RetentionEvidenceStore,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        if len({source.source_id for source in sources}) != len(sources):
            raise ValueError("retention source ids must be unique")
        self._sources = {source.source_id: source for source in sources}
        self._evidence = evidence_store
        self._now = now or (lambda: datetime.now(timezone.utc))

    def dashboard(self) -> tuple[RetentionSourceSnapshot, ...]:
        now = _aware_utc(self._now())
        latest = self._evidence.latest_by_source()
        snapshots = []
        for source in self._sources.values():
            snapshot = source.snapshot(now, RETENTION_DAYS)
            last = latest.get(source.source_id)
            if last is not None:
                snapshot = replace(snapshot, last_run_at_utc=last[0], last_outcome=last[1])
            snapshots.append(snapshot)
        return tuple(snapshots)

    def preview(
        self,
        *,
        source_id: str,
        mode: RetentionMode,
        reason: str,
        batch_size: int = DEFAULT_BATCH_SIZE,
        previewed_at_utc: datetime | None = None,
    ) -> RetentionPreview:
        source = self._source(source_id)
        normalized_reason = reason.strip()
        if not normalized_reason:
            raise RetentionError("retention_reason_required", "清理原因不可空白。")
        if mode not in {"expired", "capacity"}:
            raise RetentionError("retention_mode_invalid", "不支援的清理模式。")
        if not 1 <= batch_size <= MAX_BATCH_SIZE:
            raise RetentionError("retention_batch_size_invalid", "每批筆數必須介於 1 到 500。")
        previewed_at = _aware_utc(previewed_at_utc or self._now())
        snapshot = source.snapshot(previewed_at, RETENTION_DAYS)
        if snapshot.classification != "eligible":
            raise RetentionError(
                "retention_source_unclassified",
                "此來源尚未完成安全分類，不能清理。",
                category="domain_blocked",
            )
        cutoff = previewed_at - timedelta(days=RETENTION_DAYS)
        target_low_water = None
        if mode == "capacity":
            if snapshot.high_water_bytes is None or snapshot.low_water_bytes is None:
                raise RetentionError(
                    "retention_capacity_unconfigured",
                    "此來源尚未設定 high-water／low-water。",
                    category="domain_blocked",
                )
            target_low_water = snapshot.low_water_bytes
            if snapshot.current_logical_bytes <= snapshot.high_water_bytes:
                candidates: tuple[RetentionCandidate, ...] = ()
            else:
                candidates = _take_until_bytes(
                    source.candidates(cutoff_at_utc=previewed_at, limit=batch_size),
                    snapshot.current_logical_bytes - snapshot.low_water_bytes,
                )
            cutoff = previewed_at
        else:
            candidates = source.candidates(cutoff_at_utc=cutoff, limit=batch_size)
        fingerprint = _preview_fingerprint(
            source_id=source_id,
            mode=mode,
            reason=normalized_reason,
            previewed_at_utc=previewed_at,
            cutoff_at_utc=cutoff,
            batch_size=batch_size,
            candidates=candidates,
        )
        return RetentionPreview(
            POLICY_REVISION,
            source_id,
            mode,
            normalized_reason,
            previewed_at,
            cutoff,
            batch_size,
            len(candidates),
            sum(item.estimated_bytes for item in candidates),
            snapshot.current_logical_bytes,
            target_low_water,
            fingerprint,
            candidates,
        )

    def apply(
        self,
        *,
        source_id: str,
        mode: RetentionMode,
        reason: str,
        batch_size: int,
        previewed_at_utc: datetime,
        preview_fingerprint: PreviewFingerprint,
        idempotency_key: str,
        correlation_id: str,
        actor_id: str,
    ) -> RetentionReceipt:
        if not idempotency_key.strip() or not correlation_id.strip() or not actor_id.strip():
            raise RetentionError("retention_identity_required", "缺少操作識別資訊。")
        terminal = self._evidence.terminal_receipt(idempotency_key)
        if terminal is not None:
            return replace(terminal, replayed=True)
        intent = self._evidence.pending_intent(idempotency_key)
        if intent is None:
            preview = self.preview(
                source_id=source_id,
                mode=mode,
                reason=reason,
                batch_size=batch_size,
                previewed_at_utc=previewed_at_utc,
            )
            if preview.preview_fingerprint != preview_fingerprint:
                raise RetentionError(
                    "retention_preview_stale",
                    "可清理集合已改變，請重新預覽。",
                    category="conflict",
                )
            intent = RetentionIntent(
                idempotency_key.strip(),
                source_id,
                mode,
                preview.reason,
                POLICY_REVISION,
                preview.previewed_at_utc,
                preview.cutoff_at_utc,
                batch_size,
                preview_fingerprint.value,
                preview.candidates,
                actor_id.strip(),
                correlation_id.strip(),
                _aware_utc(self._now()),
            )
            self._evidence.append_intent(intent)
        else:
            self._validate_replay_intent(
                intent,
                source_id=source_id,
                mode=mode,
                preview_fingerprint=preview_fingerprint,
                actor_id=actor_id,
            )
        result = self._source(intent.source_id).delete(intent.candidates)
        now = _aware_utc(self._now())
        outcome: RetentionOutcome = "partial" if result.failed_count else "completed"
        if intent.mode == "capacity":
            source = self._source(intent.source_id)
            snapshot = source.snapshot(now, RETENTION_DAYS)
            if snapshot.low_water_bytes is not None and snapshot.current_logical_bytes > snapshot.low_water_bytes:
                has_more_candidates = bool(source.candidates(cutoff_at_utc=now, limit=1))
                if not has_more_candidates:
                    outcome = "capacity_unrelieved"
        receipt = RetentionReceipt(
            intent.idempotency_key,
            intent.source_id,
            intent.mode,
            intent.policy_revision,
            intent.preview_fingerprint,
            outcome,
            len(intent.candidates),
            result.deleted_count,
            result.failed_count,
            result.deleted_logical_bytes,
            intent.started_at_utc,
            now,
            intent.correlation_id,
            result.error_code,
        )
        self._evidence.append_terminal(receipt, intent.actor_id)
        return receipt

    def run_automatic(self, *, max_batches_per_source: int = 20) -> tuple[RetentionReceipt, ...]:
        if not 1 <= max_batches_per_source <= 100:
            raise ValueError("max_batches_per_source must be between 1 and 100")
        receipts: list[RetentionReceipt] = []
        now = _aware_utc(self._now())
        for source in self._sources.values():
            source.rotate_oversized(now)
            for mode in ("expired", "capacity"):
                for _ in range(max_batches_per_source):
                    try:
                        preview = self.preview(
                            source_id=source.source_id,
                            mode=mode,
                            reason=f"automatic-{mode}",
                            previewed_at_utc=now,
                        )
                    except RetentionError as error:
                        if error.code in {
                            "retention_capacity_unconfigured",
                            "retention_source_unclassified",
                        }:
                            break
                        raise
                    if not preview.candidates and not (
                        mode == "capacity"
                        and preview.target_low_water_bytes is not None
                        and preview.current_logical_bytes > preview.target_low_water_bytes
                    ):
                        break
                    key = f"retention:{POLICY_REVISION}:{source.source_id}:{mode}:{preview.preview_fingerprint.value}"
                    receipt = self.apply(
                        source_id=source.source_id,
                        mode=mode,
                        reason=preview.reason,
                        batch_size=preview.batch_size,
                        previewed_at_utc=preview.previewed_at_utc,
                        preview_fingerprint=preview.preview_fingerprint,
                        idempotency_key=key,
                        correlation_id=key[-191:],
                        actor_id="system:operational-retention",
                    )
                    receipts.append(receipt)
                    if receipt.outcome != "completed" or receipt.deleted_count == 0:
                        break
        return tuple(receipts)

    def _source(self, source_id: str) -> RetentionSource:
        try:
            return self._sources[source_id]
        except KeyError as error:
            raise RetentionError(
                "retention_source_not_found",
                "找不到指定的清理來源。",
                category="not_found",
            ) from error

    @staticmethod
    def _validate_replay_intent(
        intent: RetentionIntent,
        *,
        source_id: str,
        mode: RetentionMode,
        preview_fingerprint: PreviewFingerprint,
        actor_id: str,
    ) -> None:
        if (
            intent.source_id != source_id
            or intent.mode != mode
            or intent.preview_fingerprint != preview_fingerprint.value
            or intent.actor_id != actor_id.strip()
        ):
            raise RetentionError(
                "retention_idempotency_mismatch",
                "相同操作識別碼已綁定不同的清理命令。",
                category="idempotency_mismatch",
            )


def _preview_fingerprint(
    *,
    source_id: str,
    mode: RetentionMode,
    reason: str,
    previewed_at_utc: datetime,
    cutoff_at_utc: datetime,
    batch_size: int,
    candidates: tuple[RetentionCandidate, ...],
) -> PreviewFingerprint:
    return fingerprint_payload(
        {
            "policy_revision": POLICY_REVISION,
            "source_id": source_id,
            "mode": mode,
            "reason": reason,
            "previewed_at_utc": _iso(previewed_at_utc),
            "cutoff_at_utc": _iso(cutoff_at_utc),
            "batch_size": batch_size,
            "candidates": [
                {
                    "identity": item.identity,
                    "version": item.version,
                    "occurred_at_utc": _iso(item.occurred_at_utc),
                    "estimated_bytes": item.estimated_bytes,
                }
                for item in candidates
            ],
        }
    )


def _take_until_bytes(
    candidates: tuple[RetentionCandidate, ...],
    required_bytes: int,
) -> tuple[RetentionCandidate, ...]:
    selected = []
    total = 0
    for candidate in candidates:
        selected.append(candidate)
        total += candidate.estimated_bytes
        if total >= required_bytes:
            break
    return tuple(selected)


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _iso(value: datetime) -> str:
    return _aware_utc(value).isoformat().replace("+00:00", "Z")


__all__ = [
    "DEFAULT_BATCH_SIZE",
    "MAX_BATCH_SIZE",
    "OperationalRetentionApplication",
    "POLICY_REVISION",
    "RETENTION_DAYS",
    "RetentionCandidate",
    "RetentionDeleteResult",
    "RetentionError",
    "RetentionEvidenceStore",
    "RetentionIntent",
    "RetentionPreview",
    "RetentionReceipt",
    "RetentionSource",
    "RetentionSourceSnapshot",
]
