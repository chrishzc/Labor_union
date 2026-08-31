from datetime import date

from domains.anomalies.current_issue import RecheckScope, build_owner_lock_key
from infrastructure.mysql.scheduling_current_issue_adapter import MySqlSchedulingCurrentIssueAdapter


class _Cursor:
    def __init__(self, responses):
        self.responses = responses
        self.current = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, *_):
        self.current = self.responses.pop(0)

    def fetchall(self):
        return self.current

    def fetchone(self):
        return self.current


class _Connection:
    def __init__(self, responses):
        self.responses = list(responses)

    def cursor(self):
        return _Cursor(self.responses)


def _scope(code, subject, lock):
    return RecheckScope(
        "scheduling",
        "scheduling_current_fact",
        code,
        (subject,),
        (build_owner_lock_key("scheduling", "scheduling_current_fact", lock),),
    )


def test_overlap_readback_uses_only_current_effective_assignments() -> None:
    rows = (
        {"assignment_id": 1, "case_no": "A", "assignment_status": "active", "assigned_start_date": date(2026, 1, 1), "assigned_end_date": date(2026, 1, 5), "generation_id": 10, "generation_status": "effective", "effective_marker": 1, "effective_generation_id": 10, "aggregate_version": 3},
        {"assignment_id": 2, "case_no": "B", "assignment_status": "active", "assigned_start_date": date(2026, 1, 5), "assigned_end_date": date(2026, 1, 9), "generation_id": 20, "generation_status": "effective", "effective_marker": 1, "effective_generation_id": 20, "aggregate_version": 4},
    )
    snapshot = MySqlSchedulingCurrentIssueAdapter(_Connection([rows])).read_owner_snapshot(
        _scope("SCHEDULE-003", "1:2", "assignment:1")
    )
    assert snapshot.authoritative_complete is True
    assert snapshot.facts[0].predicate_active is True
    assert snapshot.owner_version == 4


def test_coverage_readback_checks_full_interval_external_occupancy() -> None:
    generation = {"generation_id": 10, "generation_number": 2, "generation_status": "effective", "effective_marker": 1, "effective_generation_id": 10, "aggregate_version": 8, "service_days": 2, "service_hours_per_day": 8}
    assignments = ({"assignment_id": 1, "staff_id": 7, "assigned_start_date": date(2026, 1, 1), "assigned_end_date": date(2026, 1, 5), "assignment_status": "active"},)
    schedules = (
        {"assignment_id": 1, "work_date": date(2026, 1, 1), "schedule_effective_marker": 1},
        {"assignment_id": 1, "work_date": date(2026, 1, 2), "schedule_effective_marker": 1},
    )
    external = ({"assignment_id": 9, "staff_id": 7, "assigned_start_date": date(2026, 1, 5), "assigned_end_date": date(2026, 1, 7)},)
    snapshot = MySqlSchedulingCurrentIssueAdapter(
        _Connection([generation, assignments, schedules, external])
    ).read_owner_snapshot(_scope("SCHEDULE-006", "CASE-1:2", "case:CASE-1"))
    fact = snapshot.facts[0]
    assert fact.coverage_valid is True
    assert fact.staff_occupancy_valid is False
    assert fact.predicate_active is True


def test_missing_generation_is_incomplete_and_never_authoritative_delete() -> None:
    snapshot = MySqlSchedulingCurrentIssueAdapter(_Connection([None])).read_owner_snapshot(
        _scope("SCHEDULE-006", "CASE-1:2", "case:CASE-1")
    )
    assert snapshot.authoritative_complete is False
    assert snapshot.facts[0].predicate_active is True


def test_replaced_assignment_closes_only_with_effective_lineage_and_owner_receipt() -> None:
    row = {
        "source_assignment_id": 7,
        "case_no": "CASE-7",
        "source_status": "replaced",
        "actual_start_date": None,
        "aggregate_version": 9,
        "successor_count": 1,
        "invalid_successor_count": 0,
        "receipt_count": 1,
    }
    snapshot = MySqlSchedulingCurrentIssueAdapter(_Connection([row])).read_owner_snapshot(
        _scope("SCHEDULE-002", "7", "assignment:7")
    )
    fact = snapshot.facts[0]
    assert fact.exact_successor is True
    assert fact.payroll_impact_complete is True
    assert fact.finance_impact_complete is True
    assert fact.case_no == "CASE-7"
    assert fact.service_started is False
    assert fact.predicate_active is False
