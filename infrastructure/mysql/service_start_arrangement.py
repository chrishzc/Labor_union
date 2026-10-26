"""Adapt the approved coordination result to existing Orders/Scheduling writers."""

from datetime import date
from dataclasses import replace
import json

from domains.scheduling.assignment_plan import AssignmentPlanIntent, AssignmentPlanSegmentIntent
from domains.scheduling.leave_substitution import LeaveResolutionType, LeaveSubstitutionBatchIntent, LeaveSubstitutionItem
from domains.scheduling.service_start import ServiceStartConflict
from infrastructure.mysql.automatic_client_accounting import synchronize_client_charges
from infrastructure.mysql.historical_actual_start_date_planner import _canonical_service_mode
from infrastructure.mysql.mysql_adapter import calculate_attendance_schedule
from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
from subsystems.orders.actual_start_workflow import ActualStartApplyRequest, ActualStartDateOnlyApplyRequest
from subsystems.scheduling.assignment_plan_workflow import AssignmentPlanApplyRequest, AssignmentPlanPreviewRequest
from subsystems.scheduling.leave_substitution_workflow import LeaveSubstitutionApplyRequest, LeaveSubstitutionPreviewRequest
from infrastructure.mysql.leave_result_repository import leave_context
from infrastructure.mysql.service_handover_repository import handover_context
from shared_kernel.clock import SystemBusinessClock


