"""Read current matching/date confirmation facts for automatic assignment dispatch."""

from datetime import date

from domains.scheduling.assignment_plan import AssignmentPlanIntent, AssignmentPlanSegmentIntent
from infrastructure.mysql.matching_schedule_confirmation_repository import MySqlMatchingScheduleConfirmationRepository
from subsystems.scheduling.automatic_service_arrangement import AutomaticArrangementProposal


class MySqlAutomaticServiceArrangementSource:
    def __init__(self, connection, assignment_application):
        self.connection = connection
        self.assignments = assignment_application
        self.schedules = MySqlMatchingScheduleConfirmationRepository(connection)

    def proposal(self, case_no: str, plan_id: int) -> AutomaticArrangementProposal:
        facts = self.assignments.query(case_no).assignment_plan
        if facts.effective_assignments:
            return AutomaticArrangementProposal(case_no, plan_id, 0, False, len(facts.effective_assignments), None)
        schedule = self.schedules.query(case_no, plan_id)
        if not schedule['gate_passed']:
            return AutomaticArrangementProposal(case_no, plan_id, schedule['confirmed_service_date_version'], False, 0, None)
        with self.connection.cursor() as cursor:
            cursor.execute('SELECT s.id,s.staff_id,s.assigned_start_date,s.assigned_end_date,o.actual_start_date FROM caregiver_matching_plan_segments s JOIN caregiver_matching_plans p ON p.id=s.plan_id JOIN orders o ON o.case_no=p.case_no WHERE s.plan_id=%s AND p.case_no=%s ORDER BY s.segment_order', (plan_id, case_no))
            rows = cursor.fetchall()
        intents = []
        for row in rows:
            segment = next((r for r in schedule['schedule_preview']['recipient_schedules'] if r['audience_type'] == 'caregiver' and r['segment_id'] == row['id']), None)
            if segment is None:
                raise ValueError('matching_schedule_confirmation_required_for_target_segments')
            dates = tuple(date.fromisoformat(d) for week in segment['weeks'] for d in week['service_dates'])
            if not dates:
                raise ValueError('matching_schedule_segment_dates_required')
            start = (row['actual_start_date'] or dates[0]) if len(rows) == 1 else row['assigned_start_date']
            end = dates[-1] if len(rows) == 1 else row['assigned_end_date']
            intents.append(AssignmentPlanSegmentIntent(row['staff_id'], start, end, dates))
        return AutomaticArrangementProposal(case_no, plan_id, schedule['confirmed_service_date_version'], schedule['gate_passed'], len(facts.effective_assignments), AssignmentPlanIntent(tuple(intents)))

    def pending(self, after_case_no: str, limit: int):
        if not 1 <= limit <= 200:
            raise ValueError('automatic arrangement page size is invalid')
        with self.connection.cursor() as cursor:
            cursor.execute('SELECT s.case_no,MAX(s.plan_id) AS plan_id FROM matching_schedule_snapshots s JOIN confirmed_service_date_versions v ON v.id=s.confirmed_version_id AND v.is_current=1 JOIN orders o ON o.case_no=s.case_no WHERE s.current_marker=1 AND s.case_no>%s AND o.status IN (\'洽談中\',\'訂單成立\',\'服務中\') AND NOT EXISTS (SELECT 1 FROM scheduling_aggregates a JOIN case_staff_assignments assignment ON assignment.generation_id=a.effective_generation_id AND assignment.status IN (\'active\',\'planned\',\'completed\') WHERE a.case_no=s.case_no) GROUP BY s.case_no ORDER BY s.case_no LIMIT %s', (after_case_no, limit))
            return tuple((row['case_no'], row['plan_id']) for row in cursor.fetchall())

    def job_state(self, identity: str):
        with self.connection.cursor() as cursor:
            cursor.execute('SELECT job_id,status FROM background_jobs WHERE command_identity=%s', (identity,))
            row = cursor.fetchone()
        return None if row is None else (row['job_id'], row['status'])
