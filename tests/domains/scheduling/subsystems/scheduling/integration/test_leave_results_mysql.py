"""Real local owner transactions for agreed leave results; no provider worker runs."""
import os
import runpy
from dataclasses import replace
from datetime import date, timedelta
from uuid import uuid4

import pytest

base = runpy.run_path('tests/domains/scheduling/subsystems/scheduling/modules/service-start/test_service_start_mysql.py')
http = base['http']
rows, write, checked = base['rows'], base['write'], base['checked']
postponement_submission = base['postponement_submission']
apply_confirmed_postponement = base['apply_confirmed_postponement']
owner_state, seed_legacy_pending = base['owner_state'], base['seed_legacy_pending']
RETIRED_SUBMIT = '/api/v1/line/staff-self-service/leave-results/submit'
ORIGINAL_DATE = '2027-01-05'
POSTPONED_DATE = '2027-02-10'
pytestmark = pytest.mark.skipif(not os.getenv('SERVICE_START_TEST_DB'), reason='explicit local synthetic DB required')


def setup(http, count=1):
    case, staff, segments = base['seed_case'](http, count=count)
    for index in range(count):
        checked(base['submit'](http,case,staff[index],segments[index],start=str(date(2027,1,5)+timedelta(days=30*index)))[0])
    return case, staff


def confirmed_command(http, case, staff, *, dates=((ORIGINAL_DATE, POSTPONED_DATE),)):
    return postponement_submission(http, case, staff, dates)


def block_staff_day(staff, day):
    write(
        "INSERT INTO scheduling_staff_unavailability_blocks"
        "(staff_id,block_kind,start_date,end_date,status,reason,created_by) "
        "VALUES (%s,'long_leave',%s,%s,'effective','synthetic','synthetic')",
        (staff[0], day, day),
    )


def substitute_change(command, substitute_staff):
    return {
        'scope': 'upcoming',
        'evidence': 'Recorded consent from the substitute by phone',
        'moves': [{
            'source_assignment_id': command.assignment_id,
            'source_date': ORIGINAL_DATE,
            'staff_id': substitute_staff[0],
            'replacement_date': ORIGINAL_DATE,
        }],
    }


def substitute_command(http, case, change):
    path = f'/api/v1/orders/{case}/service-attribution'
    preview = checked(http.post(path + '/preview', json=change))
    return {
        **change,
        'expected_order_version': preview['order_version'],
        'expected_scheduling_version': preview['scheduling_version'],
        'preview_fingerprint': preview['preview_fingerprint'],
        'reason': 'Temporary substitute',
    }


def schedule(case):
    return rows('SELECT a.staff_id,d.work_date,d.is_double_pay FROM staff_schedule d JOIN case_staff_assignments a ON a.id=d.assignment_id '
        'JOIN scheduling_aggregates g ON g.effective_generation_id=a.generation_id '
        'WHERE a.case_no=%s AND d.effective_marker=1 AND d.is_work_day=1 ORDER BY d.work_date',(case,))


def order_status_and_deposit_settlement(case):
    return rows(
        'SELECT o.status, d.settlement_state FROM orders o '
        'JOIN client_deposit_settlement_projection d ON d.case_no=o.case_no WHERE o.case_no=%s',
        (case,),
    )[0]


def test_selected_leave_case_distinguishes_ineligible_order_from_unassigned_staff(http):
    case, staff = setup(http)
    path = '/api/v1/line/staff-self-service/leave-results/cases'

    legacy = checked(http.post(path, json={'line_id_token': staff[0][1]}))
    assert set(legacy) == {'items'}
    target = checked(http.post(path, json={'line_id_token': staff[0][1], 'case_no': case}))
    assert target['availability'] == {'code': 'eligible'}
    assert target['items'] == [item for item in legacy['items'] if item['case_no'] == case]
    assert target['items']

    write("UPDATE orders SET status='洽談中' WHERE case_no=%s", (case,))
    assert schedule(case)
    target = checked(http.post(path, json={'line_id_token': staff[0][1], 'case_no': case}))
    assert target == {
        'items': [],
        'availability': {'code': 'order_status', 'order_status': '洽談中'},
    }

    other_staff = checked(http.post(path, json={'line_id_token': staff[1][1], 'case_no': case}))
    assert other_staff == {'items': [], 'availability': {'code': 'not_assigned'}}