class MySqlServiceStartArrangement:
    def __init__(self, repository, actual_start, service_dates, assignments, leave):
        self.repository = repository
        self.connection = repository.connection
        self.actual_start, self.service_dates = actual_start, service_dates
        self.assignments, self.leave = assignments, leave

    @staticmethod
    def is_occupancy_conflict(error):
        typed = getattr(error, 'error', None)
        codes = {getattr(typed, 'code', ''),getattr(error,'code',''), str(error)} | set(getattr(typed, 'domain_blockers', ()))
        return bool(codes & {'staff_occupancy_conflict', 'actual_start_staff_schedule_conflict',
            'service_ownership_conflict', 'scheduling.staff_effective_date_conflict',
            'availability_lock_staff_occupancy_conflict', 'staff_unavailable', 'actual_start_unavailability_conflict',
            'automatic_waiting_deposit_occupancy_conflict'})

    def apply(self, request_id, start_date, actor, key):
        request = self.repository.request(request_id, lock=True)
        candidate = self.repository.candidate(request, lock=True)
        cid, who = CorrelationId('service-start:'+key), ActorContext(actor)
        context = leave_context(request)
        query = self.actual_start._repository.load_actual_start_query(request['case_no'], for_update=True)
        if handover_context(request):
            self._handover(request, candidate, start_date, who, cid, key)
        elif context:
            self._leave_result(request, context, candidate, who, cid, key)
        elif query.has_formal_assignments:
            if candidate:
                self._substitute(request, candidate, start_date, who, cid, key)
            else:
                preview = self.actual_start.preview(request['case_no'], start_date)
                self.actual_start.apply_in_current_unit_of_work(ActualStartApplyRequest(
                    request['case_no'], start_date, ExpectedVersion(preview.order_version),
                    ExpectedVersion(preview.scheduling_version), preview.fingerprint,
                    IdempotencyKey('start-date:'+key), who, '', cid))
        else:
            if not self._initial(request, start_date, who, cid, key):
                return None
        with self.connection.cursor() as c:
            synchronize_client_charges(c, request['case_no'], actor=who, key=IdempotencyKey('start-finance:'+key),
                correlation_id=cid, source_family='service_start', source_id=str(request_id))
            c.execute('SELECT o.actual_start_date,o.actual_end_date,o.lifecycle_version,t.first_payment_due_date '
                'FROM orders o JOIN client_payment_terms t ON t.case_no=o.case_no WHERE o.case_no=%s', (request['case_no'],))
            order=c.fetchone()
            c.execute('SELECT a.staff_id,s.name,day.work_date FROM case_staff_assignments a '
                'JOIN scheduling_aggregates g ON g.effective_generation_id=a.generation_id '
                'JOIN staff s ON s.id=a.staff_id JOIN staff_schedule day ON day.assignment_id=a.id '
                'AND day.effective_marker=1 AND day.is_work_day=1 WHERE a.case_no=%s ORDER BY a.assignment_sequence,day.work_date', (request['case_no'],))
            rows=c.fetchall()
        staff={}
        for row in rows:
            staff.setdefault(row['staff_id'],{'staff_id':row['staff_id'],'staff_name':row['name'],'service_dates':[]})['service_dates'].append(str(row['work_date']))
        return {'actual_start_date':str(order['actual_start_date']), 'actual_end_date':str(order['actual_end_date']),
            'order_version':int(order['lifecycle_version']), 'first_payment_due_date':str(order['first_payment_due_date']),
            'assignments':list(staff.values())}

    def _handover(self, request, candidate, start, actor, cid, key):
        if not candidate:
            raise ServiceStartConflict('substitute_selection_required', '請先選定接任月嫂。')
        if start < SystemBusinessClock().today():
            raise ServiceStartConflict('handover_date_in_past', '交接日不可早於今天。')
        with self.connection.cursor() as c:
            c.execute('SELECT day.id,day.work_date,day.is_double_pay FROM staff_schedule day '
                'JOIN scheduling_aggregates g ON g.effective_generation_id=day.generation_id '
                'WHERE g.case_no=%s AND day.assignment_id=%s AND day.staff_id=%s '
                'AND day.effective_marker=1 AND day.is_work_day=1 AND day.work_date>=%s '
                'ORDER BY day.work_date FOR UPDATE',
                (request['case_no'],request['assignment_id'],request['staff_id'],start))
            days = c.fetchall()
        if not days:
            raise ServiceStartConflict('handover_dates_missing', '交接日起沒有可接任的原區段服務日，請核對交接日。')
        with self.connection.cursor() as c:
            c.execute("SELECT start_date,end_date FROM scheduling_staff_unavailability_blocks WHERE staff_id=%s "
                "AND status='effective' AND start_date<=%s AND (end_date IS NULL OR end_date>=%s) FOR UPDATE",
                (candidate['staff_id'],days[-1]['work_date'],days[0]['work_date']))
            if any(block['start_date'] <= day['work_date'] and (block['end_date'] is None or day['work_date'] <= block['end_date'])
                   for block in c.fetchall() for day in days):
                raise ServiceStartConflict('staff_unavailable', '接任月嫂在交接後有不可排班紀錄。')
        # The formal handover writer owns all remaining days, paid-history preservation and accounting.
        intent = LeaveSubstitutionBatchIntent(request['assignment_id'], tuple(LeaveSubstitutionItem(
            day['id'],day['work_date'],LeaveResolutionType.SUBSTITUTE,candidate['staff_id'],bool(day['is_double_pay']))
            for day in days), handover_date=start)
        preview = self.leave.preview(LeaveSubstitutionPreviewRequest(request['case_no'],intent,cid))
        self.leave.apply_in_current_unit_of_work(LeaveSubstitutionApplyRequest(request['case_no'],intent,
            ExpectedVersion(preview.order_version),ExpectedVersion(preview.scheduling_version),
            ExpectedVersion(preview.client_finance_version),ExpectedVersion(preview.payroll_version),
            preview.fingerprint,IdempotencyKey('handover:'+key),actor,'工會記錄雙方已協調的服務中換人交接日',cid))

    def _leave_result(self, request, context, candidate, actor, cid, key):
        dates = context['dates']
        originals = tuple(date.fromisoformat(item['original_date']) for item in dates)
        replacements = tuple(date.fromisoformat(item['new_date']) if item['new_date'] else None for item in dates)
        today = SystemBusinessClock().today()
        if any(day < today for day in originals) or any(day is None or day < today for day in replacements):
            raise ServiceStartConflict('leave_result_past_service', '已完成的服務日不可由請假流程變更，請重新核對日期。')
        with self.connection.cursor() as c:
            c.execute('SELECT day.id,day.assignment_id,day.work_date,day.is_double_pay FROM staff_schedule day '
                'JOIN scheduling_aggregates g ON g.effective_generation_id=day.generation_id '
                'WHERE g.case_no=%s AND day.staff_id=%s AND day.effective_marker=1 AND day.is_work_day=1 '
                'AND day.work_date BETWEEN %s AND %s ORDER BY day.work_date FOR UPDATE',
                (request['case_no'],request['staff_id'],min(originals),max(originals)))
            rows = {row['work_date']:row for row in c.fetchall()}
        if any(day not in rows for day in originals) or len({rows[day]['assignment_id'] for day in originals}) != 1:
            raise ServiceStartConflict('leave_result_dates_changed', '原服務日或服務月嫂已變更，請重新查詢排班。')
        if context['decision'] == 'substitute' and candidate is None:
            raise ServiceStartConflict('substitute_selection_required', '請先選定願意代班且已加入案件群組的月嫂。')
        staff_id = candidate['staff_id'] if candidate else request['staff_id']
        with self.connection.cursor() as c:
            c.execute("SELECT start_date,end_date FROM scheduling_staff_unavailability_blocks WHERE staff_id=%s "
                "AND status='effective' AND start_date<=%s AND (end_date IS NULL OR end_date>=%s) FOR UPDATE",
                (staff_id,max(replacements),min(replacements)))
            if any(block['start_date'] <= day and (block['end_date'] is None or day <= block['end_date'])
                   for block in c.fetchall() for day in replacements):
                raise ServiceStartConflict('staff_unavailable', '新的服務日期有不可排班紀錄。')
        intent = LeaveSubstitutionBatchIntent(rows[originals[0]]['assignment_id'], tuple(
            LeaveSubstitutionItem(rows[old]['id'], old,
                LeaveResolutionType.SUBSTITUTE if candidate else LeaveResolutionType.DEFER_FOLLOWING_ASSIGNMENTS,
                candidate['staff_id'] if candidate else None,
                bool(rows[old]['is_double_pay']) if candidate else False,
                new if new != old else None) for old,new in zip(originals,replacements)))
        preview = self.leave.preview(LeaveSubstitutionPreviewRequest(request['case_no'],intent,cid))
        self.leave.apply_in_current_unit_of_work(LeaveSubstitutionApplyRequest(request['case_no'],intent,
            ExpectedVersion(preview.order_version),ExpectedVersion(preview.scheduling_version),
            ExpectedVersion(preview.client_finance_version),ExpectedVersion(preview.payroll_version),
            preview.fingerprint,IdempotencyKey('leave-result:'+key),actor,'記錄雙方已協調的請假結果',cid))

    def _initial(self, request, start_date, actor, cid, key):
        with self.connection.cursor() as c:
            c.execute('SELECT ps.id,ps.staff_id,ps.segment_order,COUNT(day.id) AS service_days '
                'FROM caregiver_matching_plan_segments ps JOIN precontract_service_commitments commitment '
                'ON commitment.matching_plan_id=ps.plan_id JOIN precontract_service_commitment_days day '
                'ON day.commitment_id=commitment.id AND day.staff_id=ps.staff_id '
                'WHERE ps.plan_id=%s GROUP BY ps.id,ps.staff_id,ps.segment_order ORDER BY ps.segment_order', (request['plan_id'],))
            segments=c.fetchall()
            if not segments:
                raise ServiceStartConflict('commitment_required','本案尚未完成正式簽約資料，無法建立排班。')
            c.execute('SELECT r.* FROM scheduling_service_start_requests r WHERE r.case_no=%s AND r.plan_id=%s '
                'AND r.id=(SELECT MAX(latest.id) FROM scheduling_service_start_requests latest '
                "WHERE latest.case_no=r.case_no AND latest.segment_id=r.segment_id AND COALESCE(JSON_UNQUOTE(JSON_EXTRACT(latest.execution_dates,'$.kind')),'')NOT IN ('leave-v1','handover-v1')) FOR UPDATE", (request['case_no'],request['plan_id']))
            responses={row['segment_id']:row for row in c.fetchall()}
            c.execute('SELECT c.service_type FROM orders o JOIN clients c ON c.id=o.client_id WHERE o.case_no=%s', (request['case_no'],))
            mode=_canonical_service_mode(c.fetchone()['service_type'])
        intents=[]
        for segment in segments:
            response=responses.get(segment['id'])
            if response is None or response['source_order_version']!=request['source_order_version']:
                return False
            replacement=self.repository.candidate(response,lock=True)
            if response['id']==request['id']:
                day=start_date
            elif (response['decision']=='accepted' or replacement) and response['status']=='awaiting_peers':
                day=response['requested_start_date']
            else:
                return False
            if replacement:
                if replacement['willingness']!='willing' or not self.repository.joined(response,replacement):
                    return False
                staff_id=replacement['staff_id']
            else:
                if response['decision']!='accepted':
                    return False
                staff_id=segment['staff_id']
            calendar=calculate_attendance_schedule(day,int(segment['service_days']),mode)
            dates=tuple(item['date'] if isinstance(item['date'],date) else date.fromisoformat(str(item['date']))
                for item in calendar['day_by_day'] if item['is_work_day'])
            with self.connection.cursor() as c:
                c.execute("SELECT start_date,end_date FROM scheduling_staff_unavailability_blocks WHERE staff_id=%s AND status='effective' AND start_date<=%s AND (end_date IS NULL OR end_date>=%s) FOR UPDATE",(staff_id,dates[-1],day))
                if any(block['start_date']<=dates[-1] and (block['end_date'] is None or block['end_date']>=day) for block in c.fetchall()):
                    raise ServiceStartConflict('staff_unavailable','服務期間有不可排班紀錄，需由工會安排代班。')
            intents.append(AssignmentPlanSegmentIntent(int(staff_id),day,dates[-1],dates))
        start=min(item.assigned_start_date for item in intents)
        facts=self.actual_start._repository.load_actual_start_query(request['case_no'],for_update=True)
        preview=self.actual_start.preview_date_only(facts,start)
        self.actual_start.apply_date_only_in_current_unit_of_work(ActualStartDateOnlyApplyRequest(
            request['case_no'],start,ExpectedVersion(facts.order_version),preview.fingerprint,cid))
        all_dates=tuple(sorted(day for item in intents for day in item.official_service_dates))
        preview=self.service_dates.preview(request['case_no'],all_dates)
        dates=self.service_dates.apply_in_current_unit_of_work(request['case_no'],all_dates,
            expected_order_version=preview.candidate.order_version,
            expected_scheduling_version=preview.candidate.scheduling_version,
            preview_fingerprint=preview.candidate.fingerprint.value,actor=actor.actor_id,reason='',idempotency_key='start-calendar:'+key,
            reserve_waiting_deposit=False)
        with self.connection.cursor() as c:
            c.execute('SELECT id FROM confirmed_service_date_versions WHERE case_no=%s AND is_current=1',(request['case_no'],))
            version_id=c.fetchone()['id']
            for segment,intent in zip(segments,intents):
                response=responses[segment['id']]
                payload=[{'staff_id':intent.staff_id,'start_date':str(intent.assigned_start_date),
                    'dates':[str(d) for d in intent.official_service_dates]}]
                c.execute("UPDATE scheduling_service_start_requests SET execution_dates=%s,confirmed_version_id=%s,status='awaiting_peers' WHERE id=%s",
                    (json.dumps(payload),version_id,response['id']))
        intent=AssignmentPlanIntent(tuple(intents))
        preview=self.assignments.preview(AssignmentPlanPreviewRequest(request['case_no'],intent,cid))
        self.assignments.apply_in_current_unit_of_work(AssignmentPlanApplyRequest(request['case_no'],intent,
            ExpectedVersion(preview.order_version),ExpectedVersion(preview.scheduling_version),
            ExpectedVersion(preview.client_finance_version),ExpectedVersion(preview.payroll_version),
            preview.fingerprint,IdempotencyKey('start-assignment:'+key),actor,'月嫂回報雙方協調結果，自動建立正式排班',cid))
        return True

    def _substitute(self,request,candidate,start,actor,cid,key):
        with self.connection.cursor() as c:
            c.execute('SELECT day.id,day.work_date,day.is_double_pay FROM staff_schedule day '
                'JOIN scheduling_aggregates g ON g.effective_generation_id=day.generation_id '
                'WHERE day.assignment_id=%s AND day.effective_marker=1 AND day.is_work_day=1 '
                'AND day.work_date BETWEEN %s AND %s ORDER BY day.work_date FOR UPDATE',
                (request['assignment_id'],start,candidate['proposed_end_date']))
            days=c.fetchall()
        if not days:
            raise ServiceStartConflict('substitute_dates_missing','指定區段沒有可替代的正式服務日，請重新核對。')
        intent=LeaveSubstitutionBatchIntent(request['assignment_id'],tuple(LeaveSubstitutionItem(
            row['id'],row['work_date'],LeaveResolutionType.SUBSTITUTE,candidate['staff_id'],bool(row['is_double_pay'])) for row in days))
        preview=self.leave.preview(LeaveSubstitutionPreviewRequest(request['case_no'],intent,cid))
        self.leave.apply_in_current_unit_of_work(LeaveSubstitutionApplyRequest(request['case_no'],intent,
            ExpectedVersion(preview.order_version),ExpectedVersion(preview.scheduling_version),
            ExpectedVersion(preview.client_finance_version),ExpectedVersion(preview.payroll_version),
            preview.fingerprint,IdempotencyKey('start-substitute:'+key),actor,'工會記錄已加入群組的代班服務日期',cid))


