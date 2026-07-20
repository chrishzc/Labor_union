from datetime import datetime
from decimal import Decimal

import pytest

from services import subsidy_claim_workflow as workflow


class FakeCursor:
    def __init__(self, *, batch=None, assignments=None, items=None):
        self.batch = batch
        self.assignments = assignments or []
        self.items = items or []
        self.current = None
        self.calls = []
        self.lastrowid = 40

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, params=None):
        compact = " ".join(sql.split())
        self.calls.append((compact, params))
        if compact.startswith("SELECT * FROM subsidy_claim_batches"):
            self.current = self.batch
        elif "FROM case_staff_assignments" in compact:
            self.current = self.assignments
        elif "FROM subsidy_claim_batch_items" in compact:
            self.current = self.items
        elif compact.startswith("INSERT INTO subsidy_claim_batches"):
            self.lastrowid = 40
        elif compact.startswith("INSERT INTO subsidy_claim_batch_items"):
            self.lastrowid += 1

    def fetchone(self):
        return self.current

    def fetchall(self):
        return list(self.current or [])


class FakeConnection:
    def __init__(self, cursor):
        self._cursor = cursor
        self.commits = 0
        self.rollbacks = 0
        self.closed = False

    def cursor(self):
        return self._cursor

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        self.closed = True


def _items():
    return [
        {"case_no": "A", "assignment_id": 1, "staff_id": 7,
         "claimed_hours": 10, "unit_price": 300, "requested_amount": 3000},
        {"case_no": "B", "assignment_id": 2, "staff_id": 9,
         "claimed_hours": 20, "unit_price": 350, "requested_amount": 7000},
    ]


def _stored_items(approved=False):
    return [
        {"id": 11, "batch_id": 5, "case_no": "A", "assignment_id": 1, "staff_id": 7,
         "claimed_hours": Decimal("10"), "unit_price": Decimal("300"),
         "requested_amount": Decimal("3000"), "approved_amount": Decimal("3000" if approved else "0"),
         "paid_amount": Decimal("0")},
        {"id": 12, "batch_id": 5, "case_no": "B", "assignment_id": 2, "staff_id": 9,
         "claimed_hours": Decimal("20"), "unit_price": Decimal("350"),
         "requested_amount": Decimal("7000"), "approved_amount": Decimal("7000" if approved else "0"),
         "paid_amount": Decimal("0")},
    ]


def _batch(status="submitted"):
    return {"id": 5, "application_year": 2026, "quarter": 2, "revision": 1,
            "status": status, "requested_amount": Decimal("10000"),
            "approved_amount": Decimal("10000" if status == "approved" else "0"),
            "paid_amount": Decimal("0")}


def test_create_batch_persists_exact_snapshot(monkeypatch):
    cursor = FakeCursor(assignments=[
        {"id": 1, "case_no": "A", "staff_id": 7},
        {"id": 2, "case_no": "B", "staff_id": 9},
    ])
    conn = FakeConnection(cursor)
    monkeypatch.setattr(workflow, "get_connection", lambda: conn)

    result = workflow.create_subsidy_claim_batch(2026, 2, 1, _items())

    assert result["result"] == "created"
    assert result["batch"]["requested_amount"] == Decimal("10000")
    assert len(result["batch"]["items"]) == 2
    assert conn.commits == 1 and conn.rollbacks == 0 and conn.closed
    assert sum("INSERT INTO subsidy_claim_batch_items" in sql for sql, _ in cursor.calls) == 2


def test_create_rejects_amount_formula_and_duplicate_assignment_before_database(monkeypatch):
    monkeypatch.setattr(workflow, "get_connection", lambda: pytest.fail("database must not be opened"))
    bad_amount = _items()
    bad_amount[0]["requested_amount"] = 1
    with pytest.raises(ValueError, match=r"claimed_hours \* unit_price"):
        workflow.create_subsidy_claim_batch(2026, 2, 1, bad_amount)

    duplicate = _items()
    duplicate[1]["assignment_id"] = 1
    with pytest.raises(ValueError, match="repeat assignment_id"):
        workflow.create_subsidy_claim_batch(2026, 2, 1, duplicate)


