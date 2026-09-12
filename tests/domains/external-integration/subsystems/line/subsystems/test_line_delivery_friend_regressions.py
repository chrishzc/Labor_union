"""Focused regressions using real LINE workers and in-memory provider/DB seams."""

from __future__ import annotations

import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock

from domains.line.canonical_payload import canonical_line_payload_json
from domains.line.delivery import (
    LineDeliveryLease,
    LineDeliveryRequest,
    LineDeliveryStatus,
    LineDeliveryTaskSnapshot,
    LineMessageKind,
    LineRecipient,
    LineRecipientType,
)
from domains.line.identities import (
    LineDeliveryTaskId,
    LineProviderMessageId,
    LineUserId,
    LineWebhookEventId,
)
from domains.line.platform_user import (
    LineFriendEvent,
    LineFriendEventType,
    LineFriendStatus,
    LinePlatformUserSnapshot,
)
from infrastructure.mysql.line_platform_identity_repository import (
    MySqlLinePlatformUserRepository,
    _friend_event_result,
)
from shared_kernel.identities import CorrelationId, ExpectedVersion, IdempotencyKey
from subsystems.line.delivery_contracts import (
    LineProviderOutcome,
    LineProviderOutcomeType,
    LineReplyOpportunity,
)
from subsystems.line.delivery_worker import LineDeliveryWorker

NOW = datetime(2026, 9, 12, 12, tzinfo=timezone.utc)
USER = LineUserId("U-regression")


class Uow:
    def __init__(self, **repositories):
        self.__dict__.update(repositories)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def commit(self):
        pass


class DeliveryRepository:
    def __init__(self, count=1, *, knowledge=False):
        self.clock = NOW
        self.tasks = {index: _task(index, knowledge) for index in range(1, count + 1)}
        self.claims = []
        self.recorded = []

    def claim(self, query):
        self.claims.append(query)
        pending = [task for task in self.tasks.values() if task.status is LineDeliveryStatus.PENDING]
        claimed = []
        for task in pending[:query.batch_size]:
            lease = LineDeliveryLease(
                task.task_id, query.lease_owner, query.now, query.now + timedelta(seconds=60)
            )
            current = replace(task, status=LineDeliveryStatus.PROCESSING, lease=lease)
            self.tasks[task.task_id.value] = current
            claimed.append(current)
        return tuple(claimed)

    def get(self, task_id):
        return self.tasks.get(task_id.value)

    def reply_opportunity(self, _correlation_id):
        return LineReplyOpportunity("synthetic-reply-token", NOW + timedelta(seconds=45))

    def record_attempt(self, command):
        if command.completed_at > command.lease.expires_at:
            raise AssertionError("delivery was recorded after its lease expired")
        self.recorded.append(command)
        self.tasks[command.task.task_id.value] = replace(
            command.task, status=LineDeliveryStatus.SENT, lease=None
        )


def _task(index, knowledge=False):
    task_id = LineDeliveryTaskId(index)
    request = LineDeliveryRequest(
        LineRecipient(LineRecipientType.USER, USER),
        LineMessageKind.TEXT,
        canonical_line_payload_json({"type": "text", "text": "regression answer"}),
        NOW,
        IdempotencyKey(f"regression-delivery:{index}"),
        CorrelationId(f"line-event:regression:{index}"),
        "knowledge_answer_request" if knowledge else "review",
        str(index),
    )
    return LineDeliveryTaskSnapshot(task_id, request, LineDeliveryStatus.PENDING, 0, None)


def _success():
    return LineProviderOutcome(
        LineProviderOutcomeType.SUCCESS,
        provider_message_id=LineProviderMessageId("regression-provider-message"),
    )


