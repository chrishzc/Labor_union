from types import SimpleNamespace

import pytest

import infrastructure.mysql.scheduling_replacement_writer as replacement_writer


def test_actual_start_replacement_retires_effective_generation_before_schedule_insert(
    monkeypatch,
):
    """A shifted replacement must release the staff/date key before insert."""
    events = []
    retired = False

    class Cursor:
        def execute(self, _statement, _parameters):
            return None

        def fetchone(self):
            return {
                "aggregate_version": 3,
                "generation_counter": 114,
                "effective_generation_id": 114,
            }

    def insert_generation(_cursor, _command):
        events.append("insert_generation")
        return 115

    def insert_assignments(_cursor, _command, _generation_id):
        events.append("insert_assignments")
        return {"staff-16": 52}

    def cancel_previous(_cursor, _command, previous_generation_id):
        nonlocal retired
        assert previous_generation_id == 114
        retired = True
        events.append("retire_previous")

    def insert_schedules(_cursor, _command, _generation_id, _assignment_ids):
        if not retired:
            pytest.fail(
                "staff_schedule.uq_staff_schedule_effective_date would return HTTP 409"
            )
        events.append("insert_schedules")

    monkeypatch.setattr(replacement_writer, "_insert_generation", insert_generation)
    monkeypatch.setattr(
        replacement_writer, "_insert_assignments", insert_assignments
    )
    monkeypatch.setattr(
        replacement_writer, "_cancel_previous_state", cancel_previous
    )
    monkeypatch.setattr(
        replacement_writer, "_insert_schedules", insert_schedules
    )
    monkeypatch.setattr(replacement_writer, "_insert_buffers", lambda *args: None)
    monkeypatch.setattr(
        replacement_writer, "_activate_new_generation", lambda *args: None
    )
    monkeypatch.setattr(
        replacement_writer, "_insert_occupancy", lambda *args: None
    )
    monkeypatch.setattr(replacement_writer, "_advance_aggregate", lambda *args: None)
    monkeypatch.setattr(
        replacement_writer, "_append_rebuild_event", lambda *args: 901
    )
    monkeypatch.setattr(
        replacement_writer,
        "_append_notification_invalidation_outbox",
        lambda *args: None,
    )
    monkeypatch.setattr(replacement_writer, "_append_lineage", lambda *args: None)
    monkeypatch.setattr(
        replacement_writer, "_insert_scheduling_receipt", lambda *args: 902
    )

    command = SimpleNamespace(
        candidate=SimpleNamespace(
            case_no="CASE-1",
            expected_aggregate_version=3,
            resulting_aggregate_version=4,
            generation_number=115,
            assignments=(),
        ),
        command_family="orders_actual_start_rebuild",
    )

    result = replacement_writer.persist_scheduling_replacement(Cursor(), command)

    assert events == [
        "insert_generation",
        "insert_assignments",
        "retire_previous",
        "insert_schedules",
    ]
    assert result.generation_id == 115
    assert result.rebuild_event_id == 901
    assert result.scheduling_receipt_id == 902
