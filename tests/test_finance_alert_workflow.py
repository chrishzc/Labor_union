from datetime import datetime

import pytest

import services.finance_alert_workflow as workflow


NOW = datetime(2026, 7, 16, 17, 0, 0)


class Connection:
    def __init__(self, autocommit=False):
        self.autocommit = autocommit

    def get_autocommit(self):
        return self.autocommit


class Cursor:
    def __init__(
        self,
        fetches=(),
        fetchalls=(),
        *,
        rowcounts=(),
        autocommit=False,
    ):
        self.fetches = list(fetches)
        self.fetchalls = list(fetchalls)
        self.rowcounts = list(rowcounts)
        self.connection = Connection(autocommit)
        self.calls = []
        self.rowcount = 0

    def execute(self, sql, params=None):
        normalized = " ".join(sql.split())
        self.calls.append((normalized, params))
        self.rowcount = self.rowcounts.pop(0) if self.rowcounts else 0

    def fetchone(self):
        return self.fetches.pop(0)

    def fetchall(self):
        return self.fetchalls.pop(0)


def alert(**changes):
    row = {
        "id": 41,
        "alert_key": "finance-alert:key",
        "alert_code": "review_required",
        "source_domain": "government_subsidy",
        "source_type": "finance_import_row",
        "source_id": "12",
        "finance_import_row_id": 12,
        "finance_import_batch_id": 7,
        "reason": "人工覆核",
        "expected_amount": None,
        "actual_amount": None,
        "difference_amount": None,
        "candidate_snapshot": '{"ids":[3,5]}',
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


def event(event_type="claimed", **changes):
    row = {
        "id": 90,
        "alert_id": 41,
        "event_key": f"finance-alert:41:{event_type}",
        "event_type": event_type,
        "source_domain": "finance_alert",
        "source_type": "finance_alert",
        "source_id": "41",
        "actor": "owner",
        "reason": None,
        "event_snapshot": '{"claimed_by":"owner","status":"claimed"}',
        "occurred_at": NOW,
        "created_at": NOW,
    }
    row.update(changes)
    return row


def test_list_validates_filters_and_uses_stable_audit_sort():
    rows = [alert(id=42), alert()]
    cursor = Cursor(fetchalls=[rows])

    result = workflow.list_finance_alerts(
        cursor,
        status="open",
        alert_code="review_required",
        source_domain="government_subsidy",
        limit=20,
        offset=5,
    )

    assert result == rows
    sql, params = cursor.calls[0]
    assert "FROM finance_alerts" in sql
    assert "ORDER BY created_at DESC, id DESC" in sql
    assert "candidate_snapshot" not in sql.split("ORDER BY", 1)[1]
    assert params == (
        "open",
        "review_required",
        "government_subsidy",
        20,
        5,
    )


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"status": "invalid"}, "invalid"),
        ({"limit": 0}, "allowed range"),
        ({"limit": 201}, "allowed range"),
        ({"offset": -1}, "allowed range"),
        ({"offset": True}, "integer"),
    ],
)
def test_list_rejects_invalid_filters(kwargs, message):
    cursor = Cursor()

    with pytest.raises(ValueError, match=message):
        workflow.list_finance_alerts(cursor, **kwargs)

    assert cursor.calls == []


def test_detail_returns_full_ordered_event_history():
    events = [event(), event("resolved", id=91)]
    cursor = Cursor(fetches=[alert()], fetchalls=[events])

    result = workflow.get_finance_alert(cursor, 41)

    assert result["events"] == events
    assert "ORDER BY occurred_at, id" in cursor.calls[1][0]
    assert all("FOR UPDATE" not in sql for sql, _ in cursor.calls)


def test_claim_open_updates_projection_then_delegates_event(monkeypatch):
    updated = alert(status="claimed", claimed_by="owner", claimed_at=NOW)
    cursor = Cursor(
        fetches=[alert(), None, updated],
        rowcounts=[0, 0, 0, 1, 0, 0],
    )
    calls = []
    monkeypatch.setattr(
        workflow,
        "append_finance_alert_event",
        lambda cursor, **kwargs: calls.append(kwargs) or {"result": "created"},
    )

    result = workflow.claim_finance_alert(
        cursor,
        alert_id=41,
        operator="owner",
        occurred_at=NOW,
    )

    assert result == {"result": "claimed", "alert": updated}
    update_sql = next(sql for sql, _ in cursor.calls if sql.startswith("UPDATE"))
    assert "claimed_by" in update_sql and "candidate_snapshot" not in update_sql
    assert calls[0]["event_key"] == "finance-alert:41:claimed"
    assert calls[0]["event_type"] == "claimed"
    assert calls[0]["occurred_at"] == NOW