def test_confirmed_postponement_updates_schedule_and_finance_without_push(http):
    case, staff = setup(http)
    expected_status = {'status': '訂單成立', 'settlement_state': 'settled'}
    assert order_status_and_deposit_settlement(case) == expected_status
    before = schedule(case)
    payments = rows('SELECT id,amount_ntd FROM client_ledger_entries WHERE case_no=%s ORDER BY id', (case,))
    existing_deliveries = rows(
        'SELECT id FROM line_delivery_tasks WHERE recipient_identity IN '
        '(SELECT group_id FROM line_order_group_bindings WHERE case_no=%s) ORDER BY id',
        (case,),
    )
    command = confirmed_command(http, case, staff[0])
    result = apply_confirmed_postponement(command)
    assert result['workflow_kind'] == 'leave' and result['status'] == 'applied'
    assert result['result']['actual_start_date'] == '2027-01-06'
    assert result['result']['actual_end_date'] == POSTPONED_DATE
    assert result['result']['first_payment_due_date'] == '2027-01-06'
    assert order_status_and_deposit_settlement(case) == expected_status
    after = schedule(case)
    assert len(after) == len(before) == 30
    assert str(after[-1]['work_date']) == POSTPONED_DATE
    assert rows('SELECT id,amount_ntd FROM client_ledger_entries WHERE case_no=%s ORDER BY id', (case,)) == payments
    assert apply_confirmed_postponement(command)['request_id'] == result['request_id']
    assert not result['result']['group_record_queued']
    assert not rows(
        "SELECT id FROM line_delivery_tasks WHERE source_aggregate_type='service_start_schedule' "
        "AND source_aggregate_identity=%s", (str(result['request_id']),),
    )
    assert not rows(
        "SELECT id FROM line_delivery_tasks WHERE source_aggregate_type='staff_leave_customer_coordination' "
        "AND payload_snapshot LIKE %s", ('%' + case + '%',),
    )
    assert checked(http.get('/api/v1/scheduling/service-start/todos', params={'case_no': case}))['total'] == 0
    from domains.scheduling.leave_result import LeaveDateChange
    from domains.scheduling.service_start import ServiceStartConflict

    with pytest.raises(ServiceStartConflict) as raised:
        apply_confirmed_postponement(replace(
            command, dates=(LeaveDateChange(date.fromisoformat(ORIGINAL_DATE), date(2027, 2, 11)),),
        ))
    assert raised.value.code == 'leave_result_key_reused'
    assert schedule(case) == after

    second = apply_confirmed_postponement(confirmed_command(
        http, case, staff[0], dates=[('2027-01-06', '2027-02-11')],
    ))
    assert second['status'] == 'applied'
    assert second['result']['actual_start_date'] == second['result']['first_payment_due_date'] == '2027-01-07'
    assert order_status_and_deposit_settlement(case) == expected_status
    reopened = checked(http.post(
        '/api/v1/line/staff-self-service/leave-results/cases',
        json={'line_id_token': staff[0][1], 'case_no': case},
    ))
    assert reopened['availability'] == {'code': 'eligible'}
    assert [item['case_no'] for item in reopened['items']] == [case]
    assert len(schedule(case)) == len(before)
    assert rows('SELECT id,amount_ntd FROM client_ledger_entries WHERE case_no=%s ORDER BY id', (case,)) == payments
    assert not second['result']['group_record_queued']
    assert rows(
        'SELECT id FROM line_delivery_tasks WHERE recipient_identity IN '
        '(SELECT group_id FROM line_order_group_bindings WHERE case_no=%s) ORDER BY id',
        (case,),
    ) == existing_deliveries


