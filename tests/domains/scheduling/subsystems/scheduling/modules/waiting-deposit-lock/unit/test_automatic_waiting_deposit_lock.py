"""Automatic reservation borrows the fact writer's transaction and canonical lock writer."""
import json
from datetime import date, time
from types import SimpleNamespace

import pytest
from subsystems.scheduling import availability_lock_acquisition_workflow as workflow


@pytest.mark.parametrize('scenario', ['ready', 'not_ready', 'unavailable', 'changed_staff', 'occupied'])
def test_auto_reservation_is_scoped_idempotent_and_never_owns_commit(monkeypatch, scenario):
    statements = []
    transaction_calls = []
    mutex_calls = []
    if scenario == 'unavailable':
        day = date(2026, 8, 10)
        plan = {'id': 8, 'case_no': 'CASE-1', 'status': 'proposed', 'is_active': 1,
                'start_date': day, 'end_date': day}
        segments = [{'id': 18, 'plan_id': 8, 'segment_order': 1, 'staff_id': 99,
                     'assigned_start_date': day, 'assigned_end_date': day}]
        order = {'case_no': 'CASE-1', 'status': '訂單成立', 'start_date': day, 'end_date': day}
        confirmed = {'id': 14, 'service_day_count': 1, 'service_days': 1}
        confirmed_days = [{'service_date': day}]
        # Explicit read-port replies only: real normalization, confirmed dates, inner
        # acquisition, occupancy, Preview and refusal remain in the original flow.
        readbacks = iter([
            ('fetchone', 'SELECT plan.id,dates.id AS confirmed_version', ('CASE-1',), True,
             {'id': 8, 'confirmed_version': 14}),
            ('fetchone', 'SELECT id, case_no, status, is_active, start_date, end_date', (8, 'CASE-1'), False, plan),
            ('fetchall', 'SELECT id, plan_id, segment_order, staff_id, assigned_start_date, assigned_end_date', (8,), False, segments),
            ('fetchone', 'SELECT version.id,version.service_day_count,orders.service_days', ('CASE-1',), True, confirmed),
            ('fetchall', 'SELECT day.service_date FROM confirmed_service_date_days', (14,), True, confirmed_days),
            ('fetchone', 'SELECT id, case_no, status, is_active, start_date, end_date', (8, 'CASE-1'), False, plan),
            ('fetchall', 'SELECT id, plan_id, segment_order, staff_id, assigned_start_date, assigned_end_date', (8,), False, segments),
            ('fetchone', 'SELECT case_no, status, start_date, end_date FROM orders', ('CASE-1',), True, order),
            ('fetchone', 'SELECT id, case_no, status, is_active, start_date, end_date', (8, 'CASE-1'), True, plan),
            ('fetchall', 'SELECT id, plan_id, segment_order, staff_id, assigned_start_date, assigned_end_date', (8,), True, segments),
            ('fetchone', 'SELECT version.id,version.service_day_count,orders.service_days', ('CASE-1',), True, confirmed),
            ('fetchall', 'SELECT day.service_date FROM confirmed_service_date_days', (14,), True, confirmed_days),
            ('fetchone', 'SELECT event.id FROM contract_signing_events event', ('CASE-1', 8), True, {'id': 31}),
            ('fetchone', 'SELECT service_start_time,service_end_time,service_end_day_offset', ('CASE-1',), True,
             {'service_start_time': time(9), 'service_end_time': time(17), 'service_end_day_offset': 0}),
            ('fetchall', 'SELECT s.id AS source_id,s.staff_id,s.work_date AS occupancy_date', (99,), True, []),
            ('fetchall', 'SELECT d.id AS source_id,d.staff_id,d.lock_date AS occupancy_date', (99,), True, []),
            ('fetchall', 'SELECT a.id,a.staff_id,a.case_no,a.assigned_start_date,a.assigned_end_date', (99,), True, []),
            ('fetchall', 'SELECT id,staff_id,start_date,end_date FROM scheduling_staff_unavailability_blocks', (99,), True,
             [{'id': 7, 'staff_id': 99, 'start_date': day, 'end_date': None}]),
            ('fetchall', 'SELECT id AS source_id, staff_id, buffer_date AS lock_date', (99, 0, 0, 0), True, []),
            ('fetchall', 'SELECT d.id AS source_id, d.lock_id, d.segment_id, d.staff_id,', (99, 0, 0, 0), True, []),
            ('fetchone', 'SELECT id, lock_id, event_type, event_key, actor, reason, payload',
             ('auto-waiting-deposit:8:14',), True, None),
        ])

    class Cursor:
        def __init__(self): self.pending_fetch = None
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def execute(self, sql, parameters):
            statements.append((sql, parameters))
            if scenario == 'unavailable':
                assert self.pending_fetch is None
                method, prefix, expected_parameters, locked, reply = next(readbacks)
                assert sql.startswith(prefix)
                assert parameters == expected_parameters
                assert sql.endswith(' FOR UPDATE') is locked
                self.pending_fetch, self.reply = method, reply
        def fetchone(self):
            if scenario == 'unavailable':
                assert self.pending_fetch == 'fetchone'
                self.pending_fetch = None
                return self.reply
            return None if scenario == 'not_ready' else {'id': 8, 'confirmed_version': 14}
        def fetchall(self):
            if scenario == 'unavailable':
                assert self.pending_fetch == 'fetchall'
                self.pending_fetch = None
                return self.reply
            return []

    connection = SimpleNamespace(cursor=Cursor,
                                 commit=lambda: transaction_calls.append('commit'),
                                 rollback=lambda: transaction_calls.append('rollback'))
    snapshot = {'staff_ids': [99], 'lock_rows': [{'staff_id': 99, 'lock_date': '2026-08-10'}]}
    if scenario != 'unavailable':
        monkeypatch.setattr(workflow, '_load_prelock_snapshot', lambda *_: ({}, []))
        monkeypatch.setattr(workflow, 'normalize_plan_snapshot', lambda *_: snapshot)
        monkeypatch.setattr(workflow, '_with_current_confirmed_service_dates', lambda *args, **kwargs: snapshot)
    else:
        def locked_mutex(cursor, staff_ids):
            assert isinstance(cursor, Cursor) and staff_ids == [99]
            mutex_calls.append(tuple(staff_ids))
            return staff_ids
        monkeypatch.setattr(workflow, 'lock_staff_occupancy_mutex', locked_mutex)
    writes = []
    def acquire(conn, cursor, request, fingerprint):
        assert conn is connection and fingerprint is None
        if scenario == 'occupied':
            raise ValueError('{"conflicts":[{"staff_id":99,"lock_date":"2026-08-10","source_type":"active_lock","source_id":88}]}')
        writes.append(request)
        return {'lock_id': 17, 'result': 'created'}
    if scenario != 'unavailable':
        monkeypatch.setattr(workflow, '_acquire_caregiver_availability_lock_in_transaction', acquire)
    locked_staff = (100,) if scenario == 'changed_staff' else (99,)
    if scenario in {'unavailable', 'changed_staff', 'occupied'}:
        code = 'stale_plan' if scenario == 'changed_staff' else 'occupancy_conflict'
        with pytest.raises(ValueError, match=code) as refusal:
            workflow.reserve_confirmed_matching_plan(connection, 'CASE-1', 'admin:1', locked_staff)
        if scenario == 'unavailable':
            assert str(refusal.value) == 'automatic_waiting_deposit_occupancy_conflict'
            assert isinstance(refusal.value.__cause__, ValueError)
            conflicts = json.loads(str(refusal.value.__cause__))['conflicts']
            assert conflicts[0] == {'staff_id': 99, 'lock_date': '2026-08-10',
                                    'source_type': 'staff_unavailability', 'source_id': 7}
            assert all(item['source_type'] == 'buffer' for item in conflicts[1:])
            assert mutex_calls == [(99,)]
            assert list(readbacks) == []
    else:
        result = workflow.reserve_confirmed_matching_plan(connection, 'CASE-1', 'admin:1', locked_staff)
        assert result == ({'lock_id': 17, 'result': 'created'} if scenario == 'ready' else None)
    assert len(writes) == int(scenario == 'ready')
    if writes:
        assert writes[0]['event_key'] == 'auto-waiting-deposit:8:14'
        assert writes[0]['case_no'] == 'CASE-1'
        assert writes[0]['plan_id'] == 8
        assert writes[0]['actor'] == 'admin:1'
    assert all(sql.startswith('SELECT ') for sql, _ in statements)
    assert transaction_calls == []
    assert statements[0][0].endswith(' FOR UPDATE')
    assert 'NOT EXISTS (SELECT 1 FROM caregiver_availability_locks' in statements[0][0]
