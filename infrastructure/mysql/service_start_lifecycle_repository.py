"""Orders adapter; no scheduling/finance rebuild or LINE notification on date tick."""
from datetime import datetime,time
from domains.orders.lifecycle import build_terms_lifecycle_impact,OrderLifecycleStatus
from domains.scheduling.generation import AssignmentCandidate,SchedulingGenerationCandidate
from infrastructure.mysql.order_terms_read_model import load_locked_facts,preflight_staff_ids
from infrastructure.mysql.order_lifecycle_impact_writer import persist_order_lifecycle_impact,persist_order_lifecycle_projection
from shared_kernel.clock import TAIPEI_TIME_ZONE
from shared_kernel.identities import ActorContext,IdempotencyKey,CorrelationId
from subsystems.orders.actual_start_workflow import _existing_client_settlement
from subsystems.orders.terms_workflow import LifecycleImpactPersistenceCommand

class MySqlServiceStartLifecycleRepository:
    def __init__(self,connection):self.connection=connection

    def due_cases(self,evaluation_at,after,limit):
        if evaluation_at.tzinfo is None or not 1<=limit<=200:raise ValueError('invalid service start tick')
        with self.connection.cursor() as c:
            c.execute("SELECT o.case_no FROM orders o JOIN scheduling_aggregates g ON g.case_no=o.case_no WHERE o.status='訂單成立' AND o.actual_start_date<=%s AND o.case_no>%s AND g.effective_generation_id IS NOT NULL ORDER BY o.case_no LIMIT %s",(evaluation_at.astimezone(TAIPEI_TIME_ZONE).date(),after,limit))
            return tuple(row['case_no'] for row in c.fetchall())

    def advance(self,case,evaluation_at):
        with self.connection.cursor() as c:
            facts=load_locked_facts(c,case,preflight_staff_ids(c,case))
            root=facts.lifecycle
            if root.current_status is not OrderLifecycleStatus.ESTABLISHED or root.actual_start_date is None or root.actual_start_date>evaluation_at.astimezone(TAIPEI_TIME_ZONE).date():return False
            assignments=tuple(AssignmentCandidate(str(s.assignment_id),s.assignment_id,s.staff_id,s.sequence,s.assigned_start_date,s.assigned_end_date,s.official_service_dates,len(s.official_service_dates)*facts.order.terms.service_hours_per_day) for s in facts.scheduling.segments)
            if not assignments:return False
            scheduling=SchedulingGenerationCandidate(case,facts.scheduling.generation_number,facts.scheduling.aggregate_version,facts.scheduling.aggregate_version,(),assignments,())
            settlement=_existing_client_settlement(facts)
            # First enter service at the agreed day. AutoComplete remains the
            # only command allowed to complete it, including a missed old tick.
            candidate=build_terms_lifecycle_impact(root,facts.order.terms,scheduling,settlement,datetime.combine(root.actual_start_date,time.min,tzinfo=TAIPEI_TIME_ZONE))
            if candidate.after_status is not OrderLifecycleStatus.IN_SERVICE:return False
            key=f'service-start-day:{case}:{facts.order.version}'
            command=LifecycleImpactPersistenceCommand(candidate,facts.order.version,facts.order.version+1,settlement.fingerprint,IdempotencyKey(key),ActorContext('system:service-start-day'),'約定服務開始日已到',CorrelationId(key),'evaluation_time_reached')
            persist_order_lifecycle_impact(c,command);persist_order_lifecycle_projection(c,command)
            return True
