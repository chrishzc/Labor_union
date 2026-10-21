from types import SimpleNamespace

import pytest

from infrastructure.mysql.order_terms_read_model import (
    _historical_precision_restarted,
    lock_staff_mutexes,
    _select_payroll_assignment_ancestry,
)


def test_empty_impacted_staff_set_requires_no_mutex_query():
    cursor = SimpleNamespace(execute=lambda *_args: pytest.fail("unexpected SQL"))

    lock_staff_mutexes(cursor, ())


class _RestartCursor:
    def __init__(self, row):
        self.row = row
        self.statement = None
        self.parameters = None

    def execute(self, statement, parameters):
        self.statement = " ".join(statement.split())
        self.parameters = parameters

    def fetchone(self):
        return self.row


def test_historical_precision_restart_provenance_uses_the_immutable_lifecycle_event():
    cursor = _RestartCursor({"id": 17})

    assert _historical_precision_restarted(cursor, "CASE-HISTORY", lock=True) is True
    assert "trigger_event='orders_historical_precision_restart'" in cursor.statement
    assert "ORDER BY id DESC LIMIT 1 FOR UPDATE" in cursor.statement
    assert cursor.parameters == ("CASE-HISTORY", "訂單成立")


def test_missing_historical_precision_restart_event_does_not_enable_the_exception():
    cursor = _RestartCursor(None)

    assert _historical_precision_restarted(cursor, "CASE-NORMAL", lock=False) is False


def test_payment_family_ancestry_stops_at_a_different_caregiver_so_returning_staff_do_not_inherit_old_adjustments():
    class Cursor:
        def execute(self, _sql, _params):
            pass

        def fetchall(self):
            return (
                {"new_assignment_id": 2, "old_assignment_identity": "assignment:1", "old_staff_id": 7},
                {"new_assignment_id": 3, "old_assignment_identity": "assignment:2", "old_staff_id": 7},
                {"new_assignment_id": 4, "old_assignment_identity": "assignment:2", "old_staff_id": 7},
                {"new_assignment_id": 5, "old_assignment_identity": "assignment:4", "old_staff_id": 8},
            )

    result = _select_payroll_assignment_ancestry(Cursor(), "CASE", (
        {"id": 3, "staff_id": 7}, {"id": 4, "staff_id": 8}, {"id": 5, "staff_id": 7}), False)
    assert result == {3: (1, 2), 4: (), 5: ()}


def test_payment_family_rejects_cycles_without_treating_database_identity_order_as_business_history():
    class Cursor:
        def execute(self, _sql, _params):
            pass

        def fetchall(self):
            return self.rows

    cursor = Cursor()
    cursor.rows = ({"new_assignment_id": 3, "old_assignment_identity": "assignment:20", "old_staff_id": 7},)
    assert _select_payroll_assignment_ancestry(cursor, "CASE", ({"id": 3, "staff_id": 7},), False) == {3: (20,)}
    cursor.rows += ({"new_assignment_id": 20, "old_assignment_identity": "assignment:3", "old_staff_id": 7},)
    with pytest.raises(ValueError, match="payroll_assignment_lineage_invalid"):
        _select_payroll_assignment_ancestry(cursor, "CASE", ({"id": 3, "staff_id": 7},), False)


def test_payment_history_uses_canonical_links_even_when_cached_flag_is_not_set_or_net_payment_was_fully_returned():
    from infrastructure.mysql.order_terms_read_model import _STAFF_OBLIGATIONS_SQL
    from infrastructure.mysql.payroll_rebuild_repository import _EXISTING_OBLIGATION_SELECT_SQL

    for query in (_STAFF_OBLIGATIONS_SQL, _EXISTING_OBLIGATION_SELECT_SQL):
        assert "OR EXISTS(SELECT 1 FROM staff_payout_obligation_links history" in query
        assert ")) AS payout_history_exists" in query
