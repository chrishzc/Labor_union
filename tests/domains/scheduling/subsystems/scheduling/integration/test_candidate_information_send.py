"""Preview/send equivalence and stale rejection without a DB or LINE provider."""
import hashlib
import json
from datetime import date
from types import SimpleNamespace

import pytest

from subsystems.scheduling import candidate_contact_pool_workflow as workflow


class Cursor:
    lastrowid = 8
    def __init__(self):
        self.reads = iter([{"pool_id": 1, "staff_id": 2, "service_start_date": "2026-10-01", "service_end_date": "2026-10-02", "line_user_id": "U" + "a" * 32, "order_status": "洽談中"}, None])
        self.writes = []
        self.statements = []
    def execute(self, sql, args):
        self.statements.append((sql, args))
        if sql.startswith("INSERT"):
            self.writes.append((sql, args))
    def fetchone(self):
        return next(self.reads)


def test_manual_willingness_cancellation_compares_numeric_identity_without_collation():
    cursor = Cursor()

    workflow._cancel_pending_candidate_coordination(cursor, 48)

    cancellation_sql, cancellation_args = next(
        (sql, args)
        for sql, args in cursor.statements
        if "source_aggregate_type='candidate_contact_adjustment'" in sql
    )
    assert "CAST(source_aggregate_identity AS UNSIGNED)=%s" in cancellation_sql
    assert "source_aggregate_identity=CAST(%s AS CHAR)" not in cancellation_sql
    assert cancellation_args == (48, 48)


@pytest.mark.parametrize("kind", [1, 2])
def test_sender_enqueues_exact_preview_and_no_provider(monkeypatch, kind):
    preview = SimpleNamespace(text=f"訂單資訊－{kind}\n總薪資：待確認", preview_fingerprint="a" * 64)
    queued = []
    monkeypatch.setattr(workflow, "_require_full_coverage", lambda *args: {})
    monkeypatch.setenv("LINE_LIFF_ID", "1234567890-candidate")
    monkeypatch.setattr(workflow, "MySqlOrderInformationRepository", lambda connection: SimpleNamespace(preview_candidate_information=lambda *args, **kwargs: preview))
    monkeypatch.setattr(workflow, "MySqlLineDeliveryTaskRepository", lambda connection: SimpleNamespace(enqueue=lambda request: queued.append(request) or SimpleNamespace(task_id=SimpleNamespace(value=7))))
    cursor = Cursor()
    result = workflow._send_information_in_transaction(object(), cursor, "CASE-1", 3, kind, "operator", "request-1", "a" * 64)
    assert result == {"status": "queued", "event_id": 8, "line_task_id": 7}
    assert len(queued) == 1
    assert cursor.writes[0][1][2] == f"info_{kind}_sent"
    payload = json.loads(queued[0].payload_json)
    assert queued[0].message_kind.value == "flex"
    assert payload["type"] == "flex"
    assert payload["contents"]["body"]["contents"][1]["text"] == preview.text
    assert payload["contents"]["body"]["contents"][0]["text"] == "訂單編號：CASE-1"
    assert payload["altText"] == "訂單編號：CASE-1"
    actions = payload["contents"]["footer"]["contents"]
    assert [item["action"]["label"] for item in actions] == ["願意承接", "提出疑問或無法承接"]
    assert actions[0]["action"]["data"] == (
        f"candidate-contact:{hashlib.sha256(b'request-1').hexdigest()}:willing"
    )
    assert actions[1]["action"] == {
        "type": "uri",
        "label": "提出疑問或無法承接",
        "uri": (
            "https://liff.line.me/1234567890-candidate/"
            f"?target=candidate_contact&ref={hashlib.sha256(b'request-1').hexdigest()}"
        ),
    }
    cancellation = next(
        (sql, args)
        for sql, args in cursor.statements
        if "source_aggregate_type='candidate_contact_manual_followup'" in sql
    )
    assert cancellation[1] == (1,)
    assert "SUBSTRING_INDEX(source_aggregate_identity,':',1) AS UNSIGNED" in cancellation[0]
    assert " LIKE " not in cancellation[0]
    assert "processing_status IN ('pending','retryable_failed')" in cancellation[0]


