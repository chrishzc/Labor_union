"""Exercise real LINE handlers/consumer with in-memory transaction boundaries."""

from __future__ import annotations

import json
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock

from domains.line.identities import LineIdentityFlowId, LineUserId, LineWebhookEventId
from domains.line.platform_user import LineFriendStatus, LinePlatformUserSnapshot
from domains.line.webhook import LineWebhookProcessingStatus
from infrastructure.mysql.line_platform_identity_repository import _friend_event_result
from shared_kernel.identities import ExpectedVersion
from subsystems.line.event_dispatcher import LineEventDispatcher
from subsystems.line.webhook_event_consumer import LineWebhookEventConsumer
from subsystems.line.webhook_identity_handlers import LineWebhookIdentityHandlers

NOW = datetime(2026, 9, 12, tzinfo=timezone.utc)
USER = LineUserId("U-friend-feedback-regression")


def _inbox(kind="message", *, occurred_at=NOW, text="未解決"):
    event_id = LineWebhookEventId("friend-feedback-event")
    return SimpleNamespace(
        event=SimpleNamespace(
            event_type=kind,
            event_id=event_id,
            occurred_at=occurred_at,
            source=SimpleNamespace(user_id=USER),
            payload_json=json.dumps({"message": {"type": "text", "text": text}}),
        ),
        lease=SimpleNamespace(event_id=event_id),
        attempt_count=1,
        max_attempts=3,
    )


def _friend_unit(status):
    state = [LinePlatformUserSnapshot(
        USER, status, ExpectedVersion(3), last_event_at=NOW,
        blocked_at=NOW if status is LineFriendStatus.BLOCKED else None,
    )]

    def apply(event):
        state[0] = _friend_event_result(state[0], event)
        return state[0]

    unit = SimpleNamespace(
        platform_users=SimpleNamespace(apply_friend_event=apply),
        identity_flows=SimpleNamespace(open=Mock(return_value=SimpleNamespace(
            flow_id=LineIdentityFlowId("regression-flow"),
        ))),
        delivery_tasks=SimpleNamespace(enqueue=Mock(), cancel_pending_for_recipient=Mock()),
    )
    return unit, state


def _feedback_unit(service):
    return SimpleNamespace(
        platform_users=SimpleNamespace(apply_friend_event=lambda _: None),
        customer_service=service,
        delivery_tasks=SimpleNamespace(enqueue=Mock()),
    )


def _handler(**kwargs):
    return LineWebhookIdentityHandlers(
        lambda: NOW, lambda *_: "https://example.test/identity", **kwargs,
    )


class FriendHandlerRegressionTests(unittest.TestCase):
    def test_old_unfollow_does_not_cancel_new_notifications(self):
        unit, state = _friend_unit(LineFriendStatus.ACTIVE)
        _handler().handle_unfollow(_inbox("unfollow", occurred_at=NOW - timedelta(seconds=5)), unit)
        self.assertIs(state[0].friend_status, LineFriendStatus.ACTIVE)
        self.assertEqual(state[0].last_event_at, NOW)
        unit.delivery_tasks.cancel_pending_for_recipient.assert_not_called()

    def test_current_unfollow_still_cancels_notifications(self):
        for offset in (0, 5):
            with self.subTest(offset=offset):
                unit, state = _friend_unit(LineFriendStatus.ACTIVE)
                _handler().handle_unfollow(_inbox("unfollow", occurred_at=NOW + timedelta(seconds=offset)), unit)
                self.assertIs(state[0].friend_status, LineFriendStatus.BLOCKED)
                unit.delivery_tasks.cancel_pending_for_recipient.assert_called_once_with(USER)

    def test_old_follow_does_not_open_flow_or_enqueue_welcome(self):
        for status in (LineFriendStatus.ACTIVE, LineFriendStatus.BLOCKED):
            with self.subTest(status=status):
                unit, state = _friend_unit(status)
                scheduler = Mock()
                _handler(follow_scheduler=scheduler).handle_follow(
                    _inbox("follow", occurred_at=NOW - timedelta(seconds=5)), unit,
                )
                self.assertIs(state[0].friend_status, status)
                scheduler.assert_not_called()
                unit.identity_flows.open.assert_not_called()
                unit.delivery_tasks.enqueue.assert_not_called()

    def test_current_follow_still_opens_flow_and_enqueues_welcome(self):
        for offset in (0, 5):
            with self.subTest(offset=offset):
                unit, state = _friend_unit(LineFriendStatus.BLOCKED)
                scheduler = Mock()
                inbox = _inbox("follow", occurred_at=NOW + timedelta(seconds=offset))
                _handler(follow_scheduler=scheduler).handle_follow(inbox, unit)
                self.assertIs(state[0].friend_status, LineFriendStatus.ACTIVE)
                scheduler.assert_called_once_with(inbox, unit, USER)
                unit.identity_flows.open.assert_called_once()
                unit.delivery_tasks.enqueue.assert_called_once()
                self.assertIn("https://example.test/identity", unit.delivery_tasks.enqueue.call_args.args[0].payload_json)

    def test_replayed_old_unfollow_uses_latest_returned_state(self):
        unit, state = _friend_unit(LineFriendStatus.ACTIVE)
        unit.platform_users.apply_friend_event = Mock(return_value=state[0])
        _handler().handle_unfollow(_inbox("unfollow", occurred_at=NOW - timedelta(seconds=5)), unit)
        unit.delivery_tasks.cancel_pending_for_recipient.assert_not_called()

    def test_old_message_keeps_business_handling_without_rewinding_friend_state(self):
        unit, state = _friend_unit(LineFriendStatus.BLOCKED)
        unit.customer_service = SimpleNamespace(create_or_append=Mock(return_value=SimpleNamespace(ticket_id=42)))
        _handler().handle_message(_inbox(occurred_at=NOW - timedelta(seconds=5)), unit)
        self.assertIs(state[0].friend_status, LineFriendStatus.BLOCKED)
        unit.customer_service.create_or_append.assert_called_once()
        unit.delivery_tasks.enqueue.assert_called_once()


