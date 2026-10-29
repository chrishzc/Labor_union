"""Scheduling-owned service-start facts; delivery is only committed work, never a provider call."""

from infrastructure.mysql.line_message_copy import configured_message_payload

from dataclasses import asdict
from datetime import date, datetime, timezone
import hashlib
import json
import secrets

from domains.line.delivery import LineDeliveryRequest, LineMessageKind, LineRecipient, LineRecipientType
from domains.line.identities import LineGroupId, LineUserId
from domains.line.order_group import validate_invitation_url
from domains.scheduling.service_start import ServiceStartConflict
from infrastructure.mysql.line_delivery_task_repository import MySqlLineDeliveryTaskRepository
from shared_kernel.clock import SystemBusinessClock
from shared_kernel.fingerprints import fingerprint_payload
from shared_kernel.identities import CorrelationId, IdempotencyKey
from subsystems.scheduling.service_start_workflow import ServiceStartCase, ServiceStartView
from subsystems.line.order_group_application import group_invitation_payload
from subsystems.line.service_start_messages import substitute_inquiry, service_date_record
from infrastructure.mysql.leave_result_repository import (
    leave_context, leave_cases, replay_leave, create_leave, record_leave_dates,
)
from infrastructure.mysql.service_handover_repository import handover_context, load_handover, create_handover


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str, separators=(',', ':'))


def _decoded(value):
    return json.loads(value) if isinstance(value, str) else value


