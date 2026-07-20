from datetime import datetime
from decimal import Decimal

import pymysql
import pytest

from services.finance_alert_events import append_finance_alert_event


NOW = datetime(2026, 7, 16, 16, 0, 0)


class Connection:
    def __init__(self, autocommit=False):
        self.autocommit = autocommit

    def get_autocommit(self):
        return self.autocommit


class Cursor:
    def __init__(self, fetches, *, autocommit=False, fail_on=None):
        self.fetches = list(fetches)
        self.connection = Connection(autocommit)
        self.fail_on = fail_on
        self.calls = []

    def execute(self, sql, params=None):
        normalized = " ".join(sql.split())
        self.calls.append((normalized, params))
        if (
            self.fail_on == "INTEGRITY"
            and normalized.startswith("INSERT INTO finance_alert_events")
        ):
            self.fail_on = None
            raise pymysql.err.IntegrityError(1062, "duplicate")
        if self.fail_on and self.fail_on in normalized:
            raise RuntimeError("injected database failure")

    def fetchone(self):
        return self.fetches.pop(0)


def alert(**changes):
    row = {
        "id": 41,
        "status": "claimed",
        "claimed_by": "owner",
        "claimed_at": NOW,
        "resolved_by": None,
        "resolved_at": None,
        "resolution_reason": None,
    }
    row.update(changes)
    return row


def event(**changes):
    row = {
        "id": 90,
        "alert_id": 41,
        "event_key": "alert:41:claimed",
        "event_type": "claimed",
        "source_domain": "finance_alert",
        "source_type": "finance_alert",
        "source_id": "41",
        "actor": "owner",
        "reason": None,
        "event_snapshot": '{"status":"claimed"}',
        "occurred_at": NOW,
        "created_at": NOW,
    }
    row.update(changes)
    return row


def workflow_kwargs(**changes):
    values = {
        "alert_id": 41,
        "event_key": "alert:41:claimed",
        "event_type": "claimed",
        "source_domain": "finance_alert",
        "source_type": "finance_alert",
        "source_id": "41",
        "actor": "owner",
        "event_snapshot": {"status": "claimed"},
        "occurred_at": NOW,
    }
    values.update(changes)
    return values


def formal(transaction_type, status, reference="ref-1", **changes):
    row = {
        "id": 55,
        "transaction_type": transaction_type,
        "transaction_status": status,
        "external_reference": reference,
    }
    row.update(changes)
    return row


def formal_kwargs(event_type, **changes):
    values = {
        "alert_id": 41,
        "event_key": f"staff-transfer:55:{event_type}",
        "event_type": event_type,
        "source_domain": "staff_payment",
        "source_type": "staff_actual_transfer",
        "source_id": 55,
        "event_snapshot": {"status": event_type, "amount": Decimal("1000")},
        "occurred_at": NOW,
    }
    values.update(changes)
    return values


def test_append_claimed_event_and_idempotent_rerun():
    created = event()
    first = Cursor([alert(), None, created])
    second = Cursor([alert(), created])

    result = append_finance_alert_event(first, **workflow_kwargs())
    repeated = append_finance_alert_event(second, **workflow_kwargs())

    assert result == {"result": "created", "event": created}
    assert repeated == {"result": "existing", "event": created}
    assert any("INSERT INTO finance_alert_events" in sql for sql, _ in first.calls)
    assert not any(sql.startswith("INSERT") for sql, _ in second.calls)


def test_resolved_event_must_match_projection_actor_and_reason():
    resolved = alert(
        status="resolved",
        resolved_by="reviewer",
        resolved_at=NOW,
        resolution_reason="人工確認",
    )
    cursor = Cursor([resolved])

    with pytest.raises(ValueError, match="reason does not match"):
        append_finance_alert_event(
            cursor,
            **workflow_kwargs(
                event_key="alert:41:resolved",
                event_type="resolved",
                actor="reviewer",
                reason="不同原因",
                event_snapshot={"status": "resolved"},
            ),
        )


