"""Automatic reservation borrows the fact writer's transaction and canonical lock writer."""
from datetime import date
from types import SimpleNamespace

import pytest
from subsystems.scheduling import availability_lock_acquisition_workflow as workflow


@pytest.mark.parametrize('scenario', ['ready', 'not_ready', 'unavailable', 'changed_staff'])
def test_auto_reservation_is_scoped_idempotent_and_never_owns_commit(monkeypatch, scenario):
    statements = []

    class Cursor:
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def execute(self, sql, parameters): statements.append((sql, parameters))
        def fetchone(self): return None if scenario == 'not_ready' else {'id': 8, 'confirmed_version': 14}
        def fetchall(self):
            return [{'staff_id': 99, 'start_date': date(2026, 8, 10), 'end_date': None}] if scenario == 'unavailable' else []

    connection = SimpleNamespace(cursor=Cursor)
    snapshot = {'staff_ids': [99], 'lock_rows': [{'staff_id': 99, 'lock_date': '2026-08-10'}]}
    monkeypatch.setattr(workflow, '_load_prelock_snapshot', lambda *_: ({}, []))
    monkeypatch.setattr(workflow, 'normalize_plan_snapshot', lambda *_: snapshot)
    monkeypatch.setattr(workflow, '_with_current_confirmed_service_dates', lambda *args, **kwargs: snapshot)
    writes = []
    def acquire(conn, cursor, request, fingerprint):
        assert conn is connection and fingerprint is None
        writes.append(request)
        return {'lock_id': 17, 'result': 'created'}
    monkeypatch.setattr(workflow, '_acquire_caregiver_availability_lock_in_transaction', acquire)
    locked_staff = (100,) if scenario == 'changed_staff' else (99,)
    if scenario in {'unavailable', 'changed_staff'}:
        code = 'occupancy_conflict' if scenario == 'unavailable' else 'stale_plan'
        with pytest.raises(ValueError, match=code):
            workflow.reserve_confirmed_matching_plan(connection, 'CASE-1', 'admin:1', locked_staff)
    else:
        result = workflow.reserve_confirmed_matching_plan(connection, 'CASE-1', 'admin:1', locked_staff)
        assert result == ({'lock_id': 17, 'result': 'created'} if scenario == 'ready' else None)
    assert len(writes) == int(scenario == 'ready')
    if writes:
        assert writes[0]['event_key'] == 'auto-waiting-deposit:8:14'
        assert writes[0]['case_no'] == 'CASE-1'
    assert all(sql.startswith('SELECT ') for sql, _ in statements)
    assert statements[0][0].endswith(' FOR UPDATE')
