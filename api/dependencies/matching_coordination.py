"""
File: matching_coordination.py
Description: 組合 M3 Query／Preview／Apply 與 service-date owner facts 的 MySQL boundary。
"""

from __future__ import annotations

from dataclasses import dataclass

from infrastructure.mysql.assignment_plan_repository import (
    MySqlAssignmentPlanRepository,
)
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
from infrastructure.mysql.mysql_adapter import get_connection
from infrastructure.mysql.order_terms_repository import MySqlOrderTermsRepository
from infrastructure.mysql.service_date_confirmation_repository import (
    MySqlServiceDateConfirmationRepository,
)
from infrastructure.mysql.staff_availability_repository import (
    MySqlStaffAvailabilityRepository,
)
from infrastructure.mysql.staff_matching_preference_repository import (
    MySqlStaffMatchingPreferenceRepository,
)
from infrastructure.mysql.staff_retirement_repository import (
    MySqlStaffRetirementRepository,
)
from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
from shared_kernel.clock import SystemBusinessClock
from subsystems.scheduling.matching_coordination_application import (
    MatchingCoordinationApplication,
    ServiceDateRematchPreviewInput,
)
from subsystems.scheduling.matching_coordination_contracts import (
    ApplyServiceDateChangeRematch,
    PreviewServiceDateChangeRematch,
)


@dataclass(slots=True)
class MatchingCoordinationComposition:
    """Own the request connection and its single M3 application."""

    connection: object
    application: MatchingCoordinationApplication


def get_matching_coordination_composition():
    """Yield a request-scoped initial-snapshot composition."""

    connection = get_connection()
    clock = SystemBusinessClock()
    order_terms = MySqlOrderTermsRepository(connection)
    service_dates = MySqlServiceDateConfirmationRepository(connection)
    candidate_pool = MySqlCandidateContactPoolQueryAdapter(connection)
    incumbent_assignment = MySqlAssignmentPlanRepository(connection)
    staff_profile = MySqlStaffMatchingPreferenceRepository(connection)
    staff_lifecycle = MySqlStaffRetirementRepository(connection)
    staff_availability = MySqlStaffAvailabilityRepository(connection)
    availability = MatchingAvailabilityQueryAdapter(
        service_dates,
        staff_availability,
    )
    effective_generation = MatchingEffectiveGenerationQueryAdapter(order_terms)
    repository = MySqlMatchingCoordinationRepository(connection, clock)
    facts = MySqlMatchingCoordinationFactsAdapter(
        orders_terms=order_terms,
        orders_service_dates=service_dates,
        scheduling_availability=availability,
        scheduling_effective_generation=effective_generation,
        staff_profile=staff_profile,
        staff_lifecycle=staff_lifecycle,
        matching_criteria_snapshot=repository,
        candidate_pool=candidate_pool,
        matching_package=repository,
        incumbent_assignment=incumbent_assignment,
        staff_ids=candidate_pool.load_staff_ids,
    )
    application = MatchingCoordinationApplication(
        facts,
        repository,
        lambda: MySqlUnitOfWork(connection),
        service_date_input_loader=lambda command, for_update: _load_service_date_input(
            command,
            service_dates=service_dates,
            incumbent_assignment=incumbent_assignment,
            staff_availability=staff_availability,
            for_update=for_update,
        ),
        clock=clock,
    )
    try:
        yield MatchingCoordinationComposition(connection, application)
    finally:
        connection.close()


def _load_service_date_input(
    command: PreviewServiceDateChangeRematch | ApplyServiceDateChangeRematch,
    *,
    service_dates: MySqlServiceDateConfirmationRepository,
    incumbent_assignment: MySqlAssignmentPlanRepository,
    staff_availability: MySqlStaffAvailabilityRepository,
    for_update: bool,
) -> ServiceDateRematchPreviewInput:
    owner_dates = service_dates.load_service_dates(
        command.case_no,
        for_update=for_update,
    )
    if owner_dates.current_version is None or not owner_dates.current_dates:
        raise ValueError("confirmed service dates are required")
    assignments = incumbent_assignment.load_current_assignments(
        command.case_no,
        for_update=for_update,
    )
    matches = tuple(
        item
        for item in assignments.effective_assignments
        if item.assignment_id == command.assignment_id
    )
    if len(matches) != 1:
        raise ValueError("service-date assignment identity is stale")
    assignment = matches[0]
    if (
        assignment.staff_id != command.original_staff_id
        or assignment.official_service_dates != command.original_service_dates
        or not set(command.original_service_dates).issubset(owner_dates.current_dates)
    ):
        raise ValueError("service-date owner facts are stale")
    available = staff_availability.load_matching_facts(
        command.original_staff_id,
        command.shifted_service_dates,
        for_update=for_update,
    )
    return ServiceDateRematchPreviewInput(
        case_no=command.case_no,
        assignment_id=command.assignment_id,
        original_staff_id=command.original_staff_id,
        original_service_dates=command.original_service_dates,
        shifted_service_dates=command.shifted_service_dates,
        availability=available,
    )


__all__ = [
    "MatchingCoordinationComposition",
    "get_matching_coordination_composition",
]