class MySqlServiceStartRepository:
    def __init__(self, connection):
        self.connection = connection
        self.deliveries = MySqlLineDeliveryTaskRepository(connection)

    def leave_cases(self, staff_id):
        return leave_cases(self.connection, staff_id)

    def handover_context(self, case_no, assignment_id=None):
        return load_handover(self, case_no, assignment_id)

    def create_handover(self, *args):
        return create_handover(self, *args)

    def replay_leave(self, submission):
        return replay_leave(self, submission)

    def create_leave(self, submission):
        return create_leave(self, submission)

    def record_leave_dates(self, request_id, dates, *, defer=False):
        return record_leave_dates(self, request_id, dates, defer=defer)

    def staff_options(self, keyword=""):
        with self.connection.cursor() as c:
            c.execute("SELECT s.id,s.name FROM staff s LEFT JOIN staff_lifecycle_states l ON l.staff_id=s.id "
                "WHERE s.status='active' AND COALESCE(l.lifecycle_state,'active')='active' AND s.name LIKE %s ORDER BY s.id LIMIT 50",('%'+keyword+'%',))
            return [{'staff_id':int(row['id']),'name':row['name']} for row in c.fetchall()]

    def staff_cases(self, staff_id):
        with self.connection.cursor() as c:
            c.execute(_STAFF_CASES, (staff_id, staff_id))
            return tuple(ServiceStartCase(str(r['case_no']), staff_id, r['staff_name'], r['segment_id'],
                int(r['lifecycle_version']), int(r['service_days']), str(r['start_date']),r['assignment_id'],
                str(r['segment_start_date']),str(r['segment_end_date'])) for r in c.fetchall())

    def lock_submission(self, submission):
        self.lock_case(submission.case_no,(submission.staff_id,))

    def lock_case(self,case_no,extra_staff=()):
        from subsystems.scheduling.occupancy_mutex import lock_staff_occupancy_mutex
        with self.connection.cursor() as c:
            c.execute('SELECT s.staff_id FROM caregiver_matching_plan_segments s JOIN caregiver_matching_plans p ON p.id=s.plan_id WHERE p.case_no=%s AND p.is_active=1 '
                'UNION SELECT a.staff_id FROM case_staff_assignments a JOIN scheduling_aggregates g ON g.effective_generation_id=a.generation_id WHERE a.case_no=%s '
                'UNION SELECT candidate.staff_id FROM scheduling_service_start_candidates candidate JOIN scheduling_service_start_requests r ON r.selected_candidate_id=candidate.id WHERE r.case_no=%s',
                (case_no,case_no,case_no))
            staff_ids=sorted({int(row['staff_id']) for row in c.fetchall()}|set(extra_staff))
            lock_staff_occupancy_mutex(c,staff_ids)
            c.execute('SELECT case_no FROM orders WHERE case_no=%s FOR UPDATE',(case_no,))

    def lock_subject(self, submission):
        with self.connection.cursor() as c:
            c.execute(_STAFF_CASES + ' FOR UPDATE', (submission.staff_id, submission.staff_id))
            subjects=[r for r in c.fetchall() if r['case_no'] == submission.case_no
                and r['segment_id'] == submission.segment_id
                and (submission.assignment_id is None or r['assignment_id']==submission.assignment_id)]
            if len(subjects)>1:
                raise ServiceStartConflict('service_start_segment_required','請選擇需要處理的服務區段。')
            subject=subjects[0] if subjects else None
            if subject is None:
                raise ServiceStartConflict('service_start_subject_invalid', '目前無法對這個案件或服務區段提交。')
            if subject['lifecycle_version'] != submission.expected_order_version:
                raise ServiceStartConflict('service_start_stale', '案件已更新，請重新查詢後再送出。')
            c.execute("SELECT s.id FROM staff s LEFT JOIN staff_lifecycle_states l ON l.staff_id=s.id WHERE s.id=%s AND s.status='active' AND COALESCE(l.lifecycle_state,'active')='active' FOR UPDATE",(submission.staff_id,))
            if not c.fetchone():
                raise ServiceStartConflict('service_start_subject_invalid','目前無法提交服務安排。')
            return subject

    def replay_submission(self, submission, *, lock=False):
        with self.connection.cursor() as c:
            c.execute('SELECT id,staff_id,submit_fingerprint FROM scheduling_service_start_requests WHERE submit_key=%s'+(' FOR UPDATE' if lock else ''), (submission.key,))
            row = c.fetchone()
        if row is None:
            return None
        if row['staff_id'] != submission.staff_id or row['submit_fingerprint'] != self._submission_fingerprint(submission):
            raise ServiceStartConflict('service_start_key_reused', '這筆操作識別已用於不同內容。')
        return self.view(row['id'], staff_id=submission.staff_id,lock=lock)

    @staticmethod
    def _submission_fingerprint(submission):
        return fingerprint_payload({**asdict(submission), 'decision': submission.decision.value,
            'start_date': str(submission.start_date)}).value

    def create_submission(self, submission, subject):
        with self.connection.cursor() as c:
            c.execute('INSERT INTO scheduling_service_start_requests '
                '(case_no,staff_id,plan_id,segment_id,assignment_id,decision,requested_start_date,source_order_version,status,submit_key,submit_fingerprint) '
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (submission.case_no, submission.staff_id, subject['plan_id'], submission.segment_id,
                 subject['assignment_id'], submission.decision.value, submission.start_date, submission.expected_order_version,
                 'substitute_required' if submission.decision.value == 'declined' else 'awaiting_peers',
                 submission.key, self._submission_fingerprint(submission)))
            return int(c.lastrowid)

    def request(self, request_id, *, lock=False):
        with self.connection.cursor() as c:
            c.execute('SELECT * FROM scheduling_service_start_requests WHERE id=%s' + (' FOR UPDATE' if lock else ''), (request_id,))
            row = c.fetchone()
        if row is None:
            raise ServiceStartConflict('service_start_not_found', '找不到這筆服務安排。')
        return row

    def candidate(self, request, *, lock=False):
        with self.connection.cursor() as c:
            c.execute('SELECT candidate.*,staff.name AS staff_name,binding.line_user_id '
                'FROM scheduling_service_start_candidates candidate JOIN staff ON staff.id=candidate.staff_id '
                "LEFT JOIN line_identity_role_bindings binding ON binding.subject_type='staff' AND binding.binding_status='bound' "
                'AND binding.subject_reference=CAST(staff.id AS CHAR CHARACTER SET utf8mb4) COLLATE utf8mb4_unicode_ci '
                "AND binding.line_user_id=staff.line_user_id AND staff.status='active' "
                "AND NOT EXISTS (SELECT 1 FROM staff_lifecycle_states lifecycle WHERE lifecycle.staff_id=staff.id AND lifecycle.lifecycle_state<>'active') "
                'WHERE candidate.id=%s' + (' FOR UPDATE' if lock else ''),
                (request['selected_candidate_id'],))
            return c.fetchone()

    def group(self, case_no, *, lock=False):
        with self.connection.cursor() as c:
            c.execute('SELECT g.case_no,g.group_id,g.aggregate_version,g.invitation_url,'
                '(SELECT MAX(e.occurred_at_utc) FROM line_order_group_binding_events e WHERE e.case_no=g.case_no) AS bound_at '
                "FROM line_order_group_bindings g WHERE g.case_no=%s AND g.binding_status IN ('bound','inviting','active','attention')" + (' FOR UPDATE' if lock else ''), (case_no,))
            return c.fetchone()

    def joined(self, request, candidate, *, lock=False):
        group = self.group(request['case_no'],lock=lock)
        if not group or not group['group_id'] or not candidate or not candidate['line_user_id']:
            return False
        with self.connection.cursor() as c:
            c.execute('SELECT event_type FROM line_order_group_runtime_events '
                "WHERE case_no=%s AND line_user_id=%s AND event_type IN ('member_joined','member_left') "
                'AND occurred_at_utc >= %s ORDER BY occurred_at_utc DESC,id DESC LIMIT 1'+(' FOR UPDATE' if lock else ''),
                (request['case_no'], candidate['line_user_id'], group['bound_at']))
            event = c.fetchone()
        return bool(event and event['event_type'] == 'member_joined')

    def view(self, request_id, *, staff_id=None,lock=False):
        request = self.request(request_id,lock=lock)
        if staff_id is not None and request['staff_id'] != staff_id:
            raise ServiceStartConflict('service_start_forbidden', '只能查詢本人的服務安排結果。')
        candidate = self.candidate(request,lock=lock)
        with self.connection.cursor() as c:
            c.execute('SELECT name FROM staff WHERE id=%s', (request['staff_id'],))
            staff = c.fetchone()
            c.execute('SELECT lifecycle_version FROM orders WHERE case_no=%s'+(' FOR UPDATE' if lock else ''), (request['case_no'],))
            order = c.fetchone()
            delivery = None
            if candidate and candidate['invitation_identity']:
                c.execute('SELECT processing_status FROM line_delivery_tasks '
                    "WHERE source_aggregate_type='service_start_invitation' AND source_aggregate_identity=%s ORDER BY id DESC LIMIT 1"+(' FOR UPDATE' if lock else ''),
                    (candidate['invitation_identity'],))
                delivery = c.fetchone()
        return ServiceStartView(int(request['id']), request['case_no'], int(request['staff_id']), staff['name'],
            request['segment_id'], int(order['lifecycle_version']), int(request['aggregate_version']), request['status'],
            str(request['requested_start_date']) if request['requested_start_date'] else None,
            int(candidate['staff_id']) if candidate else None, candidate['staff_name'] if candidate else None,
            candidate['willingness'] if candidate else None, delivery['processing_status'] if delivery else None,
            self.joined(request, candidate,lock=lock), _decoded(request['result_snapshot']),
            str(candidate['proposed_start_date']) if candidate else None,
            str(candidate['proposed_end_date']) if candidate else None,
            'handover' if handover_context(request) else 'leave' if leave_context(request) else 'service_start',
            tuple(leave_context(request)['dates']) if leave_context(request) else (),
            (handover_context(request) or leave_context(request) or {}).get('conflict_message'),
            tuple(day for day in handover_context(request)['dates']
                if request['status']=='applied' or day>=str(SystemBusinessClock().today())) if handover_context(request) else ())

    def todos(self, page, page_size, case_no=None):
        if page < 1 or not 1 <= page_size <= 100:
            raise ValueError('invalid page')
        with self.connection.cursor() as c:
            where = " FROM scheduling_service_start_requests r JOIN orders o ON o.case_no=r.case_no WHERE r.status='substitute_required' AND o.status IN ('洽談中','訂單成立','服務中') AND (JSON_UNQUOTE(JSON_EXTRACT(r.execution_dates,'$.kind')) IN ('leave-v1','handover-v1') OR r.id=(SELECT MAX(latest.id) FROM scheduling_service_start_requests latest WHERE latest.case_no=r.case_no AND latest.staff_id=r.staff_id AND latest.segment_id<=>r.segment_id AND latest.assignment_id<=>r.assignment_id AND COALESCE(JSON_UNQUOTE(JSON_EXTRACT(latest.execution_dates,'$.kind')),'')NOT IN ('leave-v1','handover-v1')))"
            params=()
            if case_no is not None:
                where += ' AND r.case_no=%s'
                params=(case_no,)
            c.execute('SELECT COUNT(*) AS total' + where,params)
            total = int(c.fetchone()['total'])
            c.execute('SELECT r.id' + where + ' ORDER BY r.id LIMIT %s OFFSET %s', (*params,page_size, (page-1)*page_size))
            identities = [row['id'] for row in c.fetchall()]
        return tuple(self.view(value) for value in identities), total

    def command_replay(self, kind, key, payload):
        with self.connection.cursor() as c:
            c.execute('SELECT request_fingerprint,result_snapshot FROM admin_command_receipts WHERE command_family=%s AND idempotency_key=%s FOR UPDATE',
                ('scheduling.service_start.' + kind, key))
            row = c.fetchone()
        if row and row['request_fingerprint'] != fingerprint_payload({'payload': payload}).value:
            raise ServiceStartConflict('service_start_key_reused', '操作內容已變更，請重新查詢。')
        return int(_decoded(row['result_snapshot'])['request_id']) if row else None

    def lock_command(self, request_id, extra_staff=()):
        # Occupancy/case locks precede receipt locks for all shared union commands.
        self.lock_case(self.request(request_id)['case_no'], extra_staff)

    def save_command(self, kind, key, request_id, payload):
        fp = fingerprint_payload({'payload': payload}).value
        with self.connection.cursor() as c:
            c.execute('INSERT INTO admin_command_receipts '
                '(command_family,idempotency_key,request_fingerprint,preview_fingerprint,actor,reason,result_snapshot) VALUES (%s,%s,%s,%s,%s,%s,%s)',
                ('scheduling.service_start.'+kind, key, fp, fp, str(payload[-1]), '', _json({'request_id':request_id})))

    def require_pending(self, request_id, version, *, prelocked=False):
        if not prelocked:
            self.lock_case(self.request(request_id)['case_no'])
        request = self.request(request_id, lock=True)
        if request['aggregate_version'] != version or request['status'] != 'substitute_required':
            raise ServiceStartConflict('service_start_stale', '這筆代班已更新，請重新查詢。')
        if not self.is_current_request(request):
            raise ServiceStartConflict('service_start_stale','本區段已有新的協調結果，請重新查詢。')
        with self.connection.cursor() as c:
            c.execute("SELECT case_no FROM orders WHERE case_no=%s AND status IN ('洽談中','訂單成立','服務中') FOR UPDATE",(request['case_no'],))
            if not c.fetchone():
                raise ServiceStartConflict('service_start_case_closed','本案目前不可安排代班。')
        return request

    def is_current_request(self,request):
        if leave_context(request) or handover_context(request):
            return request['status'] != 'applied'
        with self.connection.cursor() as c:
            c.execute("SELECT MAX(id) AS latest FROM scheduling_service_start_requests WHERE case_no=%s AND staff_id=%s AND segment_id<=>%s AND assignment_id<=>%s AND COALESCE(JSON_UNQUOTE(JSON_EXTRACT(execution_dates,'$.kind')),'')NOT IN ('leave-v1','handover-v1') FOR UPDATE",
                (request['case_no'],request['staff_id'],request['segment_id'],request['assignment_id']))
            return c.fetchone()['latest']==request['id']

    def inquire(self, request_id, staff_id, start_date, end_date, version, actor, key):
        self.lock_case(self.request(request_id)['case_no'],(staff_id,))
        request = self.require_pending(request_id, version,prelocked=True)
        context = leave_context(request)
        handover = handover_context(request)
        if handover:
            fresh = load_handover(self, request['case_no'], request['assignment_id'],lock=True)
            dates = fresh.service_dates
            if tuple(handover['dates']) != dates:
                # Dates that have since passed are excluded, but changed formal scope is not guessed.
                if tuple(d for d in handover['dates'] if d >= str(SystemBusinessClock().today())) != dates:
                    raise ServiceStartConflict('handover_stale', '原服務區段已更新，請從案件重新開啟。')
            if str(start_date) != dates[0] or str(end_date) != dates[-1]:
                raise ServiceStartConflict('handover_period_invalid', '換人意願詢問需包含原區段的全部剩餘服務日。')
        if context:
            dates = [date.fromisoformat(item['original_date']) for item in context['dates']]
            if start_date != min(dates) or end_date != max(dates):
                raise ServiceStartConflict('leave_substitute_period_invalid', '代班區段需與本筆請假的原服務日一致。')
        if start_date > end_date or staff_id == request['staff_id']:
            raise ServiceStartConflict('substitute_selection_invalid', '請核對代班人選與服務期間。')
        token = secrets.token_urlsafe(24)
        with self.connection.cursor() as c:
            c.execute("SELECT s.id,b.line_user_id FROM staff s LEFT JOIN staff_lifecycle_states l ON l.staff_id=s.id "
                "JOIN line_identity_role_bindings b ON b.subject_type='staff' AND b.binding_status='bound' "
                'AND b.subject_reference=CAST(s.id AS CHAR CHARACTER SET utf8mb4) COLLATE utf8mb4_unicode_ci '
                "AND b.line_user_id=s.line_user_id WHERE s.id=%s AND s.status='active' AND COALESCE(l.lifecycle_state,'active')='active'", (staff_id,))
            selected = c.fetchone()
            if not selected:
                raise ServiceStartConflict('substitute_binding_required', '請選擇已完成 LINE 綁定的有效月嫂。')
            c.execute('INSERT INTO scheduling_service_start_candidates (request_id,staff_id,proposed_start_date,proposed_end_date,interaction_hash) VALUES (%s,%s,%s,%s,%s)',
                (request_id, staff_id, start_date, end_date, hashlib.sha256(token.encode()).hexdigest()))
            candidate_id = int(c.lastrowid)
            c.execute('UPDATE scheduling_service_start_requests SET selected_candidate_id=%s,aggregate_version=aggregate_version+1 WHERE id=%s', (candidate_id, request_id))
        service_dates = list(dates) if handover else [item['original_date'] for item in context['dates']] if context else None
        inquiry = substitute_inquiry(request['case_no'], start_date, end_date, token, service_dates=service_dates)
        inquiry = configured_message_payload(self.connection, 'service-start-inquiry', inquiry, {'case_no': request['case_no'], 'service_period': '服務日期：'+'、'.join(str(day) for day in service_dates) if service_dates else f'服務期間：{start_date}～{end_date}'})
        self._enqueue(LineRecipientType.USER,selected['line_user_id'], inquiry,
            'service_start_inquiry',str(candidate_id),'inquire:'+key)

    def record_willingness(self, token, line_user_id, willingness, event_key):
        if willingness not in ('willing','unwilling'):
            return False
        with self.connection.cursor() as c:
            c.execute('SELECT c.*,r.case_no,r.status,r.selected_candidate_id FROM scheduling_service_start_candidates c '
                "JOIN scheduling_service_start_requests r ON r.id=c.request_id JOIN orders o ON o.case_no=r.case_no AND o.status IN ('洽談中','訂單成立','服務中') "
                'WHERE c.interaction_hash=%s FOR UPDATE', (hashlib.sha256(token.encode()).hexdigest(),))
            row = c.fetchone()
            if not row or row['selected_candidate_id'] != row['id'] or row['status'] != 'substitute_required':
                return False
            if not self.is_current_request(self.request(row['request_id'],lock=True)):
                return False
            c.execute("SELECT 1 FROM line_identity_role_bindings b JOIN staff s ON s.id=%s AND b.line_user_id=s.line_user_id "
                "WHERE b.subject_type='staff' AND b.subject_reference=CAST(s.id AS CHAR CHARACTER SET utf8mb4) COLLATE utf8mb4_unicode_ci "
                "AND b.binding_status='bound' AND b.line_user_id=%s AND s.status='active' "
                "AND NOT EXISTS (SELECT 1 FROM staff_lifecycle_states lifecycle WHERE lifecycle.staff_id=s.id AND lifecycle.lifecycle_state<>'active')", (row['staff_id'],line_user_id))
            if c.fetchone() is None:
                return False
            if row['willingness'] != 'pending':
                return row['response_event_key'] == event_key
            c.execute('UPDATE scheduling_service_start_candidates SET willingness=%s,response_event_key=%s WHERE id=%s', (willingness,event_key,row['id']))
            c.execute('UPDATE scheduling_service_start_requests SET aggregate_version=aggregate_version+1 WHERE id=%s',(row['request_id'],))
        text = '已收到您願意承接的回覆，後續由工會安排媒合。' if willingness=='willing' else '已收到您無法代班的回覆，謝謝您。'
        self._enqueue(LineRecipientType.USER,line_user_id,{'type':'text','text':text},'service_start_receipt',str(row['id']),'reply:'+event_key)
        return True

    def invite(self, request_id, version, actor, key):
        request = self.require_pending(request_id,version)
        candidate = self.candidate(request,lock=True)
        if not candidate or candidate['willingness']!='willing' or not candidate['line_user_id']:
            raise ServiceStartConflict('substitute_not_willing', '需先收到這位月嫂願意代班的回覆。')
        group = self.group(request['case_no'],lock=True)
        if not group or not group['group_id'] or not group['invitation_url']:
            raise ServiceStartConflict('service_group_not_ready','本案服務群組或邀請網址尚未設定。')
        validate_invitation_url(group['invitation_url'])
        with self.connection.cursor() as c:
            c.execute("SELECT 1 FROM client_deposit_settlement_projection WHERE case_no=%s AND settlement_state='settled'", (request['case_no'],))
            if c.fetchone() is None:
                raise ServiceStartConflict('deposit_required','訂金尚未確認入帳，不能寄送群組邀請。')
            identity = self.invitation_identity(candidate,group)
            c.execute('UPDATE scheduling_service_start_candidates SET invitation_identity=%s WHERE id=%s',(identity,candidate['id']))
            c.execute('UPDATE scheduling_service_start_requests SET aggregate_version=aggregate_version+1 WHERE id=%s',(request_id,))
        self._enqueue(LineRecipientType.USER,candidate['line_user_id'],
            configured_message_payload(self.connection, 'group-invitation-staff', group_invitation_payload(request['case_no'],'月嫂',group['invitation_url']), {'case_no': request['case_no']}), 'service_start_invitation',identity,'invite:'+key)

    @staticmethod
    def invitation_identity(candidate,group):
        digest=fingerprint_payload({'group':group['group_id'],'version':group['aggregate_version'],
            'url':group['invitation_url'],'staff':candidate['staff_id'],'line':candidate['line_user_id']}).value
        return f"{candidate['id']}:{digest}"

    def require_joined_candidate(self,request_id,version):
        request=self.require_pending(request_id,version)
        candidate=self.candidate(request,lock=True)
        if not candidate or candidate['willingness']!='willing' or not self.joined(request,candidate):
            raise ServiceStartConflict('substitute_not_joined','需先確認選定且願意代班的月嫂已加入本案群組。')
        return candidate

    def arrangement_savepoint(self):
        with self.connection.cursor() as c: c.execute('SAVEPOINT service_start_arrangement')

    def record_candidate_date(self,request_id,start_date):
        with self.connection.cursor() as c:
            c.execute("UPDATE scheduling_service_start_requests SET requested_start_date=%s,status='awaiting_peers' WHERE id=%s",(start_date,request_id))

    def rollback_arrangement(self):
        with self.connection.cursor() as c: c.execute('ROLLBACK TO SAVEPOINT service_start_arrangement')

    def mark_substitute_required(self,request_id,error=None):
        with self.connection.cursor() as c:
            c.execute("UPDATE scheduling_service_start_requests SET status='substitute_required',aggregate_version=aggregate_version+1 WHERE id=%s",(request_id,))
            request = self.request(request_id, lock=True)
            context = handover_context(request) or leave_context(request)
            if context:
                context['conflict_message'] = ('接任月嫂的排程有衝突，原排班與帳務尚未變更；請調整交接日或改選月嫂。'
                    if handover_context(request) else '提出的日期有排程衝突，原排班尚未變更；請依雙方重新談妥的日期記錄，或安排代班。')
                c.execute('UPDATE scheduling_service_start_requests SET execution_dates=%s WHERE id=%s', (_json(context), request_id))

    def complete(self,request_id,result,actor,key):
        request=self.request(request_id,lock=True)
        group=self.group(request['case_no'])
        result={**result,'group_record_queued':bool(group and group['group_id']),
                'group_version':int(group['aggregate_version']) if group else None}
        with self.connection.cursor() as c:
            if request['confirmed_version_id']:
                c.execute("UPDATE scheduling_service_start_requests SET status='applied',result_snapshot=%s,aggregate_version=aggregate_version+1 WHERE case_no=%s AND confirmed_version_id=%s AND status='awaiting_peers'",(_json(result),request['case_no'],request['confirmed_version_id']))
            else:
                c.execute("UPDATE scheduling_service_start_requests SET status='applied',result_snapshot=%s,aggregate_version=aggregate_version+1 WHERE id=%s",(_json(result),request_id))
        if group and group['group_id']:
            self._enqueue(LineRecipientType.GROUP,group['group_id'],configured_message_payload(self.connection, 'service-start-result', service_date_record(request['case_no'],result['assignments']), {'case_no': request['case_no'], 'assignments': '\n'.join(item['staff_name']+'：'+'、'.join(item['service_dates']) for item in result['assignments'])}),
                'service_start_schedule',str(request_id),'schedule:'+key)

    def delivery_is_current(self, task):
        """Fresh audience/selection checks immediately before the existing worker sends."""
        source=task.request.source_aggregate_type
        identity=task.request.source_aggregate_identity
        if source not in {'service_start_inquiry','service_start_invitation','service_start_schedule'}:
            return True
        try:
            candidate_id=int(identity.split(':',1)[0])
        except ValueError:
            return False
        if source=='service_start_schedule':
            request=self.request(candidate_id,lock=True)
            group=self.group(request['case_no'],lock=True)
            with self.connection.cursor() as c:
                c.execute('SELECT result_snapshot FROM scheduling_service_start_requests WHERE case_no=%s AND result_snapshot IS NOT NULL ORDER BY updated_at_utc DESC,id DESC LIMIT 1',(request['case_no'],))
                latest=c.fetchone()['result_snapshot']
                result = _decoded(request['result_snapshot']) or {}
                c.execute("SELECT 1 FROM orders WHERE case_no=%s AND status<>'訂單取消' AND actual_start_date=%s FOR UPDATE",(request['case_no'],result.get('actual_start_date')))
                active=bool(c.fetchone())
                c.execute('SELECT a.staff_id,d.work_date FROM case_staff_assignments a '
                    'JOIN scheduling_aggregates g ON g.effective_generation_id=a.generation_id '
                    'JOIN staff_schedule d ON d.assignment_id=a.id AND d.effective_marker=1 AND d.is_work_day=1 '
                    'WHERE a.case_no=%s FOR UPDATE',(request['case_no'],))
                current_dates={(int(row['staff_id']),str(row['work_date'])) for row in c.fetchall()}
                recorded_dates={(int(item['staff_id']),day) for item in result.get('assignments',[]) for day in item['service_dates']}
            return bool(active and current_dates==recorded_dates and request['status']=='applied' and _decoded(request['result_snapshot'])==_decoded(latest) and group
                and (result.get('group_version') is None or result['group_version']==group['aggregate_version'])
                and task.request.recipient.recipient_type is LineRecipientType.GROUP
                and task.request.recipient.identity.value==group['group_id'])
        with self.connection.cursor() as c:
            c.execute('SELECT request_id FROM scheduling_service_start_candidates WHERE id=%s',(candidate_id,))
            row=c.fetchone()
        if not row:
            return False
        request=self.request(row['request_id'],lock=True)
        candidate=self.candidate(request,lock=True)
        with self.connection.cursor() as c:
            c.execute("SELECT 1 FROM orders o JOIN staff s ON s.id=%s LEFT JOIN staff_lifecycle_states l ON l.staff_id=s.id WHERE o.case_no=%s AND o.status IN ('洽談中','訂單成立','服務中') AND s.status='active' AND COALESCE(l.lifecycle_state,'active')='active'",(candidate_id if not candidate else candidate['staff_id'],request['case_no']))
            active=bool(c.fetchone())
            if handover_context(request):
                c.execute('SELECT 1 FROM case_staff_assignments a JOIN scheduling_aggregates g '
                    'ON g.effective_generation_id=a.generation_id JOIN staff_schedule day ON day.assignment_id=a.id '
                    'AND day.effective_marker=1 AND day.is_work_day=1 '
                    'WHERE g.case_no=%s AND a.id=%s AND a.staff_id=%s AND day.work_date>=%s LIMIT 1 FOR UPDATE',
                    (request['case_no'],request['assignment_id'],request['staff_id'],SystemBusinessClock().today()))
                active=active and bool(c.fetchone())
        if (not active or not candidate or candidate['id']!=candidate_id or request['status']!='substitute_required'
                or not self.is_current_request(request)
                or task.request.recipient.recipient_type is not LineRecipientType.USER
                or task.request.recipient.identity.value!=candidate['line_user_id']):
            return False
        if source=='service_start_inquiry':
            return candidate['willingness']=='pending'
        group=self.group(request['case_no'],lock=True)
        with self.connection.cursor() as c:
            c.execute("SELECT 1 FROM client_deposit_settlement_projection WHERE case_no=%s AND settlement_state='settled'",(request['case_no'],))
            settled=bool(c.fetchone())
        return bool(settled and candidate['willingness']=='willing' and group and group['invitation_url']
            and identity==self.invitation_identity(candidate,group))

    def _enqueue(self,recipient_type,identity,body,source,source_id,key):
        recipient=LineUserId(identity) if recipient_type is LineRecipientType.USER else LineGroupId(identity)
        return self.deliveries.enqueue(LineDeliveryRequest(LineRecipient(recipient_type,recipient),
            LineMessageKind.FLEX if body['type']=='flex' else LineMessageKind.TEXT,_json(body),datetime.now(timezone.utc),
            IdempotencyKey(key),CorrelationId('service-start:'+source_id),source,source_id))


