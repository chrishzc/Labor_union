"""Focused #88 regression for immutable source period and pairing evidence."""

from datetime import date
import json

from infrastructure.mysql.historical_order_adoption_evidence_repository import (
    MySqlHistoricalOrderAdoptionEvidenceRepository,
)
from subsystems.orders.historical_adoption_evidence_query import (
    query_historical_order_adoption_evidence,
)


class _Cursor:
    def __init__(self, connection):
        self.connection = connection
        self.rows = ()
        self.one = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, sql, params):
        self.connection.calls.append((sql, params))
        if "historical_order_adoption_receipts" in sql:
            self.one = self.connection.receipt
        else:
            self.rows = self.connection.pairings

    def fetchone(self):
        return self.one

    def fetchall(self):
        return self.rows


class _Connection:
    def __init__(self):
        self.calls = []
        self.receipt = {
            "id": 77,
            "case_no": "CASE-FUTURE",
            "source_event_identity": "historical-orders:sheet:row:17",
            "source_fingerprint": "a" * 64,
            "preview_fingerprint": "b" * 64,
            "result_snapshot": json.dumps({
                "historical_source_status": "deposit_paid",
                "operational_baseline_step": 9,
            }),
            "lifecycle_facts_snapshot": json.dumps({"date_patch": []}),
        }
        self.pairings = (
            {
                "caregiver_ordinal": 1,
                "masked_staff_name": "陳*嫂",
                "staff_id": 42,
                "resolution": "evidence_only",
                "source_start_date": date(2026, 9, 3),
                "source_end_date": date(2026, 9, 22),
                "assignment_id": None,
            },
            {
                "caregiver_ordinal": 2,
                "masked_staff_name": "待確認",
                "staff_id": None,
                "resolution": "staff_missing",
                "source_start_date": date(2026, 9, 3),
                "source_end_date": date(2026, 9, 22),
                "assignment_id": None,
            },
        )

    def cursor(self):
        return _Cursor(self)


def test_future_source_period_and_evidence_only_staff_are_visible_without_becoming_formal_facts():
    repository = MySqlHistoricalOrderAdoptionEvidenceRepository(_Connection())

    evidence = query_historical_order_adoption_evidence(repository, "CASE-FUTURE")

    assert evidence.source_start_date == date(2026, 9, 3)
    assert evidence.source_end_date == date(2026, 9, 22)
    assert evidence.source_period_availability == "available"
    assert evidence.operational_baseline_step == 9
    assert evidence.receipt_identity == "historical-order-adoption-receipt:77"
    assert [(item.staff_id, item.resolution) for item in evidence.paired_staff] == [
        (42, "evidence_only")
    ]
    assert evidence.paired_staff[0].assignment_id is None
    assert evidence.paired_staff_availability == "available"
