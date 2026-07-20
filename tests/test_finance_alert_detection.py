from datetime import datetime
from decimal import Decimal

import pytest

from services.finance_alert_detection import create_or_get_finance_alert


NOW = datetime(2026, 7, 16, 12, 0, 0)


class Cursor:
    def __init__(self, fetches, *, lastrowid=41, autocommit=False, fail_on=None):
        self.fetches = list(fetches)
        self.lastrowid = lastrowid
        self.calls = []
        self.connection = Connection(autocommit)
        self.fail_on = fail_on

    def execute(self, sql, params=None):
        normalized = " ".join(sql.split())
        self.calls.append((normalized, params))
        if self.fail_on and self.fail_on in normalized:
            raise RuntimeError("injected database failure")

    def fetchone(self):
        return self.fetches.pop(0)


class Connection:
    def __init__(self, autocommit):
        self.autocommit = autocommit

    def get_autocommit(self):
        return self.autocommit


def alert(**changes):
    row = {
        "id": 41,
        "alert_key": (
            "finance-alert:"
            "71677dc63006075955db7d87bcb15f337fd574ec972096eba9f40cdd01a8e95a"
        ),
        "alert_code": "government_subsidy_unmatched",
        "source_domain": "government_subsidy",
        "source_type": "finance_import_row",
        "source_id": "12",
        "finance_import_row_id": 12,
        "finance_import_batch_id": 7,
        "reason": "找不到唯一核銷批次",
        "expected_amount": Decimal("1000.00"),
        "actual_amount": Decimal("1000.00"),
        "difference_amount": Decimal("0.00"),
        "candidate_snapshot": '{"amount":"1000","ids":[3,5]}',
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


def detected_event(**changes):
    row = {
        "id": 90,
        "alert_id": 41,
        "event_key": (
            "finance-alert-detected:"
            "d3fe2241c96b79b314a11764ae7badf6a1b0422022a6a2aec82acc955ab07918"
        ),
        "event_type": "detected",
        "source_domain": "government_subsidy",
        "source_type": "finance_import_row",
        "source_id": "12",
        "actor": None,
        "reason": "找不到唯一核銷批次",
        "event_snapshot": (
            '{"alert_code":"government_subsidy_unmatched",'
            '"candidate_snapshot":{"amount":"1000","ids":[3,5]},'
            '"finance_import_batch_id":7,"finance_import_row_id":12}'
        ),
        "occurred_at": NOW,
        "created_at": NOW,
    }
    row.update(changes)
    return row


def detection_kwargs(**changes):
    values = {
        "alert_code": "government_subsidy_unmatched",
        "source_domain": "government_subsidy",
        "source_type": "finance_import_row",
        "source_id": "12",
        "finance_import_row_id": 12,
        "finance_import_batch_id": 7,
        "reason": "找不到唯一核銷批次",
        "expected_amount": Decimal("1000"),
        "actual_amount": Decimal("1000.0"),
        "difference_amount": Decimal("-0"),
        "candidate_snapshot": {"ids": [3, 5], "amount": Decimal("1000.00")},
        "detected_at": NOW,
    }
    values.update(changes)
    return values


def test_create_alert_and_detected_event_atomically():
    cursor = Cursor([{"id": 12}, None, alert()])

    result = create_or_get_finance_alert(cursor, **detection_kwargs())

    assert result == {"result": "created", "alert": alert()}
    assert any("INSERT INTO finance_alerts" in sql for sql, _ in cursor.calls)
    assert any(
        "INSERT INTO finance_alert_events" in sql and "'detected'" in sql
        for sql, _ in cursor.calls
    )
    alert_insert = next(
        params for sql, params in cursor.calls if "INSERT INTO finance_alerts" in sql
    )
    assert alert_insert[-1] == '{"amount":"1000","ids":[3,5]}'
    assert any(sql == "SAVEPOINT finance_alert_detection" for sql, _ in cursor.calls)
    assert any(
        sql == "RELEASE SAVEPOINT finance_alert_detection"
        for sql, _ in cursor.calls
    )


def test_detected_event_failure_rolls_back_alert_savepoint():
    cursor = Cursor(
        [{"id": 12}, None],
        fail_on="INSERT INTO finance_alert_events",
    )

    with pytest.raises(RuntimeError, match="injected database failure"):
        create_or_get_finance_alert(cursor, **detection_kwargs())

    assert any(
        sql == "ROLLBACK TO SAVEPOINT finance_alert_detection"
        for sql, _ in cursor.calls
    )
    assert cursor.calls[-1][0] == "RELEASE SAVEPOINT finance_alert_detection"


def test_autocommit_connection_is_rejected_before_database_access():
    cursor = Cursor([], autocommit=True)

    with pytest.raises(RuntimeError, match="autocommit disabled"):
        create_or_get_finance_alert(cursor, **detection_kwargs())

    assert cursor.calls == []


def test_identical_rerun_returns_existing_without_writes_or_reopen():
    existing = alert(status="resolved", resolved_by="owner", resolved_at=NOW,
                     resolution_reason="已人工確認")
    cursor = Cursor([{"id": 12}, existing, detected_event()])

    result = create_or_get_finance_alert(cursor, **detection_kwargs())

    assert result["result"] == "existing"
    assert result["alert"]["status"] == "resolved"
    assert not any(sql.startswith(("INSERT", "UPDATE")) for sql, _ in cursor.calls)


def test_same_alert_key_with_changed_snapshot_fails_fast():
    cursor = Cursor([{"id": 12}, alert()])

    with pytest.raises(ValueError, match="immutable detection data"):
        create_or_get_finance_alert(
            cursor,
            **detection_kwargs(candidate_snapshot={"ids": [3], "amount": 1000}),
        )

    assert not any(sql.startswith(("INSERT", "UPDATE")) for sql, _ in cursor.calls)


def test_existing_alert_without_detected_event_is_partial_residue():
    cursor = Cursor([{"id": 12}, alert(), None])

    with pytest.raises(RuntimeError, match="missing its detected event"):
        create_or_get_finance_alert(cursor, **detection_kwargs())


def test_detected_event_time_is_part_of_immutable_rerun_input():
    cursor = Cursor([
        {"id": 12},
        alert(),
        detected_event(occurred_at=datetime(2026, 7, 17, 12, 0, 0)),
    ])

    with pytest.raises(ValueError, match="detected event conflicts"):
        create_or_get_finance_alert(cursor, **detection_kwargs())


def test_row_and_batch_must_have_a_canonical_or_occurrence_relation():
    cursor = Cursor([None])

    with pytest.raises(ValueError, match="row/batch relation"):
        create_or_get_finance_alert(cursor, **detection_kwargs())

    assert "finance_import_occurrences" in cursor.calls[0][0]


def test_bank_alert_identity_uses_row_id_before_caller_source_identity():
    first = Cursor([{"id": 12}, None, alert()])
    second = Cursor([{"id": 12}, None, alert()])

    create_or_get_finance_alert(first, **detection_kwargs(source_id="caller-a"))
    create_or_get_finance_alert(second, **detection_kwargs(source_id="caller-b"))

    first_key = next(
        params[0] for sql, params in first.calls if "INSERT INTO finance_alerts" in sql
    )
    second_key = next(
        params[0] for sql, params in second.calls if "INSERT INTO finance_alerts" in sql
    )
    assert first_key == second_key


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("alert_code", ""),
        ("source_domain", " "),
        ("source_type", None),
        ("source_id", ""),
        ("expected_amount", Decimal("-0.01")),
        ("actual_amount", Decimal("NaN")),
    ],
)
def test_invalid_detection_input_fails_before_database_access(field, value):
    cursor = Cursor([])
    kwargs = detection_kwargs()
    kwargs[field] = value

    with pytest.raises(ValueError):
        create_or_get_finance_alert(cursor, **kwargs)

    assert cursor.calls == []
