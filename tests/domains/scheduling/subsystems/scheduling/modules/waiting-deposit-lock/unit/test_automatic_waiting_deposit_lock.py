"""Automatic reservation borrows the fact writer's transaction and canonical lock writer."""
import json
from datetime import date, time
from types import SimpleNamespace

import pytest
from subsystems.scheduling import availability_lock_acquisition_workflow as workflow


@pytest.mark.parametrize(
    'scenario', ['ready', 'not_ready', 'unavailable', 'available_outside_block', 'changed_staff', 'occupied']
)
def test_auto_reservation_is_scoped_idempotent_and_never_owns_commit(scenario):
    statements = []
    writes = []
    service_day = date(2026, 8, 10)
    plan = {
        'id': 8, 'case_no': 'CASE-1', 'status': 'proposed', 'is_active': 1,
        'start_date': service_day, 'end_date': service_day,
    }
    segments = [{
        'id': 4, 'plan_id': 8, 'segment_order': 1, 'staff_id': 99,
        'assigned_start_date': service_day, 'assigned_end_date': service_day,
    }]
    service_time = {
        'service_start_time': time(9), 'service_end_time': time(17), 'service_end_day_offset': 0,
    }
    block_start = {'unavailable': service_day, 'available_outside_block': date(2026, 8, 20)}.get(scenario)

    class Cursor:
        lastrowid = 17
        rowcount = 1

        def __enter__(self): return self
        def __exit__(self, *_): pass

        def execute(self, sql, parameters):
            statements.append((sql, parameters))
            self.rows = []
            if sql.startswith('SELECT plan.id,dates.id'):
                assert 'NOT EXISTS (SELECT 1 FROM caregiver_availability_locks' in sql
                assert sql.endswith(' FOR UPDATE')
                has_lock = any(statement.startswith('INSERT INTO caregiver_availability_locks ') for statement, _ in writes)
                if scenario != 'not_ready' and not has_lock:
                    self.rows = [{'id': 8, 'confirmed_version': 14}]
            elif sql.startswith('SELECT id, case_no, status, is_active'):
                self.rows = [plan]
            elif sql.startswith('SELECT id, plan_id, segment_order'):
                self.rows = segments
            elif sql.startswith('SELECT id FROM staff'):
                self.rows = [{'id': 99}]
            elif sql.startswith('SELECT case_no, status, start_date'):
                self.rows = [{'case_no': 'CASE-1', 'status': '訂單成立',
                              'start_date': service_day, 'end_date': service_day}]
            elif sql.startswith('SELECT version.id,version.service_day_count'):
                self.rows = [{'id': 14, 'service_day_count': 1, 'service_days': 1}]
            elif sql.startswith('SELECT day.service_date'):
                self.rows = [{'service_date': service_day}]
            elif sql.startswith('SELECT response_value'):
                self.rows = [{'response_value': 'accepted'}]
            elif sql.startswith('SELECT service_start_time,service_end_time'):
                self.rows = [service_time]
            elif 'FROM scheduling_staff_unavailability_blocks' in sql:
                assert parameters == (99,)
                assert sql.endswith(' FOR UPDATE')
                if block_start is not None:
                    self.rows = [{'id': 25, 'staff_id': 99, 'start_date': block_start, 'end_date': None}]
            elif 'AS occupancy_date,p.case_no,l.id AS lock_id' in sql:
                if scenario == 'occupied':
                    self.rows = [{'source_id': 88, 'staff_id': 99, 'occupancy_date': service_day,
                                  'case_no': 'OTHER', 'lock_id': 10, **service_time}]
            elif sql.startswith(('INSERT ', 'UPDATE ')):
                writes.append((sql, parameters))
            else:
                assert sql.startswith('SELECT '), sql

        def fetchone(self):
            return next(iter(self.rows), None)

        def fetchall(self):
            return self.rows

    # The caller owns commit and rollback. Either call on this connection would fail.
    connection = SimpleNamespace(cursor=Cursor)
    locked_staff = (100,) if scenario == 'changed_staff' else (99,)
    if scenario in {'unavailable', 'changed_staff', 'occupied'}:
        code = 'stale_plan' if scenario == 'changed_staff' else 'occupancy_conflict'
        with pytest.raises(ValueError, match=f'^automatic_waiting_deposit_{code}$') as error:
            workflow.reserve_confirmed_matching_plan(connection, 'CASE-1', 'admin:1', locked_staff)
        if scenario != 'changed_staff':
            source_type, source_id = ('staff_unavailability', 25) if scenario == 'unavailable' else ('active_lock', 88)
            assert json.loads(str(error.value.__cause__)) == {'conflicts': [{
                'staff_id': 99, 'lock_date': service_day.isoformat(), 'source_type': source_type, 'source_id': source_id,
            }]}
        assert writes == []
    else:
        result = workflow.reserve_confirmed_matching_plan(connection, 'CASE-1', 'admin:1', locked_staff)
        if scenario == 'not_ready':
            assert result is None
            assert writes == []
        else:
            assert result == {
                'lock_id': 17, 'result': 'created', 'case_no': 'CASE-1', 'plan_id': 8,
                'lock_rows': [{'segment_id': 4, 'staff_id': 99, 'lock_date': service_day.isoformat()}],
            }
            assert len(writes) == 4
            event_sql, event_params = writes[-1]
            assert event_sql.startswith('INSERT INTO caregiver_availability_lock_events ')
            assert event_params[:3] == (17, 'auto-waiting-deposit:8:14', 'admin:1')
            assert workflow.reserve_confirmed_matching_plan(connection, 'CASE-1', 'admin:1', locked_staff) is None
            assert len(writes) == 4
    assert statements[0][1] == ('CASE-1',)
