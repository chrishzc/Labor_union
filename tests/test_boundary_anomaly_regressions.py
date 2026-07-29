"""Regression tests locking in the boundary-anomaly defenses confirmed to exist.

Each test below corresponds to one row in
document/資料庫、資料處理/邊界異常資料_UI驗收落差清單.md marked ✅ or the "conflict
detection" half of a ⚠️ row, derived from the fixtures in
scripts/seed_boundary_anomalies.py. Anomalies marked ❌ in that gap list have no
implemented defense to test yet and are intentionally not represented here.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pytest

from services.finance_transaction_classifier import classify_finance_transaction
from services.finance_alert_detection import create_or_get_finance_alert
from services.finance_alert_workflow import claim_finance_alert, resolve_finance_alert
from services import subsidy_claim_workflow


NOW = datetime(2026, 7, 15, 9, 8, 7)


# ---------------------------------------------------------------------------
# D1 / D4 / D6 / E2: services/finance_transaction_classifier.py
# (pure function, no DB/mocking needed)
# ---------------------------------------------------------------------------

def _bank_row(**overrides):
    row = {
        "format_id": "sinopac",
        "source_file": "test.xlsx",
        "source_bank_account": "UNION-TEST-001",
        "sheet_name": "sheet1",
        "source_row": 1,
        "source_reference": None,
        "transaction_date": "2026-07-15",
        "transaction_time": None,
        "posting_date": None,
        "value_date": None,
        "debit": None,
        "credit": Decimal("1000"),
        "direction": "incoming",
        "balance": None,
        "currency": "TWD",
        "summary": "test",
        "memo": "test",
        "counterparty_name": None,
        "counterparty_account": None,
        "cancellation_code": None,
        "bank_references": {},
        "warnings": [],
        "raw_payload": {},
    }
    row.update(overrides)
    return row


def test_d1_invalid_virtual_account_is_non_business_review():
    """A malformed 銷帳編號 (contains letters) must never resolve to a client_receipt."""
    row = _bank_row(bank_references={"銷帳編號": "997816ABC12345"})

    result = classify_finance_transaction(row, {}, {})

    assert result["classification_type"] == "non_business_review"
    assert result["reason"] == "sinopac_invalid_or_missing_virtual_account"


def test_d4_missing_payment_reference_is_non_business_review():
    """A receipt with no 銷帳編號 must not be auto-reconciled by name/memo alone."""
    row = _bank_row(bank_references={}, summary="陳小美合約款", memo="陳小美合約款")

    result = classify_finance_transaction(row, {}, {})

    assert result["classification_type"] == "non_business_review"


def test_d6_shared_refund_account_is_non_business_review():
    """An outgoing refund whose account maps to more than one client must not auto-pick one."""
    account = "807-0014-12345678"
    row = _bank_row(
        format_id="taishin", direction="outgoing", debit=Decimal("1000"), credit=None,
        counterparty_account=account,
    )

    result = classify_finance_transaction(row, {account: [101, 102]}, {})

    assert result["classification_type"] == "non_business_review"
    assert result["reason"] == "counterparty_account_multiple_matches"


def test_e2_shared_staff_bank_account_is_non_business_review():
    """An outgoing staff payout whose account maps to more than one staff must not auto-pick one."""
    account = "812-000000000000"
    row = _bank_row(
        format_id="taishin", direction="outgoing", debit=Decimal("18000"), credit=None,
        counterparty_account=account,
    )

    result = classify_finance_transaction(row, {}, {account: [201, 202]})

    assert result["classification_type"] == "non_business_review"
    assert result["reason"] == "counterparty_account_multiple_matches"


# ---------------------------------------------------------------------------
# F1 / F2: services/finance_alert_workflow.py conflict detection
# ---------------------------------------------------------------------------

class _Connection:
    def __init__(self, autocommit=False):
        self._autocommit = autocommit

    def get_autocommit(self):
        return self._autocommit


class _Cursor:
    """Minimal fake matching the shape finance_alert_workflow/detection expect from pymysql."""

    def __init__(self, fetches, *, lastrowid=41):
        self.fetches = list(fetches)
        self.connection = _Connection(autocommit=False)
        self.calls = []
        self.lastrowid = lastrowid

    def execute(self, sql, params=None):
        self.calls.append((" ".join(sql.split()), params))

    def fetchone(self):
        return self.fetches.pop(0)


def _alert_row(**changes):
    row = {
        "id": 41,
        "alert_key": "finance-alert:key",
        "alert_code": "review_required",
        "source_domain": "STAFF",
        "source_type": "boundary_fixture",
        "source_id": "f3-domain-coverage-staff",
        "finance_import_row_id": None,
        "finance_import_batch_id": None,
        "reason": "邊界測試",
        "expected_amount": None,
        "actual_amount": None,
        "difference_amount": None,
        "candidate_snapshot": "{}",
        "status": "open",
        "claimed_by": None,
        "claimed_at": None,
        "resolved_by": None,
        "resolved_at": None,
        "resolution_reason": None,
        "created_at": NOW,
        "updated_at": NOW,
    }
    row.update(changes)
    return row


def test_f1_claiming_an_already_claimed_alert_by_someone_else_conflicts():
    """Mirrors seed F1 (alert_claim_conflict): a second operator must not steal a claim."""
    cursor = _Cursor([_alert_row(status="claimed", claimed_by="操作員A", claimed_at=NOW)])

    result = claim_finance_alert(cursor, alert_id=41, operator="操作員B")

    assert result["result"] == "conflict"
    assert result["alert"]["claimed_by"] == "操作員A"


def test_f2_resolving_an_already_resolved_alert_with_a_different_reason_conflicts():
    """Mirrors seed F2 (resolved_alert_history): a resolved alert must not be silently reopened/edited."""
    cursor = _Cursor([
        _alert_row(
            status="resolved",
            resolved_by="操作員B",
            resolved_at=NOW,
            resolution_reason="已線下聯繫補齊金額",
        )
    ])

    result = resolve_finance_alert(
        cursor, alert_id=41, operator="操作員C", reason="其他理由",
    )

    assert result["result"] == "conflict"
    assert result["alert"]["resolution_reason"] == "已線下聯繫補齊金額"


# ---------------------------------------------------------------------------
# F3: services/finance_alert_detection.py — independent alerts per domain
# ---------------------------------------------------------------------------

def test_f3_alerts_for_different_domains_are_created_independently():
    """Mirrors seed F3 (alert_domain_coverage): CLIENT/RETURN/SUBSIDY/STAFF must
    each get their own alert_key and not collide with one another."""
    created_keys = set()
    for domain in ("CLIENT", "RETURN", "SUBSIDY", "STAFF"):
        cursor = _Cursor([None, _alert_row(source_domain=domain, id=hash(domain) % 1000)])

        result = create_or_get_finance_alert(
            cursor,
            alert_code="review_required",
            source_domain=domain,
            source_type="boundary_fixture",
            source_id=f"f3-domain-coverage-{domain.lower()}",
            reason=f"邊界測試：{domain} 領域警示涵蓋",
            candidate_snapshot={"fixture": "f3_alert_domain_coverage", "domain": domain},
            detected_at=NOW,
        )

        assert result["result"] == "created"
        alert_key = next(
            params[0] for sql, params in cursor.calls if sql.startswith("INSERT INTO finance_alerts")
        )
        assert alert_key not in created_keys, f"{domain} produced a colliding alert_key"
        created_keys.add(alert_key)


# ---------------------------------------------------------------------------
# D9: services/subsidy_claim_workflow.py — same-amount batches don't collide
# ---------------------------------------------------------------------------

class _BatchCursor:
    def __init__(self, *, batch=None, assignments=None, items=None):
        self.batch = batch
        self.assignments = assignments or []
        self.items = items or []
        self.current = None
        self.lastrowid = 40

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, params=None):
        compact = " ".join(sql.split())
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


class _BatchConnection:
    def __init__(self, cursor):
        self._cursor = cursor
        self.commits = 0
        self.rollbacks = 0

    def cursor(self):
        return self._cursor

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        pass


def test_d9_two_batches_with_the_same_requested_amount_do_not_collide(monkeypatch):
    """Mirrors seed D9 (multi_batch_same_amount_ambiguity): the workflow keys batches
    by (application_year, quarter, revision), not by amount, so two batches that both
    request 5000.00 in different quarters must both succeed as independent batches —
    there is no automatic ambiguity detection between them (see gap list D9)."""
    item = {
        "case_no": "115900020", "assignment_id": 1, "staff_id": 7,
        "claimed_hours": 50, "unit_price": 100, "requested_amount": 5000,
    }
    for quarter in (1, 2):
        cursor = _BatchCursor(assignments=[{"id": 1, "case_no": "115900020", "staff_id": 7}])
        conn = _BatchConnection(cursor)
        monkeypatch.setattr(subsidy_claim_workflow, "get_connection", lambda: conn)

        result = subsidy_claim_workflow.create_subsidy_claim_batch(2026, quarter, 1, [item])

        assert result["result"] == "created"
        assert result["idempotent"] is False
        assert result["batch"]["requested_amount"] == Decimal("5000")
