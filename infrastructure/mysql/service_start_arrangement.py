"""Adapt the approved coordination result to existing Orders/Scheduling writers."""

from datetime import date, timedelta
from functools import partial
from dataclasses import replace
import json

from domains.scheduling.assignment_plan import (
    AssignmentPlanIntent, AssignmentPlanSegmentIntent, StaffOccupancyFact, first_shift_conflict, service_shift_may_overlap,
)
from domains.scheduling.commitment_execution import ExecutionServiceDay
from domains.scheduling.generation import AssignmentCandidate, SchedulingGenerationCandidate
from domains.payroll.installments import payroll_installments
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
from infrastructure.mysql.scheduling_occupancy_facts import _unavailability_rows, load_case_service_time, load_occupancy_snapshot
from infrastructure.mysql.order_terms_read_model import load_preview_facts
from shared_kernel.clock import SystemBusinessClock
from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
from infrastructure.mysql.order_actual_start_repository import MySqlOrderActualStartRepository
from infrastructure.mysql.matching_schedule_confirmation_repository import MySqlMatchingScheduleConfirmationRepository
from infrastructure.mysql.service_start_repository import MySqlServiceStartRepository
from subsystems.orders.actual_start_workflow import ActualStartWorkflow
from subsystems.orders.historical_restart_arrangement import HistoricalRestartArrangementReceipt
from subsystems.orders.service_date_confirmation_workflow import ServiceDateConfirmationWorkflow
from subsystems.payroll.terms_impact import calculate_assignment_payroll


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

    def _require_available_days(self, case_no, staff_id, dates, message):
        dates = tuple(dates)
        with self.connection.cursor() as cursor:
            service_time = load_case_service_time(cursor, case_no, lock=True)
            blocks = _unavailability_rows(cursor, (staff_id,), True)
        for row in blocks:
            block = StaffOccupancyFact(
                staff_id, row['start_date'], 'staff_unavailability',
                all_day=True, block_end=row['end_date'],
            )
            if any(service_shift_may_overlap(day, service_time, block) for day in dates):
                raise ServiceStartConflict('staff_unavailable', message)

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
            c.execute('SELECT day.id,day.work_date FROM staff_schedule day '
                'JOIN scheduling_aggregates g ON g.effective_generation_id=day.generation_id '
                'WHERE g.case_no=%s AND day.assignment_id=%s AND day.staff_id=%s '
                'AND day.effective_marker=1 AND day.is_work_day=1 AND day.work_date>=%s '
                'ORDER BY day.work_date FOR UPDATE',
                (request['case_no'],request['assignment_id'],request['staff_id'],start))
            days = c.fetchall()
        if not days:
            raise ServiceStartConflict('handover_dates_missing', '交接日起沒有可接任的原區段服務日，請核對交接日。')
        self._require_available_days(
            request['case_no'], candidate['staff_id'], (day['work_date'] for day in days),
            '接任月嫂在交接後有不可排班紀錄。',
        )
        # The formal handover writer owns all remaining days, paid-history preservation and accounting.
        intent = LeaveSubstitutionBatchIntent(request['assignment_id'], tuple(LeaveSubstitutionItem(
            day['id'],day['work_date'],LeaveResolutionType.SUBSTITUTE,candidate['staff_id'])
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
            c.execute('SELECT day.id,day.assignment_id,day.work_date FROM staff_schedule day '
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
        self._require_available_days(request['case_no'], staff_id, replacements, '新的服務日期有不可排班紀錄。')
        intent = LeaveSubstitutionBatchIntent(rows[originals[0]]['assignment_id'], tuple(
            LeaveSubstitutionItem(rows[old]['id'], old,
                LeaveResolutionType.SUBSTITUTE if candidate else LeaveResolutionType.DEFER_FOLLOWING_ASSIGNMENTS,
                candidate['staff_id'] if candidate else None,
                False,
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
            service_type=c.fetchone()['service_type']
            if service_type is None or not service_type.strip():
                raise ServiceStartConflict('service_start_service_type_required',
                    '本案尚未設定服務方式，請聯絡工會補齊資料後再送出。')
            mode=_canonical_service_mode(service_type)
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
            self._require_available_days(request['case_no'], staff_id, dates, '服務時段有不可排班紀錄，需由工會安排代班。')
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
            c.execute('SELECT day.id,day.work_date FROM staff_schedule day '
                'JOIN scheduling_aggregates g ON g.effective_generation_id=day.generation_id '
                'WHERE day.assignment_id=%s AND day.effective_marker=1 AND day.is_work_day=1 '
                'AND day.work_date BETWEEN %s AND %s ORDER BY day.work_date FOR UPDATE',
                (request['assignment_id'],start,candidate['proposed_end_date']))
            days=c.fetchall()
        if not days:
            raise ServiceStartConflict('substitute_dates_missing','指定區段沒有可替代的正式服務日，請重新核對。')
        intent=LeaveSubstitutionBatchIntent(request['assignment_id'],tuple(LeaveSubstitutionItem(
            row['id'],row['work_date'],LeaveResolutionType.SUBSTITUTE,candidate['staff_id']) for row in days))
        preview=self.leave.preview(LeaveSubstitutionPreviewRequest(request['case_no'],intent,cid))
        self.leave.apply_in_current_unit_of_work(LeaveSubstitutionApplyRequest(request['case_no'],intent,
            ExpectedVersion(preview.order_version),ExpectedVersion(preview.scheduling_version),
            ExpectedVersion(preview.client_finance_version),ExpectedVersion(preview.payroll_version),
            preview.fingerprint,IdempotencyKey('start-substitute:'+key),actor,'工會記錄已加入群組的代班服務日期',cid))


def current_service_start_execution(cursor,case_no,plan_id=None,*,lock=False):
    """Current explicit results, never legacy date-card confirmation events."""
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


def _require_office_assignment_ownership(cursor, case_no, *, lock):
    cursor.execute(
        "SELECT a.id FROM case_staff_assignments a "
        "LEFT JOIN scheduling_aggregates g ON g.case_no=a.case_no "
        "WHERE a.case_no=%s AND a.status IN ('planned','active','completed') "
        "AND (a.generation_id IS NULL OR NOT (a.generation_id <=> g.effective_generation_id))"
        + (" FOR UPDATE" if lock else ""),
        (case_no,),
    )
    if cursor.fetchone() is not None:
        raise ValueError("office_schedule_assignment_ownership_blocked")


def preview_office_schedule(connection, case_no, segments, *, actual_start_date, reason, lock=False):
    with connection.cursor() as cursor:
        facts = load_preview_facts(cursor, case_no, office_first_schedule=True)
        dates = tuple(day for segment in segments for day in segment.service_dates)
        staff_ids = tuple(segment.staff_id for segment in segments)
        if (facts.lifecycle.current_status.value != '訂單成立' or facts.order.service_data_locked
                or any(item.official_service_dates for item in facts.scheduling.segments)):
            raise ValueError('office_schedule_not_pending_blocked')
        _require_office_assignment_ownership(cursor, case_no, lock=lock)
        if (len(dates) != facts.order.terms.service_days or dates != tuple(sorted(set(dates)))
                or not dates or dates[0] < actual_start_date):
            raise ValueError('office_schedule_dates_invalid')
        if len(set(staff_ids)) != len(staff_ids):
            raise ValueError('office_schedule_segments_invalid')
        existing = {item.staff_id: item.assignment_id for item in facts.scheduling.segments}
        assignments = tuple(AssignmentCandidate(
            f'office-preview:{index}', existing.get(segment.staff_id), segment.staff_id, index,
            segment.service_dates[0], segment.service_dates[-1], segment.service_dates,
            len(segment.service_dates) * float(facts.order.terms.service_hours_per_day),
        ) for index, segment in enumerate(segments, start=1))
        candidate = SchedulingGenerationCandidate(
            case_no, facts.scheduling.generation_number + 1, facts.scheduling.aggregate_version,
            facts.scheduling.aggregate_version + 1, tuple(existing.values()), assignments, (),
        )
        occupied, _ = load_occupancy_snapshot(cursor, tuple(sorted(staff_ids)), case_no, lock=lock)
        conflict = first_shift_conflict(case_no, load_case_service_time(cursor, case_no, lock=lock), assignments, occupied)
        if conflict:
            raise ServiceStartConflict('office_schedule_occupancy_conflict',
                                       f'月嫂 {conflict.staff_id} 在 {conflict.occupancy_date} 有檔期衝突。')
        if facts.payroll is None:
            raise ValueError('payroll_bootstrap_required')
        payroll = calculate_assignment_payroll(facts.payroll, candidate, facts.order.terms)
        amounts = [
            {'staff_id': item.staff_id, 'amount_ntd': item.total_payable.amount,
             'funding': [{'kind': part.funding_kind, 'amount_ntd': part.amount}
                         for part in payroll_installments(item, dates[-1])]} for item in payroll.assignments
        ]
        fingerprint = fingerprint_payload({
            'case_no': case_no, 'order_version': facts.order.version,
            'scheduling_version': facts.scheduling.aggregate_version, 'payroll_version': facts.payroll.payroll_version,
            'start': actual_start_date.isoformat(), 'reason': reason.strip(),
            'segments': [(item.staff_id, tuple(d.isoformat() for d in item.service_dates)) for item in assignments],
            'payroll': payroll.fingerprint.value,
        })
    return {'preview_fingerprint': fingerprint.value, 'staff_entitlements': amounts}


def save_office_schedule(
    connection, assignment_application_factory, case_no, segments, *, actual_start_date, expected_order_version,
    expected_scheduling_version, expected_confirmed_version, idempotency_key, actor,
    reason, correlation_id, preview_fingerprint=None,
):
    reallocation_reason = reason.strip() if preview_fingerprint else ""
    reason = reason.strip() or "工會確認服務日期並建立正式班表"
    key = IdempotencyKey(idempotency_key)
    who = ActorContext(actor)
    cid = CorrelationId(correlation_id)
    dates = tuple(day for segment in segments for day in segment.service_dates)
    digest = fingerprint_payload({
        "case": case_no, "start": str(actual_start_date), "actor": actor, "reason": reason,
        "versions": (expected_order_version, expected_scheduling_version, expected_confirmed_version),
        "segments": [(segment.staff_id, tuple(map(str, segment.service_dates))) for segment in segments],
        **({"preview_fingerprint": preview_fingerprint} if preview_fingerprint else {}),
    }).value
    from infrastructure.mysql.service_date_confirmation_repository import MySqlServiceDateConfirmationRepository

    date_repository = MySqlServiceDateConfirmationRepository(connection)
    actual_repository = MySqlOrderActualStartRepository(connection, office_first_schedule=True)
    units = partial(MySqlUnitOfWork, connection)
    date_workflow = ServiceDateConfirmationWorkflow(
        date_repository, units, MySqlMatchingScheduleConfirmationRepository(connection),
    )
    actual_workflow = ActualStartWorkflow(actual_repository, units, SystemBusinessClock())
    if not dates or dates != tuple(sorted(set(dates))) or dates[0] < actual_start_date:
        raise ValueError("office_schedule_dates_invalid")
    if len({segment.staff_id for segment in segments}) != len(segments):
        raise ValueError("office_schedule_segments_invalid")

    with units() as unit:
        MySqlServiceStartRepository(connection).lock_case(case_no, tuple(segment.staff_id for segment in segments))
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT e.payload FROM precontract_service_commitment_events e "
                "JOIN precontract_service_commitments c ON c.id=e.commitment_id "
                "WHERE c.case_no=%s AND e.event_type='converted' "
                "AND JSON_UNQUOTE(JSON_EXTRACT(e.payload,'$.office_command_key'))=%s FOR UPDATE",
                (case_no, key.value),
            )
            replay = cursor.fetchone()
        if replay:
            payload = replay["payload"]
            payload = json.loads(payload) if isinstance(payload, str) else payload
            if payload["office_command_fingerprint"] != digest:
                raise ValueError("office_schedule_idempotency_conflict")
            current = assignment_application_factory(connection).query(case_no).assignment_plan
            if {a.assignment_id for a in current.effective_assignments} != set(payload["assignment_ids"]):
                raise ValueError("office_schedule_result_stale")
            return HistoricalRestartArrangementReceipt(
                case_no, current.scheduling_version, current.scheduling_generation,
                tuple(payload["assignment_ids"]), PreviewFingerprint(payload["preview_fingerprint"]),
            )
        facts = date_repository.load(case_no, lock=True)
        if (facts.order_version, facts.scheduling_version, facts.current_version) != (
            expected_order_version, expected_scheduling_version, expected_confirmed_version,
        ):
            raise ValueError("office_schedule_stale_version")
        if preview_fingerprint is not None and preview_office_schedule(
            connection, case_no, segments, actual_start_date=actual_start_date, reason=reallocation_reason, lock=True,
        )["preview_fingerprint"] != preview_fingerprint:
            raise ValueError("office_schedule_stale_version")
        current = assignment_application_factory(connection).query(case_no).assignment_plan
        if facts.restart_generation_number is not None or any(a.official_service_dates for a in current.effective_assignments):
            raise ValueError("office_schedule_not_pending_blocked")
        if preview_fingerprint is None:
            with connection.cursor() as cursor:
                _require_office_assignment_ownership(cursor, case_no, lock=True)
        staff_ids = {segment.staff_id for segment in segments}
        if (current.effective_assignments and {a.staff_id for a in current.effective_assignments} != staff_ids
                and not reallocation_reason):
            raise ValueError("office_schedule_incumbent_conflict")
        start = actual_repository.load_actual_start_query(case_no, for_update=True)
        if start.service_data_locked:
            raise ValueError("office_schedule_locked_blocked")
        if start.current_actual_start_date != actual_start_date:
            if start.has_formal_assignments:
                raise ValueError("office_schedule_existing_start_conflict")
            preview = actual_workflow.preview_date_only(start, actual_start_date)
            actual_workflow.apply_date_only_in_current_unit_of_work(ActualStartDateOnlyApplyRequest(
                case_no, actual_start_date, ExpectedVersion(start.order_version), preview.fingerprint, cid,
            ))
            facts = date_repository.load(case_no, lock=True)
        if facts.current_version is None or facts.current_dates != dates or facts.current_confirmed_order_version != facts.order_version:
            preview = date_workflow.preview_from_facts(facts, dates)
            date_workflow.apply_in_current_unit_of_work(
                case_no, dates, expected_order_version=facts.order_version,
                expected_scheduling_version=facts.scheduling_version, preview_fingerprint=preview.candidate.fingerprint.value,
                actor=actor, reason=reason, idempotency_key=f"office-dates:{digest}", reserve_waiting_deposit=False,
            )

        def execution(cursor, requested_case, plan_id, *, lock):
            if requested_case != case_no:
                raise ValueError("office_schedule_case_conflict")
            cursor.execute(
                "SELECT p.id, v.id AS version_id FROM caregiver_matching_plans p "
                "JOIN precontract_service_commitments c ON c.matching_plan_id=p.id AND c.case_no=p.case_no "
                "JOIN confirmed_service_date_versions v ON v.case_no=p.case_no AND v.is_current=1 "
                "JOIN orders o ON o.case_no=p.case_no AND o.status='訂單成立' "
                "WHERE p.case_no=%s AND p.is_active=1 AND p.status IN ('proposed','accepted') "
                "AND EXISTS (SELECT 1 FROM order_contract_flow_events e WHERE e.case_no=o.case_no AND e.event_type='contract_completed')"
                + (" FOR UPDATE" if lock else ""), (case_no,),
            )
            matches = cursor.fetchall()
            if len(matches) != 1 or (plan_id is not None and matches[0]["id"] != plan_id):
                raise ValueError("office_schedule_commitment_blocked")
            match = matches[0]
            return {
                "substitutions": {}, "service_start_response_ids": (), "confirmed_version_id": match["version_id"],
                "office_command_key": key.value, "office_command_fingerprint": digest,
                "office_reallocation_reason": reallocation_reason,
            }, tuple(ExecutionServiceDay(segment.staff_id, day) for segment in segments for day in segment.service_dates)

        interval_start = actual_start_date
        intents = []
        for segment in segments:
            interval_end = segment.service_dates[-1]
            intents.append(AssignmentPlanSegmentIntent(segment.staff_id, interval_start, interval_end, segment.service_dates))
            interval_start = interval_end + timedelta(days=1)
        intent = AssignmentPlanIntent(tuple(intents))
        workflow = assignment_application_factory(connection, office_execution=execution).workflow
        preview = workflow.preview(AssignmentPlanPreviewRequest(case_no, intent, cid))
        receipt = workflow.apply_in_current_unit_of_work(AssignmentPlanApplyRequest(
            case_no, intent, ExpectedVersion(preview.order_version), ExpectedVersion(preview.scheduling_version),
            ExpectedVersion(preview.client_finance_version), ExpectedVersion(preview.payroll_version),
            preview.fingerprint, IdempotencyKey(f"office-schedule:{digest}"), who, reason, cid,
        ))
        observed = workflow.query(case_no).assignment_plan
        if {a.staff_id: a.official_service_dates for a in observed.effective_assignments} != {
            segment.staff_id: segment.service_dates for segment in segments
        } or len(observed.effective_assignments) != len(segments):
            raise ValueError("office_schedule_result_conflict")
        unit.commit()
        return HistoricalRestartArrangementReceipt(
            case_no, receipt.scheduling_version, receipt.scheduling_generation,
            tuple(a.assignment_id for a in observed.effective_assignments), receipt.preview_fingerprint,
        )