def test_claim_same_operator_retry_requires_and_validates_event(monkeypatch):
    claimed = alert(status="claimed", claimed_by="owner", claimed_at=NOW)
    cursor = Cursor(fetches=[claimed, event()])
    calls = []
    monkeypatch.setattr(
        workflow,
        "append_finance_alert_event",
        lambda cursor, **kwargs: calls.append(kwargs) or {"result": "existing"},
    )

    result = workflow.claim_finance_alert(
        cursor,
        alert_id=41,
        operator="owner",
        occurred_at=datetime(2026, 7, 17),
    )

    assert result == {"result": "existing", "alert": claimed}
    assert calls[0]["occurred_at"] == NOW
    assert not any(sql.startswith("UPDATE") for sql, _ in cursor.calls)


def test_claim_partial_residue_fails_fast(monkeypatch):
    claimed = alert(status="claimed", claimed_by="owner", claimed_at=NOW)
    cursor = Cursor(fetches=[claimed, None])
    monkeypatch.setattr(
        workflow,
        "append_finance_alert_event",
        lambda *args, **kwargs: pytest.fail("must not repair residue"),
    )

    with pytest.raises(RuntimeError, match="missing its claimed event"):
        workflow.claim_finance_alert(cursor, alert_id=41, operator="owner")


def test_claim_event_without_projection_fails_fast(monkeypatch):
    cursor = Cursor(fetches=[alert(), event()])
    monkeypatch.setattr(
        workflow,
        "append_finance_alert_event",
        lambda *args, **kwargs: pytest.fail("must not accept inverse residue"),
    )

    with pytest.raises(RuntimeError, match="already has a claimed event"):
        workflow.claim_finance_alert(
            cursor,
            alert_id=41,
            operator="owner",
            occurred_at=NOW,
        )

    assert not any(sql.startswith("UPDATE") for sql, _ in cursor.calls)


def test_claim_other_operator_or_resolved_returns_conflict():
    claimed = alert(status="claimed", claimed_by="owner", claimed_at=NOW)
    resolved = alert(
        status="resolved",
        resolved_by="reviewer",
        resolved_at=NOW,
        resolution_reason="done",
    )

    assert workflow.claim_finance_alert(
        Cursor(fetches=[claimed]), alert_id=41, operator="other"
    )["result"] == "conflict"
    assert workflow.claim_finance_alert(
        Cursor(fetches=[resolved]), alert_id=41, operator="owner"
    )["result"] == "conflict"


def test_resolve_open_directly_preserves_claim_fields(monkeypatch):
    resolved = alert(
        status="resolved",
        resolved_by="reviewer",
        resolved_at=NOW,
        resolution_reason="確認無須入帳",
    )
    cursor = Cursor(
        fetches=[alert(), None, resolved],
        rowcounts=[0, 0, 0, 1, 0, 0],
    )
    calls = []
    monkeypatch.setattr(
        workflow,
        "append_finance_alert_event",
        lambda cursor, **kwargs: calls.append(kwargs) or {"result": "created"},
    )

    result = workflow.resolve_finance_alert(
        cursor,
        alert_id=41,
        operator="reviewer",
        reason="確認無須入帳",
        occurred_at=NOW,
    )

    assert result == {"result": "resolved", "alert": resolved}
    update_sql = next(sql for sql, _ in cursor.calls if sql.startswith("UPDATE"))
    assert "resolved_by" in update_sql
    assert "claimed_by" not in update_sql and "candidate_snapshot" not in update_sql
    assert calls[0]["event_type"] == "resolved"
    assert calls[0]["reason"] == "確認無須入帳"


