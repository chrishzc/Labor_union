"""
File: service_start_arrangement.py
Description: 轉接服務開始、請假順延與換人協調結果至 Orders 與 Scheduling 正式寫入器。
"""

from datetime import date, timedelta
from functools import partial
from dataclasses import replace
import json

from domains.scheduling.assignment_plan import (
    AssignmentPlanIntent, AssignmentPlanSegmentIntent, StaffOccupancyFact, first_shift_conflict, service_shift_may_overlap,
)
from domains.scheduling.commitment_execution import (
    CommitmentExecutionMismatch, CommitmentServiceDay, ExecutionServiceDay, require_exact_commitment_execution,
)
from domains.scheduling.generation import AssignmentCandidate, SchedulingGenerationCandidate
from domains.payroll.installments import payroll_installments
from domains.scheduling.leave_substitution import LeaveResolutionType, LeaveSubstitutionBatchIntent, LeaveSubstitutionItem
from domains.scheduling.service_start import ServiceStartConflict
from infrastructure.mysql.automatic_client_accounting import synchronize_client_charges
from infrastructure.mysql.assignment_plan_repository import (
    _locked_waiting_lock_plan_ids, _require_exact_commitment_days, _require_retired_staff_assignment_preservation,
)
from infrastructure.mysql.historical_actual_start_date_planner import _canonical_service_mode
from infrastructure.mysql.mysql_adapter import calculate_attendance_schedule
from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
from subsystems.orders.actual_start_workflow import ActualStartApplyRequest, ActualStartDateOnlyApplyRequest
from subsystems.scheduling.assignment_plan_workflow import AssignmentPlanApplyRequest, AssignmentPlanPreviewRequest
from subsystems.scheduling.leave_substitution_workflow import LeaveSubstitutionApplyRequest, LeaveSubstitutionPreviewRequest
from infrastructure.mysql.leave_result_repository import leave_context
from infrastructure.mysql.service_handover_repository import handover_context
from infrastructure.mysql.scheduling_occupancy_facts import _unavailability_rows, load_case_service_time, load_occupancy_snapshot
from infrastructure.mysql.order_terms_read_model import load_preview_facts, preflight_staff_ids
from shared_kernel.clock import SystemBusinessClock
from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
from infrastructure.mysql.order_actual_start_repository import MySqlOrderActualStartRepository
from infrastructure.mysql.matching_schedule_confirmation_repository import MySqlMatchingScheduleConfirmationRepository
from infrastructure.mysql.service_start_repository import MySqlServiceStartRepository
from infrastructure.mysql.service_date_adjustment_repository import load_first_schedule_dates
from subsystems.orders.actual_start_workflow import ActualStartWorkflow
from subsystems.orders.historical_restart_arrangement import HistoricalRestartArrangementReceipt
from subsystems.orders.service_date_confirmation_workflow import ServiceDateConfirmationWorkflow
from subsystems.payroll.terms_impact import calculate_assignment_payroll
from subsystems.contract_signing.final_document_workflow import ArchivedCommitmentPort, FinalSigningPrerequisiteCommand


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
            self._leave_result(request, context, who, cid, key)
        elif query.has_formal_assignments:
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
        return self.repository.effective_schedule_result(request["case_no"])

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

    def _leave_result(self, request, context, actor, cid, key):
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
        self._require_available_days(request['case_no'], request['staff_id'], replacements,
                                     '新的服務日期有不可排班紀錄。請重新協調補班日期或聯繫工會。')
        intent = LeaveSubstitutionBatchIntent(rows[originals[0]]['assignment_id'], tuple(
            LeaveSubstitutionItem(rows[old]['id'], old,
                LeaveResolutionType.DEFER_FOLLOWING_ASSIGNMENTS,
                None,
                False,
                new if new != old else None) for old,new in zip(originals,replacements)))
        preview = self.leave.preview(LeaveSubstitutionPreviewRequest(request['case_no'],intent,cid))
        self.leave.apply_in_current_unit_of_work(LeaveSubstitutionApplyRequest(request['case_no'],intent,
            ExpectedVersion(preview.order_version),ExpectedVersion(preview.scheduling_version),
            ExpectedVersion(preview.client_finance_version),ExpectedVersion(preview.payroll_version),
            preview.fingerprint,IdempotencyKey('leave-result:'+key),actor,'記錄雙方已協調的請假結果',cid))

    def preview_leave_defer(self, case_no: str, staff_id: int, assignment_id: int, dates: tuple) -> dict:
        """零寫入預檢請假順延日期的月嫂檔期衝突與服務總天數守恆。"""
        if not dates:
            raise ServiceStartConflict('leave_result_dates_required', '請至少選擇一個要請假的服務日。')
        originals = tuple(
            item.original_date if isinstance(item.original_date, date) else date.fromisoformat(str(item.original_date))
            for item in dates
        )
        replacements = tuple(
            (item.new_date if isinstance(item.new_date, date) else date.fromisoformat(str(item.new_date)))
            if item.new_date else None
            for item in dates
        )
        if any(day is None for day in replacements) or len(set(replacements)) != len(replacements):
            raise ServiceStartConflict('leave_result_new_dates_invalid', '合意補班日期不可空白或重複，且須確保總天數守恆。')
        if any(new <= old for old, new in zip(originals, replacements)):
            raise ServiceStartConflict('leave_result_must_defer', '合意補班日必須晚於原本請假日。')
        today = SystemBusinessClock().today()
        if any(day < today for day in originals) or any(day < today for day in replacements):
            raise ServiceStartConflict('leave_result_past_service', '已完成的服務日不可由請假流程變更，請重新核對日期。')
        conserved = len(originals) == len(replacements)
        with self.connection.cursor() as c:
            c.execute(
                'SELECT day.id,day.assignment_id,day.work_date FROM staff_schedule day '
                'JOIN scheduling_aggregates g ON g.effective_generation_id=day.generation_id '
                'WHERE g.case_no=%s AND day.staff_id=%s AND day.effective_marker=1 AND day.is_work_day=1 '
                'AND day.work_date BETWEEN %s AND %s ORDER BY day.work_date',
                (case_no, staff_id, min(originals), max(originals)),
            )
            rows = {row['work_date']: row for row in c.fetchall()}
        if any(day not in rows for day in originals) or (assignment_id and any(int(rows[day]['assignment_id']) != int(assignment_id) for day in originals)):
            raise ServiceStartConflict('leave_result_dates_changed', '原服務日或服務月嫂已變更，請重新查詢排班。')
        actual_assignment_id = int(assignment_id or rows[originals[0]]['assignment_id'])
        try:
            self._require_available_days(
                case_no,
                staff_id,
                replacements,
                '此補班日已有不可排班紀錄（檔期衝突），請重新與客戶協調其他日期！',
            )
            intent = LeaveSubstitutionBatchIntent(
                actual_assignment_id,
                tuple(
                    LeaveSubstitutionItem(
                        rows[old]['id'],
                        old,
                        LeaveResolutionType.DEFER_FOLLOWING_ASSIGNMENTS,
                        None,
                        False,
                        new if new != old else None,
                    )
                    for old, new in zip(originals, replacements)
                ),
            )
            preview = self.leave.preview(
                LeaveSubstitutionPreviewRequest(case_no, intent, CorrelationId('leave-preview:' + case_no))
            )
        except Exception as error:
            if isinstance(error, ServiceStartConflict) or self.is_occupancy_conflict(error):
                code = getattr(getattr(error, 'error', None), 'code', None) or getattr(error, 'code', None) or 'staff_occupancy_conflict'
                return {
                    'conflict': True,
                    'code': code,
                    'message': '此補班日已有其他案件排班或不可服務紀錄（檔期衝突），請重新與客戶協調其他日期！',
                    'total_service_days_conserved': conserved,
                    'original_dates': [str(d) for d in originals],
                    'new_dates': [str(d) for d in replacements],
                }
            raise
        if preview.apply_readiness.status == 'blocked':
            blockers = tuple(preview.apply_readiness.blockers)
            is_conflict = bool(set(blockers) & {
                'staff_occupancy_conflict',
                'actual_start_staff_schedule_conflict',
                'service_ownership_conflict',
                'scheduling.staff_effective_date_conflict',
                'availability_lock_staff_occupancy_conflict',
                'staff_unavailable',
                'actual_start_unavailability_conflict',
                'automatic_waiting_deposit_occupancy_conflict',
            })
            return {
                'conflict': True,
                'code': blockers[0] if blockers else 'leave_preview_blocked',
                'message': (
                    '此補班日已有其他案件排班或不可服務紀錄（檔期衝突），請重新與客戶協調其他日期！'
                    if is_conflict
                    else '目前排班或帳務狀態暫時無法完成順延（請聯絡工會確認）。'
                ),
                'total_service_days_conserved': conserved and preview.calendar_candidate.conservation_status == 'conserved',
                'original_dates': [str(d) for d in originals],
                'new_dates': [str(d) for d in replacements],
            }
        conserved = conserved and preview.calendar_candidate.conservation_status == 'conserved'
        return {
            'conflict': not conserved,
            'code': None if conserved else 'service_days_conservation_failed',
            'message': (
                '檔期無衝突，服務總天數與補助時數守恆，可送出延期確認。'
                if conserved
                else '順延後服務總天數未能守恆，請重新與客戶協調日期！'
            ),
            'total_service_days_conserved': conserved,
            'original_dates': [str(d) for d in originals],
            'new_dates': [str(d) for d in replacements],
        }

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
            if response['id']==request['id']:
                day=start_date
            elif response['decision']=='accepted' and response['status']=='awaiting_peers' and response['selected_candidate_id'] is None:
                day=response['requested_start_date']
            else:
                return False
            staff_id=segment['staff_id']
            calendar=calculate_attendance_schedule(day,int(segment['service_days']),mode)
            dates=tuple(item['date'] if isinstance(item['date'],date) else date.fromisoformat(str(item['date']))
                for item in calendar['day_by_day'] if item['is_work_day'])
            self._require_available_days(request['case_no'], staff_id, dates, '服務時段有不可排班紀錄，請聯繫工會調整本案排班。')
            intents.append(AssignmentPlanSegmentIntent(int(staff_id),day,dates[-1],dates))
        start=min(item.assigned_start_date for item in intents)
        facts=self.actual_start._repository.load_actual_start_query(request['case_no'],for_update=True)
        preview=self.actual_start.preview_date_only(facts,start)
        self.actual_start.apply_date_only_in_current_unit_of_work(ActualStartDateOnlyApplyRequest(
            request['case_no'],start,ExpectedVersion(facts.order_version),preview.fingerprint,cid))
        all_dates=tuple(sorted(day for item in intents for day in item.official_service_dates))
        with self.connection.cursor() as c:
            original, adjusted = load_first_schedule_dates(c, request['case_no'], lock=True)
        if adjusted:
            if tuple(day.service_date for day in original) != all_dates:
                raise ValueError("service_date_adjustment_first_schedule_ownership_conflict")
        else:
            preview=self.service_dates.preview(request['case_no'],all_dates)
            self.service_dates.apply_in_current_unit_of_work(request['case_no'],all_dates,
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


def _office_schedule_dates(segments, actual_start_date):
    dates = tuple(sorted(day for segment in segments for day in segment.service_dates))
    if (not dates or len(dates) != len(set(dates)) or dates[0] < actual_start_date
            or any(not segment.service_dates or segment.service_dates != tuple(sorted(segment.service_dates))
                   for segment in segments)):
        raise ValueError("office_schedule_dates_invalid")
    if len({segment.staff_id for segment in segments}) != len(segments):
        raise ValueError("office_schedule_segments_invalid")
    return dates


def _office_assignment_intent(segments, dates, actual_start_date):
    ordered = sorted(segments, key=lambda segment: segment.service_dates[0])
    interleaved = tuple(day for segment in ordered for day in segment.service_dates) != dates
    interval_start = actual_start_date
    intents = []
    for segment in ordered:
        interval_end = segment.service_dates[-1]
        start = segment.service_dates[0] if interleaved else interval_start
        intents.append(AssignmentPlanSegmentIntent(segment.staff_id, start, interval_end, segment.service_dates))
        interval_start = interval_end + timedelta(days=1)
    return AssignmentPlanIntent(tuple(intents), office_day_allocation=interleaved)


def _office_execution_days(segments):
    return tuple(ExecutionServiceDay(segment.staff_id, day) for segment in segments for day in segment.service_dates)


def preview_office_schedule(
    connection, case_no, segments, *, actual_start_date, reason, lock=False,
    commitments: ArchivedCommitmentPort | None = None,
):
    with connection.cursor() as cursor:
        facts = load_preview_facts(cursor, case_no, office_first_schedule=True)
        staff_ids = tuple(segment.staff_id for segment in segments)
        if (facts.lifecycle.current_status.value != '訂單成立' or facts.order.service_data_locked
                or any(item.official_service_dates for item in facts.scheduling.segments)):
            raise ValueError('office_schedule_not_pending_blocked')
        _require_office_assignment_ownership(cursor, case_no, lock=lock)
        dates = _office_schedule_dates(segments, actual_start_date)
        if len(dates) != facts.order.terms.service_days:
            raise ValueError('office_schedule_dates_invalid')
        intent = _office_assignment_intent(segments, dates, actual_start_date)
        _require_retired_staff_assignment_preservation(cursor, facts, intent, lock=lock)
        existing_staff = {item.staff_id for item in facts.scheduling.segments}
        if existing_staff and existing_staff != set(staff_ids) and not reason.strip():
            raise ValueError('office_schedule_reallocation_reason_required')
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
        impacted_staff = tuple(sorted(set(staff_ids) | set(preflight_staff_ids(cursor, case_no))))
        occupied, lock_ids = load_occupancy_snapshot(cursor, impacted_staff, case_no, lock=lock)
        execution_days = _office_execution_days(segments)

        def preview_execution(_cursor, _case, _plan, *, lock):
            return {"substitutions": {}, "office_reallocation_reason": reason.strip()}, execution_days

        commitment = commitments.preview_archived_commitment(case_no, for_update=lock) if commitments else None
        if commitment is None:
            _require_exact_commitment_days(cursor, case_no, execution_days, lock_ids, lock=lock,
                                           execution_reader=preview_execution, office_preview=True)
        else:
            options = dict(
                confirmed_days=execution_days, service_start_plan_id=commitment.matching_plan_id,
                office_reallocation=bool(reason.strip()),
            )
            signed_days = tuple(CommitmentServiceDay(day.staff_id, day.service_date) for day in commitment.days)
            plan_ids = _locked_waiting_lock_plan_ids(cursor, lock_ids, lock=lock)
            try:
                require_exact_commitment_execution(commitment.matching_plan_id, plan_ids, signed_days, execution_days, **options)
            except CommitmentExecutionMismatch:
                if reason.strip():
                    raise
                options["office_reallocation"] = True
                require_exact_commitment_execution(commitment.matching_plan_id, plan_ids, signed_days, execution_days, **options)
                raise ValueError("office_schedule_reallocation_reason_required") from None
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
    reason, correlation_id, preview_fingerprint=None, commitments: ArchivedCommitmentPort | None = None,
):
    reallocation_reason = reason.strip()
    reason = reallocation_reason or "工會確認服務日期並建立正式班表"
    key = IdempotencyKey(idempotency_key)
    who = ActorContext(actor)
    cid = CorrelationId(correlation_id)
    dates = _office_schedule_dates(segments, actual_start_date)
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
            commitments=commitments,
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
            raise ValueError("office_schedule_reallocation_reason_required")
        start = actual_repository.load_actual_start_query(case_no, for_update=True)
        if start.service_data_locked:
            raise ValueError("office_schedule_locked_blocked")
        if commitments is not None:
            candidate = commitments.preview_archived_commitment(case_no, for_update=True)
            if candidate is not None:
                commitments.ensure_archived_commitment(FinalSigningPrerequisiteCommand(
                    case_no, candidate.matching_plan_id, who, key, cid,
                ))
        if start.current_actual_start_date != actual_start_date:
            if start.has_formal_assignments:
                raise ValueError("office_schedule_existing_start_conflict")
            preview = actual_workflow.preview_date_only(start, actual_start_date)
            actual_workflow.apply_date_only_in_current_unit_of_work(ActualStartDateOnlyApplyRequest(
                case_no, actual_start_date, ExpectedVersion(start.order_version), preview.fingerprint, cid,
            ))
            facts = date_repository.load(case_no, lock=True)
        with connection.cursor() as cursor:
            baseline, adjusted = load_first_schedule_dates(cursor, case_no, lock=True)
        if adjusted:
            if tuple(day.service_date for day in baseline) != dates:
                raise ValueError("service_date_adjustment_first_schedule_ownership_conflict")
        elif facts.current_version is None or facts.current_dates != dates or facts.current_confirmed_order_version != facts.order_version:
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
            }, _office_execution_days(segments)

        intent = _office_assignment_intent(segments, dates, actual_start_date)
        workflow = assignment_application_factory(connection, office_execution=execution).workflow
        preview = workflow.preview(AssignmentPlanPreviewRequest(case_no, intent, cid))
        receipt = workflow.apply_in_current_unit_of_work(AssignmentPlanApplyRequest(
            case_no, intent, ExpectedVersion(preview.order_version), ExpectedVersion(preview.scheduling_version),
            ExpectedVersion(preview.client_finance_version), ExpectedVersion(preview.payroll_version),
            preview.fingerprint, IdempotencyKey(f"office-schedule:{digest}"), who, reason, cid,
        ))
        observed = workflow.query(case_no).assignment_plan
        intended = {day: segment.staff_id for segment in segments for day in segment.service_dates}
        if adjusted:
            intended = {day.service_date: day.staff_id or intended.get(day.service_date) for day in adjusted}
        actual = {day: assignment.staff_id for assignment in observed.effective_assignments
                  for day in assignment.official_service_dates}
        if actual != intended or len(observed.effective_assignments) != len(segments):
            raise ValueError("office_schedule_result_conflict")
        unit.commit()
        return HistoricalRestartArrangementReceipt(
            case_no, receipt.scheduling_version, receipt.scheduling_generation,
            tuple(a.assignment_id for a in observed.effective_assignments), receipt.preview_fingerprint,
        )
