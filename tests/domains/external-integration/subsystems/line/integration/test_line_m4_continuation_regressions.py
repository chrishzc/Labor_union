"""Cross-owner LINE/customer-service SQL and delivery regressions without network effects.

SQLite executes the ticket/target adapter SQL after placeholder conversion and
removal of MySQL's FOR UPDATE suffix. It does not prove MySQL locking behavior.
"""

from __future__ import annotations

import copy
import json
import os
import sqlite3
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock, patch

from domains.customer_service.ticket import CustomerServiceCategory, CustomerServiceStatus, CustomerServiceVersionConflictError
from domains.line.delivery import LineDeliveryLease, LineDeliveryStatus, LineDeliveryTaskSnapshot
from domains.line.identities import LineDeliveryTaskId, LineProviderMessageId
from infrastructure.mysql.customer_service_repository import MySqlCustomerServiceRepository
from infrastructure.mysql.customer_service_escalation_repository import MySqlCustomerServiceEscalationRepository
from infrastructure.mysql.line_safe_review_link_repository import MySqlLineSafeReviewLinkRepository
from shared_kernel.identities import ActorContext, CorrelationId, IdempotencyKey
from subsystems.customer_service.contracts import CreateCustomerServiceMessage
from subsystems.customer_service.escalation_application import _admin_resolution_delivery
from subsystems.line.delivery_contracts import LineProviderOutcome, LineProviderOutcomeType
from subsystems.line.delivery_worker import LineDeliveryWorker
from subsystems.line.human_escalation_delivery import HumanEscalationDeliveryError, HumanEscalationOutboxItem, _request
from subsystems.line.runtime_alert_target_application import RuntimeAlertTargetApplication, RuntimeAlertTargetError, _target_view
from subsystems.line.runtime_alert_target_contracts import ResetLineAlertGroupCommand
from subsystems.line.safe_review_link_application import SafeReviewLinkApplication
from subsystems.line.safe_review_link_contracts import IssueSafeReviewLink, RedeemSafeReviewLink, SafeReviewLinkError

NOW = datetime(2026, 9, 13, tzinfo=timezone.utc)
ACTOR = ActorContext("admin:7", ("line.alert.manage",))


class SqlCursor:
    def __init__(self, owner):
        self.owner = owner
        self.inner = owner.db.cursor()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.inner.close()
        return False

    def execute(self, sql, params=()):
        self.owner.statements.append((sql, params))
        self.inner.execute(sql.replace("%s", "?").replace(" FOR UPDATE", ""), params)

    @property
    def rowcount(self):
        return self.inner.rowcount

    def fetchone(self):
        row = self.inner.fetchone()
        return dict(row) if row is not None else None

    def fetchall(self):
        return [dict(row) for row in self.inner.fetchall()]


class SqlConnection:
    def __init__(self):
        self.db = sqlite3.connect(":memory:")
        self.db.row_factory = sqlite3.Row
        self.db.create_function("IF", 3, lambda condition, yes, no: yes if condition else no)
        self.statements = []
        self.db.executescript("""
            CREATE TABLE clients (id INTEGER PRIMARY KEY, name TEXT, phone TEXT);
            CREATE TABLE customer_service_tickets (
                id INTEGER PRIMARY KEY, line_user_id TEXT, category TEXT, status TEXT,
                version INTEGER, assigned_to_admin_user_id INTEGER, client_id INTEGER,
                resolved_at_utc TEXT);
            CREATE TABLE customer_service_ticket_events (
                id INTEGER PRIMARY KEY, ticket_id INTEGER, event_key TEXT UNIQUE,
                event_type TEXT, message_text TEXT, actor_id TEXT);
            CREATE TABLE admin_users (id INTEGER PRIMARY KEY, linked_line_user_id TEXT);
            CREATE TABLE line_alert_notification_targets (
                id INTEGER PRIMARY KEY, target_type TEXT, group_id TEXT, minimum_status TEXT,
                updated_at_utc TEXT, enabled BOOLEAN, admin_user_id INTEGER);
            CREATE TABLE line_safe_review_link_events (
                id INTEGER PRIMARY KEY, link_id INTEGER, event_type TEXT, event_payload TEXT);
        """)

    def cursor(self):
        return SqlCursor(self)