def test_stale_preview_rejects_without_event_or_delivery(monkeypatch):
    monkeypatch.setattr(workflow, "_require_full_coverage", lambda *args: {})
    monkeypatch.setattr(workflow, "MySqlOrderInformationRepository", lambda connection: SimpleNamespace(preview_candidate_information=lambda *args, **kwargs: SimpleNamespace(preview_fingerprint="b" * 64)))
    monkeypatch.setattr(workflow, "MySqlLineDeliveryTaskRepository", lambda connection: pytest.fail("stale preview must not enqueue"))
    cursor = Cursor()
    with pytest.raises(ValueError, match="candidate_information_preview_stale"):
        workflow._send_information_in_transaction(object(), cursor, "CASE-1", 3, 1, "operator", "request-1", "a" * 64)
    assert cursor.writes == []


def test_recontact_refreshes_candidate_period_from_current_order_before_queue(monkeypatch):
    class RefreshCursor(Cursor):
        rowcount = 0

        def __init__(self):
            self.reads = iter(
                [
                    {
                        "pool_id": 1,
                        "staff_id": 2,
                        "service_start_date": date(2026, 10, 1),
                        "service_end_date": date(2026, 10, 20),
                        "line_user_id": "U" + "a" * 32,
                        "order_status": "洽談中",
                        "order_start_date": date(2026, 10, 4),
                        "order_end_date": date(2026, 10, 23),
                    },
                    None,
                ]
            )
            self.writes = []
            self.statements = []

        def execute(self, sql, args):
            super().execute(sql, args)
            self.rowcount = 1 if sql.startswith("UPDATE caregiver_candidate_contact_entries") else 0

    preview_periods = []
    preview = SimpleNamespace(
        text="訂單資訊－1\n預計服務開始日期：2026-10-04",
        preview_fingerprint="a" * 64,
    )
    monkeypatch.setattr(
        workflow,
        "_require_full_coverage",
        lambda *_: {
            "staff_id": 2,
            "case_period_start": "2026-10-04",
            "case_period_end": "2026-10-23",
            "required_service_dates": ["2026-10-04"],
            "supported_service_dates": ["2026-10-04"],
            "source_scheduling_version": 9,
        },
    )
    monkeypatch.setenv("LINE_LIFF_ID", "1234567890-candidate")
    monkeypatch.setattr(
        workflow,
        "MySqlOrderInformationRepository",
        lambda _connection: SimpleNamespace(
            preview_candidate_information=lambda *args, **kwargs: preview_periods.append(
                kwargs["service_period"]
            )
            or preview
        ),
    )
    monkeypatch.setattr(
        workflow,
        "MySqlLineDeliveryTaskRepository",
        lambda _connection: SimpleNamespace(
            enqueue=lambda _request: SimpleNamespace(task_id=SimpleNamespace(value=7))
        ),
    )
    cursor = RefreshCursor()

    result = workflow._send_information_in_transaction(
        object(),
        cursor,
        "CASE-1",
        3,
        1,
        "operator",
        "followup-1",
        "a" * 64,
        refresh_period_from_order=True,
    )

    assert result == {"status": "queued", "event_id": 8, "line_task_id": 7}
    assert preview_periods == [(date(2026, 10, 4), date(2026, 10, 23))]
    period_update = next(item for item in cursor.statements if item[0].startswith("UPDATE caregiver_candidate_contact_entries"))
    assert period_update[1][0:2] == (date(2026, 10, 4), date(2026, 10, 23))
    period_event = next(item for item in cursor.writes if "'willingness_changed'" in item[0])
    assert period_event[1][2] == "followup-1:period"
    assert json.loads(period_event[1][4])["response_kind"] == "candidate_period_refreshed"
