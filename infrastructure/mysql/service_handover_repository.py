"""Formal handover context in the existing Scheduling coordination aggregate."""

import json

from domains.scheduling.service_start import ServiceStartConflict
from shared_kernel.clock import SystemBusinessClock
from shared_kernel.fingerprints import fingerprint_payload
from subsystems.scheduling.service_start_workflow import HandoverContext


def handover_context(request):
    raw = request.get('execution_dates')
    raw = json.loads(raw) if isinstance(raw, str) else raw
    return raw if isinstance(raw, dict) and raw.get('kind') == 'handover-v1' else None


def load_handover(repository, case_no, assignment_id=None, *, lock=False):
    today = SystemBusinessClock().today()
    suffix = ' FOR UPDATE' if lock else ''
    with repository.connection.cursor() as c:
        c.execute("SELECT r.id FROM scheduling_service_start_requests r WHERE r.case_no=%s "
            "AND r.assignment_id=%s AND JSON_UNQUOTE(JSON_EXTRACT(r.execution_dates,'$.kind'))='handover-v1' "
            'ORDER BY r.id DESC LIMIT 1'+suffix, (case_no, assignment_id))
        existing = c.fetchone()
        c.execute('SELECT a.id,a.staff_id,s.name,o.lifecycle_version,g.aggregate_version,day.work_date '
            'FROM orders o JOIN scheduling_aggregates g ON g.case_no=o.case_no '
            'JOIN case_staff_assignments a ON a.generation_id=g.effective_generation_id '
            'JOIN staff s ON s.id=a.staff_id JOIN staff_schedule day ON day.assignment_id=a.id '
            'AND day.effective_marker=1 AND day.is_work_day=1 '
            "WHERE o.case_no=%s AND o.status IN ('訂單成立','服務中') AND o.actual_start_date<=%s "
            'AND (%s IS NULL OR a.id=%s) AND day.work_date>=%s '
            'AND NOT EXISTS (SELECT 1 FROM order_service_data_locks l WHERE l.case_no=o.case_no) '
            'ORDER BY a.assignment_sequence,day.work_date'+suffix, (case_no,today,assignment_id,assignment_id,today))
        rows = c.fetchall()
    if existing:
        view = repository.view(existing['id'],lock=lock)
        if view.status == 'applied':
            # The successful generation replaces the original assignment; its result stays reviewable.
            with repository.connection.cursor() as c:
                c.execute('SELECT aggregate_version FROM scheduling_aggregates WHERE case_no=%s'+suffix,(case_no,))
                scheduling = c.fetchone()
            return HandoverContext(case_no, assignment_id, view.staff_id, view.staff_name,
                view.order_version, int(scheduling['aggregate_version']), view.handover_dates, view)
    if not rows:
        raise ServiceStartConflict('handover_assignment_unavailable', '本區段沒有尚未完成的正式服務日，請從案件重新開啟。')
    if len({row['id'] for row in rows}) != 1:
        raise ServiceStartConflict('handover_assignment_required', '本案有多個服務區段，請從原月嫂的服務中換人按鈕開啟。')
    row = rows[0]
    if assignment_id is None:
        with repository.connection.cursor() as c:
            c.execute("SELECT id FROM scheduling_service_start_requests WHERE case_no=%s AND assignment_id=%s "
                "AND JSON_UNQUOTE(JSON_EXTRACT(execution_dates,'$.kind'))='handover-v1' ORDER BY id DESC LIMIT 1"+suffix,
                (case_no,row['id']))
            existing = c.fetchone()
    return HandoverContext(case_no, int(row['id']), int(row['staff_id']), row['name'],
        int(row['lifecycle_version']), int(row['aggregate_version']),
        tuple(str(r['work_date']) for r in rows), repository.view(existing['id'],lock=lock) if existing else None)


def create_handover(repository, case_no, assignment_id, order_version, scheduling_version, key, payload):
    context = load_handover(repository, case_no, assignment_id,lock=True)
    if context.request is not None:
        raise ServiceStartConflict('handover_already_pending', '本區段已有換人作業，請重新查詢並接續處理。')
    if context.order_version != order_version or context.scheduling_version != scheduling_version:
        raise ServiceStartConflict('handover_stale', '案件或排班已更新，請重新查詢後再選人。')
    envelope = {'kind':'handover-v1', 'dates':list(context.service_dates)}
    with repository.connection.cursor() as c:
        c.execute('SELECT id FROM scheduling_service_start_requests WHERE submit_key=%s FOR UPDATE', (key,))
        if c.fetchone():
            raise ServiceStartConflict('service_start_key_reused', '操作識別已用於其他內容，請重新查詢。')
        c.execute('INSERT INTO scheduling_service_start_requests '
            '(case_no,staff_id,assignment_id,decision,source_order_version,status,submit_key,submit_fingerprint,execution_dates) '
            "VALUES (%s,%s,%s,'declined',%s,'substitute_required',%s,%s,%s)",
            (case_no,context.staff_id,context.assignment_id,order_version,key,
             fingerprint_payload({'payload':payload}).value,json.dumps(envelope,ensure_ascii=False)))
        return int(c.lastrowid), context.service_dates