class TicketSqlTests(unittest.TestCase):
    def setUp(self):
        self.connection = SqlConnection()
        self.addCleanup(self.connection.db.close)
        self.repo = MySqlCustomerServiceRepository(self.connection)
        self.connection.db.execute(
            "INSERT INTO customer_service_tickets VALUES (31,'U-m4','other','resolved',2,NULL,NULL,'2026-09-01')"
        )

    def test_new_message_reopens_then_escalation_can_take_over_same_ticket(self):
        ticket = self.repo.create_or_append(CreateCustomerServiceMessage(
            "U-m4", CustomerServiceCategory.OTHER, "synthetic complaint", "message:m4:1"
        ))
        self.assertIs(ticket.status, CustomerServiceStatus.HANDLING)
        self.assertEqual(ticket.version, 3)
        handled = self.repo.start_handling_for_escalation(31, 3, "admin:7")
        self.assertIs(handled.status, CustomerServiceStatus.HANDLING)
        self.assertEqual(handled.version, 4)
        self.assertEqual(handled.assigned_admin_user_id, 7)
        self.assertEqual(self.connection.db.execute("SELECT COUNT(*) FROM customer_service_ticket_events").fetchone()[0], 2)

    def test_waiting_ticket_can_still_be_taken_over(self):
        self.connection.db.execute("UPDATE customer_service_tickets SET status='waiting'")
        self.assertEqual(self.repo.start_handling_for_escalation(31, 2, "admin:7").version, 3)

    def test_stale_version_does_not_append_an_event_or_change_ticket(self):
        self.connection.db.execute("UPDATE customer_service_tickets SET status='handling'")
        with self.assertRaises(CustomerServiceVersionConflictError):
            self.repo.start_handling_for_escalation(31, 1, "admin:7")
        self.assertEqual(self.repo.get(31).version, 2)
        self.assertEqual(self.connection.db.execute("SELECT COUNT(*) FROM customer_service_ticket_events").fetchone()[0], 0)

    def test_resolved_ticket_cannot_be_taken_over_without_new_message(self):
        with self.assertRaises(CustomerServiceVersionConflictError):
            self.repo.start_handling_for_escalation(31, 2, "admin:7")
        self.assertIs(self.repo.get(31).status, CustomerServiceStatus.RESOLVED)


class TargetSqlTests(unittest.TestCase):
    def setUp(self):
        self.connection = SqlConnection()
        self.addCleanup(self.connection.db.close)
        self.repo = MySqlCustomerServiceEscalationRepository(self.connection)
        self.connection.db.execute("INSERT INTO admin_users VALUES (1,'U-admin')")

    def add(self, identifier, kind, enabled=True):
        self.connection.db.execute(
            "INSERT INTO line_alert_notification_targets VALUES (?,?,?,?,?,?,?)",
            (identifier, kind, f"C-group-{identifier}" if kind == "group" else None,
             "warning", NOW.isoformat(), enabled, 1 if kind == "admin_user" else None),
        )

    def test_retired_group_does_not_override_admin_target(self):
        self.add(1, "admin_user")
        self.add(9, "group")
        target = self.repo._active_alert_target_snapshot()
        self.assertEqual((target["target_id"], target["recipient_type"]), (1, "user"))

    def test_group_alone_is_not_a_delivery_target(self):
        self.add(9, "group")
        self.assertIsNone(self.repo._active_alert_target_snapshot())

    def test_single_admin_without_group_keeps_existing_behavior(self):
        self.add(1, "admin_user")
        self.assertEqual(self.repo._active_alert_target_snapshot()["recipient_type"], "user")

    def test_multiple_admins_without_group_remain_ambiguous(self):
        self.add(1, "admin_user")
        self.add(2, "admin_user")
        self.assertIsNone(self.repo._active_alert_target_snapshot())

    def test_multiple_retired_groups_do_not_hide_the_admin_target(self):
        self.add(1, "admin_user")
        self.add(2, "group")
        self.add(9, "group")
        self.assertEqual(self.repo._active_alert_target_snapshot()["target_id"], 1)

    def test_disabled_group_is_not_selected(self):
        self.add(9, "group", False)
        self.assertIsNone(self.repo._active_alert_target_snapshot())

    def test_issued_target_snapshot_is_loaded_from_immutable_event(self):
        snapshot = {"target_id": 9, "current_version": "a" * 64}
        self.connection.db.execute("INSERT INTO line_safe_review_link_events VALUES (1,12,'issued',?)",
                                   (json.dumps({"runtime_alert_target": snapshot}),))
        repo = MySqlLineSafeReviewLinkRepository(self.connection)
        self.assertEqual(repo.get_issued_runtime_target(12), snapshot)
        self.assertIsNone(repo.get_issued_runtime_target(99))
        self.assertEqual(self.connection.statements[-1][1], (99,))


