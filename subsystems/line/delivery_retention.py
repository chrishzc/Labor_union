"""Expire completed LINE delivery details while retaining replay protection."""
from calendar import monthrange
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable
from zoneinfo import ZoneInfo

from domains.line.delivery import LineDeliveryStatus
from domains.line.identities import LineDeliveryTaskId
from shared_kernel.fingerprints import fingerprint_payload
from shared_kernel.identities import IdempotencyKey, IdempotencyReceipt
from subsystems.line.ports import LineAuditIntent, LineUnitOfWorkPort


RETENTION_PAYLOAD = '{"_retention_expired":true}'
TAIPEI = ZoneInfo('Asia/Taipei')


def delivery_retention_cutoff(now: datetime) -> datetime:
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError('delivery retention clock must be timezone-aware')
    local = now.astimezone(TAIPEI)
    month_index = local.year * 12 + local.month - 1 - 6
    year, month_zero = divmod(month_index, 12)
    month = month_zero + 1
    day = min(local.day, monthrange(year, month)[1])
    return local.replace(year=year, month=month, day=day).astimezone(timezone.utc)


@dataclass(frozen=True, slots=True)
class LineDeliveryRetentionFacts:
    task_id: LineDeliveryTaskId
    status: LineDeliveryStatus
    updated_at: datetime
    has_lease: bool
    error_code: str | None
    completed_attempts: int
    attempt_completed_at: tuple[datetime, ...]
    latest_attempt_error_code: str | None
    intent_statuses: tuple[str, ...]
    expired: bool

    def eligible(self, cutoff: datetime) -> bool:
        expected_intent = {LineDeliveryStatus.SENT: 'provider_accepted',
                           LineDeliveryStatus.CANCELLED: 'cancelled'}.get(self.status)
        return bool(expected_intent and not self.expired and not self.has_lease
            and self.updated_at < cutoff
            and self.error_code != 'line_reply_outcome_uncertain'
            and self.latest_attempt_error_code != 'line_reply_outcome_uncertain'
            and len(self.attempt_completed_at) == self.completed_attempts
            and all(completed_at < cutoff for completed_at in self.attempt_completed_at)
            and all(status == expected_intent for status in self.intent_statuses))


class LineDeliveryRetentionApplication:
    def __init__(self, unit_of_work_factory: Callable[[], LineUnitOfWorkPort],
            now: Callable[[], datetime], worker_identity: str, *, batch_size: int = 25):
        if not 1 <= batch_size <= 25:
            raise ValueError('delivery retention batch size must be between 1 and 25')
        self._factory = unit_of_work_factory
        self._now = now
        self._actor = worker_identity
        self._batch_size = batch_size

    def run_once(self) -> int:
        now = self._now()
        cutoff = delivery_retention_cutoff(now)
        with self._factory() as unit:
            candidates = unit.delivery_tasks.retention_candidates(cutoff, self._batch_size)
        expired = 0
        for task_id in candidates:
            # Each task is independently atomic. A later failure cannot undo an
            # earlier completed receipt or partially clear the current task.
            with self._factory() as unit:
                facts = unit.delivery_tasks.retention_facts(task_id)
                if facts is None or not facts.eligible(cutoff):
                    continue
                key = IdempotencyKey(f'line-delivery-retention:{task_id.value}')
                existing = unit.receipts.get(key, for_update=True)
                if existing is not None:
                    raise RuntimeError('line_delivery_retention_receipt_conflict')
                snapshot = {'task_id':task_id.value,
                    'cutoff':cutoff.replace(tzinfo=None).strftime('%Y-%m-%d %H:%M:%S.%f'),
                    'expired_at':now.astimezone(timezone.utc).isoformat()}
                unit.receipts.append(IdempotencyReceipt(key, fingerprint_payload(snapshot), key.value),
                                     result_snapshot=snapshot)
                unit.delivery_tasks.expire_retention_details(facts, key)
                unit.audit.append(LineAuditIntent('line.delivery.retention.expired', self._actor,
                    'line_delivery_task', str(task_id.value)))
                unit.commit()
                expired += 1
        return expired
