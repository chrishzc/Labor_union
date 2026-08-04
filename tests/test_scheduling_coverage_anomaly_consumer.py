from datetime import date

import pytest

from subsystems.anomalies.scheduling_coverage_anomaly_consumer import (
    AssignmentOfficialServiceDays,
    SchedulingCoverageAnomalyConsumer,
    SchedulingCoverageRootFact,
    SchedulingCoverageScanPage,
    SchedulingCoverageScanRequest,
    build_schedule_coverage_project_request,
)


def test_coverage_mismatch_projects_the_canonical_schedule_alert():
    request = build_schedule_coverage_project_request(_root_fact())

    assert request.desired.definition_code == "SCHEDULE-006"
    assert request.desired.source_identity == "case:CASE-7"
    assert request.desired.active is True
    assert request.desired.fingerprint_values == {"case_no": "CASE-7", "generation": "2"}
    assert request.partition_identity == "SCHEDULE-006:case:CASE-7:generation:2"
    assert request.display_snapshot == {
        "case_no": "CASE-7",
        "generation": 2,
        "expected_days": 3,
        "actual_days": 2,
    }


@pytest.mark.parametrize("effective,eligible", [(False, True), (True, False)])
def test_non_effective_or_non_completed_fact_closes_the_coverage_alert(effective, eligible):
    request = build_schedule_coverage_project_request(
        _root_fact(generation_effective=effective, completed_eligible=eligible)
    )

    assert request.desired.active is False


def test_actual_days_are_distinct_dates_across_all_assignments():
    root_fact = _root_fact(
        assignments=(
            AssignmentOfficialServiceDays(1, (date(2026, 1, 1), date(2026, 1, 2))),
            AssignmentOfficialServiceDays(2, (date(2026, 1, 2), date(2026, 1, 3))),
        )
    )

    assert root_fact.actual_service_days == 3


def test_scan_rejects_a_source_page_beyond_requested_limit():
    fact = _root_fact()
    consumer = SchedulingCoverageAnomalyConsumer(_OversizedSource(fact), _UnusedApplication())

    with pytest.raises(ValueError, match="bounded scan limit"):
        consumer.scan_page(SchedulingCoverageScanRequest(1))


def test_assignment_dates_must_be_sorted_and_unique():
    with pytest.raises(ValueError, match="sorted and unique"):
        AssignmentOfficialServiceDays(1, (date(2026, 1, 2), date(2026, 1, 1)))


class _OversizedSource:
    def __init__(self, fact):
        self._fact = fact

    def load_page(self, _request):
        return SchedulingCoverageScanPage((self._fact, self._fact), None)


class _UnusedApplication:
    def project(self, _request):
        raise AssertionError("must reject oversized page before projection")


def _root_fact(*, assignments=None, generation_effective=True, completed_eligible=True):
    return SchedulingCoverageRootFact(
        case_no="CASE-7",
        generation=2,
        expected_service_days=3,
        assignments=assignments
        or (AssignmentOfficialServiceDays(1, (date(2026, 1, 1), date(2026, 1, 2))),),
        generation_effective=generation_effective,
        completed_eligible=completed_eligible,
        source_version=4,
        source_event_identity="event-7",
    )
