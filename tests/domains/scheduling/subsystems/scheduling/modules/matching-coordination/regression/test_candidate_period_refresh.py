"""Updating an inquiry period retains history and requires fresh willingness."""
from datetime import date, datetime
import json

from subsystems.scheduling import candidate_contact_pool_workflow as workflow


def test_readding_existing_candidate_updates_period_and_resets_old_confirmation(monkeypatch):
    class Cursor:
        def __init__(self):
            self.reads = iter([{"status": "洽談中"}, {"id": 1}, {"id": 2, "status": "active", "service_start_date": date(2026, 11, 15), "service_end_date": date(2026, 12, 4)}, None])
            self.writes = []
        def execute(self, sql, params):
            if not sql.startswith("SELECT "): self.writes.append((sql, params))
        def fetchone(self): return next(self.reads)
    cursor = Cursor()
    monkeypatch.setattr(workflow, "require_candidate_matching_open", lambda *_: None)
    monkeypatch.setattr(workflow, "lock_active_candidate_staff", lambda *_: None)
    monkeypatch.setattr(workflow, "_require_current_candidate", lambda *args: {
        "staff_id": args[1], "case_period_start": args[2], "case_period_end": args[3],
    })
    monkeypatch.setattr(workflow, "_coverage_fingerprint", lambda *_: "a" * 64)
    result = workflow._add_candidates_in_transaction(
        None, cursor, "TEST", [(2, "2026-11-15", "2026-12-11")], "operator", "refresh-period",
    )
    assert result["candidate_ids"] == [2]
    assert len([sql for sql, _ in cursor.writes if sql.startswith("UPDATE caregiver_candidate_contact_entries")]) == 1
    event = next(params for sql, params in cursor.writes if "'willingness_changed'" in sql)
    payload = json.loads(event[-1])
    assert payload["before_end_date"] == "2026-12-04"
    assert payload["after_end_date"] == "2026-12-11"
    old = [{"id": 1, "event_type": "willingness_changed", "payload": {"willingness": "willing"}}, {"id": 2, "event_type": "info_1_sent", "payload": {"delivery_status": "manually_confirmed"}, "occurred_at": datetime(2026, 10, 14)}]
    current = workflow._candidate_projection([*old, {"id": 3, "event_type": "willingness_changed", "payload": payload}])
    assert current[0] == "pending" and current[2] == 3
    assert all(value is None for value in current[3].values())
    assert old[0]["payload"]["willingness"] == "willing"
