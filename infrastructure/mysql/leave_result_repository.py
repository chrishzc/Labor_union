"""Leave coordination stored in the existing Scheduling result/nominee owner.

The execution_dates JSON has a versioned leave envelope; no schema, approval
state or duplicate financial writer is introduced.
"""

from dataclasses import asdict
from datetime import date
import json

from domains.scheduling.service_start import ServiceStartConflict
from shared_kernel.clock import SystemBusinessClock
from shared_kernel.fingerprints import fingerprint_payload
from subsystems.scheduling.service_start_workflow import LeaveCase


def leave_context(request):
    raw = request.get('execution_dates')
    raw = json.loads(raw) if isinstance(raw, str) else raw
    return raw if isinstance(raw, dict) and raw.get('kind') == 'leave-v1' else None


def leave_cases(connection, staff_id, *, lock=False):
    with connection.cursor() as c:
        c.execute("SELECT o.case_no,o.lifecycle_version AS order_version,g.aggregate_version AS scheduling_version,"
            "a.id AS assignment_id,day.work_date FROM orders o "
            "JOIN scheduling_aggregates g ON g.case_no=o.case_no "
            "JOIN case_staff_assignments a ON a.generation_id=g.effective_generation_id "
            "JOIN staff_schedule day ON day.assignment_id=a.id AND day.effective_marker=1 AND day.is_work_day=1 "
            "WHERE a.staff_id=%s AND o.status IN ('訂單成立','服務中') AND day.work_date>=%s "
            "AND NOT EXISTS (SELECT 1 FROM order_service_data_locks l WHERE l.case_no=o.case_no) "
            "ORDER BY o.case_no,a.id,day.work_date" + (' FOR UPDATE' if lock else ''),
            (staff_id, SystemBusinessClock().today()))
        rows = c.fetchall()
    result = {}
    for row in rows:
        identity = (row['case_no'], row['assignment_id'])
        item = result.setdefault(identity, {**row, 'service_dates': []})
        item.pop('work_date', None)
        item['service_dates'].append(str(row['work_date']))
    return tuple(LeaveCase(**{**item,'service_dates':tuple(item['service_dates'])}) for item in result.values())


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
        c.execute("SELECT r.id,r.execution_dates FROM scheduling_service_start_requests r "
                  "WHERE r.case_no=%s AND r.staff_id=%s AND r.status='substitute_required' FOR UPDATE",
                  (submission.case_no, submission.staff_id))
        selected = {str(d.original_date) for d in submission.dates}
        for pending in c.fetchall():
            context = leave_context(pending)
            if context and selected & {d['original_date'] for d in context['dates']}:
                raise ServiceStartConflict('leave_result_already_pending', '這些日期已有待處理結果，請勿重複送出。')
        context = {'kind': 'leave-v1', 'decision': submission.decision,
                   'dates': [{'original_date': str(d.original_date),
                              'new_date': str(d.new_date) if d.new_date else None} for d in submission.dates]}
        c.execute('INSERT INTO scheduling_service_start_requests '
            '(case_no,staff_id,assignment_id,decision,requested_start_date,source_order_version,status,'
            'submit_key,submit_fingerprint,execution_dates) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
            (submission.case_no, submission.staff_id, submission.assignment_id,
             'accepted' if submission.decision == 'defer' else 'declined', submission.dates[0].new_date,
             submission.expected_order_version, 'awaiting_peers' if submission.decision == 'defer' else 'substitute_required',
             submission.key, submission_fingerprint(submission), json.dumps(context, ensure_ascii=False)))
        return int(c.lastrowid)


def record_leave_dates(repository, request_id, dates, *, defer=False):
    request = repository.request(request_id, lock=True)
    context = leave_context(request)
    if not context:
        if dates is not None or defer:
            raise ServiceStartConflict('leave_result_required', '此操作只適用於請假協調結果。')
        return
    if not dates or {str(d.original_date) for d in dates} != {d['original_date'] for d in context['dates']}:
        raise ServiceStartConflict('leave_result_dates_required', '請為每個原服務日填寫雙方確認後的實際日期。')
    new_dates = tuple(d.new_date for d in dates)
    if any(day is None for day in new_dates) or len(set(new_dates)) != len(new_dates):
        raise ServiceStartConflict('leave_result_new_dates_invalid', '實際服務日期不可空白或重複。')
    if defer and any(d.new_date <= d.original_date for d in dates):
        raise ServiceStartConflict('leave_result_must_defer', '順延日期必須晚於原服務日。')
    if defer:
        context['decision'] = 'defer'
    context['dates'] = [{'original_date': str(d.original_date), 'new_date': str(d.new_date)} for d in dates]
    context.pop('conflict_message', None)
    with repository.connection.cursor() as c:
        c.execute('UPDATE scheduling_service_start_requests SET execution_dates=%s,selected_candidate_id='
                  + ('NULL' if defer else 'selected_candidate_id') + ' WHERE id=%s',
                  (json.dumps(context, ensure_ascii=False), request_id))
