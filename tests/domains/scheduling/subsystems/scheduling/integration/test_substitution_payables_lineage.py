"""Scheduling→Payroll→Staff Payables lineage readback contract."""

from datetime import date

import pytest

from infrastructure.mysql.substitution_payables_lineage_repository import (
    MySqlSubstitutionPayablesLineageRepository,
)


_MISSING = object()


class _Cursor:
    def __init__(self, *, event_rows=None, projection=_MISSING):
        self.event_rows = event_rows if event_rows is not None else [_event()]
        self.projection = _projection() if projection is _MISSING else projection
        self.rows = ()

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, params):
        if "FROM scheduling_leave_substitution_outcomes" in sql:
            self.rows = (_outcome(),)
        elif "FROM scheduling_leave_substitution_receipts" in sql:
            self.rows = (_receipt(),)
        elif "FROM staff_obligation_events" in sql:
            self.rows = tuple(self.event_rows)
        elif "FROM staff_obligations" in sql:
            self.rows = (_obligation(),)
        elif "FROM staff_payable_projections" in sql:
            self.rows = () if self.projection is None else (self.projection,)
        else:
            raise AssertionError(f"unexpected query: {sql}")

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return self.rows


class _Connection:
    def __init__(self, **kwargs):
        self.cursor_instance = _Cursor(**kwargs)

    def cursor(self):
        return self.cursor_instance
def _receipt():
    return {
        "batch_key": "leave-batch-1",
        "case_no": "CASE-1",
        "scheduling_receipt_id": 91,
        "resulting_scheduling_version": 4,
        "resulting_generation_number": 3,
        "expected_payroll_version": 8,
        "resulting_payroll_version": 9,
    }


def _outcome():
    return {
        "id": 501,
        "item_index": 0,
        "original_assignment_id": 11,
        "original_schedule_id": 101,
        "original_staff_id": 7,
        "original_work_date": date(2026, 9, 1),
        "resolution_type": "substitute",
        "resulting_assignment_id": 22,
        "resulting_staff_id": 8,
        "resulting_service_date": date(2026, 9, 1),
    }


def _event():
    return {
        "id": 601,
        "obligation_identity": "staff-obligation:22",
        "assignment_id": 22,
        "staff_id": 8,
        "payroll_fingerprint": "a" * 64,
        "expected_payroll_version": 8,
        "resulting_payroll_version": 9,
    }


def _obligation():
    return {
        "obligation_identity": "staff-obligation:22",
        "assignment_id": 22,
        "staff_id": 8,
        "amount_due_ntd": 4800,
        "due_date": date(2026, 9, 15),
        "status": "open",
        "current_event_id": 601,
        "payroll_version": 9,
    }


def _projection():
    return {
        "obligation_amount_ntd": 4800,
        "net_paid_ntd": 0,
        "balance_ntd": 4800,
        "status": "payable",
        "aggregate_version": 5,
        "current_event_id": 701,
    }


def test_lineage_readback_requires_exact_owner_versions_and_subject():
    result = MySqlSubstitutionPayablesLineageRepository(_Connection()).query(
        "CASE-1", "leave-batch-1"
    )

    assert result.authoritative_complete is True
    assert result.blockers == ()
    item = result.items[0]
    assert item.lineage_subject == "substitution:leave-batch-1:outcome:501"
    assert item.payroll_event_resulting_version == 9
    assert item.payables_evidence is not None
    assert item.payables_evidence.projection_version == 5


@pytest.mark.parametrize(
    ("connection_kwargs", "expected_blocker"),
    (
        ({"event_rows": []}, "payroll_obligation_event_missing"),
        ({"event_rows": [_event(), {**_event(), "id": 602}]}, "payroll_obligation_event_ambiguous"),
        ({"event_rows": [{**_event(), "assignment_id": 999}]}, "payroll_obligation_assignment_mismatch"),
        ({"event_rows": [{**_event(), "expected_payroll_version": 7}]}, "payroll_obligation_version_invalid"),
        ({"event_rows": [{**_event(), "resulting_payroll_version": 10}]}, "payroll_obligation_version_mismatch"),
        ({"projection": None}, "staff_payables_projection_missing"),
        ({"projection": {**_projection(), "balance_ntd": 4700}}, "staff_payables_balance_mismatch"),
    ),
)
def test_lineage_readback_fails_closed_for_incomplete_owner_evidence(
    connection_kwargs, expected_blocker
):
    result = MySqlSubstitutionPayablesLineageRepository(
        _Connection(**connection_kwargs)
    ).query("CASE-1", "leave-batch-1")

    assert result.authoritative_complete is False
    assert expected_blocker in result.items[0].blockers