def test_conflict_preserves_all_owner_facts_then_fresh_agreement_can_apply(http):
    from domains.scheduling.service_start import ServiceStartConflict

    case, staff = setup(http)
    block_staff_day(staff[0], POSTPONED_DATE)
    before = owner_state(case)
    command = confirmed_command(http, case, staff[0])
    with pytest.raises(ServiceStartConflict) as raised:
        apply_confirmed_postponement(command)
    assert raised.value.code == 'staff_unavailable'
    assert owner_state(case) == before
    assert checked(http.get('/api/v1/scheduling/service-start/todos', params={'case_no': case}))['total'] == 0
    new_command = confirmed_command(http, case, staff[0], dates=[(ORIGINAL_DATE, '2027-02-11')])
    updated = apply_confirmed_postponement(new_command)
    assert updated['status'] == 'applied'
    assert apply_confirmed_postponement(new_command) == updated

def test_manual_substitution_updates_only_requested_day_without_todo_or_group_join(http):
    case, staff = setup(http)
    before = schedule(case)
    original = owner_state(case)
    confirmation = confirmed_command(http, case, staff[0])
    command = substitute_command(http, case, substitute_change(confirmation, staff[1]))
    headers = {'Idempotency-Key': uuid4().hex, 'X-Correlation-ID': case}
    assert owner_state(case) == original
    path = f'/api/v1/orders/{case}/service-attribution/apply'
    receipt = checked(http.post(path, json=command, headers=headers))
    assert schedule(case) == [
        {**row, 'staff_id': staff[1][0]} if str(row['work_date']) == ORIGINAL_DATE else row for row in before
    ]
    after = owner_state(case)
    assert after['orders'][0]['actual_start_date'] == original['orders'][0]['actual_start_date']
    assert after['orders'][0]['actual_end_date'] == original['orders'][0]['actual_end_date']
    for field in ('first_payment_due_date', 'second_payment_due_date'):
        assert after['client_payment_terms'][0][field] == original['client_payment_terms'][0][field]
    assert after['staff_obligations'] != original['staff_obligations']
    assert after['client_obligations'] == original['client_obligations']
    assert after['scheduling_service_start_requests'] == original['scheduling_service_start_requests']
    assert checked(http.post(path, json=command, headers=headers)) == receipt
    assert owner_state(case) == after
    assert checked(http.get('/api/v1/scheduling/service-start/todos', params={'case_no': case}))['total'] == 0

def test_confirmed_postponement_guards_scope_versions_dates_and_rollback(http, monkeypatch):
    from domains.scheduling.leave_result import LeaveDateChange
    from domains.scheduling.service_start import ServiceStartConflict
    from infrastructure.mysql.service_start_repository import MySqlServiceStartRepository

    case, staff = setup(http)
    command = confirmed_command(http, case, staff[0])
    invalid_commands = (
        (replace(command, expected_scheduling_version=0), 'leave_result_stale'),
        (replace(command, staff_id=staff[1][0]), 'leave_result_forbidden'),
        (replace(command, dates=(LeaveDateChange(date(2027, 1, 4), date(2027, 2, 10)),)), 'leave_result_dates_changed'),
    )
    before = schedule(case)
    for invalid, code in invalid_commands:
        with pytest.raises(ServiceStartConflict) as raised:
            apply_confirmed_postponement(invalid)
        assert raised.value.code == code

    def fail(*args, **kwargs):
        raise RuntimeError('synthetic failure after financial writes')

    with monkeypatch.context() as patch:
        patch.setattr(MySqlServiceStartRepository, 'complete', fail)
        with pytest.raises(RuntimeError, match='synthetic failure'):
            apply_confirmed_postponement(command)
    assert schedule(case) == before
    assert rows('SELECT COUNT(*) n FROM scheduling_service_start_requests WHERE case_no=%s', (case,))[0]['n'] == 1


def test_same_case_date_collision_returns_conflict_and_preserves_all_owner_facts(http):
    from domains.scheduling.service_start import ServiceStartConflict

    case, staff = setup(http, count=2)
    before = owner_state(case)
    command = confirmed_command(http, case, staff[1], dates=[('2027-02-04', '2027-02-05')])
    with pytest.raises(ServiceStartConflict):
        apply_confirmed_postponement(command)
    assert owner_state(case) == before
    before_schedule = schedule(case)
    result = apply_confirmed_postponement(confirmed_command(
        http, case, staff[1], dates=[('2027-02-04', '2027-03-10')],
    ))
    assert result['status'] == 'applied'
    assert [r for r in schedule(case) if r['staff_id'] == staff[0][0]] == [
        r for r in before_schedule if r['staff_id'] == staff[0][0]
    ]
    assert len(schedule(case)) == len(before_schedule)

