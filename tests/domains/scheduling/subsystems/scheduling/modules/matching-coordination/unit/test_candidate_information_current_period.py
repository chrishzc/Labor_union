"""Fresh candidate information and coverage use the same current Orders period."""

from datetime import date
from types import SimpleNamespace
import json

import pytest
from subsystems.scheduling import candidate_contact_pool_workflow as workflow


class Cursor:
    rowcount = 1
    lastrowid = 9

    def __init__(self, existing=None):
        self.existing = existing
        self.current = None
        self.statements = []
        self.entry = {
            "pool_id": 3, "staff_id": 7, "order_status": "洽談中",
            "line_user_id": "U" + "a" * 32,
            "service_start_date": date(2026, 9, 1), "service_end_date": date(2026, 9, 20),
            "order_start_date": date(2026, 11, 20), "order_end_date": date(2026, 12, 19),
            "coverage_fingerprint": "old-coverage",
        }

    def execute(self, statement, parameters):
        self.statements.append((statement, parameters))
        if "SELECT p.id AS pool_id" in statement:
            self.current = self.entry
        elif "SELECT id,pool_id,candidate_id,event_type" in statement:
            self.current = self.existing

    def fetchone(self):
        return self.current


@pytest.fixture
def ports(monkeypatch):
    calls = []

    def require(case, staff, start, end):
        calls.append(("coverage", start, end))
        return {"staff_id": staff}

    class Information:
        def __init__(self, connection):
            pass

        def preview_candidate_information(self, case, candidate, info_type, **kwargs):
            calls.append(("preview", kwargs["service_period"]))
            start, end = kwargs["service_period"]
            return SimpleNamespace(preview_fingerprint="current", line_sections=(
                SimpleNamespace(title="服務約定", rows=(("預計服務開始日", str(start)), ("預計服務結束日", str(end)))),
            ))

    class Delivery:
        def __init__(self, connection):
            pass

        def enqueue(self, request):
            calls.append(("enqueue",))
            return SimpleNamespace(task_id=SimpleNamespace(value=10))

    monkeypatch.setattr(workflow, "_require_current_candidate", require)
    monkeypatch.setattr(workflow, "_coverage_fingerprint", lambda *args: "current-coverage")
    monkeypatch.setattr(workflow, "_candidate_contact_liff_url", lambda reference: f"https://example.invalid/candidate?ref={reference}")
    monkeypatch.setattr(workflow, "MySqlOrderInformationRepository", Information)
    monkeypatch.setattr(workflow, "MySqlLineDeliveryTaskRepository", Delivery)
    monkeypatch.setattr(workflow, "_cancel_pending_manual_followup", lambda *args: None)
    return calls


def test_standard_send_refreshes_changed_period_and_preserves_history(ports):
    cursor = Cursor()
    receipt = workflow._send_information_in_transaction(
        object(), cursor, "CASE-1", 17, 1, "admin", "send-current", "current",
    )
    assert receipt["line_task_id"] == 10
    assert ("coverage", "2026-11-20", "2026-12-19") in ports
    assert ("preview", (date(2026, 11, 20), date(2026, 12, 19))) in ports
    update = next(values for sql, values in cursor.statements if sql.startswith("UPDATE caregiver_candidate_contact_entries"))
    assert update[:2] == (date(2026, 11, 20), date(2026, 12, 19))
    event = next(values for sql, values in cursor.statements if "candidate_period_refreshed" in str(values))
    payload = json.loads(event[-1])
    assert payload["before_end_date"] == "2026-09-20"
    assert payload["after_end_date"] == "2026-12-19"


def test_old_preview_is_rejected_before_any_send_or_period_write(ports):
    cursor = Cursor()
    with pytest.raises(ValueError, match="candidate_information_preview_stale"):
        workflow._send_information_in_transaction(
            object(), cursor, "CASE-1", 17, 1, "admin", "stale-current", "old",
        )
    assert not any(call[0] == "enqueue" for call in ports)
    assert all(sql.startswith("SELECT") for sql, _ in cursor.statements)


def test_existing_receipt_replays_without_refreshing_or_sending(ports):
    cursor = Cursor({"id": 20, "pool_id": 3, "candidate_id": 17, "event_type": "info_1_sent",
                     "actor": "admin", "payload": {"preview_fingerprint": "old", "line_task_id": 10}})
    receipt = workflow._send_information_in_transaction(
        object(), cursor, "CASE-1", 17, 1, "admin", "replay-old", "old",
    )
    assert receipt["status"] == "idempotent_replay"
    assert ports == []
    assert all(sql.startswith("SELECT") for sql, _ in cursor.statements)
