"""Payroll-owned assignment rate snapshot persistence tests."""

from types import SimpleNamespace

from infrastructure.mysql.payroll_terms_writer import (
    persist_scheduling_assignment_rate_snapshots,
)


class _Cursor:
    def __init__(self, source_policy):
        self.source_policy = source_policy
        self.current = None
        self.inserted = ()

    def execute(self, statement, _parameters):
        self.current = self.source_policy if "WHERE assignment_id=" in statement else {
            "policy_version": "case-v1",
            "policy_kind": "citizen",
            "hourly_rate_ntd": 300,
            "source_identity_status": "一般市民",
        }

    def fetchone(self):
        return self.current

    def executemany(self, _statement, rows):
        self.inserted = rows


def _command():
    assignment = SimpleNamespace(
        candidate_key="CASE-1:g2:a1",
        source_assignment_id=91,
    )
    return SimpleNamespace(
        candidate=SimpleNamespace(case_no="CASE-1", assignments=(assignment,))
    )


def _result():
    return SimpleNamespace(
        assignment_resolution=SimpleNamespace(
            assignment_id_by_candidate_key={"CASE-1:g2:a1": 101}
        )
    )


def test_assignment_rate_falls_back_to_existing_case_policy():
    cursor = _Cursor(None)

    persist_scheduling_assignment_rate_snapshots(cursor, _command(), _result())

    assert cursor.inserted == ((101, "case-v1", "citizen", 300, "case-policy"),)


def test_assignment_rate_carries_the_source_assignment_snapshot():
    cursor = _Cursor({
        "policy_version": "frozen-v2",
        "policy_kind": "private",
        "hourly_rate_ntd": 450,
        "source_identity_status": "legacy",
    })

    persist_scheduling_assignment_rate_snapshots(cursor, _command(), _result())

    assert cursor.inserted == (
        (101, "frozen-v2", "private", 450, "carried-from:91"),
    )
