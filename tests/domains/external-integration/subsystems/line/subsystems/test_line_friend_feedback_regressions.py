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


def _canonical_follow_handler(now=NOW):
    """Exercise the production composition; isolate unrelated worker components."""
    from contextlib import ExitStack
    from unittest.mock import patch
    from api.dependencies import line_worker_operation as runtime

    captured = []

    def capture_handler(*args, **kwargs):
        captured.append(LineWebhookIdentityHandlers(*args, **kwargs))
        # Follow handling is exercised below, not the unrelated dispatch registry.
        return SimpleNamespace(registry=lambda: {"postback": Mock()})

    with ExitStack() as stack:
        stack.enter_context(patch.object(runtime, "LineWebhookIdentityHandlers", side_effect=capture_handler))
        stack.enter_context(patch.object(runtime, "_identity_flow_url", lambda *_: "https://example.test/identity"))
        for name in (
            "LineOrderGroupApplication", "LineCandidateContactPostbackApplication",
            "LineMatchingPostbackApplication", "MatchingNotificationApplication",
            "MySqlSegmentedAvailabilityFactsRepository", "LineServiceHelpApplication",
            "HumanEscalationApplication", "LineMenuCommandApplication",
            "LineFeedbackApplication", "LineWebhookEventConsumer", "LineEventDispatcher",
        ):
            stack.enter_context(patch.object(runtime, name))
        runtime._event_consumer("worker:refollow-regression", lambda: now)
    return captured[0]


def _welcome_configuration(legacy="missing"):
    from domains.line.configuration import LineConfigurationKind

    templates = [{
        "id": "customer_onboarding_welcome", "message_type": "text",
        "enabled": True, "content": "目前的歡迎訊息：{url}",
        "variables": [{"name": "url", "required": True}],
    }]
    templates.extend({
        "id": f"new_user_d{day}", "message_type": "text", "enabled": True,
        "content": f"retired-day-{day}", "variables": [],
    } for day in (1, 2, 3))

    def get(kind):
        if kind is LineConfigurationKind.MESSAGE_TEMPLATES:
            return SimpleNamespace(definition_json=json.dumps({"templates": templates}))
        if kind is LineConfigurationKind.MESSAGE_SCHEDULES:
            if legacy == "missing":
                return None
            if legacy == "broken":
                raise RuntimeError("retired schedule unavailable")
            return SimpleNamespace(definition_json=json.dumps({
                "timezone": "Asia/Taipei", "schedules": [{
                    "id": "new_user_onboarding", "enabled": True, "trigger": "follow",
                    "restart_on_refollow": False,
                    "steps": [{"day": day, "send_time": "10:00", "template_id": f"new_user_d{day}"}
                              for day in (1, 2, 3)],
                }],
            }))
        raise AssertionError("unexpected configuration read")

    return SimpleNamespace(get=Mock(side_effect=get))