def group(identifier=1, enabled=True):
    return {"id": identifier, "group_id": f"C-group-{identifier}", "target_type": "group",
            "enabled": enabled, "minimum_status": "critical", "updated_at_utc": NOW}


class RuntimeRepo:
    def __init__(self, rows=()):
        self.rows = {row["id"]: dict(row) for row in rows}
        self.receipts = {}
        self.audits = []
        self.updates = 0
        self.inserts = 0
        self.lock_ok = True
        self.locked = False
        self.releases = 0
        self.read_locks = []

    def list_alert_targets(self):
        return tuple(dict(row) for row in self.rows.values())

    def find_active_group_targets(self, *, for_update):
        self.read_locks.append(for_update)
        return tuple(dict(row) for row in self.rows.values() if row["target_type"] == "group" and row["enabled"])

    def find_group_target(self, group_id, *, for_update):
        return next((dict(row) for row in self.rows.values() if row["group_id"] == group_id), None)

    def get_alert_target(self, identifier, *, for_update):
        return dict(self.rows[identifier])

    def insert_group_target(self, group_id, name, actor):
        self.inserts += 1
        identifier = max(self.rows, default=0) + 1
        self.rows[identifier] = {**group(identifier), "group_id": group_id}
        return identifier

    def update_alert_target_enabled(self, identifier, enabled):
        self.updates += 1
        self.rows[identifier]["enabled"] = enabled
        self.rows[identifier]["updated_at_utc"] += timedelta(microseconds=1)

    def acquire_alert_target_lock(self, seconds):
        self.locked = self.lock_ok
        return self.lock_ok

    def release_alert_target_lock(self):
        self.locked = False
        self.releases += 1
        return True

    def load_admin_command_receipt(self, family, key, *, for_update):
        return self.receipts.get((family, key))

    def save_admin_command_receipt(self, family, key, fingerprint, actor, reason, result):
        self.receipts[(family, key)] = {"request_fingerprint": fingerprint, "result_snapshot": copy.deepcopy(result)}

    def save_alert_target_admin_audit(self, actor, action, identifier, details):
        self.audits.append((actor, action, identifier, copy.deepcopy(details)))


class Uow:
    def __init__(self, **repositories):
        self.__dict__.update(repositories)
        self.committed = False
        self.hooks = []

    def __enter__(self):
        self.committed = False
        runtime = getattr(self, "runtime_monitor", None)
        self.runtime_before = None if runtime is None else copy.deepcopy({
            name: getattr(runtime, name)
            for name in ("rows", "receipts", "audits", "updates", "inserts")
        })
        return self

    def __exit__(self, error_type, *_):
        # Model the existing caller-owned runtime transaction for rollback tests.
        if self.runtime_before is not None and (error_type is not None or not self.committed):
            for name, value in self.runtime_before.items():
                setattr(self.runtime_monitor, name, value)
        hooks, self.hooks = self.hooks, []
        for hook in hooks:
            hook()
        return False

    def commit(self):
        self.committed = True

    def add_after_completion(self, hook):
        self.hooks.append(hook)


