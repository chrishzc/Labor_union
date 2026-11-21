"""Leave coordination stored in the existing Scheduling result/nominee owner.

The execution_dates JSON has a versioned leave envelope; no schema, approval
state or duplicate financial writer is introduced.
"""

from dataclasses import asdict
from datetime import date
import json

from domains.orders.lifecycle import OrderLifecycleStatus
from domains.scheduling.service_start import ServiceStartConflict
from shared_kernel.clock import SystemBusinessClock
from shared_kernel.fingerprints import fingerprint_payload
from subsystems.scheduling.service_start_workflow import LeaveCase, LeaveCaseAvailability


_ELIGIBLE_ORDER_STATUSES = (OrderLifecycleStatus.ESTABLISHED.value, OrderLifecycleStatus.IN_SERVICE.value)


def leave_context(request):
    raw = request.get('execution_dates')
    raw = json.loads(raw) if isinstance(raw, str) else raw
    return raw if isinstance(raw, dict) and raw.get('kind') == 'leave-v1' else None


def leave_cases(connection, staff_id, *, lock=False, case_no=None):
    case_filter = '' if case_no is None else ' AND o.case_no=%s'
    parameters = (staff_id, *_ELIGIBLE_ORDER_STATUSES, SystemBusinessClock().today())
    if case_no is not None:
        parameters += (case_no,)
    with connection.cursor() as c:
        c.execute("SELECT o.case_no,o.lifecycle_version AS order_version,g.aggregate_version AS scheduling_version,"
            "a.id AS assignment_id,day.work_date FROM orders o "
            "JOIN scheduling_aggregates g ON g.case_no=o.case_no "
            "JOIN case_staff_assignments a ON a.generation_id=g.effective_generation_id "
            "JOIN staff_schedule day ON day.assignment_id=a.id AND day.effective_marker=1 AND day.is_work_day=1 "
            "WHERE a.staff_id=%s AND o.status IN (%s,%s) AND day.work_date>=%s "
            "AND NOT EXISTS (SELECT 1 FROM order_service_data_locks l WHERE l.case_no=o.case_no)"
            + case_filter + " ORDER BY o.case_no,a.id,day.work_date" + (' FOR UPDATE' if lock else ''),
            parameters)
        rows = c.fetchall()
    result = {}
    for row in rows:
        identity = (row['case_no'], row['assignment_id'])
        item = result.setdefault(identity, {**row, 'service_dates': []})
        item.pop('work_date', None)
        item['service_dates'].append(str(row['work_date']))
    return tuple(LeaveCase(**{**item,'service_dates':tuple(item['service_dates'])}) for item in result.values())


def selected_leave_case(connection, staff_id: int, case_no: str, *, lock: bool = False) -> tuple[tuple[LeaveCase, ...], LeaveCaseAvailability]:
    cases = leave_cases(connection, staff_id, case_no=case_no, lock=lock)
    if cases:
        return cases, LeaveCaseAvailability('eligible')

    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT o.status, EXISTS(SELECT 1 FROM order_service_data_locks l "
            "WHERE l.case_no=o.case_no) AS service_data_locked FROM orders o "
            "JOIN scheduling_aggregates g ON g.case_no=o.case_no "
            "WHERE o.case_no=%s AND EXISTS(SELECT 1 FROM case_staff_assignments a "
            "WHERE a.generation_id=g.effective_generation_id AND a.staff_id=%s)",
            (case_no, staff_id),
        )
        order = cursor.fetchone()
    if order is None:
        return (), LeaveCaseAvailability('not_assigned')
    if order['status'] not in _ELIGIBLE_ORDER_STATUSES:
        return (), LeaveCaseAvailability('order_status', str(order['status']))
    if order['service_data_locked']:
        return (), LeaveCaseAvailability('service_data_locked')
    return (), LeaveCaseAvailability('no_adjustable_days')


def submission_fingerprint(submission):
    payload = json.loads(json.dumps(asdict(submission), default=str))
    return fingerprint_payload({'family': 'scheduling-leave-result/v1', **payload}).value


def replay_leave(repository, submission):
    with repository.connection.cursor() as c:
        c.execute('SELECT id,staff_id,submit_fingerprint,execution_dates FROM scheduling_service_start_requests '
                  'WHERE submit_key=%s FOR UPDATE', (submission.key,))
        row = c.fetchone()
    if not row:
        return None
    if (row['staff_id'] != submission.staff_id or not leave_context(row)
            or row['submit_fingerprint'] != submission_fingerprint(submission)):
        raise ServiceStartConflict('leave_result_key_reused', '這筆操作識別已用於不同內容，請重新查詢。')
    return repository.view(row['id'], staff_id=submission.staff_id, lock=True)


def create_leave(repository, submission):
    subject = next((r for r in leave_cases(repository.connection, submission.staff_id, lock=True)
                    if r.case_no == submission.case_no and r.assignment_id == submission.assignment_id), None)
    if not subject:
        raise ServiceStartConflict('leave_result_forbidden', '只能提交本人尚未完成服務的正式排班。')
    if (subject.order_version != submission.expected_order_version
            or subject.scheduling_version != submission.expected_scheduling_version):
        raise ServiceStartConflict('leave_result_stale', '排班已更新，請重新查詢並核對日期。')
    if any(str(item.original_date) not in subject.service_dates for item in submission.dates):
        raise ServiceStartConflict('leave_result_dates_changed', '選擇的日期已不在本人正式排班，請重新查詢。')
    with repository.connection.cursor() as c:
        context = {'kind': 'leave-v1', 'decision': submission.decision,
                   'dates': [{'original_date': str(d.original_date),
                              'new_date': str(d.new_date) if d.new_date else None} for d in submission.dates]}
        c.execute('INSERT INTO scheduling_service_start_requests '
            '(case_no,staff_id,assignment_id,decision,requested_start_date,source_order_version,status,'
            'submit_key,submit_fingerprint,execution_dates) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
            (submission.case_no, submission.staff_id, submission.assignment_id,
             'accepted', submission.dates[0].new_date,
             submission.expected_order_version, 'awaiting_peers',
             submission.key, submission_fingerprint(submission), json.dumps(context, ensure_ascii=False)))
        return int(c.lastrowid)
