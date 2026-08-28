"""Source-partition checkpoint rules for the historical-baseline projector."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib

from shared_kernel.fingerprints import PreviewFingerprint

from infrastructure.mysql.historical_baseline_projector_delivery import (
    HistoricalBaselineDeliveryError,
    HistoricalBaselineProjectorTrigger,
)


@dataclass(frozen=True, slots=True)
class HistoricalBaselineSourceCheckpoint:
    checkpoint_identity: str
    source_domain: str
    source_stream: str
    partition_key: str
    last_source_event_identity: str
    last_source_version: int
    last_projection_sequence: int
    checkpoint_fingerprint: PreviewFingerprint

    @classmethod
    def advance(
        cls,
        trigger: HistoricalBaselineProjectorTrigger,
        *,
        projection_sequence: int,
    ) -> HistoricalBaselineSourceCheckpoint:
        identity = _checkpoint_identity(trigger)
        fingerprint = PreviewFingerprint(
            hashlib.sha256(
                (
                    f"{identity}\x1f{trigger.source_event_identity}\x1f"
                    f"{trigger.source_version}\x1f{projection_sequence}"
                ).encode("utf-8")
            ).hexdigest()
        )
        return cls(
            checkpoint_identity=identity,
            source_domain=trigger.source_domain,
            source_stream=trigger.source_stream,
            partition_key=trigger.partition_key,
            last_source_event_identity=trigger.source_event_identity,
            last_source_version=trigger.source_version,
            last_projection_sequence=projection_sequence,
            checkpoint_fingerprint=fingerprint,
        )


def validate_checkpoint_progress(
    checkpoint: HistoricalBaselineSourceCheckpoint | None,
    trigger: HistoricalBaselineProjectorTrigger,
) -> None:
    if checkpoint is None:
        if trigger.source_version != trigger.stream_start_version:
            raise HistoricalBaselineDeliveryError("projector_source_version_gap")
        return
    expected_identity = _checkpoint_identity(trigger)
    if checkpoint.checkpoint_identity != expected_identity:
        raise HistoricalBaselineDeliveryError("projector_checkpoint_partition_mismatch")
    if trigger.source_version == checkpoint.last_source_version:
        if trigger.source_event_identity == checkpoint.last_source_event_identity:
            raise HistoricalBaselineDeliveryError("projector_source_event_already_checkpointed")
        raise HistoricalBaselineDeliveryError("projector_source_version_integrity_conflict")
    if trigger.source_version < checkpoint.last_source_version:
        raise HistoricalBaselineDeliveryError("projector_source_version_stale")
    if trigger.source_version != checkpoint.last_source_version + 1:
        raise HistoricalBaselineDeliveryError("projector_source_version_gap")


def _checkpoint_identity(trigger: HistoricalBaselineProjectorTrigger) -> str:
    value = "\x1f".join(
        (trigger.source_domain, trigger.source_stream, trigger.partition_key)
    )
    return hashlib.sha256(
        f"historical-baseline-checkpoint-v2:{value}".encode("utf-8")
    ).hexdigest()


__all__ = [
    "HistoricalBaselineSourceCheckpoint",
    "validate_checkpoint_progress",
]
