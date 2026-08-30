"""
File: runtime_alert_application.py
Description: 投影 runtime health 並委派 LINE alert target 唯一 registration writer。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable, Protocol

from domains.line.canonical_payload import canonical_line_payload_json
from domains.line.delivery import LineDeliveryRequest, LineMessageKind, LineRecipient, LineRecipientType
from domains.line.identities import LineGroupId, LineUserId
from shared_kernel.identities import CorrelationId, IdempotencyKey
from subsystems.line.runtime_contracts import LineWebhookSecurityReceipt, LineWorkerHeartbeat
from subsystems.line.runtime_monitoring import RuntimeHealthObservation


class _RuntimeIdentity(Protocol):
    service_name: str
    instance_id: str
    process_id: int
    hostname: str
    release_version: str
    started_at: datetime


class _LineRuntimeRepository(Protocol):
    def append_security_receipt(self, receipt: LineWebhookSecurityReceipt) -> None: ...

    def record_heartbeat(self, heartbeat: LineWorkerHeartbeat) -> None: ...


class _LineRuntimeUnitOfWork(Protocol):
    def __enter__(self): ...

    def __exit__(self, exception_type, exception, traceback) -> bool: ...

    def commit(self) -> None: ...


class LineRuntimeApplication:
    """Own LINE runtime persistence UoWs while adapters borrow the connection."""

    def __init__(self, unit_of_work_factory, repository_factory) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._repository_factory = repository_factory

    def record_webhook_security_receipt(
        self,
        request_fingerprint: str,
        signature_present: bool,
        outcome,
        event_count: int,
        correlation_id: str,
    ) -> None:
        receipt = LineWebhookSecurityReceipt(
            request_fingerprint,
            signature_present,
            outcome,
            event_count,
            correlation_id,
            datetime.now(timezone.utc),
        )
        with self._unit_of_work_factory() as unit_of_work:
            self._repository_factory(unit_of_work).append_security_receipt(receipt)
            unit_of_work.commit()

    def record_heartbeat(self, heartbeat: LineWorkerHeartbeat) -> None:
        with self._unit_of_work_factory() as unit_of_work:
            self._repository_factory(unit_of_work).record_heartbeat(heartbeat)
            unit_of_work.commit()


class RuntimeHeartbeatApplication:
    """Persist a service heartbeat in one application-owned UoW."""

    def __init__(self, unit_of_work_factory, repository_factory) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._repository_factory = repository_factory

    def record(self, identity: _RuntimeIdentity, processed: int) -> None:
        with self._unit_of_work_factory() as unit_of_work:
            self._repository_factory(unit_of_work).record_heartbeat(
                identity.service_name,
                identity.instance_id,
                identity.process_id,
                identity.hostname,
                "running",
                _runtime_heartbeat_details(identity, processed),
                datetime.now(timezone.utc),
            )
            unit_of_work.commit()


class RuntimeMonitoringApplication:
    """Run one monitor cycle and persist its health projection atomically."""

    def __init__(
        self,
        unit_of_work_factory,
        line_runtime_repository_factory,
        delivery_task_repository_factory,
        connection_factory,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._line_runtime_repository_factory = line_runtime_repository_factory
        self._delivery_task_repository_factory = delivery_task_repository_factory
        self._connection_factory = connection_factory

    def record_cycle(self, runtime_identity: _RuntimeIdentity, observations: Iterable[object]):
        from subsystems.line.runtime_monitoring_application import (
            _database_observations,
            _external_observations,
            _heartbeat_details,
            _media_storage_observation,
            _record_observations,
            _redis_observation,
        )

        with self._unit_of_work_factory() as unit_of_work:
            connection = self._connection_factory(unit_of_work)
            now = datetime.now(timezone.utc)
            application_checks = (_redis_observation(now), _media_storage_observation(now))
            runtime_monitor = unit_of_work.runtime_monitor
            runtime_monitor.record_heartbeat(
                runtime_identity.service_name,
                runtime_identity.instance_id,
                runtime_identity.process_id,
                runtime_identity.hostname,
                "running",
                _heartbeat_details(runtime_identity, 0),
                now,
            )
            projected_observations = [
                *_external_observations(observations),
                *_database_observations(
                    connection, self._line_runtime_repository_factory(unit_of_work), now
                ),
                *application_checks,
            ]
            projected_count = _record_observations(
                runtime_monitor,
                self._delivery_task_repository_factory(unit_of_work),
                projected_observations,
            )
            unit_of_work.commit()
            return len(projected_observations), projected_count

    def inspect_readiness(self) -> tuple[RuntimeHealthObservation, ...]:
        from subsystems.line.runtime_monitoring_application import (
            _database_readiness_observation,
            _media_storage_observation,
            _redis_observation,
        )

        with self._unit_of_work_factory() as unit_of_work:
            connection = self._connection_factory(unit_of_work)
            now = datetime.now(timezone.utc)
            return (
                _database_readiness_observation(connection, now),
                _redis_observation(now),
                _media_storage_observation(now),
            )


def _runtime_heartbeat_details(identity: _RuntimeIdentity, processed: int) -> dict[str, object]:
    return {
        "processed_last_cycle": processed,
        "release_version": identity.release_version,
        "caller_started_at": identity.started_at.isoformat(),
    }


class RuntimeLineAlertProjector:
    def __init__(self, now) -> None:
        self._now = now

    def project(self, event_id: int, repository, delivery_tasks) -> int:
        queued = 0
        for target in repository.pending_alert_targets(event_id):
            resolved_type, resolved_id = _resolve_target(target)
            if not resolved_id or not _meets_threshold(str(target["resulting_status"]), str(target["minimum_status"])):
                repository.append_alert_intent(event_id, int(target["id"]), None, "skipped", resolved_type, resolved_id, "target_unavailable_or_below_threshold")
                continue
            identity = LineGroupId(resolved_id) if resolved_type == "group" else LineUserId(resolved_id)
            result = delivery_tasks.enqueue(LineDeliveryRequest(
                LineRecipient(LineRecipientType(resolved_type), identity),
                LineMessageKind.TEXT,
                canonical_line_payload_json({"type": "text", "text": _message(target)}),
                self._now(),
                IdempotencyKey(f"runtime-alert:{event_id}:{target['id']}"),
                CorrelationId(f"runtime-health-event:{event_id}"),
                "runtime_health_event",
                str(event_id),
            ))
            repository.append_alert_intent(event_id, int(target["id"]), result.task_id.value, "queued", resolved_type, resolved_id)
            queued += 1
        return queued


def register_group_alert_target(inbox, unit_of_work, actor) -> bool:
    from subsystems.line.runtime_alert_target_application import RuntimeAlertTargetApplication

    return RuntimeAlertTargetApplication(
        lambda: unit_of_work,
        lambda: inbox.event.occurred_at,
    ).register_group(
        unit_of_work,
        inbox.event.source.source_id,
        actor.actor_id,
        inbox.event.event_id.value,
    )


def _resolve_target(target):
    if str(target["target_type"]) == "group":
        return "group", str(target["group_id"] or "")
    return "user", str(target["linked_line_user_id"] or "")


def _meets_threshold(status, threshold):
    weights = {"healthy": 0, "unknown": 0, "maintenance": 0, "warning": 1, "critical": 2}
    return weights.get(status, 0) >= weights.get(threshold, 1) or status == "healthy"


def _message(target):
    status = str(target["resulting_status"])
    heading = "系統已恢復" if status == "healthy" else "系統異常通知"
    occurred = target["occurred_at_utc"]
    stamp = occurred.isoformat(sep=" ", timespec="seconds") if isinstance(occurred, datetime) else str(occurred)
    return f"【{heading}】\n元件：{target['check_name']}\n狀態：{status}\n說明：{target['message']}\n時間：{stamp} UTC"


__all__ = ["RuntimeLineAlertProjector", "register_group_alert_target"]
