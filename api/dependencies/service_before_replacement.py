"""
File: service_before_replacement.py
Description: 組裝服務前換人 application；缺少安全 facts/source loader 時 fail closed。
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Header

from infrastructure.mysql.assignment_plan_repository import MySqlAssignmentPlanRepository
from infrastructure.mysql.candidate_contact_pool_query_adapter import (
    MySqlCandidateContactPoolQueryAdapter,
)
from infrastructure.mysql.matching_coordination_facts_adapter import (
    MatchingAvailabilityQueryAdapter,
    MatchingEffectiveGenerationQueryAdapter,
    MySqlMatchingCoordinationFactsAdapter,
)
from infrastructure.mysql.matching_coordination_repository import (
    MySqlMatchingCoordinationRepository,
)
from infrastructure.mysql.matching_successor_persistence_adapter import (
    MatchingSuccessorPersistenceAdapter,
)
from infrastructure.mysql.mysql_adapter import get_connection
from infrastructure.mysql.order_terms_repository import MySqlOrderTermsRepository
from infrastructure.mysql.service_before_replacement_loader import (
    MySqlServiceBeforeReplacementLoader,
)
from infrastructure.mysql.service_before_replacement_repository import (
    MySqlServiceBeforeReplacementRepository,
)
from infrastructure.mysql.service_date_confirmation_repository import (
    MySqlServiceDateConfirmationRepository,
)
from infrastructure.mysql.staff_availability_repository import (
    MySqlStaffAvailabilityRepository,
)
from infrastructure.mysql.staff_matching_preference_repository import (
    MySqlStaffMatchingPreferenceRepository,
)
from infrastructure.mysql.staff_retirement_repository import MySqlStaffRetirementRepository
from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
from shared_kernel.clock import SystemBusinessClock

from subsystems.scheduling.service_before_replacement_workflow import (
    ServiceBeforeReplacementQueryRequest,
    ServiceBeforeReplacementWorkflow,
)


_CorrelationHeader = Annotated[
    str,
    Header(alias="X-Correlation-ID", min_length=1, max_length=191),
]


class ServiceBeforeReplacementApplication:
    """Typed façade kept small so routes cannot reach repositories directly."""

    def __init__(self, workflow) -> None:
        self.workflow = workflow

    def query(self, request: ServiceBeforeReplacementQueryRequest):
        return self.workflow.query(request)

    def preview(self, request):
        return self.workflow.preview(request)

    def apply(self, command):
        return self.workflow.apply(command)


def get_service_before_replacement_application(
    correlation_id: _CorrelationHeader = "service-before-replacement-dependency",
):
    """Yield one request-scoped connection and one outer-UoW workflow."""
    del correlation_id
    connection = get_connection()
    try:
        yield build_service_before_replacement_application(connection)
    finally:
        connection.close()


def build_service_before_replacement_application(connection):
    """Compose all production owner readers on the repository's borrowed connection."""
    clock = SystemBusinessClock()
    order_terms = MySqlOrderTermsRepository(connection)
    service_dates = MySqlServiceDateConfirmationRepository(connection)
    candidate_pool = MySqlCandidateContactPoolQueryAdapter(connection)
    assignments = MySqlAssignmentPlanRepository(connection)
    staff_profile = MySqlStaffMatchingPreferenceRepository(connection)
    staff_lifecycle = MySqlStaffRetirementRepository(connection)
    staff_availability = MySqlStaffAvailabilityRepository(connection)
    matching_repository = MySqlMatchingCoordinationRepository(connection, clock)
    matching_facts = MySqlMatchingCoordinationFactsAdapter(
        orders_terms=order_terms,
        orders_service_dates=service_dates,
        scheduling_availability=MatchingAvailabilityQueryAdapter(
            service_dates, staff_availability
        ),
        scheduling_effective_generation=MatchingEffectiveGenerationQueryAdapter(order_terms),
        staff_profile=staff_profile,
        staff_lifecycle=staff_lifecycle,
        matching_criteria_snapshot=matching_repository,
        candidate_pool=candidate_pool,
        matching_package=matching_repository,
        incumbent_assignment=assignments,
        staff_ids=candidate_pool.load_staff_ids,
    )
    loader = MySqlServiceBeforeReplacementLoader(connection, matching_facts, clock)
    repository = MySqlServiceBeforeReplacementRepository(
        connection,
        MatchingSuccessorPersistenceAdapter(connection),
        facts_loader=loader.load_facts,
        matching_source_loader=loader.load_matching_source,
    )
    workflow = ServiceBeforeReplacementWorkflow(
        repository,
        lambda: MySqlUnitOfWork(connection),
    )
    return ServiceBeforeReplacementApplication(workflow)


__all__ = [
    "ServiceBeforeReplacementApplication",
    "build_service_before_replacement_application",
    "get_service_before_replacement_application",
]
