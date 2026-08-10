from __future__ import annotations

import json
from types import SimpleNamespace

from api.routes import anomaly_registry, staff
from domains.anomalies.registry import default_anomaly_registry
from infrastructure.mysql import anomaly_registry_repository
from scripts.imports import import_client_hcm
from subsystems.anomalies import finance_import_anomaly_consumer
from ui.pages.scheduling.navigation_state import (
    apply_one_time_default,
    clear_staff_calendar_navigation,
    consume_staff_calendar_selection,
    staff_option_label,
)
from ui.pages.scheduling import matching_center


class _Cursor:
    def __init__(self, rows=()):
        self.rows = list(rows)
        self.executed = []

    def __enter__(self):
        return self

    def __exit__(self, exception_type, exception, traceback):
        return False

    def execute(self, query, parameters=None):
        self.executed.append((query, parameters))

    def fetchall(self):
        return list(self.rows)


class _Connection:
    def __init__(self, rows=()):
        self.cursor_instance = _Cursor(rows)
        self.closed = False

    def cursor(self):
        return self.cursor_instance

    def close(self):
        self.closed = True


def test_historical_reprocess_outbox_projects_import006_with_event_version(monkeypatch):
    captured = {}

    def project(cursor, batch_id, **kwargs):
        captured.update(batch_id=batch_id, cursor=cursor, **kwargs)

    monkeypatch.setattr(
        finance_import_anomaly_consumer,
        "project_finance_import_review_alert",
        project,
    )
    connection = _Connection()
    event = {
        "id": 91,
        "payload_snapshot": json.dumps(
            {"batch_identity": "finance-import-batch:7"}
        ),
    }

    finance_import_anomaly_consumer._project_historical_reprocess_integrity(
        connection,
        event,
    )

    assert captured == {
        "batch_id": 7,
        "cursor": connection.cursor_instance,
        "source_version": 91,
        "source_event_identity": "finance-import-historical-reprocess:91",
    }


def test_projector_idempotency_key_is_fixed_length_and_semantic():
    request = SimpleNamespace(
        consumer_identity="consumer" * 40,
        partition_identity="partition" * 40,
        source_event_identity="event" * 100,
    )

    first = anomaly_registry_repository._projector_key(request, "reopen")
    second = anomaly_registry_repository._projector_key(request, "reopen")
    different = anomaly_registry_repository._projector_key(request, "auto_resolve")

    assert first == second
    assert first != different
    assert len(first) == len("anomaly-projector:") + 64


def test_schedule_navigation_is_typed_by_api_adapter():
    schedule_001 = anomaly_registry._staff_calendar_navigation(
        "SCHEDULE-001",
        {"staff_id": 7, "holiday_date": "2026-10-10"},
    )
    schedule_003 = anomaly_registry._staff_calendar_navigation(
        "SCHEDULE-003",
        {"staff_id": 8, "assignment_a": {"start": "2026-09-03"}},
    )

    assert schedule_001 == {"staff_id": 7, "target_date": "2026-10-10"}
    assert schedule_003 == {"staff_id": 8, "target_date": "2026-09-03"}
    assert anomaly_registry._staff_calendar_navigation(
        "SCHEDULE-005",
        {"staff_id": 9, "work_date": "not-a-date"},
    ) is None


def test_schedule_registry_declares_staff_name_display_contract():
    registry = default_anomaly_registry()

    for code in ("SCHEDULE-001", "SCHEDULE-003", "SCHEDULE-005"):
        assert "staff_name" in registry.require(code).display_fields


def test_staff_summary_supports_exact_typed_lookup(monkeypatch):
    connection = _Connection([{"id": 7, "name": "王小美", "phone": "0900"}])
    monkeypatch.setattr(staff.db_service, "get_connection", lambda: connection)

    response = staff.get_staff_summaries(
        page_size=1,
        after_id=None,
        staff_id=7,
    )

    assert response.data.items[0].id == 7
    assert response.data.next_cursor is None
    assert connection.cursor_instance.executed[0][1] == (7,)
    assert connection.closed is True


def test_staff_calendar_pending_target_is_not_consumed_until_present():
    state = {
        "pending_staff_calendar_staff_id": 77,
        "pending_staff_calendar_year": 2026,
        "pending_staff_calendar_month": 10,
        "pending_staff_calendar_note": "holiday conflict",
    }

    assert consume_staff_calendar_selection(state, {"other": 1}) is None
    assert state["pending_staff_calendar_staff_id"] == 77

    selection = consume_staff_calendar_selection(state, {"target": 77})

    assert selection is not None
    assert (selection.label, selection.year, selection.month) == (
        "target",
        2026,
        10,
    )
    assert "pending_staff_calendar_staff_id" not in state


def test_matching_plan_default_only_applies_once_per_navigation_event():
    state = {"matching_center_plan_navigation_token": "event-1"}

    apply_one_time_default(
        state,
        enabled=True,
        navigation_value="plan",
    )
    state["matching_center_sub_nav"] = "details"
    apply_one_time_default(
        state,
        enabled=True,
        navigation_value="plan",
    )
    assert state["matching_center_sub_nav"] == "details"

    state["matching_center_plan_navigation_token"] = "event-2"
    apply_one_time_default(
        state,
        enabled=True,
        navigation_value="plan",
    )
    assert state["matching_center_sub_nav"] == "plan"


def test_missing_staff_navigation_is_cleared_after_exact_lookup_fails():
    state = {
        "pending_staff_calendar_staff_id": 77,
        "pending_staff_calendar_year": 2026,
        "pending_staff_calendar_month": 10,
        "pending_staff_calendar_note": "holiday conflict",
    }

    clear_staff_calendar_navigation(state)

    assert state == {}


def test_staff_option_label_uses_staff_id_as_immutable_identity():
    first = staff_option_label({"id": 7, "name": "同名", "phone": "0900"})
    second = staff_option_label({"id": 8, "name": "同名", "phone": "0900"})

    assert first != second
    assert first.endswith("#7")


def test_smart_matching_entry_renders_the_real_matching_flow(monkeypatch):
    calls = []
    monkeypatch.setattr(matching_center.st, "markdown", lambda *_: None)
    monkeypatch.setattr(matching_center.st, "caption", lambda *_: None)
    monkeypatch.setattr(
        matching_center,
        "_render_multi_segment_matching",
        lambda order, staff: calls.append((order, staff)),
    )
    order = {"case_no": "CASE-1"}
    staff = [{"id": 7}]

    matching_center._render_single_caregiver_matching(order, staff)

    assert calls == [(order, staff)]


def test_existing_hcm_case_replays_missing_validation_anomaly(monkeypatch):
    emitted = []
    monkeypatch.setattr(
        import_client_hcm,
        "_emit_hcm_validation_anomaly",
        lambda *args: emitted.append(args),
    )

    result = import_client_hcm._replay_existing_hcm_anomaly(
        "CASE-7",
        3,
        {"服務天數": "invalid"},
    )

    assert result == "skipped_existing"
    assert emitted == [("CASE-7", 3, {"服務天數": "invalid"})]


def test_existing_hcm_case_remains_reviewable_when_projection_fails(monkeypatch):
    def fail(*args):
        raise RuntimeError("temporary projector failure")

    monkeypatch.setattr(import_client_hcm, "_emit_hcm_validation_anomaly", fail)

    assert import_client_hcm._replay_existing_hcm_anomaly(
        "CASE-7",
        3,
        {"服務天數": "invalid"},
    ) == "review_required"