@pytest.mark.parametrize(
    ("event_type", "transaction_type", "status"),
    [
        ("failed", "transfer", "failed"),
        ("returned", "return", "succeeded"),
        ("reversed", "reversal", "succeeded"),
        ("reversed", "transfer", "reversed"),
    ],
)
def test_formal_event_requires_matching_existing_transaction(
    event_type,
    transaction_type,
    status,
):
    created = event(
        event_key=f"staff-transfer:55:{event_type}",
        event_type=event_type,
        source_domain="staff_payment",
        source_type="staff_actual_transfer",
        source_id="55",
        actor=None,
        event_snapshot=f'{{"amount":"1000","status":"{event_type}"}}',
    )
    cursor = Cursor([alert(), formal(transaction_type, status), None, created])

    result = append_finance_alert_event(
        cursor,
        **formal_kwargs(event_type),
    )

    assert result["result"] == "created"
    source_sql = next(
        sql for sql, _ in cursor.calls if "FROM staff_actual_transfers" in sql
    )
    assert "WHERE id=%s" in source_sql and "FOR UPDATE" in source_sql


@pytest.mark.parametrize(
    ("source_type", "table"),
    [
        ("client_payment_transaction", "client_payment_transactions"),
        ("staff_payment_transaction", "staff_payment_transactions"),
        ("staff_actual_transfer", "staff_actual_transfers"),
        (
            "government_subsidy_transaction",
            "government_subsidy_transactions",
        ),
    ],
)
def test_each_allowed_source_type_uses_its_fixed_table(source_type, table):
    created = event(
        event_key=f"{source_type}:55:failed",
        event_type="failed",
        source_domain="finance",
        source_type=source_type,
        source_id="55",
        actor=None,
        event_snapshot='{"amount":"1000","status":"failed"}',
    )
    cursor = Cursor([alert(), formal("transfer", "failed"), None, created])

    result = append_finance_alert_event(
        cursor,
        **formal_kwargs(
            "failed",
            event_key=f"{source_type}:55:failed",
            source_type=source_type,
            source_domain="finance",
        ),
    )

    assert result["result"] == "created"
    assert any(f"FROM {table}" in sql for sql, _ in cursor.calls)


@pytest.mark.parametrize(
    ("event_type", "transaction_type", "status"),
    [
        ("failed", "transfer", "succeeded"),
        ("returned", "transfer", "succeeded"),
        ("returned", "return", "failed"),
        ("reversed", "transfer", "succeeded"),
    ],
)
def test_formal_event_rejects_mismatched_transaction(
    event_type,
    transaction_type,
    status,
):
    cursor = Cursor([alert(), formal(transaction_type, status)])

    with pytest.raises(ValueError):
        append_finance_alert_event(cursor, **formal_kwargs(event_type))

    assert not any(sql.startswith("INSERT") for sql, _ in cursor.calls)


def test_retransfer_requires_distinct_successful_new_reference():
    created = event(
        event_key="staff-transfer:56:retransferred",
        event_type="retransferred",
        source_domain="staff_payment",
        source_type="staff_actual_transfer",
        source_id="56",
        actor=None,
        event_snapshot=(
            '{"amount":"1000","original_source_id":55,'
            '"status":"retransferred"}'
        ),
    )
    cursor = Cursor(
        [
            alert(),
            formal("transfer", "succeeded", "new-ref", id=56),
            formal("transfer", "failed", "old-ref", id=55),
            None,
            created,
        ]
    )

    result = append_finance_alert_event(
        cursor,
        **formal_kwargs(
            "retransferred",
            event_key="staff-transfer:56:retransferred",
            source_id=56,
            original_source_id=55,
        ),
    )

    assert result["result"] == "created"
    assert sum(
        "FROM staff_actual_transfers" in sql for sql, _ in cursor.calls
    ) == 2


def test_retransfer_original_source_is_part_of_immutable_snapshot():
    existing = event(
        event_key="staff-transfer:56:retransferred",
        event_type="retransferred",
        source_domain="staff_payment",
        source_type="staff_actual_transfer",
        source_id="56",
        actor=None,
        event_snapshot=(
            '{"amount":"1000","original_source_id":54,'
            '"status":"retransferred"}'
        ),
    )
    cursor = Cursor(
        [
            alert(),
            formal("transfer", "succeeded", "new-ref", id=56),
            formal("transfer", "failed", "old-ref", id=55),
            existing,
        ]
    )

    with pytest.raises(ValueError, match="immutable event data"):
        append_finance_alert_event(
            cursor,
            **formal_kwargs(
                "retransferred",
                event_key="staff-transfer:56:retransferred",
                source_id=56,
                original_source_id=55,
            ),
        )