class CanonicalWelcomeRegressionTests(unittest.TestCase):
    def assert_welcome(self, unit, event_id):
        from domains.line.configuration import LineConfigurationKind

        unit.identity_flows.open.assert_called_once()
        unit.delivery_tasks.enqueue.assert_called_once()
        delivery = unit.delivery_tasks.enqueue.call_args.args[0]
        self.assertEqual(json.loads(delivery.payload_json)["text"],
                         "目前的歡迎訊息：https://example.test/identity")
        self.assertEqual(delivery.recipient.identity, USER)
        self.assertEqual(delivery.idempotency_key.value, f"identity-link:customer_binding:{event_id}")
        self.assertEqual(delivery.source_aggregate_type, "line_webhook_event")
        unit.configurations.get.assert_called_once_with(LineConfigurationKind.MESSAGE_TEMPLATES)

    def test_canonical_welcome_does_not_install_retired_scheduler(self):
        self.assertIsNone(_canonical_follow_handler()._follow_scheduler)

    def test_first_follow_creates_only_current_welcome_despite_old_enabled_schedule(self):
        unit, state = _friend_unit(LineFriendStatus.UNKNOWN)
        unit.configurations = _welcome_configuration("enabled")
        _canonical_follow_handler().handle_follow(_inbox("follow"), unit)
        self.assertIs(state[0].friend_status, LineFriendStatus.ACTIVE)
        self.assert_welcome(unit, "friend-feedback-event")

    def test_cross_day_refollow_ignores_missing_broken_or_old_enabled_schedule(self):
        for legacy in ("missing", "broken", "enabled"):
            with self.subTest(legacy=legacy):
                unit, state = _friend_unit(LineFriendStatus.BLOCKED)
                unit.configurations = _welcome_configuration(legacy)
                later = NOW + timedelta(days=2)
                inbox = _inbox("follow", occurred_at=later)
                inbox.event.event_id = LineWebhookEventId("refollow-event")
                _canonical_follow_handler(later).handle_follow(inbox, unit)
                self.assertIs(state[0].friend_status, LineFriendStatus.ACTIVE)
                self.assertIsNone(state[0].blocked_at)
                self.assert_welcome(unit, "refollow-event")
                self.assertEqual(unit.delivery_tasks.enqueue.call_args.args[0].scheduled_at, later)

    def test_unfollow_then_refollow_uses_a_new_welcome_event_identity(self):
        unit, state = _friend_unit(LineFriendStatus.UNKNOWN)
        unit.configurations = _welcome_configuration()
        _canonical_follow_handler().handle_follow(_inbox("follow"), unit)
        first_key = unit.delivery_tasks.enqueue.call_args.args[0].idempotency_key
        later = NOW + timedelta(days=1)
        _canonical_follow_handler(later).handle_unfollow(_inbox("unfollow", occurred_at=later), unit)
        unit.delivery_tasks.cancel_pending_for_recipient.assert_called_once_with(USER)
        self.assertIs(state[0].friend_status, LineFriendStatus.BLOCKED)
        unit.identity_flows.open.reset_mock()
        unit.delivery_tasks.enqueue.reset_mock()
        unit.configurations.get.reset_mock()
        later += timedelta(days=1)
        inbox = _inbox("follow", occurred_at=later)
        inbox.event.event_id = LineWebhookEventId("refollow-event")
        _canonical_follow_handler(later).handle_follow(inbox, unit)
        self.assert_welcome(unit, "refollow-event")
        self.assertNotEqual(unit.delivery_tasks.enqueue.call_args.args[0].idempotency_key, first_key)

    def test_same_follow_event_preserves_existing_welcome_idempotency_key(self):
        unit, _ = _friend_unit(LineFriendStatus.UNKNOWN)
        unit.configurations = _welcome_configuration()
        handler = _canonical_follow_handler()
        inbox = _inbox("follow")
        handler.handle_follow(inbox, unit)
        handler.handle_follow(inbox, unit)
        first, second = (call.args[0] for call in unit.delivery_tasks.enqueue.call_args_list)
        self.assertEqual(first.idempotency_key, second.idempotency_key)
        self.assertEqual(first.fingerprint, second.fingerprint)
        # Actual duplicate persistence remains owned by the unchanged delivery repository.

    def test_old_follow_does_not_reactivate_or_welcome_after_newer_unfollow(self):
        unit, state = _friend_unit(LineFriendStatus.BLOCKED)
        unit.configurations = _welcome_configuration("broken")
        _canonical_follow_handler().handle_follow(
            _inbox("follow", occurred_at=NOW - timedelta(days=1)), unit,
        )
        self.assertIs(state[0].friend_status, LineFriendStatus.BLOCKED)
        unit.identity_flows.open.assert_not_called()
        unit.delivery_tasks.enqueue.assert_not_called()
        unit.configurations.get.assert_not_called()

    def test_real_welcome_enqueue_failure_is_not_swallowed(self):
        unit, _ = _friend_unit(LineFriendStatus.BLOCKED)
        unit.configurations = _welcome_configuration()
        unit.delivery_tasks.enqueue.side_effect = RuntimeError("welcome persistence unavailable")
        with self.assertRaisesRegex(RuntimeError, "welcome persistence unavailable"):
            _canonical_follow_handler().handle_follow(_inbox("follow"), unit)

    def test_identity_flow_failure_cannot_claim_a_welcome_was_created(self):
        unit, _ = _friend_unit(LineFriendStatus.BLOCKED)
        unit.configurations = _welcome_configuration()
        unit.identity_flows.open.side_effect = RuntimeError("identity flow unavailable")
        with self.assertRaisesRegex(RuntimeError, "identity flow unavailable"):
            _canonical_follow_handler().handle_follow(_inbox("follow"), unit)
        unit.delivery_tasks.enqueue.assert_not_called()
