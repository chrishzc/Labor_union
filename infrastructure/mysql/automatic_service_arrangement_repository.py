"""Read current matching/date confirmation facts for automatic assignment dispatch."""

from datetime import date

from domains.scheduling.assignment_plan import AssignmentPlanIntent, AssignmentPlanSegmentIntent
from subsystems.scheduling.automatic_service_arrangement import AutomaticArrangementProposal
from subsystems.scheduling.availability_lock_acquisition_workflow import (
    lock_current_matching_staff, reserve_confirmed_matching_plan,
)
from infrastructure.mysql.unit_of_work import MySqlUnitOfWork


class MySqlAutomaticServiceArrangementSource:
    def __init__(self, connection, assignment_application):
        self.connection = connection
        self.assignments = assignment_application

    def reserve_waiting_deposit(self, case_no: str) -> None:
        """Discovery catches pre-upgrade confirmations; Query stays read-only."""
        with MySqlUnitOfWork(self.connection) as unit:
            locked_staff = lock_current_matching_staff(self.connection, case_no)
            reserve_confirmed_matching_plan(self.connection, case_no, 'system:automatic-waiting-deposit-lock', locked_staff)
            unit.commit()

    def proposal(self, case_no: str, plan_id: int) -> AutomaticArrangementProposal:
        facts = self.assignments.query(case_no).assignment_plan
        if facts.effective_assignments:
            return AutomaticArrangementProposal(case_no, plan_id, 0, False, len(facts.effective_assignments), None)
        from infrastructure.mysql.service_start_arrangement import current_service_start_execution
        with self.connection.cursor() as cursor:
            try:
                proof, days = current_service_start_execution(cursor,case_no,plan_id)
            except ValueError as error:
                if str(error) != 'service_start_result_required':
                    raise
                return AutomaticArrangementProposal(case_no,plan_id,0,False,0,None)
        grouped={}
        for day in days:
            grouped.setdefault(day.staff_id,[]).append(day.service_date)
        intents=tuple(AssignmentPlanSegmentIntent(staff,min(values),max(values),tuple(sorted(values)))
                      for staff,values in grouped.items())
        return AutomaticArrangementProposal(case_no,plan_id,proof['confirmed_version_id'],True,0,AssignmentPlanIntent(intents))

    def pending(self, after_case_no: str, limit: int):
        if not 1 <= limit <= 200:
            raise ValueError('automatic arrangement page size is invalid')
        with self.connection.cursor() as cursor:
            cursor.execute('SELECT p.case_no,MAX(p.id) AS plan_id FROM caregiver_matching_plans p JOIN confirmed_service_date_versions v ON v.case_no=p.case_no AND v.is_current=1 JOIN orders o ON o.case_no=p.case_no JOIN scheduling_service_start_requests r ON r.case_no=p.case_no AND r.confirmed_version_id=v.id AND r.execution_dates IS NOT NULL WHERE p.is_active=1 AND p.status IN (\'proposed\',\'accepted\') AND p.case_no>%s AND o.status IN (\'洽談中\',\'訂單成立\',\'服務中\') AND NOT EXISTS (SELECT 1 FROM scheduling_aggregates a JOIN case_staff_assignments assignment ON assignment.generation_id=a.effective_generation_id AND assignment.status IN (\'active\',\'planned\',\'completed\') WHERE a.case_no=p.case_no) GROUP BY p.case_no ORDER BY p.case_no LIMIT %s', (after_case_no, limit))
            return tuple((row['case_no'], row['plan_id']) for row in cursor.fetchall())

    def job_state(self, identity: str):
        with self.connection.cursor() as cursor:
            cursor.execute('SELECT job_id,status FROM background_jobs WHERE command_identity=%s', (identity,))
            row = cursor.fetchone()
        return None if row is None else (row['job_id'], row['status'])
