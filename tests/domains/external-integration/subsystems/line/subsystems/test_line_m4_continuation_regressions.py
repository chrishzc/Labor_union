"""M4 regressions: real applications and SQL with local, non-network persistence seams.

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

    def test_group_and_admin_coexist_without_losing_group_target(self):
        self.add(1, "admin_user")
        self.add(9, "group")
        target = self.repo._active_alert_target_snapshot()
        self.assertEqual((target["target_id"], target["recipient_type"]), (9, "group"))

    def test_only_one_group_is_selected(self):
        self.add(9, "group")
        self.assertEqual(self.repo._active_alert_target_snapshot()["target_id"], 9)

    def test_single_admin_without_group_keeps_existing_behavior(self):
        self.add(1, "admin_user")
        self.assertEqual(self.repo._active_alert_target_snapshot()["recipient_type"], "user")

    def test_multiple_admins_without_group_remain_ambiguous(self):
        self.add(1, "admin_user")
        self.add(2, "admin_user")
        self.assertIsNone(self.repo._active_alert_target_snapshot())

    def test_multiple_groups_fail_closed_even_with_an_admin(self):
        self.add(1, "admin_user")
        self.add(2, "group")
        self.add(9, "group")
        self.assertIsNone(self.repo._active_alert_target_snapshot())

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
        return self

    def __exit__(self, *_):
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
        with Uow(runtime_monitor=self.repo) as uow:
            result = self.app.register_group(uow, group_id, ACTOR.actor_id, event)
            self.assertFalse(uow.committed)
            uow.commit()
            return result

    def reset(self):
        version = _target_view(self.repo.rows[1]).current_version
        return self.app.reset(ResetLineAlertGroupCommand(
            version, "synthetic reset", IdempotencyKey("reset:1"), CorrelationId("corr:reset"), ACTOR
        ))

    def test_reset_then_new_command_reactivates_same_row_and_preserves_configuration(self):
        self.assertTrue(self.register())
        self.reset()
        before = _target_view(self.repo.rows[1]).current_version
        self.assertTrue(self.register("event:2"))
        self.assertEqual(self.repo.inserts, 1)
        self.assertEqual(len(self.repo.rows), 1)
        self.assertTrue(self.repo.rows[1]["enabled"])
        self.assertEqual(self.repo.rows[1]["minimum_status"], "critical")
        audit = self.repo.audits[-1][3]
        self.assertEqual((audit["previous_state"], audit["resulting_state"]), ("disabled", "active"))
        self.assertEqual(audit["expected_version"], before)
        self.assertNotEqual(audit["resulting_version"], before)
        self.assertFalse(self.repo.locked)

    def test_old_event_replay_after_reset_does_not_reactivate(self):
        self.register()
        self.reset()
        before = (self.repo.updates, len(self.repo.audits), len(self.repo.receipts))
        self.assertTrue(self.register())
        self.assertFalse(self.repo.rows[1]["enabled"])
        self.assertEqual(before, (self.repo.updates, len(self.repo.audits), len(self.repo.receipts)))

    def test_already_active_same_group_is_noop_with_current_state_audit(self):
        self.register()
        self.assertFalse(self.register("event:2"))
        self.assertEqual(self.repo.updates, 0)
        self.assertEqual(self.repo.audits[-1][3]["previous_state"], "active")

    def test_other_active_group_is_not_replaced(self):
        self.repo.rows = {1: group(1, False), 2: group(2)}
        with self.assertRaises(RuntimeAlertTargetError) as error:
            self.register()
        self.assertEqual(error.exception.code, "line_alert_group_already_active")
        self.assertFalse(self.repo.rows[1]["enabled"])
        self.assertTrue(self.repo.rows[2]["enabled"])
        self.assertEqual(self.repo.updates, 0)
        self.assertEqual(self.repo.receipts, {})

    def test_multiple_active_groups_fail_before_any_mutation(self):
        self.repo.rows = {1: group(1), 2: group(2)}
        with self.assertRaises(RuntimeAlertTargetError) as error:
            self.register()
        self.assertEqual(error.exception.code, "line_alert_group_singleton_violation")
        self.assertEqual(self.repo.audits, [])

    def test_lock_failure_is_zero_write(self):
        self.repo.rows = {1: group(1, False)}
        self.repo.lock_ok = False
        with self.assertRaises(RuntimeAlertTargetError) as error:
            self.register()
        self.assertEqual(error.exception.code, "line_alert_target_serialization_unavailable")
        self.assertEqual((self.repo.updates, self.repo.inserts), (0, 0))
        self.assertEqual(self.repo.receipts, {})


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

    def test_issue_records_exact_owner_version_without_raw_token(self):
        self.app.issue(self.issue)
        target = self.links.get_issued_runtime_target(1)
        self.assertEqual(target, {"target_id": 1, "current_version": _target_view(self.runtime.rows[1]).current_version})
        self.assertNotIn(self.issue.raw_token, repr(self.links.events))
        self.assertTrue(all(self.runtime.read_locks))

    def test_unchanged_target_redeems_and_exact_replay_does_not_write_again(self):
        self.app.issue(self.issue)
        self.assertEqual(self.app.redeem(self.redeem).outcome.value, "redeemed")
        count = len(self.links.events)
        self.assertTrue(self.app.redeem(self.redeem).replayed)
        self.assertEqual(len(self.links.events), count)

    def test_old_caller_version_cannot_hide_actual_runtime_version_change(self):
        self.app.issue(self.issue)
        self.runtime.rows[1]["updated_at_utc"] += timedelta(seconds=1)
        with self.assertRaises(SafeReviewLinkError) as error:
            self.app.redeem(self.redeem)
        self.assertEqual(error.exception.code, "safe_review_link_version_conflict")
        self.assertEqual(self.links.links[self.issue.link_id]["status"], "issued")
        self.assertEqual(len(self.links.events), 1)
        self.assertNotIn(self.redeem.idempotency_key.value, self.links.receipts)
        self.assertFalse(self.units[-1].committed)

    def test_disable_then_reactivate_same_group_does_not_revive_old_link(self):
        self.app.issue(self.issue)
        self.runtime.update_alert_target_enabled(1, False)
        self.runtime.update_alert_target_enabled(1, True)
        with self.assertRaises(SafeReviewLinkError) as error:
            self.app.redeem(self.redeem)
        self.assertEqual(error.exception.code, "safe_review_link_version_conflict")

    def test_changed_group_identity_is_stale(self):
        self.app.issue(self.issue)
        self.runtime.rows = {2: group(2)}
        with self.assertRaises(SafeReviewLinkError) as error:
            self.app.redeem(self.redeem)
        self.assertEqual(error.exception.code, "safe_review_link_target_stale")

    def test_no_active_group_cannot_issue_or_redeem(self):
        self.runtime.rows[1]["enabled"] = False
        with self.assertRaises(SafeReviewLinkError):
            self.app.issue(self.issue)
        self.assertEqual((self.links.links, self.links.events, self.links.outbox), ({}, [], []))
        self.runtime.rows[1]["enabled"] = True
        self.app.issue(self.issue)
        self.runtime.rows[1]["enabled"] = False
        with self.assertRaises(SafeReviewLinkError):
            self.app.redeem(self.redeem)
        self.assertEqual(self.links.links[self.issue.link_id]["status"], "issued")

    def test_old_link_without_owner_evidence_fails_closed(self):
        self.app.issue(self.issue)
        self.links.events[0][2].pop("runtime_alert_target")
        with self.assertRaises(SafeReviewLinkError) as error:
            self.app.redeem(self.redeem)
        self.assertEqual(error.exception.code, "safe_review_link_target_stale")

    def test_expiry_and_actor_checks_are_preserved(self):
        self.app.issue(self.issue)
        with self.assertRaises(SafeReviewLinkError) as error:
            self.app.redeem(replace(self.redeem, actor=ActorContext("admin:8", ("line.alert.manage",))))
        self.assertEqual(error.exception.code, "safe_review_link_wrong_actor")
        self.clock += timedelta(seconds=61)
        with self.assertRaises(SafeReviewLinkError) as error:
            self.app.redeem(self.redeem)
        self.assertEqual(error.exception.code, "safe_review_link_expired")
        self.assertEqual(self.links.links[self.issue.link_id]["status"], "expired")


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


class AlertNavigationTests(unittest.TestCase):
    def item(self):
        return HumanEscalationOutboxItem(1, "escalation:9", {
            "urgency": "high", "hold_state": "active", "safe_summary": "complaint_explicit", "category": "other",
            "target_snapshot": {"recipient_type": "group", "recipient_identity": "C-group-1", "active": True,
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