def test_retired_linked_substitution_and_fresh_occupancy_conflict_write_nothing(http):
    case, staff = setup(http)
    confirmation = confirmed_command(http, case, staff[0])
    request_id = seed_legacy_pending(case, staff[0][0], assignment_id=confirmation.assignment_id, execution={
        'kind': 'leave-v1', 'decision': 'defer',
        'dates': [{'original_date': ORIGINAL_DATE, 'new_date': POSTPONED_DATE}],
    })
    task_path = f'/api/v1/scheduling/service-start/{request_id}'
    old_task = checked(http.get(task_path))
    before = owner_state(case)
    change = substitute_change(confirmation, staff[1])
    linked = {'substitute_request_id': request_id, 'expected_substitute_request_version': old_task['version']}
    path = f'/api/v1/orders/{case}/service-attribution'
    response = http.post(path + '/preview', json={**change, **linked})
    assert response.status_code == 410
    command = substitute_command(http, case, change)
    response = http.post(path + '/apply', json={**command, **linked},
                         headers={'Idempotency-Key': uuid4().hex, 'X-Correlation-ID': case})
    assert response.status_code == 410
    blocked = http.post(task_path + '/dates', json={
        'expected_version': old_task['version'], 'idempotency_key': uuid4().hex, 'start_date': ORIGINAL_DATE,
    })
    assert blocked.status_code == 410
    assert blocked.json()['detail']['error']['code'] == 'leave_substitute_dates_retired'
    block_staff_day(staff[1], ORIGINAL_DATE)
    response = http.post(path + '/apply', json=command,
                         headers={'Idempotency-Key': uuid4().hex, 'X-Correlation-ID': case})
    assert response.status_code == 409
    assert owner_state(case) == before
    assert checked(http.get(task_path)) == old_task

def test_in_service_defer_preserves_started_days_and_receipt_history(http):
    from shared_kernel.clock import SystemBusinessClock

    today = SystemBusinessClock().today()
    start = today - timedelta(days=1)
    day = str(today + timedelta(days=3))
    new_day = str(today + timedelta(days=35))
    case, staff, segments = base['seed_case'](http)
    checked(base['submit'](http, case, staff[0], segments[0], start=str(start))[0])
    expected_status = {'status': '服務中', 'settlement_state': 'settled'}
    assert order_status_and_deposit_settlement(case) == expected_status
    before = schedule(case)
    paid = rows('SELECT id,amount_ntd FROM client_ledger_entries WHERE case_no=%s ORDER BY id', (case,))
    result = apply_confirmed_postponement(confirmed_command(http, case, staff[0], dates=[(day, new_day)]))
    assert result['status'] == 'applied'
    assert result['result']['actual_start_date'] == str(start)
    assert result['result']['first_payment_due_date'] == str(start)
    assert order_status_and_deposit_settlement(case) == expected_status
    assert [r for r in schedule(case) if str(r['work_date']) < day] == [r for r in before if str(r['work_date']) < day]
    assert rows('SELECT id,amount_ntd FROM client_ledger_entries WHERE case_no=%s ORDER BY id', (case,)) == paid


def test_retired_staff_submit_does_not_change_owner_facts(http):
    case, staff = setup(http)
    before = schedule(case)
    requests = rows('SELECT id,aggregate_version FROM scheduling_service_start_requests WHERE case_no=%s', (case,))
    command = confirmed_command(http, case, staff[0])
    response = http.post(RETIRED_SUBMIT, json={
        'line_id_token': staff[0][1], 'case_no': case, 'assignment_id': command.assignment_id,
        'decision': command.decision, 'expected_order_version': command.expected_order_version,
        'expected_scheduling_version': command.expected_scheduling_version, 'idempotency_key': command.key,
        'dates': [{'original_date': ORIGINAL_DATE, 'new_date': POSTPONED_DATE}],
    })
    assert response.status_code == 410
    assert schedule(case) == before
    assert rows('SELECT id,aggregate_version FROM scheduling_service_start_requests WHERE case_no=%s', (case,)) == requests