_STAFF_CASES = (
    'SELECT o.case_no,o.lifecycle_version,o.service_days,o.start_date,s.name AS staff_name,'
    'p.id AS plan_id,segment.id AS segment_id,assignment.id AS assignment_id,'
    'COALESCE(assignment.assigned_start_date,segment.assigned_start_date) AS segment_start_date,'
    'COALESCE(assignment.assigned_end_date,segment.assigned_end_date) AS segment_end_date '
    'FROM orders o JOIN caregiver_matching_plans p ON p.case_no=o.case_no AND p.is_active=1 '
    'JOIN caregiver_matching_plan_segments segment ON segment.plan_id=p.id '
    'JOIN staff s ON s.id=segment.staff_id '
    'LEFT JOIN scheduling_aggregates aggregate ON aggregate.case_no=o.case_no '
    'LEFT JOIN case_staff_assignments assignment ON assignment.generation_id=aggregate.effective_generation_id '
    'AND assignment.staff_id=s.id '
    "WHERE segment.staff_id=%s AND o.status IN ('洽談中','訂單成立','服務中') "
    "AND COALESCE(assignment.status,'planned') IN ('planned','active') "
    'AND (assignment.id IS NOT NULL OR NOT EXISTS (SELECT 1 FROM case_staff_assignments existing '
    'WHERE existing.generation_id=aggregate.effective_generation_id)) '
    'AND NOT EXISTS (SELECT 1 FROM order_service_data_locks locked WHERE locked.case_no=o.case_no) '
    'UNION SELECT o.case_no,o.lifecycle_version,o.service_days,o.start_date,s.name,NULL,NULL,a.id,a.assigned_start_date,a.assigned_end_date '
    'FROM case_staff_assignments a JOIN scheduling_aggregates aggregate ON aggregate.effective_generation_id=a.generation_id '
    'JOIN orders o ON o.case_no=a.case_no JOIN staff s ON s.id=a.staff_id '
    "WHERE a.staff_id=%s AND a.status IN ('planned','active') AND o.status IN ('訂單成立','服務中') "
    'AND NOT EXISTS (SELECT 1 FROM caregiver_matching_plans p JOIN caregiver_matching_plan_segments ps ON ps.plan_id=p.id '
    'WHERE p.case_no=o.case_no AND p.is_active=1 AND ps.staff_id=a.staff_id) '
    'AND NOT EXISTS (SELECT 1 FROM order_service_data_locks locked WHERE locked.case_no=o.case_no)'
)
