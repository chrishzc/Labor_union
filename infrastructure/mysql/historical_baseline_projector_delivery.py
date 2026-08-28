"""Typed durable-delivery state for the historical-baseline v2 projector."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from enum import StrEnum
import hashlib
import json
from typing import Literal

from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.validation import require_canonical_text
from subsystems.anomalies.historical_baseline_projection import (
    HistoricalBaselineProjectionSourceIntent,
)


class HistoricalBaselineDeliveryError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class HistoricalBaselineDeliveryStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    RETRYABLE_FAILED = "retryable_failed"
    COMMITTED_UNVERIFIED = "committed_unverified"
    PROCESSED = "processed"
    DEAD_LETTER = "dead_letter"


@dataclass(frozen=True, slots=True)
class HistoricalBaselineProjectorTrigger:
    trigger_identity: str
    source_kind: Literal["baseline_confirmed", "owner_repair"]
    source_domain: str
    source_stream: str
    source_event_identity: str
    source_version: int
    stream_start_version: int
    partition_key: str
    source_intent: HistoricalBaselineProjectionSourceIntent
    payload_digest: PreviewFingerprint

    def __post_init__(self) -> None:
        for value, label in (
            (self.trigger_identity, "historical baseline trigger identity"),
            (self.source_domain, "historical baseline trigger source domain"),
            (self.source_stream, "historical baseline trigger source stream"),
            (self.source_event_identity, "historical baseline trigger event identity"),
            (self.partition_key, "historical baseline trigger partition"),
        ):
            require_canonical_text(value, label, 191)
        if self.source_kind not in {"baseline_confirmed", "owner_repair"}:
            raise HistoricalBaselineDeliveryError("projector_source_kind_unknown")
        if (
            isinstance(self.source_version, bool)
            or not isinstance(self.source_version, int)
            or self.source_version < 0
            or isinstance(self.stream_start_version, bool)
            or not isinstance(self.stream_start_version, int)
            or self.stream_start_version < 0
        ):
            raise HistoricalBaselineDeliveryError("projector_source_version_invalid")
        if not isinstance(self.source_intent, HistoricalBaselineProjectionSourceIntent):
            raise TypeError("historical baseline trigger source intent is invalid")
        if not isinstance(self.payload_digest, PreviewFingerprint):
            raise TypeError("historical baseline trigger payload digest is invalid")
        if self.source_intent.source_intent_key != self.trigger_identity:
            raise HistoricalBaselineDeliveryError("projector_trigger_intent_mismatch")
        if self.source_intent.source_trigger_version != self.source_version:
            raise HistoricalBaselineDeliveryError("projector_trigger_version_mismatch")

    @classmethod
    def build(
        cls,
        *,
        trigger_identity: str,
        source_kind: Literal["baseline_confirmed", "owner_repair"],
        source_domain: str,
        source_stream: str,
        source_event_identity: str,
        source_version: int,
        stream_start_version: int,
        partition_key: str,
        source_intent: HistoricalBaselineProjectionSourceIntent,
        payload: dict[str, object],
    ) -> HistoricalBaselineProjectorTrigger:
        return cls(
            trigger_identity=trigger_identity,
            source_kind=source_kind,
            source_domain=source_domain,
            source_stream=source_stream,
            source_event_identity=source_event_identity,
            source_version=source_version,
            stream_start_version=stream_start_version,
            partition_key=partition_key,
            source_intent=source_intent,
            payload_digest=_payload_digest(
                {
                    "payload": payload,
                    "source_kind": source_kind,
                    "source_domain": source_domain,
                    "source_stream": source_stream,
                    "source_event_identity": source_event_identity,
                    "source_version": source_version,
                    "stream_start_version": stream_start_version,
                    "partition_key": partition_key,
                    "source_intent": {
                        "source_intent_key": source_intent.source_intent_key,
                        "idempotency_key": source_intent.idempotency_key,
                        "baseline_event_identity": source_intent.baseline_event_identity,
                        "baseline_receipt_identity": source_intent.baseline_receipt_identity,
                        "baseline_outbox_identity": source_intent.baseline_outbox_identity,
                        "case_no": source_intent.identity.case_no,
                        "order_identity": source_intent.identity.order_identity,
                        "selected_step": source_intent.selected_step,
                        "catalog_identity": source_intent.catalog_identity.value,
                        "catalog_version": source_intent.catalog_version,
                        "expected_owner_binding_fingerprint": (
                            source_intent.expected_owner_binding_fingerprint.value
                        ),
                        "source_trigger_version": source_intent.source_trigger_version,
                    },
                }
            ),
        )


@dataclass(frozen=True, slots=True)
class HistoricalBaselineProjectorDelivery:
    delivery_identity: str
    trigger: HistoricalBaselineProjectorTrigger
    status: HistoricalBaselineDeliveryStatus
    attempt_count: int
    max_attempts: int
    projection_sequence: int | None = None
    projector_receipt_identity: str | None = None
    next_attempt_at: datetime | None = None
    lease_owner: str | None = None
    lease_expires_at: datetime | None = None
    last_error_code: str | None = None

    def __post_init__(self) -> None:
        require_canonical_text(
            self.delivery_identity, "historical baseline delivery identity", 64
        )
        if not isinstance(self.status, HistoricalBaselineDeliveryStatus):
            raise TypeError("historical baseline delivery status is invalid")
        if (
            isinstance(self.attempt_count, bool)
            or not isinstance(self.attempt_count, int)
            or self.attempt_count < 0
            or isinstance(self.max_attempts, bool)
            or not isinstance(self.max_attempts, int)
            or self.max_attempts < 1
            or self.attempt_count > self.max_attempts
        ):
            raise HistoricalBaselineDeliveryError("projector_delivery_attempts_invalid")

    @classmethod
    def pending(
        cls, trigger: HistoricalBaselineProjectorTrigger, *, max_attempts: int
    ) -> HistoricalBaselineProjectorDelivery:
        identity = hashlib.sha256(
            f"historical-baseline-delivery-v2:{trigger.trigger_identity}".encode("utf-8")
        ).hexdigest()
        return cls(
            delivery_identity=identity,
            trigger=trigger,
            status=HistoricalBaselineDeliveryStatus.PENDING,
            attempt_count=0,
            max_attempts=max_attempts,
        )

    def assert_same_trigger(
        self, trigger: HistoricalBaselineProjectorTrigger
    ) -> HistoricalBaselineProjectorDelivery:
        if self.trigger.trigger_identity != trigger.trigger_identity:
            raise HistoricalBaselineDeliveryError("projector_trigger_identity_mismatch")
        if self.trigger.payload_digest != trigger.payload_digest or self.trigger != trigger:
            raise HistoricalBaselineDeliveryError("projector_trigger_integrity_conflict")
        return self

    def claim(
        self, *, now: datetime, lease_owner: str, lease_duration: timedelta
    ) -> HistoricalBaselineProjectorDelivery:
        require_canonical_text(lease_owner, "historical baseline lease owner", 191)
        claimable = self.status in {
            HistoricalBaselineDeliveryStatus.PENDING,
            HistoricalBaselineDeliveryStatus.RETRYABLE_FAILED,
        }
        if self.status is HistoricalBaselineDeliveryStatus.PROCESSING:
            claimable = self.lease_expires_at is not None and self.lease_expires_at <= now
        if not claimable:
            raise HistoricalBaselineDeliveryError("projector_delivery_not_claimable")
        if self.next_attempt_at is not None and self.next_attempt_at > now:
            raise HistoricalBaselineDeliveryError("projector_delivery_not_retry_ready")
        if self.attempt_count >= self.max_attempts:
            raise HistoricalBaselineDeliveryError("projector_delivery_attempts_exhausted")
        return replace(
            self,
            status=HistoricalBaselineDeliveryStatus.PROCESSING,
            attempt_count=self.attempt_count + 1,
            next_attempt_at=None,
            lease_owner=lease_owner,
            lease_expires_at=now + lease_duration,
            last_error_code=None,
        )

    def fail(
        self, *, error_code: str, retryable: bool, next_attempt_at: datetime | None
    ) -> HistoricalBaselineProjectorDelivery:
        require_canonical_text(error_code, "historical baseline delivery error", 191)
        if self.status is not HistoricalBaselineDeliveryStatus.PROCESSING:
            raise HistoricalBaselineDeliveryError("projector_delivery_not_processing")
        exhausted = self.attempt_count >= self.max_attempts
        status = (
            HistoricalBaselineDeliveryStatus.RETRYABLE_FAILED
            if retryable and not exhausted
            else HistoricalBaselineDeliveryStatus.DEAD_LETTER
        )
        return replace(
            self,
            status=status,
            next_attempt_at=next_attempt_at if status is HistoricalBaselineDeliveryStatus.RETRYABLE_FAILED else None,
            lease_owner=None,
            lease_expires_at=None,
            last_error_code=error_code,
        )

    def committed(
        self, *, projection_sequence: int, projector_receipt_identity: str
    ) -> HistoricalBaselineProjectorDelivery:
        if self.status is not HistoricalBaselineDeliveryStatus.PROCESSING:
            raise HistoricalBaselineDeliveryError("projector_delivery_not_processing")
        require_canonical_text(
            projector_receipt_identity, "historical baseline projector receipt", 64
        )
        return replace(
            self,
            status=HistoricalBaselineDeliveryStatus.COMMITTED_UNVERIFIED,
            projection_sequence=projection_sequence,
            projector_receipt_identity=projector_receipt_identity,
            lease_owner=None,
            lease_expires_at=None,
            last_error_code=None,
        )

    def processed(self) -> HistoricalBaselineProjectorDelivery:
        if self.status is not HistoricalBaselineDeliveryStatus.COMMITTED_UNVERIFIED:
            raise HistoricalBaselineDeliveryError("projector_delivery_not_committed")
        return replace(self, status=HistoricalBaselineDeliveryStatus.PROCESSED)


def _payload_digest(payload: dict[str, object]) -> PreviewFingerprint:
    if not isinstance(payload, dict) or any(not isinstance(key, str) for key in payload):
        raise HistoricalBaselineDeliveryError("projector_trigger_payload_invalid")
    try:
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise HistoricalBaselineDeliveryError("projector_trigger_payload_invalid") from error
    return PreviewFingerprint(hashlib.sha256(encoded).hexdigest())


__all__ = [
    "HistoricalBaselineDeliveryError",
    "HistoricalBaselineDeliveryStatus",
    "HistoricalBaselineProjectorDelivery",
    "HistoricalBaselineProjectorTrigger",
]