class GroupRegistrationTests(unittest.TestCase):
    def setUp(self):
        self.repo = RuntimeRepo()
        self.app = RuntimeAlertTargetApplication(lambda: Uow(runtime_monitor=self.repo), lambda: NOW)

    def register(self, event="event:1", group_id="C-group-1"):
        before = copy.deepcopy((self.repo.rows, self.repo.receipts, self.repo.audits))
        unit = Uow(runtime_monitor=self.repo)
        with self.assertRaises(RuntimeAlertTargetError) as error:
            self.app.register_group(unit, group_id, ACTOR.actor_id, event)
        self.assertEqual(error.exception.code, "line_alert_group_retired")
        self.assertEqual((self.repo.rows, self.repo.receipts, self.repo.audits), before)
        self.assertFalse(unit.committed)
        self.assertEqual((self.repo.updates, self.repo.inserts, self.repo.releases), (0, 0, 0))

    def reset(self):
        before = copy.deepcopy((self.repo.rows, self.repo.receipts, self.repo.audits))
        with self.assertRaises(RuntimeAlertTargetError) as error:
            self.app.reset(ResetLineAlertGroupCommand(
                "a" * 64, "historical reset", IdempotencyKey("reset:1"), CorrelationId("corr:reset"), ACTOR))
        self.assertEqual(error.exception.code, "line_alert_group_retired")
        self.assertEqual((self.repo.rows, self.repo.receipts, self.repo.audits), before)
        self.assertEqual((self.repo.updates, self.repo.inserts, self.repo.releases), (0, 0, 0))

    def test_retired_reset_and_new_event_cannot_reactivate_disabled_group(self):
        self.repo.rows = {1: group(1, False)}
        self.reset()
        self.register("event:2")

    def test_old_registration_receipt_cannot_reactivate_group(self):
        self.repo.rows = {1: group(1, False)}
        self.repo.receipts[("line_alert_target", "line-alert-registration:event:1")] = {"legacy": "receipt"}
        self.register()

    def test_active_group_registration_is_rejected_without_new_audit(self):
        self.repo.rows = {1: group(1)}
        self.register("event:2")

    def test_retired_registration_preserves_other_active_group(self):
        self.repo.rows = {1: group(1, False), 2: group(2)}
        self.register()

    def test_retired_registration_preserves_multiple_historical_groups(self):
        self.repo.rows = {1: group(1), 2: group(2)}
        self.register()

    def test_retired_registration_does_not_attempt_lock(self):
        self.repo.rows = {1: group(1, False)}
        self.repo.lock_ok = False
        self.register()

    def test_retired_event_cannot_register_another_group(self):
        self.repo.receipts[("line_alert_target", "line-alert-registration:event:1")] = {"legacy": "receipt"}
        self.register(group_id="C-other")

    def test_retired_registration_does_not_call_audit_writer(self):
        self.repo.rows = {1: group(1, False)}
        with patch.object(self.repo, "save_alert_target_admin_audit", side_effect=AssertionError("retired audit writer")):
            self.register()


class LinkRepo:
    def __init__(self):
        self.links = {}
        self.events = []
        self.outbox = []
        self.receipts = {}

    def load_receipt(self, key, *, for_update=False):
        return copy.deepcopy(self.receipts.get(key))

    def get_link(self, key, *, for_update=False):
        return copy.deepcopy(self.links.get(key))

    def insert_link(self, **values):
        values["issued_at_utc"] = values.pop("issued_at")
        values["expires_at_utc"] = values.pop("expires_at")
        row = {**values, "id": len(self.links) + 1, "status": "issued", "root_version": 0}
        self.links[values["link_id"]] = row
        return row["id"]

    def insert_event(self, identifier, event_type, *args):
        self.events.append((identifier, event_type, copy.deepcopy(args[-1])))

    def get_issued_runtime_target(self, identifier):
        return next((copy.deepcopy(payload.get("runtime_alert_target")) for pk, kind, payload in self.events
                     if pk == identifier and kind == "issued"), None)

    def insert_outbox(self, *args):
        self.outbox.append(copy.deepcopy(args))

    def insert_receipt(self, key, fingerprint, outcome, result, identifier):
        self.receipts[key] = {"idempotency_key": key, "command_fingerprint": fingerprint,
                              "outcome": outcome, "result_snapshot": copy.deepcopy(result)}

    def transition(self, identifier, status, at):
        row = next(row for row in self.links.values() if row["id"] == identifier)
        row["status"] = status
        row["root_version"] += 1
        if status in {"redeemed", "revoked"}:
            row[status + "_at_utc"] = at