class DeliveryRegressionTests(unittest.TestCase):
    def test_reply_server_errors_do_not_push_or_allow_automatic_retry(self):
        for status in (500, 502, 503, 504):
            with self.subTest(status=status):
                repository = DeliveryRepository(knowledge=True)
                provider = Mock()
                provider.reply.return_value = LineProviderOutcome(
                    LineProviderOutcomeType.UNAVAILABLE, error_code=f"line_http_{status}"
                )
                worker = LineDeliveryWorker(
                    lambda: Uow(delivery_tasks=repository), provider, "worker:regression",
                    lambda: repository.clock, batch_size=1,
                )
                self.assertEqual(worker.run_once(), 1)
                provider.reply.assert_called_once()
                provider.send.assert_not_called()
                self.assertEqual(repository.recorded[0].provider_outcome.error_code, "line_reply_outcome_uncertain")
                self.assertFalse(repository.recorded[0].retry_allowed)

    def test_reply_rate_limit_keeps_existing_push_behavior(self):
        repository = DeliveryRepository(knowledge=True)
        provider = Mock()
        provider.reply.return_value = LineProviderOutcome(
            LineProviderOutcomeType.RATE_LIMITED, error_code="line_http_429"
        )
        provider.send.return_value = _success()
        worker = LineDeliveryWorker(
            lambda: Uow(delivery_tasks=repository), provider, "worker:regression",
            lambda: repository.clock, batch_size=1,
        )
        self.assertEqual(worker.run_once(), 1)
        provider.reply.assert_called_once()
        provider.send.assert_called_once()

    def test_slow_batch_leases_each_task_only_when_it_is_ready_to_send(self):
        repository = DeliveryRepository(count=25)
        provider = Mock()

        def send(_request):
            repository.clock += timedelta(seconds=9)
            return _success()

        provider.send.side_effect = send
        worker = LineDeliveryWorker(
            lambda: Uow(delivery_tasks=repository), provider, "worker:regression",
            lambda: repository.clock,
        )
        self.assertEqual(worker.run_once(), 25)
        self.assertEqual(len(repository.recorded), 25)
        self.assertEqual(provider.send.call_count, 25)
        self.assertTrue(all(query.batch_size == 1 for query in repository.claims))
        self.assertEqual(
            [command.lease.acquired_at for command in repository.recorded],
            [NOW + timedelta(seconds=9 * index) for index in range(25)],
        )
        self.assertEqual(repository.clock, NOW + timedelta(seconds=225))

    def test_per_cycle_limit_is_preserved(self):
        repository = DeliveryRepository(count=3)
        provider = Mock()
        provider.send.return_value = _success()
        worker = LineDeliveryWorker(
            lambda: Uow(delivery_tasks=repository), provider, "worker:regression",
            lambda: repository.clock, batch_size=2,
        )
        self.assertEqual(worker.run_once(), 2)
        self.assertEqual(provider.send.call_count, 2)
        self.assertIs(repository.tasks[3].status, LineDeliveryStatus.PENDING)

    def test_expired_lease_after_validation_is_not_sent(self):
        repository = DeliveryRepository()
        provider = Mock()

        def validate(_task_id):
            repository.clock += timedelta(seconds=60)
            return None

        rules = SimpleNamespace(manual_replay_delivery_validation_failure=validate)
        worker = LineDeliveryWorker(
            lambda: Uow(delivery_tasks=repository, notification_rules=rules), provider,
            "worker:regression", lambda: repository.clock, batch_size=1,
        )
        self.assertEqual(worker.run_once(), 1)
        provider.send.assert_not_called()
        self.assertEqual(repository.recorded, [])

    def test_cancelled_task_is_not_sent(self):
        repository = DeliveryRepository()
        provider = Mock()

        def validate(task_id):
            repository.tasks[task_id] = replace(
                repository.tasks[task_id], status=LineDeliveryStatus.CANCELLED, lease=None
            )
            return None

        rules = SimpleNamespace(manual_replay_delivery_validation_failure=validate)
        worker = LineDeliveryWorker(
            lambda: Uow(delivery_tasks=repository, notification_rules=rules), provider,
            "worker:regression", lambda: repository.clock, batch_size=1,
        )
        self.assertEqual(worker.run_once(), 1)
        provider.send.assert_not_called()
        self.assertEqual(repository.recorded, [])


class FriendProjectionRegressionTests(unittest.TestCase):
    def test_late_unfollow_preserves_newer_follow_state_and_times(self):
        current = _snapshot(LineFriendStatus.ACTIVE)
        result = _friend_event_result(current, _event(LineFriendEventType.UNFOLLOW, NOW - timedelta(minutes=1)))
        self.assertEqual(result, replace(current, version=ExpectedVersion(3)))

    def test_late_follow_or_activity_cannot_clear_newer_block(self):
        current = _snapshot(LineFriendStatus.BLOCKED)
        for kind in (LineFriendEventType.FOLLOW, LineFriendEventType.ACTIVITY):
            with self.subTest(kind=kind):
                result = _friend_event_result(current, _event(kind, NOW - timedelta(minutes=1)))
                self.assertEqual(result, replace(current, version=ExpectedVersion(3)))

    def test_new_unfollow_still_blocks(self):
        when = NOW + timedelta(minutes=1)
        result = _friend_event_result(_snapshot(LineFriendStatus.ACTIVE), _event(LineFriendEventType.UNFOLLOW, when))
        self.assertIs(result.friend_status, LineFriendStatus.BLOCKED)
        self.assertEqual(result.blocked_at, when)
        self.assertEqual(result.last_event_at, when)

    def test_new_follow_still_unblocks(self):
        when = NOW + timedelta(minutes=1)
        result = _friend_event_result(_snapshot(LineFriendStatus.BLOCKED), _event(LineFriendEventType.FOLLOW, when))
        self.assertIs(result.friend_status, LineFriendStatus.ACTIVE)
        self.assertIsNone(result.blocked_at)
        self.assertEqual(result.last_event_at, when)

    def test_late_event_is_recorded_without_rewinding_legacy_projection(self):
        cursor = Mock()
        cursor.__enter__ = Mock(return_value=cursor)
        cursor.__exit__ = Mock(return_value=False)
        cursor.rowcount = 1
        cursor.fetchone.side_effect = [None, {
            "line_user_id": USER.value, "friend_status": "active",
            "aggregate_version": 2, "first_followed_at_utc": NOW,
            "last_followed_at_utc": NOW, "blocked_at_utc": None,
            "last_event_at_utc": NOW,
        }]
        repository = MySqlLinePlatformUserRepository(SimpleNamespace(cursor=lambda: cursor))
        result = repository.apply_friend_event(_event(LineFriendEventType.UNFOLLOW, NOW - timedelta(minutes=1)))
        statements = [call.args[0] for call in cursor.execute.call_args_list]
        self.assertIs(result.friend_status, LineFriendStatus.ACTIVE)
        self.assertEqual(result.version.value, 3)
        self.assertTrue(any("INSERT INTO line_friend_state_events" in sql for sql in statements))
        self.assertFalse(any("INSERT INTO line_users " in sql for sql in statements))


def _snapshot(status):
    return LinePlatformUserSnapshot(
        USER, status, ExpectedVersion(2),
        first_followed_at=NOW - timedelta(days=1), last_followed_at=NOW,
        blocked_at=NOW if status is LineFriendStatus.BLOCKED else None,
        last_event_at=NOW,
    )


def _event(kind, when):
    return LineFriendEvent(USER, LineWebhookEventId(f"regression:{kind.value}"), kind, when)


if __name__ == "__main__":
    unittest.main()
