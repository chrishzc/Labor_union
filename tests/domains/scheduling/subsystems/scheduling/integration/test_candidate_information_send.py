"""Preview/send equivalence and stale rejection without a DB or LINE provider."""
from types import SimpleNamespace
import json
import pytest
from subsystems.scheduling import candidate_contact_pool_workflow as workflow


class Cursor:
    lastrowid = 8
    def __init__(self):
        self.reads = iter([{"pool_id": 1, "staff_id": 2, "service_start_date": "2026-10-01", "service_end_date": "2026-10-02", "line_user_id": "U" + "a" * 32}, None])
        self.writes = []
    def execute(self, sql, args):
        if sql.startswith("INSERT"):
            self.writes.append((sql, args))
    def fetchone(self):
        return next(self.reads)


@pytest.mark.parametrize("kind", [1, 2])
def test_sender_enqueues_exact_preview_and_no_provider(monkeypatch, kind):
    preview = SimpleNamespace(text=f"訂單資訊－{kind}\n服務薪資：待確認", preview_fingerprint="a" * 64)
    queued = []
    monkeypatch.setattr(workflow, "_require_full_coverage", lambda *args: {})
    monkeypatch.setattr(workflow, "MySqlOrderInformationRepository", lambda connection: SimpleNamespace(preview_candidate_information=lambda *args, **kwargs: preview))
    monkeypatch.setattr(workflow, "MySqlLineDeliveryTaskRepository", lambda connection: SimpleNamespace(enqueue=lambda request: queued.append(request) or SimpleNamespace(task_id=SimpleNamespace(value=7))))
    cursor = Cursor()
    result = workflow._send_information_in_transaction(object(), cursor, "CASE-1", 3, kind, "operator", "request-1", "a" * 64)
    assert result == {"status": "queued", "event_id": 8, "line_task_id": 7}
    assert len(queued) == 1
    assert cursor.writes[0][1][2] == f"info_{kind}_sent"
    assert json.loads(queued[0].payload_json)["text"] == preview.text


def test_stale_preview_rejects_without_event_or_delivery(monkeypatch):
    monkeypatch.setattr(workflow, "_require_full_coverage", lambda *args: {})
    monkeypatch.setattr(workflow, "MySqlOrderInformationRepository", lambda connection: SimpleNamespace(preview_candidate_information=lambda *args, **kwargs: SimpleNamespace(preview_fingerprint="b" * 64)))
    monkeypatch.setattr(workflow, "MySqlLineDeliveryTaskRepository", lambda connection: pytest.fail("stale preview must not enqueue"))
    cursor = Cursor()
    with pytest.raises(ValueError, match="candidate_information_preview_stale"):
        workflow._send_information_in_transaction(object(), cursor, "CASE-1", 3, 1, "operator", "request-1", "a" * 64)
    assert cursor.writes == []