def test_retransfer_rejects_same_external_reference():
    cursor = Cursor(
        [
            alert(),
            formal("transfer", "succeeded", "same-ref", id=56),
            formal("transfer", "failed", "same-ref", id=55),
        ]
    )

    with pytest.raises(ValueError, match="new succeeded"):
        append_finance_alert_event(
            cursor,
            **formal_kwargs(
                "retransferred",
                source_id=56,
                original_source_id=55,
            ),
        )


def test_arbitrary_source_table_name_is_rejected():
    cursor = Cursor([alert()])

    with pytest.raises(ValueError, match="allowed formal"):
        append_finance_alert_event(
            cursor,
            **formal_kwargs("failed", source_type="finance_alert_events"),
        )

    assert all("finance_alert_events WHERE id=" not in sql for sql, _ in cursor.calls)


@pytest.mark.parametrize("source_id", [True, 55.9, Decimal("55"), "55.0"])
def test_formal_source_id_rejects_non_integer_forms(source_id):
    cursor = Cursor([alert()])

    with pytest.raises(ValueError, match="positive integer"):
        append_finance_alert_event(
            cursor,
            **formal_kwargs("failed", source_id=source_id),
        )

    assert not any("FROM staff_actual_transfers" in sql for sql, _ in cursor.calls)


def test_formal_source_id_is_persisted_in_canonical_decimal_form():
    created = event(
        event_key="staff-transfer:55:failed",
        event_type="failed",
        source_domain="staff_payment",
        source_type="staff_actual_transfer",
        source_id="55",
        actor=None,
        event_snapshot='{"amount":"1000","status":"failed"}',
    )
    cursor = Cursor([alert(), formal("transfer", "failed"), None, created])

    result = append_finance_alert_event(
        cursor,
        **formal_kwargs("failed", source_id="055"),
    )

    assert result["result"] == "created"
    insert_params = next(
        params
        for sql, params in cursor.calls
        if sql.startswith("INSERT INTO finance_alert_events")
    )
    assert insert_params[5] == "55"


@pytest.mark.parametrize("event_type", ["failed", "returned", "reversed"])
def test_original_source_id_is_rejected_outside_retransfer(event_type):
    cursor = Cursor([alert()])

    with pytest.raises(ValueError, match="only valid for retransferred"):
        append_finance_alert_event(
            cursor,
            **formal_kwargs(
                event_type,
                original_source_id=54,
            ),
        )

    assert not any("FROM staff_actual_transfers" in sql for sql, _ in cursor.calls)


def test_event_key_conflict_checks_all_immutable_fields():
    cursor = Cursor([alert(), event(reason="changed")])

    with pytest.raises(ValueError, match="immutable event data"):
        append_finance_alert_event(cursor, **workflow_kwargs())


def test_insert_failure_rolls_back_savepoint():
    cursor = Cursor([alert(), None], fail_on="INSERT INTO finance_alert_events")

    with pytest.raises(RuntimeError, match="injected"):
        append_finance_alert_event(cursor, **workflow_kwargs())

    assert any(
        sql == "ROLLBACK TO SAVEPOINT finance_alert_event_append"
        for sql, _ in cursor.calls
    )
    assert cursor.calls[-1][0] == "RELEASE SAVEPOINT finance_alert_event_append"


def test_concurrent_identical_insert_returns_existing():
    concurrent = event()
    cursor = Cursor(
        [alert(), None, concurrent],
        fail_on="INTEGRITY",
    )

    result = append_finance_alert_event(cursor, **workflow_kwargs())

    assert result == {"result": "existing", "event": concurrent}
    assert any(
        sql == "ROLLBACK TO SAVEPOINT finance_alert_event_append"
        for sql, _ in cursor.calls
    )


def test_autocommit_is_rejected_before_queries():
    cursor = Cursor([], autocommit=True)

    with pytest.raises(RuntimeError, match="autocommit disabled"):
        append_finance_alert_event(cursor, **workflow_kwargs())

    assert cursor.calls == []