def test_assignment_identity_mismatch_returns_review_without_insert(monkeypatch):
    cursor = FakeCursor(assignments=[
        {"id": 1, "case_no": "WRONG", "staff_id": 7},
        {"id": 2, "case_no": "B", "staff_id": 9},
    ])
    conn = FakeConnection(cursor)
    monkeypatch.setattr(workflow, "get_connection", lambda: conn)

    result = workflow.create_subsidy_claim_batch(2026, 2, 1, _items())

    assert result["result"] == "review_required"
    assert conn.rollbacks == 1
    assert not any(sql.startswith("INSERT") for sql, _ in cursor.calls)


def test_existing_revision_is_idempotent_only_for_identical_snapshot(monkeypatch):
    cursor = FakeCursor(batch={**_batch("draft")}, items=_stored_items())
    conn = FakeConnection(cursor)
    monkeypatch.setattr(workflow, "get_connection", lambda: conn)
    result = workflow.create_subsidy_claim_batch(2026, 2, 1, _items())
    assert result["result"] == "created" and result["idempotent"] is True

    changed = _items()
    changed[0]["claimed_hours"] = 5
    changed[0]["requested_amount"] = 1500
    cursor = FakeCursor(batch={**_batch("draft")}, items=_stored_items())
    conn = FakeConnection(cursor)
    monkeypatch.setattr(workflow, "get_connection", lambda: conn)
    result = workflow.create_subsidy_claim_batch(2026, 2, 1, changed)
    assert result["result"] == "review_required"
    assert conn.rollbacks == 1


def test_submit_requires_complete_snapshot_and_freezes_batch(monkeypatch):
    cursor = FakeCursor(batch=_batch("draft"), items=_stored_items())
    conn = FakeConnection(cursor)
    monkeypatch.setattr(workflow, "get_connection", lambda: conn)

    result = workflow.submit_subsidy_claim_batch(5, datetime(2026, 7, 15, 10, 0))

    assert result["result"] == "submitted"
    assert any("SET status = 'submitted'" in sql for sql, _ in cursor.calls)
    assert conn.commits == 1


def test_partial_or_missing_approval_stays_submitted_without_updates(monkeypatch):
    cursor = FakeCursor(batch=_batch("submitted"), items=_stored_items())
    conn = FakeConnection(cursor)
    monkeypatch.setattr(workflow, "get_connection", lambda: conn)

    result = workflow.approve_subsidy_claim_batch(
        5, [{"item_id": 11, "approved_amount": 2999}], datetime(2026, 7, 16, 10, 0),
    )

    assert result["result"] == "review_required"
    assert result["batch"]["status"] == "submitted"
    assert conn.rollbacks == 1
    assert not any(sql.startswith("UPDATE") for sql, _ in cursor.calls)


def test_full_approval_updates_every_item_and_batch(monkeypatch):
    cursor = FakeCursor(batch=_batch("submitted"), items=_stored_items())
    conn = FakeConnection(cursor)
    monkeypatch.setattr(workflow, "get_connection", lambda: conn)

    result = workflow.approve_subsidy_claim_batch(5, [
        {"item_id": 11, "approved_amount": 3000},
        {"item_id": 12, "approved_amount": 7000},
    ], datetime(2026, 7, 16, 10, 0))

    assert result["result"] == "approved"
    assert result["batch"]["approved_amount"] == Decimal("10000")
    assert sum("UPDATE subsidy_claim_batch_items" in sql for sql, _ in cursor.calls) == 2
    assert any("SET status = 'approved'" in sql for sql, _ in cursor.calls)
    assert conn.commits == 1 and conn.rollbacks == 0
