"""LIFF system status is an authenticated, sanitized and read-only snapshot."""

from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from api.routes import notification_task_actions as routes
from subsystems.line.capabilities import LineCapability
from subsystems.line.runtime_status_query import NotificationQueueCounts, RuntimeStatusQuery
from subsystems.line.runtime_alert_application import RuntimeLineAlertProjector


NOW = datetime(2026, 10, 30, tzinfo=timezone.utc)


@pytest.mark.parametrize('age,worker,failed,expected', [
    (0, 'healthy', 0, 'healthy'), (0, 'critical', 0, 'critical'),
    (91, 'healthy', 0, 'unknown'), (0, 'healthy', 2, 'warning'),
])
def test_snapshot_uses_existing_health_freshness_and_sanitizes_details(monkeypatch, age, worker, failed, expected):
    monkeypatch.setenv('LINE_WORKER_STALE_SECONDS', '90')
    record = SimpleNamespace(check_name='line_worker', status=worker, checked_at=NOW-timedelta(seconds=age),
                             message='internal-error-secret', details={'path':'private-path'})
    @contextmanager
    def unit():
        yield SimpleNamespace(runtime_monitor=SimpleNamespace(
            list_status=lambda: [record], notification_queue_counts=lambda: NotificationQueueCounts(3, failed)))
    view = RuntimeStatusQuery(unit, lambda: NOW).query()
    assert view.status == expected and view.pending_count == 3 and view.failed_count == failed
    assert 'secret' not in str(asdict(view)) and 'private-path' not in str(asdict(view))
    assert view.checks[0].label == 'LINE 訊息發送服務'


def test_missing_monitoring_is_unknown_and_never_opens_a_writer():
    @contextmanager
    def unit():
        yield SimpleNamespace(runtime_monitor=SimpleNamespace(
            list_status=lambda: [], notification_queue_counts=lambda: NotificationQueueCounts(0, 0)))
    view = RuntimeStatusQuery(unit, lambda: NOW).query()
    assert view.status == view.worker_status == 'unknown'
    assert view.last_checked_at is None and view.checks == ()


@pytest.mark.parametrize('allowed', [True, False])
def test_mobile_query_checks_current_line_monitor_permission_before_reading(monkeypatch, allowed):
    calls = []
    def auth(token, capability):
        assert token == 'synthetic-token' and capability == LineCapability.MONITOR_READ
        calls.append('auth')
        if not allowed:
            raise HTTPException(403, 'denied')
    def query():
        calls.append('query')
        return SimpleNamespace(status='unknown', worker_status='unknown', pending_count=0,
                               failed_count=0, last_checked_at=None, checks=())
    monkeypatch.setattr(routes, '_mobile', auth)
    monkeypatch.setattr(routes, 'get_runtime_status_query', lambda: SimpleNamespace(query=query))
    app = FastAPI(); app.include_router(routes.mobile_router)
    with TestClient(app) as client:
        result = client.post('/api/v1/line/mobile-admin/notification-task-actions/runtime/query',
                             json={'line_id_token':'synthetic-token'})
    assert result.status_code == (200 if allowed else 403)
    assert calls == (['auth', 'query'] if allowed else ['auth'])
    assert 'synthetic-token' not in result.text
    if allowed:
        assert set(result.json()['data']) == {'status','worker_status','pending_count','failed_count','last_checked_at','checks'}


def test_runtime_transition_does_not_access_targets_or_delivery_writer():
    assert RuntimeLineAlertProjector(lambda: NOW).project(7, object(), object()) == 0


def test_query_failure_is_closed_and_does_not_expose_database_errors(monkeypatch):
    monkeypatch.setattr(routes, '_mobile', lambda *_: None)
    def fail():
        raise RuntimeError('SELECT private_path AND credential')
    monkeypatch.setattr(routes, 'get_runtime_status_query', lambda: SimpleNamespace(query=fail))
    app = FastAPI(); app.include_router(routes.mobile_router)
    response = TestClient(app).post('/api/v1/line/mobile-admin/notification-task-actions/runtime/query',
                                   json={'line_id_token':'synthetic'})
    assert response.status_code == 503
    assert 'SELECT' not in response.text and 'credential' not in response.text


def test_notification_counts_exclude_retired_alerts_without_selecting_content():
    from infrastructure.mysql.runtime_monitor_repository import MySqlRuntimeMonitorRepository
    calls = []
    class Cursor:
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def execute(self, sql): calls.append(sql)
        def fetchone(self): return {'pending':3, 'failed':2}
    result = MySqlRuntimeMonitorRepository(SimpleNamespace(cursor=Cursor)).notification_queue_counts()
    assert result == NotificationQueueCounts(3, 2) and len(calls) == 1
    assert 'runtime_health_event' in calls[0] and 'complaint.ingress.hold_high_ticket' in calls[0]
    assert 'payload' not in calls[0] and 'recipient_identity' not in calls[0]