class SafeLinkFreshTargetTests(unittest.TestCase):
    def setUp(self):
        self.links = LinkRepo()
        self.runtime = RuntimeRepo((group(),))
        self.clock = NOW
        self.units = []
        def factory():
            unit = Uow(safe_review_links=self.links, runtime_monitor=self.runtime)
            self.units.append(unit)
            return unit
        self.app = SafeReviewLinkApplication(factory, lambda: self.clock)
        self.issue = IssueSafeReviewLink(
            "link:m4", "synthetic-m4-link-token", "/api/v1/runtime/health-status", 3,
            "alert:m4", ACTOR.actor_id, "line.alert.manage", 60, ACTOR,
            IdempotencyKey("issue:m4"), CorrelationId("corr:issue"),
        )
        self.redeem = RedeemSafeReviewLink(
            self.issue.link_id, self.issue.raw_token, ACTOR, "line.alert.manage",
            self.issue.canonical_internal_target, 3, IdempotencyKey("redeem:m4"), CorrelationId("corr:redeem"),
        )

    def assert_retired_without_effect(self):
        before = copy.deepcopy((self.links.links, self.links.events, self.links.outbox, self.links.receipts))
        for operation in (lambda: self.app.issue(self.issue), lambda: self.app.redeem(self.redeem)):
            with self.assertRaises(SafeReviewLinkError) as error:
                operation()
            self.assertEqual(error.exception.code, "line_alert_group_retired")
        self.assertEqual((self.links.links, self.links.events, self.links.outbox, self.links.receipts), before)
        self.assertEqual(self.units, [])

    def test_retired_issue_does_not_record_owner_or_token(self):
        self.assert_retired_without_effect()

    def test_retired_link_cannot_redeem_for_unchanged_target(self):
        self.links.links[self.issue.link_id] = {"id": 1, "status": "issued", "root_version": 0}
        self.assert_retired_without_effect()

    def test_retired_link_cannot_redeem_after_owner_version_changes(self):
        self.runtime.rows[1]["updated_at_utc"] += timedelta(seconds=1)
        self.assert_retired_without_effect()

    def test_disable_then_reactivate_group_cannot_revive_retired_link(self):
        self.runtime.update_alert_target_enabled(1, False)
        self.runtime.update_alert_target_enabled(1, True)
        self.assert_retired_without_effect()

    def test_changed_group_identity_cannot_enable_retired_link(self):
        self.runtime.rows = {2: group(2)}
        self.assert_retired_without_effect()

    def test_absent_group_cannot_enable_retired_link(self):
        self.runtime.rows[1]["enabled"] = False
        self.assert_retired_without_effect()

    def test_retired_link_without_owner_evidence_has_zero_effect(self):
        self.links.events = [(1, "issued", {})]
        self.assert_retired_without_effect()

    def test_expired_link_and_other_actor_cannot_bypass_retirement(self):
        self.clock += timedelta(seconds=61)
        self.redeem = replace(self.redeem, actor=ActorContext("admin:8", ("line.alert.manage",)))
        self.assert_retired_without_effect()

    def test_retired_issue_preserves_historical_receipt_and_outbox(self):
        self.links.receipts[self.issue.idempotency_key.value] = {"legacy": "receipt"}
        self.links.outbox = [("historical", "unchanged")]
        self.assert_retired_without_effect()

    def test_threshold_change_cannot_enable_retired_link(self):
        self.runtime.rows[1]["minimum_status"] = "warning"
        self.assert_retired_without_effect()

    def test_new_key_cannot_redeem_historical_used_link(self):
        self.links.links[self.issue.link_id] = {"id": 1, "status": "redeemed", "root_version": 1}
        self.redeem = replace(self.redeem, idempotency_key=IdempotencyKey("redeem:other"))
        self.assert_retired_without_effect()


class DeliveryRepo:
    def __init__(self, request, resulting_status):
        task_id = LineDeliveryTaskId(1)
        self.task = LineDeliveryTaskSnapshot(task_id, request, LineDeliveryStatus.PROCESSING, 0,
            LineDeliveryLease(task_id, "worker:m4", NOW, NOW + timedelta(seconds=60)))
        self.claimed = False
        self.recorded = []
        self.resulting_status = resulting_status

    def claim(self, query):
        if self.claimed:
            return ()
        self.claimed = True
        return (self.task,)

    def get(self, task_id):
        return self.task

    def record_attempt(self, command):
        self.recorded.append(command)
        return SimpleNamespace(plan=SimpleNamespace(resulting_status=self.resulting_status))


