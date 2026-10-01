"""
File: notification_manual_replay_application.py
Description: 讓管理員先預覽再以新 immutable source 執行 historical-silent LINE 通知手動重送。
"""

from __future__ import annotations

from datetime import datetime
from dataclasses import dataclass
from typing import Callable

from shared_kernel.identities import ActorContext, CorrelationId, IdempotencyKey, IdempotencyReceipt
from shared_kernel.fingerprints import fingerprint_payload
from subsystems.line.capabilities import LineCapability, require_line_capability
from subsystems.line.ports import LineAuditIntent, LineUnitOfWorkPort
from subsystems.line.notification_failure_current_fact import (
    append_line_notification_failure_rechecks,
    build_line_notification_failure_recheck_intent,
    LineNotificationFailureCurrentFactQuery, LineNotificationFailureReason,
    LINE_NOTIFICATION_WARNING_SKIP_ACTION,
)


@dataclass(frozen=True, slots=True)
class LineNotificationWarningSkipPreview:
    issue_key: str
    case_no: str
    notification_reason: str
    owner_snapshot_token: str
    preview_fingerprint: str


@dataclass(frozen=True, slots=True)
class LineNotificationWarningSkipReceipt:
    issue_key: str
    replayed: bool


class LineNotificationWarningSkipConflict(ValueError):
    pass


def _warning_skip_preview(unit_of_work, issue_key: str, *, for_update: bool = False):
    projection = unit_of_work.anomaly_rechecks.query_current(issue_key, for_update=for_update)
    if projection is None or projection.candidate.definition_code != "LINE-006":
        raise LineNotificationWarningSkipConflict("line_warning_skip_not_current")
    candidate = projection.candidate
    if candidate.owner_domain != "line" or candidate.owner_root_type != "notification_failure":
        raise LineNotificationWarningSkipConflict("line_warning_skip_not_current")
    query = LineNotificationFailureCurrentFactQuery(candidate.subject_identity["case_no"],
                                                    LineNotificationFailureReason(candidate.subject_identity["notification_reason"]))
    readback = unit_of_work.notification_rules.current_failure_fact(query)
    if not readback.authoritative_complete or not readback.predicate_active:
        raise LineNotificationWarningSkipConflict("line_warning_skip_not_current")
    preview = LineNotificationWarningSkipPreview(issue_key, query.case_no, query.notification_reason.value,
        readback.owner_snapshot_token, fingerprint_payload({"operation": LINE_NOTIFICATION_WARNING_SKIP_ACTION,
            "issue_key": issue_key, "owner_snapshot_token": readback.owner_snapshot_token}).value)
    return preview, readback, query


class LineNotificationManualReplayApplication:
    def __init__(self, unit_of_work_factory: Callable[[], LineUnitOfWorkPort], now: Callable[[], datetime]) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._now = now

    def preview_warning_skip(self, issue_key: str, actor: ActorContext) -> LineNotificationWarningSkipPreview:
        require_line_capability(actor, LineCapability.CONFIG_MANAGE)
        with self._unit_of_work_factory() as unit_of_work:
            return _warning_skip_preview(unit_of_work, issue_key)[0]

    def apply_warning_skip(self, issue_key: str, expected_snapshot: str, approved_fingerprint: str,
                           actor: ActorContext, idempotency_key: IdempotencyKey) -> LineNotificationWarningSkipReceipt:
        require_line_capability(actor, LineCapability.CONFIG_MANAGE)
        command_fingerprint = fingerprint_payload({"operation": LINE_NOTIFICATION_WARNING_SKIP_ACTION,
            "issue_key": issue_key, "owner_snapshot_token": expected_snapshot,
            "preview_fingerprint": approved_fingerprint, "actor": actor.actor_id})
        with self._unit_of_work_factory() as unit_of_work:
            existing = unit_of_work.receipts.get(idempotency_key, for_update=True)
            if existing is not None:
                if existing.payload_fingerprint != command_fingerprint or existing.result_reference != issue_key:
                    raise LineNotificationWarningSkipConflict("line_warning_skip_idempotency_conflict")
                return LineNotificationWarningSkipReceipt(issue_key, True)
            preview, readback, query = _warning_skip_preview(unit_of_work, issue_key, for_update=True)
            scope = build_line_notification_failure_recheck_intent(readback, cause_identity=idempotency_key.value).scope
            unit_of_work.anomaly_rechecks.lock_scope(scope)
            unit_of_work.add_after_completion(lambda: unit_of_work.anomaly_rechecks.release_scope(scope))
            preview, readback, query = _warning_skip_preview(unit_of_work, issue_key, for_update=True)
            if preview.owner_snapshot_token != expected_snapshot or preview.preview_fingerprint != approved_fingerprint:
                raise LineNotificationWarningSkipConflict("line_warning_skip_stale")
            unit_of_work.audit.append(LineAuditIntent(LINE_NOTIFICATION_WARNING_SKIP_ACTION, actor.actor_id,
                                                     "line_notification_failure", readback.owner_snapshot_token))
            after = unit_of_work.notification_rules.current_failure_fact(query)
            if not after.authoritative_complete or after.predicate_active:
                raise LineNotificationWarningSkipConflict("line_warning_skip_readback_conflict")
            unit_of_work.anomaly_rechecks.delete_current(issue_key)
            unit_of_work.anomaly_rechecks.append_recheck_intent(
                build_line_notification_failure_recheck_intent(after, cause_identity=idempotency_key.value))
            unit_of_work.receipts.append(IdempotencyReceipt(idempotency_key, command_fingerprint, issue_key))
            unit_of_work.commit()
        return LineNotificationWarningSkipReceipt(issue_key, False)

    def preview(self, source_event_id: int, actor: ActorContext) -> dict[str, object]:
        require_line_capability(actor, LineCapability.CONFIG_MANAGE)
        with self._unit_of_work_factory() as unit_of_work:
            return unit_of_work.notification_rules.preview_manual_replay(source_event_id)

    def apply(self, source_event_id: int, actor: ActorContext, reason: str, idempotency_key: IdempotencyKey, correlation_id: CorrelationId) -> int:
        require_line_capability(actor, LineCapability.CONFIG_MANAGE)
        if not reason.strip():
            raise ValueError("manual replay reason is required")
        with self._unit_of_work_factory() as unit_of_work:
            replayed_source_id = unit_of_work.notification_rules.manual_replay_source(
                source_event_id, f"manual-replay:{source_event_id}:{idempotency_key.value}", self._now()
            )
            targets = unit_of_work.notification_rules.line006_recheck_targets_for_source(
                source_event_id
            )
            append_line_notification_failure_rechecks(
                unit_of_work,
                targets,
                cause_identity=f"manual-replay:{source_event_id}:{idempotency_key.value}",
            )
            unit_of_work.audit.append(LineAuditIntent(
                "line.notification.manual_replay", actor.actor_id,
                "line_notification_source_event", str(source_event_id),
            ))
            unit_of_work.commit()
        return replayed_source_id


__all__ = ["LineNotificationManualReplayApplication"]