class FeedbackHandlerRegressionTests(unittest.TestCase):
    def test_ticket_failure_propagates_without_success_acknowledgement(self):
        unit = _feedback_unit(SimpleNamespace(create_or_append=Mock(side_effect=RuntimeError("ticket unavailable"))))
        with self.assertRaisesRegex(RuntimeError, "ticket unavailable"):
            _handler().handle_message(_inbox(), unit)
        unit.delivery_tasks.enqueue.assert_not_called()

    def test_missing_repository_cannot_claim_success(self):
        for missing in (True, False):
            with self.subTest(missing=missing):
                unit = _feedback_unit(None)
                if missing:
                    del unit.customer_service
                with self.assertRaises(AttributeError):
                    _handler().handle_message(_inbox(), unit)
                unit.delivery_tasks.enqueue.assert_not_called()

    def test_success_acknowledgement_contains_created_ticket(self):
        service = SimpleNamespace(create_or_append=Mock(return_value=SimpleNamespace(ticket_id=42)))
        unit = _feedback_unit(service)
        _handler().handle_message(_inbox(), unit)
        command = service.create_or_append.call_args.args[0]
        self.assertEqual(command.event_key, "line-feedback-ticket:friend-feedback-event")
        self.assertEqual(command.line_user_id, USER.value)
        unit.delivery_tasks.enqueue.assert_called_once()
        delivery = unit.delivery_tasks.enqueue.call_args.args[0]
        self.assertIn("#42", delivery.payload_json)
        self.assertEqual(delivery.idempotency_key.value, "feedback-unresolved:friend-feedback-event")

    def test_resolved_feedback_does_not_require_a_ticket(self):
        unit = _feedback_unit(None)
        _handler().handle_message(_inbox(text="有幫助"), unit)
        unit.delivery_tasks.enqueue.assert_called_once()
        self.assertNotIn("已為您通報", unit.delivery_tasks.enqueue.call_args.args[0].payload_json)

    def test_ticket_failure_rolls_back_then_retries_without_false_acknowledgement(self):
        inbox = _inbox()
        state = {"fail_ticket": True, "persisted": [], "transactions": []}
        consumer = _consumer(inbox, state)
        self.assertEqual(consumer.run_once(), 1)
        self.assertEqual(state["transactions"], ["commit", "rollback", "commit"])
        self.assertEqual([kind for kind, _ in state["persisted"]], ["completion"])
        failure = state["persisted"][0][1]
        self.assertIs(failure.target_status, LineWebhookProcessingStatus.RETRYABLE_FAILED)
        self.assertEqual(failure.error_code, "RuntimeError")
        self.assertEqual(failure.retry_after_seconds, 15)

        state["fail_ticket"] = False
        inbox.attempt_count = 2
        self.assertEqual(consumer.run_once(), 1)
        self.assertEqual([kind for kind, _ in state["persisted"]], ["completion", "ticket", "delivery", "completion"])
        self.assertEqual(state["persisted"][1][1], "line-feedback-ticket:friend-feedback-event")
        self.assertIn("#42", state["persisted"][2][1].payload_json)
        self.assertIs(state["persisted"][3][1].target_status, LineWebhookProcessingStatus.PROCESSED)

    def test_exhausted_ticket_failure_is_terminal_without_success_acknowledgement(self):
        inbox = _inbox()
        inbox.attempt_count = inbox.max_attempts
        state = {"fail_ticket": True, "persisted": [], "transactions": []}
        self.assertEqual(_consumer(inbox, state).run_once(), 1)
        self.assertEqual([kind for kind, _ in state["persisted"]], ["completion"])
        completion = state["persisted"][0][1]
        self.assertIs(completion.target_status, LineWebhookProcessingStatus.TERMINAL_FAILED)
        self.assertIsNone(completion.retry_after_seconds)


def _consumer(inbox, state):
    class UnitOfWork:
        def __init__(self):
            self.pending = []
            self.committed = False
            self.platform_users = SimpleNamespace(apply_friend_event=lambda _: None)
            self.customer_service = self
            self.delivery_tasks = self
            self.webhook_inbox = self

        def __enter__(self):
            return self

        def __exit__(self, *_):
            if not self.committed:
                self.pending.clear()
                state["transactions"].append("rollback")
            return False

        def claim(self, _query):
            return (inbox,)

        def create_or_append(self, command):
            self.pending.append(("ticket", command.event_key))
            if state["fail_ticket"]:
                raise RuntimeError("ticket unavailable")
            return SimpleNamespace(ticket_id=42)

        def enqueue(self, delivery):
            self.pending.append(("delivery", delivery))

        def complete(self, command):
            self.pending.append(("completion", command))

        def commit(self):
            state["persisted"].extend(self.pending)
            self.committed = True
            state["transactions"].append("commit")

    return LineWebhookEventConsumer(
        UnitOfWork, LineEventDispatcher(_handler().registry()), "worker:test", lambda: NOW,
    )
