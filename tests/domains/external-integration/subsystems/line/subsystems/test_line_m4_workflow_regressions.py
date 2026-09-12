"""M4 regressions using production modules, SQLite SQL and in-memory UoWs.

No provider, network, application database, or external package is used.
SQLite exercises the ticket UPDATE predicates, not MySQL row-lock semantics.
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

from domains.customer_service.ticket import CustomerServiceCategory, CustomerServiceStatus
from domains.line.delivery import LineDeliveryLease, LineDeliveryStatus, LineDeliveryTaskSnapshot
from domains.line.identities import LineDeliveryTaskId, LineProviderMessageId
from infrastructure.mysql.customer_service_repository import (
    MySqlCustomerServiceRepository, CustomerServiceVersionConflictError,
)
from infrastructure.mysql.customer_service_escalation_repository import MySqlCustomerServiceEscalationRepository
from infrastructure.mysql.line_safe_review_link_repository import MySqlLineSafeReviewLinkRepository
from shared_kernel.identities import ActorContext, CorrelationId, IdempotencyKey
from subsystems.customer_service.contracts import CreateCustomerServiceMessage
from subsystems.customer_service.escalation_application import _admin_resolution_delivery
from subsystems.line.delivery_contracts import LineProviderOutcome, LineProviderOutcomeType
from subsystems.line.delivery_worker import LineDeliveryWorker
from subsystems.line.human_escalation_delivery import (
    HumanEscalationDeliveryError, HumanEscalationOutboxItem, _request,
)
from subsystems.line.runtime_alert_target_application import RuntimeAlertTargetApplication, _target_view
from subsystems.line.runtime_alert_target_contracts import ResetLineAlertGroupCommand, RuntimeAlertTargetError
from subsystems.line.safe_review_link_application import SafeReviewLinkApplication
from subsystems.line.safe_review_link_contracts import IssueSafeReviewLink, RedeemSafeReviewLink, SafeReviewLinkError

NOW = datetime(2026, 9, 12, 12, tzinfo=timezone.utc)


class SqlCursor:
    def __init__(self, database):
        self.cursor = database.cursor()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.cursor.close()
        return False

    def execute(self, sql, parameters=()):
        self.cursor.execute(sql.replace("%s", "?").removesuffix(" FOR UPDATE"), parameters)

    @property
    def rowcount(self):
        return self.cursor.rowcount

    @property
    def lastrowid(self):
        return self.cursor.lastrowid

    def fetchone(self):
        row = self.cursor.fetchone()
        return dict(row) if row is not None else None

    def fetchall(self):
        return [dict(row) for row in self.cursor.fetchall()]


class SqlConnection:
    def __init__(self):
        self.database = sqlite3.connect(":memory:")
        self.database.row_factory = sqlite3.Row
        self.database.create_function("IF", 3, lambda condition, yes, no: yes if condition else no)

    def cursor(self):
        return SqlCursor(self.database)


class TicketTests(unittest.TestCase):
    def setUp(self):
        self.connection = SqlConnection()
        self.addCleanup(self.connection.database.close)
        self.connection.database.executescript("""
            CREATE TABLE clients(id INTEGER PRIMARY KEY, name TEXT, phone TEXT);
            CREATE TABLE customer_service_tickets(
                id INTEGER PRIMARY KEY, line_user_id TEXT, category TEXT, status TEXT,
                version INTEGER, client_id INTEGER, case_no TEXT,
                assigned_to_admin_user_id INTEGER, resolved_at_utc TEXT);
            CREATE TABLE customer_service_ticket_events(
                ticket_id INTEGER, event_key TEXT UNIQUE, event_type TEXT,
                message_text TEXT, actor_id TEXT);
            INSERT INTO customer_service_tickets(id,line_user_id,category,status,version)
                VALUES(22,'U-synthetic','other','resolved',4);
        """)
        self.repository = MySqlCustomerServiceRepository(self.connection)

    def test_reopened_ticket_can_start_escalation_handling(self):
        ticket = self.repository.create_or_append(CreateCustomerServiceMessage(
            'U-synthetic', CustomerServiceCategory.OTHER, 'synthetic follow-up', 'm4:follow-up',
        ))
        self.assertEqual(ticket.ticket_id, 22)
        self.assertIs(ticket.status, CustomerServiceStatus.HANDLING)
        result = self.repository.start_handling_for_escalation(22, ticket.version, 'admin:7')
        self.assertIs(result.status, CustomerServiceStatus.HANDLING)
        self.assertEqual(result.version, ticket.version + 1)
        self.assertEqual(result.assigned_admin_user_id, 7)
        self.assertEqual(self.connection.database.execute(
            'SELECT COUNT(*) FROM customer_service_tickets').fetchone()[0], 1)
        self.assertEqual(self.connection.database.execute(
            'SELECT COUNT(*) FROM customer_service_ticket_events').fetchone()[0], 2)

    def test_waiting_ticket_still_starts_handling(self):
        self.connection.database.execute("UPDATE customer_service_tickets SET status='waiting'")
        result = self.repository.start_handling_for_escalation(22, 4, 'admin:7')
        self.assertIs(result.status, CustomerServiceStatus.HANDLING)
        self.assertEqual(result.version, 5)

    def test_resolved_ticket_is_not_silently_reopened_by_handling(self):
        with self.assertRaises(CustomerServiceVersionConflictError):
            self.repository.start_handling_for_escalation(22, 4, 'admin:7')
        self.assertEqual(self.repository.get(22).version, 4)
        self.assertEqual(self.connection.database.execute(
            'SELECT COUNT(*) FROM customer_service_ticket_events').fetchone()[0], 0)

    def test_stale_handling_version_has_no_event_or_update(self):
        self.connection.database.execute("UPDATE customer_service_tickets SET status='handling',version=5")
        with self.assertRaises(CustomerServiceVersionConflictError):
            self.repository.start_handling_for_escalation(22, 4, 'admin:7')
        self.assertEqual(self.repository.get(22).version, 5)
        self.assertEqual(self.connection.database.execute(
            'SELECT COUNT(*) FROM customer_service_ticket_events').fetchone()[0], 0)


class AlertSelectionTests(unittest.TestCase):
    def setUp(self):
        self.connection = SqlConnection()
        self.addCleanup(self.connection.database.close)
        self.connection.database.executescript("""
            CREATE TABLE admin_users(id INTEGER PRIMARY KEY, linked_line_user_id TEXT);
            CREATE TABLE line_alert_notification_targets(
                id INTEGER PRIMARY KEY,target_type TEXT,group_id TEXT,admin_user_id INTEGER,
                minimum_status TEXT,updated_at_utc TEXT,enabled BOOLEAN);
            INSERT INTO admin_users VALUES(7,'U-synthetic-admin');
        """)
        self.repository = MySqlCustomerServiceEscalationRepository(self.connection)

    def add_target(self, target_id, kind, enabled=True):
        self.connection.database.execute(
            'INSERT INTO line_alert_notification_targets VALUES(?,?,?,?,?,?,?)',
            (target_id, kind, f'C-synthetic-{target_id}' if kind == 'group' else None,
             7 if kind == 'admin_user' else None, 'warning', NOW.isoformat(), enabled),
        )

    def test_group_is_selected_even_with_enabled_admin_target(self):
        self.add_target(1, 'admin_user')
        self.add_target(2, 'group')
        target = self.repository._active_alert_target_snapshot()
        self.assertEqual(target['target_id'], 2)
        self.assertEqual(target['recipient_type'], 'group')
        self.assertEqual(target['recipient_identity'], 'C-synthetic-2')

    def test_multiple_groups_remain_ambiguous(self):
        self.add_target(1, 'group')
        self.add_target(2, 'group')
        self.add_target(3, 'admin_user')
        self.assertIsNone(self.repository._active_alert_target_snapshot())

    def test_single_admin_without_group_preserves_existing_behavior(self):
        self.add_target(1, 'group', False)
        self.add_target(2, 'admin_user')
        target = self.repository._active_alert_target_snapshot()
        self.assertEqual(target['target_id'], 2)
        self.assertEqual(target['recipient_type'], 'user')

    def test_multiple_admins_without_group_are_not_arbitrarily_selected(self):
        self.add_target(1, 'admin_user')
        self.add_target(2, 'admin_user')
        self.assertIsNone(self.repository._active_alert_target_snapshot())

    def test_no_enabled_target_remains_unavailable(self):
        self.add_target(1, 'group', False)
        self.assertIsNone(self.repository._active_alert_target_snapshot())


class RuntimeRepo:
    def __init__(self, *, enabled=False):
        self.rows = {1: {'id': 1, 'target_type': 'group', 'group_id': 'C-synthetic',
                        'enabled': enabled, 'minimum_status': 'warning', 'updated_at_utc': NOW}}
        self.receipts = {}
        self.audits = []
        self.updates = []
        self.log = []
        self.locked = False
        self.lock_available = True
        self.fail_audit = False

    def acquire_alert_target_lock(self, timeout):
        self.log.append('acquire')
        self.locked = self.lock_available
        return self.lock_available

    def release_alert_target_lock(self):
        self.log.append('release')
        self.locked = False
        return True

    def find_active_group_targets(self, *, for_update):
        self.log.append(('read-active', for_update))
        return tuple(dict(row) for row in self.rows.values()
                     if row['target_type'] == 'group' and row['enabled'])

    def find_group_target(self, group_id, *, for_update):
        return next((dict(row) for row in self.rows.values() if row.get('group_id') == group_id), None)

    def get_alert_target(self, target_id, *, for_update):
        return dict(self.rows[target_id])

    def insert_group_target(self, group_id, display_name, actor_id):
        raise AssertionError('same-group registration must reuse its existing row')

    def update_alert_target_enabled(self, target_id, enabled):
        if not self.locked:
            raise AssertionError('mutation lost the existing serialization lock')
        self.updates.append((target_id, enabled))
        self.rows[target_id]['enabled'] = enabled
        self.rows[target_id]['updated_at_utc'] += timedelta(seconds=1)

    def load_admin_command_receipt(self, family, key, *, for_update):
        return self.receipts.get((family, key))

    def save_admin_command_receipt(self, family, key, fingerprint, actor, reason, result):
        self.receipts[(family, key)] = {'request_fingerprint': fingerprint, 'result_snapshot': copy.deepcopy(result)}

    def save_alert_target_admin_audit(self, actor_id, action, target_id, details):
        if self.fail_audit:
            raise RuntimeError('synthetic audit failure')
        self.audits.append((actor_id, action, target_id, copy.deepcopy(details)))


class RuntimeUow:
    def __init__(self, repo):
        self.runtime_monitor = repo
        self.hooks = []
        self.committed = False

    def __enter__(self):
        repo = self.runtime_monitor
        self.before = copy.deepcopy((repo.rows, repo.receipts, repo.audits, repo.updates))
        return self

    def commit(self):
        self.runtime_monitor.log.append('commit')
        self.committed = True

    def add_after_completion(self, callback):
        self.hooks.append(callback)

    def __exit__(self, kind, *_):
        if kind is not None or not self.committed:
            repo = self.runtime_monitor
            repo.rows, repo.receipts, repo.audits, repo.updates = self.before
            repo.log.append('rollback')
        for callback in self.hooks:
            callback()
        return False


class GroupRebindTests(unittest.TestCase):
    def setUp(self):
        self.repo = RuntimeRepo()
        self.app = RuntimeAlertTargetApplication(lambda: RuntimeUow(self.repo), lambda: NOW)

    def register(self, event='m4:event:1', group='C-synthetic'):
        with RuntimeUow(self.repo) as uow:
            result = self.app.register_group(uow, group, 'admin:7', event)
            self.assertTrue(self.repo.locked or not uow.hooks)
            uow.commit()
        return result

    def test_disabled_same_group_reuses_id_and_records_before_after(self):
        before = _target_view(self.repo.rows[1]).current_version
        self.assertTrue(self.register())
        self.assertEqual(list(self.repo.rows), [1])
        self.assertTrue(self.repo.rows[1]['enabled'])
        self.assertEqual(self.repo.updates, [(1, True)])
        details = self.repo.audits[0][3]
        self.assertEqual(details['previous_state'], 'disabled')
        self.assertEqual(details['expected_version'], before)
        self.assertNotEqual(details['resulting_version'], before)
        self.assertEqual(self.repo.log[-2:], ['commit', 'release'])
        result = next(iter(self.repo.receipts.values()))['result_snapshot']
        self.assertFalse(result['created'])
        self.assertTrue(result['reactivated'])

    def test_active_same_group_is_a_noop(self):
        self.repo.rows[1]['enabled'] = True
        self.assertFalse(self.register())
        self.assertEqual(self.repo.updates, [])
        self.assertEqual(self.repo.audits[0][3]['previous_state'], 'active')

    def test_old_registration_replay_does_not_undo_later_reset(self):
        self.register()
        current = _target_view(self.repo.rows[1]).current_version
        self.app.reset(ResetLineAlertGroupCommand(
            current, 'synthetic reset', IdempotencyKey('m4:reset'),
            CorrelationId('m4:reset'), ActorContext('admin:7'),
        ))
        before = len(self.repo.updates)
        self.register()
        self.assertFalse(self.repo.rows[1]['enabled'])
        self.assertEqual(len(self.repo.updates), before)
        self.assertTrue(self.register(event='m4:event:2'))
        self.assertTrue(self.repo.rows[1]['enabled'])

    def test_other_active_group_cannot_be_replaced_by_rebind(self):
        self.repo.rows[2] = {**self.repo.rows[1], 'id': 2, 'group_id': 'C-other', 'enabled': True}
        with self.assertRaises(RuntimeAlertTargetError) as caught:
            self.register()
        self.assertEqual(caught.exception.code, 'line_alert_group_already_active')
        self.assertFalse(self.repo.rows[1]['enabled'])
        self.assertTrue(self.repo.rows[2]['enabled'])
        self.assertEqual(self.repo.updates, [])
        self.assertEqual(self.repo.receipts, {})

    def test_same_event_different_group_is_not_repurposed(self):
        self.register()
        with self.assertRaises(RuntimeAlertTargetError) as caught:
            self.register(group='C-other')
        self.assertEqual(caught.exception.code, 'line_alert_target_idempotency_mismatch')
        self.assertEqual(self.repo.updates, [(1, True)])

    def test_audit_failure_rolls_back_reactivation_and_receipt(self):
        self.repo.fail_audit = True
        with self.assertRaisesRegex(RuntimeError, 'synthetic audit'):
            self.register()
        self.assertFalse(self.repo.rows[1]['enabled'])
        self.assertEqual(self.repo.receipts, {})
        self.assertEqual(self.repo.log[-2:], ['rollback', 'release'])

    def test_lock_failure_is_zero_write(self):
        self.repo.lock_available = False
        with self.assertRaises(RuntimeAlertTargetError) as caught:
            self.register()
        self.assertEqual(caught.exception.code, 'line_alert_target_serialization_unavailable')
        self.assertEqual(self.repo.updates, [])
        self.assertEqual(self.repo.receipts, {})


class PlainUow:
    def __init__(self, **repositories):
        self.__dict__.update(repositories)
        self.commits = 0

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def commit(self):
        self.commits += 1


class DeliveryRepo:
    def __init__(self, request, terminal):
        task_id = LineDeliveryTaskId(1)
        self.task = LineDeliveryTaskSnapshot(task_id, request, LineDeliveryStatus.PROCESSING, 0,
            LineDeliveryLease(task_id, 'worker:m4', NOW, NOW + timedelta(seconds=60)))
        self.claimed = False
        self.recorded = []
        self.terminal = terminal

    def claim(self, query):
        if self.claimed:
            return ()
        self.claimed = True
        return (self.task,)

    def get(self, task_id):
        return self.task

    def record_attempt(self, command):
        self.recorded.append(command)
        return SimpleNamespace(plan=SimpleNamespace(resulting_status=self.terminal))


def resolution_request():
    ticket = SimpleNamespace(ticket_id=22, line_user_id='U-synthetic')
    command = SimpleNamespace(expected_escalation_version=2, correlation_id=CorrelationId('m4:resolution'))
    return _admin_resolution_delivery(ticket, command, 41, NOW)


class ResolutionDeliveryTests(unittest.TestCase):
    def test_resolution_uses_ticket_source_and_keeps_escalation_lineage_in_key(self):
        request = resolution_request()
        self.assertEqual(request.source_aggregate_type, 'customer_service_ticket')
        self.assertEqual(request.source_aggregate_identity, '22')
        self.assertEqual(request.idempotency_key.value, 'human-escalation-resolution:41:3')

    def test_resolution_terminals_commit_without_overwriting_group_alert(self):
        for terminal, outcome in (
            (LineDeliveryStatus.SENT, LineProviderOutcome(LineProviderOutcomeType.SUCCESS,
                provider_message_id=LineProviderMessageId('synthetic-message'))),
            (LineDeliveryStatus.FAILED, LineProviderOutcome(LineProviderOutcomeType.REJECTED,
                error_code='synthetic_rejection', error_message='synthetic failure')),
        ):
            with self.subTest(status=terminal):
                repository = DeliveryRepo(resolution_request(), terminal)
                escalations = Mock()
                escalations.record_alert_delivery_outcome.side_effect = AssertionError('customer notice cannot rewrite group alert')
                uow = PlainUow(delivery_tasks=repository, escalations=escalations)
                provider = Mock()
                provider.send.return_value = outcome
                worker = LineDeliveryWorker(lambda: uow, provider, 'worker:m4', lambda: NOW, batch_size=1)
                self.assertEqual(worker.run_once(), 1)
                self.assertEqual(len(repository.recorded), 1)
                self.assertEqual(uow.commits, 2)
                escalations.record_alert_delivery_outcome.assert_not_called()

    def test_group_alert_still_records_its_own_outcome(self):
        request = replace(resolution_request(), source_aggregate_type='customer_service_escalation',
                          source_aggregate_identity='escalation:41')
        repository = DeliveryRepo(request, LineDeliveryStatus.SENT)
        escalations = Mock()
        provider = Mock()
        provider.send.return_value = LineProviderOutcome(LineProviderOutcomeType.SUCCESS,
            provider_message_id=LineProviderMessageId('synthetic-message'))
        uow = PlainUow(delivery_tasks=repository, escalations=escalations)
        worker = LineDeliveryWorker(lambda: uow, provider, 'worker:m4', lambda: NOW, batch_size=1)
        self.assertEqual(worker.run_once(), 1)
        escalations.record_alert_delivery_outcome.assert_called_once_with(
            'escalation:41', 'line-delivery-attempt:1:1', 'sent')


def alert_item():
    return HumanEscalationOutboxItem(1, 'escalation:41', {
        'urgency': 'high', 'hold_state': 'active', 'safe_summary': 'complaint_explicit', 'category': 'other',
        'target_snapshot': {'active': True, 'configuration': {}, 'recipient_type': 'group',
                            'recipient_identity': 'C-synthetic'},
    }, 0, 3, 'worker:m4', NOW + timedelta(seconds=60))


class AlertEntryTests(unittest.TestCase):
    def test_alert_contains_existing_mobile_entry_without_credentials(self):
        with patch.dict(os.environ, {'LINE_PUBLIC_BASE_URL': 'https://example.test', 'BASE_URL': ''}):
            request, _ = _request(alert_item(), NOW)
        text = json.loads(request.payload_json)['text']
        self.assertIn('https://example.test/line-mobile-admin?target=customer_service', text)
        self.assertNotIn('C-synthetic', text)
        self.assertNotIn('token', text.lower())

    def test_missing_public_origin_is_explicit_not_an_incomplete_success(self):
        with patch.dict(os.environ, {'LINE_PUBLIC_BASE_URL': '', 'BASE_URL': ''}):
            with self.assertRaises(HumanEscalationDeliveryError) as caught:
                _request(alert_item(), NOW)
        self.assertEqual(caught.exception.code, 'human_escalation_review_entry_unconfigured')


class SafeLinkRepo:
    def __init__(self):
        self.links = {}
        self.receipts = {}
        self.events = []
        self.outbox = []

    def get_link(self, link_id, *, for_update=False):
        row = self.links.get(link_id)
        return dict(row) if row else None

    def insert_link(self, **values):
        values['expires_at_utc'] = values.pop('expires_at')
        values['issued_at_utc'] = values.pop('issued_at')
        self.links[values['link_id']] = {'id': 1, **values, 'status': 'issued', 'root_version': 0}
        return 1

    def transition(self, pk, status, at):
        row = self.links['m4:link']
        row['status'] = status
        row['root_version'] += 1
        row['redeemed_at_utc'] = at if status == 'redeemed' else None

    def insert_event(self, pk, *args):
        self.events.append((pk, copy.deepcopy(args)))

    def issued_runtime_target(self, pk):
        return next((args[-1].get('runtime_target') for identity, args in self.events
                     if identity == pk and args[0] == 'issued'), None)

    def insert_outbox(self, *args):
        self.outbox.append(args)

    def insert_receipt(self, key, fingerprint, outcome, result, pk):
        self.receipts[key] = {'idempotency_key': key, 'command_fingerprint': fingerprint,
                              'outcome': outcome, 'result_snapshot': result}

    def load_receipt(self, key, *, for_update=False):
        return self.receipts.get(key)


class SafeLinkFreshnessTests(unittest.TestCase):
    def setUp(self):
        self.repo = SafeLinkRepo()
        self.runtime = RuntimeRepo(enabled=True)
        self.uow = PlainUow(safe_review_links=self.repo, runtime_monitor=self.runtime)
        self.app = SafeReviewLinkApplication(lambda: self.uow, lambda: NOW)
        self.actor = ActorContext('admin:7', ('line.alert.manage',))
        self.issue = IssueSafeReviewLink('m4:link', 'synthetic-token-for-tests', '/api/v1/runtime/health-status',
            3, 'alert:41', 'admin:7', 'line.alert.manage', 60, self.actor,
            IdempotencyKey('m4:issue'), CorrelationId('m4:issue'))
        self.redeem = RedeemSafeReviewLink('m4:link', 'synthetic-token-for-tests', self.actor, 'line.alert.manage',
            '/api/v1/runtime/health-status', 3, IdempotencyKey('m4:redeem'), CorrelationId('m4:redeem'))

    def test_issue_persists_actual_runtime_version_and_redeem_locks_current_target(self):
        self.app.issue(self.issue)
        snapshot = self.repo.issued_runtime_target(1)
        self.assertEqual(snapshot, {'target_id': 1, 'current_version': _target_view(self.runtime.rows[1]).current_version})
        receipt = self.app.redeem(self.redeem)
        self.assertEqual(receipt.outcome.value, 'redeemed')
        self.assertEqual(self.runtime.log.count(('read-active', True)), 2)
        with self.assertRaises(SafeReviewLinkError) as caught:
            self.app.redeem(replace(self.redeem, idempotency_key=IdempotencyKey('m4:redeem:again')))
        self.assertEqual(caught.exception.code, 'safe_review_link_replayed')

    def test_unchanged_browser_version_cannot_hide_runtime_revision_change(self):
        self.app.issue(self.issue)
        self.runtime.rows[1]['minimum_status'] = 'critical'
        with self.assertRaises(SafeReviewLinkError) as caught:
            self.app.redeem(self.redeem)
        self.assertEqual(caught.exception.code, 'safe_review_link_version_conflict')
        self.assertEqual(self.repo.links['m4:link']['status'], 'issued')
        self.assertEqual(len(self.repo.events), 1)
        self.assertNotIn('m4:redeem', self.repo.receipts)

    def test_disabled_runtime_group_rejects_old_link(self):
        self.app.issue(self.issue)
        self.runtime.rows[1]['enabled'] = False
        with self.assertRaises(SafeReviewLinkError) as caught:
            self.app.redeem(self.redeem)
        self.assertEqual(caught.exception.code, 'safe_review_link_target_stale')
        self.assertEqual(self.repo.links['m4:link']['status'], 'issued')

    def test_same_group_reactivation_does_not_revive_old_link(self):
        self.app.issue(self.issue)
        self.runtime.rows[1]['updated_at_utc'] += timedelta(seconds=1)
        with self.assertRaises(SafeReviewLinkError) as caught:
            self.app.redeem(self.redeem)
        self.assertEqual(caught.exception.code, 'safe_review_link_version_conflict')

    def test_replacement_group_rejects_old_link(self):
        self.app.issue(self.issue)
        self.runtime.rows[1]['id'] = 2
        with self.assertRaises(SafeReviewLinkError) as caught:
            self.app.redeem(self.redeem)
        self.assertEqual(caught.exception.code, 'safe_review_link_target_stale')

    def test_legacy_link_without_issuance_snapshot_fails_closed(self):
        self.app.issue(self.issue)
        self.repo.events[0][1][-1].pop('runtime_target')
        with self.assertRaises(SafeReviewLinkError) as caught:
            self.app.redeem(self.redeem)
        self.assertEqual(caught.exception.code, 'safe_review_link_target_stale')

    def test_issue_without_active_target_is_zero_write(self):
        self.runtime.rows[1]['enabled'] = False
        with self.assertRaises(SafeReviewLinkError):
            self.app.issue(self.issue)
        self.assertEqual(self.repo.links, {})
        self.assertEqual(self.repo.receipts, {})
        self.assertEqual(self.repo.outbox, [])

    def test_issue_replay_preserves_original_snapshot_without_new_intent(self):
        self.app.issue(self.issue)
        original = copy.deepcopy(self.repo.issued_runtime_target(1))
        self.runtime.rows[1]['updated_at_utc'] += timedelta(seconds=1)
        receipt, token = self.app.issue(self.issue)
        self.assertTrue(receipt.replayed)
        self.assertEqual(token, '')
        self.assertEqual(len(self.repo.outbox), 1)
        self.assertEqual(self.repo.issued_runtime_target(1), original)

    def test_repository_reads_issuance_snapshot_without_changing_it(self):
        connection = SqlConnection()
        self.addCleanup(connection.database.close)
        connection.database.execute('CREATE TABLE line_safe_review_link_events(link_id INTEGER,event_type TEXT,event_payload TEXT)')
        payload = {'runtime_target': {'target_id': 7, 'current_version': 'a' * 64}}
        connection.database.execute('INSERT INTO line_safe_review_link_events VALUES(?,?,?)', (1, 'issued', json.dumps(payload)))
        result = MySqlLineSafeReviewLinkRepository(connection).issued_runtime_target(1)
        self.assertEqual(result, payload['runtime_target'])


if __name__ == '__main__':
    unittest.main()