def current_service_start_execution(cursor,case_no,plan_id=None,*,lock=False):
    """Current explicit results, never legacy date-card confirmation events."""
    from domains.scheduling.commitment_execution import ExecutionServiceDay
    suffix=' FOR UPDATE' if lock else ''
    cursor.execute('SELECT r.id,r.staff_id,r.selected_candidate_id,r.execution_dates,r.confirmed_version_id '
        'FROM scheduling_service_start_requests r JOIN confirmed_service_date_versions v '
        'ON v.id=r.confirmed_version_id AND v.is_current=1 '
        "WHERE r.case_no=%s AND r.status IN ('awaiting_peers','applied') AND r.execution_dates IS NOT NULL "
        'AND (%s IS NULL OR r.plan_id=%s) '
        'AND r.id=(SELECT MAX(latest.id) FROM scheduling_service_start_requests latest '
        "WHERE latest.case_no=r.case_no AND latest.segment_id<=>r.segment_id AND latest.staff_id=r.staff_id AND COALESCE(JSON_UNQUOTE(JSON_EXTRACT(latest.execution_dates,'$.kind')),'')NOT IN ('leave-v1','handover-v1'))"+suffix,
        (case_no,plan_id,plan_id))
    rows=cursor.fetchall()
    if not rows:
        raise ValueError('service_start_result_required')
    days=[]; substitutions={}
    for row in rows:
        payload=json.loads(row['execution_dates']) if isinstance(row['execution_dates'],str) else row['execution_dates']
        for item in payload:
            days.extend(ExecutionServiceDay(int(item['staff_id']),date.fromisoformat(value)) for value in item['dates'])
            if int(item['staff_id'])!=row['staff_id']:
                if row['selected_candidate_id'] is None:
                    raise ValueError('service_start_substitute_invalid')
                cursor.execute("SELECT staff_id FROM scheduling_service_start_candidates WHERE id=%s AND willingness='willing'"+suffix,(row['selected_candidate_id'],))
                selected=cursor.fetchone()
                if not selected or selected['staff_id']!=int(item['staff_id']):
                    raise ValueError('service_start_substitute_invalid')
                substitutions[row['staff_id']]=int(item['staff_id'])
    return {'service_start_response_ids':[row['id'] for row in rows],
        'confirmed_version_id':rows[0]['confirmed_version_id'],'substitutions':substitutions},tuple(days)