def test_resolve_claimed_requires_claim_owner():
    claimed = alert(status="claimed", claimed_by="owner", claimed_at=NOW)

    result = workflow.resolve_finance_alert(
        Cursor(fetches=[claimed]),
        alert_id=41,
        operator="other",
        reason="done",
    )

    assert result == {"result": "conflict", "alert": claimed}


def test_resolved_event_without_projection_fails_fast(monkeypatch):
    cursor = Cursor(fetches=[alert(), event("resolved")])
    monkeypatch.setattr(
        workflow,
        "append_finance_alert_event",
        lambda *args, **kwargs: pytest.fail("must not accept inverse residue"),
    )

    with pytest.raises(RuntimeError, match="already has a resolved event"):
        workflow.resolve_finance_alert(
            cursor,
            alert_id=41,
            operator="reviewer",
            reason="done",
            occurred_at=NOW,
        )

    assert not any(sql.startswith("UPDATE") for sql, _ in cursor.calls)


def test_resolved_retry_uses_stored_time_and_detects_partial_residue(monkeypatch):
    resolved = alert(
        status="resolved",
        resolved_by="reviewer",
        resolved_at=NOW,
        resolution_reason="done",
    )
    existing_event = event(
        "resolved",
        actor="reviewer",
        reason="done",
        event_snapshot=(
            '{"resolution_reason":"done","resolved_by":"reviewer",'
            '"status":"resolved"}'
        ),
    )
    cursor = Cursor(fetches=[resolved, existing_event])
    calls = []
    monkeypatch.setattr(
        workflow,
        "append_finance_alert_event",
        lambda cursor, **kwargs: calls.append(kwargs) or {"result": "existing"},
    )

    result = workflow.resolve_finance_alert(
        cursor,
        alert_id=41,
        operator="reviewer",
        reason="done",
        occurred_at=datetime(2026, 7, 17),
    )

    assert result["result"] == "existing"
    assert calls[0]["occurred_at"] == NOW

    with pytest.raises(RuntimeError, match="missing its resolved event"):
        workflow.resolve_finance_alert(
            Cursor(fetches=[resolved, None]),
            alert_id=41,
            operator="reviewer",
            reason="done",
        )


def test_resolved_different_operator_or_reason_is_conflict():
    resolved = alert(
        status="resolved",
        resolved_by="reviewer",
        resolved_at=NOW,
        resolution_reason="done",
    )

    assert workflow.resolve_finance_alert(
        Cursor(fetches=[resolved]),
        alert_id=41,
        operator="other",
        reason="done",
    )["result"] == "conflict"
    assert workflow.resolve_finance_alert(
        Cursor(fetches=[resolved]),
        alert_id=41,
        operator="reviewer",
        reason="changed",
    )["result"] == "conflict"


@pytest.mark.parametrize("action", ["claim", "resolve"])
def test_event_failure_rolls_back_workflow_projection(monkeypatch, action):
    cursor = Cursor(fetches=[alert(), None], rowcounts=[0, 0, 0, 1, 0, 0])
    monkeypatch.setattr(
        workflow,
        "append_finance_alert_event",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            RuntimeError("event failed")
        ),
    )

    with pytest.raises(RuntimeError, match="event failed"):
        if action == "claim":
            workflow.claim_finance_alert(
                cursor,
                alert_id=41,
                operator="owner",
                occurred_at=NOW,
            )
        else:
            workflow.resolve_finance_alert(
                cursor,
                alert_id=41,
                operator="owner",
                reason="done",
                occurred_at=NOW,
            )

    assert any(
        sql.startswith("ROLLBACK TO SAVEPOINT finance_alert_")
        for sql, _ in cursor.calls
    )
    assert cursor.calls[-1][0].startswith("RELEASE SAVEPOINT finance_alert_")


def test_autocommit_and_invalid_action_inputs_fail_before_queries():
    with pytest.raises(RuntimeError, match="autocommit disabled"):
        workflow.claim_finance_alert(
            Cursor(autocommit=True),
            alert_id=41,
            operator="owner",
        )
    cursor = Cursor()
    with pytest.raises(ValueError, match="operator"):
        workflow.claim_finance_alert(cursor, alert_id=41, operator=" ")
    with pytest.raises(ValueError, match="reason"):
        workflow.resolve_finance_alert(
            cursor,
            alert_id=41,
            operator="owner",
            reason="",
        )
    assert cursor.calls == []