class ResolutionDeliveryTests(unittest.TestCase):
    def request(self):
        return _admin_resolution_delivery(
            SimpleNamespace(ticket_id=31, line_user_id="U-requester"),
            SimpleNamespace(expected_escalation_version=2, correlation_id=CorrelationId("corr:resolve")), 9, NOW,
        )

    def test_resolution_success_and_failure_do_not_write_group_alert_outcome(self):
        for outcome, status in (
            (LineProviderOutcome(LineProviderOutcomeType.SUCCESS, provider_message_id=LineProviderMessageId("message:m4")), LineDeliveryStatus.SENT),
            (LineProviderOutcome(LineProviderOutcomeType.REJECTED, error_code="line_http_400", error_message="synthetic failure"), LineDeliveryStatus.FAILED),
        ):
            with self.subTest(status=status):
                request = self.request()
                self.assertEqual((request.source_aggregate_type, request.source_aggregate_identity), ("customer_service_ticket", "31"))
                repository = DeliveryRepo(request, status)
                provider = Mock()
                provider.send.return_value = outcome
                connection = SqlConnection()
                try:
                    escalations = MySqlCustomerServiceEscalationRepository(connection)
                    units = []
                    def factory():
                        unit = Uow(delivery_tasks=repository, escalations=escalations)
                        units.append(unit)
                        return unit
                    worker = LineDeliveryWorker(factory, provider, "worker:m4", lambda: NOW, batch_size=1)
                    self.assertEqual(worker.run_once(), 1)
                    self.assertEqual(len(repository.recorded), 1)
                    self.assertTrue(units[-1].committed)
                    self.assertEqual(connection.statements, [])
                finally:
                    connection.db.close()

    def test_actual_group_alert_still_records_its_outcome(self):
        request = replace(self.request(), source_aggregate_type="customer_service_escalation", source_aggregate_identity="escalation:9")
        repository = DeliveryRepo(request, LineDeliveryStatus.SENT)
        escalations = Mock()
        provider = Mock()
        provider.send.return_value = LineProviderOutcome(LineProviderOutcomeType.SUCCESS, provider_message_id=LineProviderMessageId("message:alert"))
        worker = LineDeliveryWorker(lambda: Uow(delivery_tasks=repository, escalations=escalations), provider, "worker:m4", lambda: NOW, batch_size=1)
        self.assertEqual(worker.run_once(), 1)
        escalations.record_alert_delivery_outcome.assert_called_once_with("escalation:9", "line-delivery-attempt:1:1", "sent")

    def test_resolution_key_retains_escalation_lineage_with_ticket_source(self):
        request = self.request()
        self.assertEqual((request.source_aggregate_type, request.source_aggregate_identity), ("customer_service_ticket", "31"))
        self.assertEqual(request.idempotency_key.value, "human-escalation-resolution:9:3")


class AlertNavigationTests(unittest.TestCase):
    def item(self):
        return HumanEscalationOutboxItem(1, "escalation:9", {
            "urgency": "high", "hold_state": "active", "safe_summary": "complaint_explicit", "category": "other",
            "target_snapshot": {"recipient_type": "user", "recipient_identity": "U-admin", "active": True,
                                "configuration": {"minimum_status": "warning"}},
        }, 0, 3, "worker:m4", NOW + timedelta(seconds=60))

    def test_alert_contains_existing_authenticated_management_entry_not_identity_token(self):
        with patch.dict(os.environ, {"LINE_PUBLIC_BASE_URL": "https://example.test", "BASE_URL": ""}):
            request, _ = _request(self.item(), NOW)
        text = json.loads(request.payload_json)["text"]
        self.assertIn("https://example.test/line-mobile-admin?target=customer_service", text)
        self.assertNotIn("C-group-1", text)
        self.assertNotIn("token", text)
        self.assertEqual(request.source_aggregate_identity, "escalation:9")

    def test_unconfigured_management_origin_has_explicit_failure_instead_of_broken_link(self):
        with patch.dict(os.environ, {"LINE_PUBLIC_BASE_URL": "", "BASE_URL": ""}):
            with self.assertRaises(HumanEscalationDeliveryError) as error:
                _request(self.item(), NOW)
        self.assertEqual(error.exception.code, "human_escalation_management_url_unavailable")


if __name__ == "__main__":
    unittest.main()
