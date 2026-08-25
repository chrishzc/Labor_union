"""File: test_candidate_contact_pool_workflow.py
Description: 驗證候選聯繫池 projection 與 typed query state。
"""

import json
from datetime import date, datetime, timezone

import pytest

import subsystems.scheduling.candidate_contact_pool_workflow as workflow

from subsystems.scheduling.candidate_contact_pool_workflow import (
    CandidateContactEventState,
    CandidateContactEntryState,
    CandidateContactPoolState,
    CandidateInformationDelivery,
    CandidateInformationState,
    _candidate_projection,
    _coverage_fingerprint,
    _manual_information_preview,
)
from shared_kernel.fingerprints import fingerprint_payload


def test_candidate_contact_event_state_constructor_validation():
    occurred_at = datetime(2026, 8, 22, 10, 0, tzinfo=timezone.utc)
    fingerprint = "a" * 64
    added = CandidateContactEventState(
        id=1,
        candidate_id=None,
        event_key="evt-added",
        event_type="candidates_added",
        actor="admin",
        occurred_at=occurred_at,
        payload_fingerprint=fingerprint,
    )
    changed = CandidateContactEventState(
        id=2,
        candidate_id=8,
        event_key="evt-changed",
        event_type="willingness_changed",
        actor="admin",
        occurred_at=occurred_at,
        payload_fingerprint=fingerprint,
    )
    state = CandidateContactPoolState(
        pool_id=3,
        case_no="CASE-1",
        candidates=(),
        events=(added, changed),
    )
    assert state.events == (added, changed)

    with pytest.raises(ValueError):
        CandidateContactEventState(
            id=3,
            candidate_id=8,
            event_key="evt",
            event_type="candidates_added",
            actor="admin",
            occurred_at=occurred_at,
            payload_fingerprint=fingerprint,
        )
    with pytest.raises(ValueError):
        CandidateContactEventState(
            id=4,
            candidate_id=None,
            event_key="evt",
            event_type="info_1_sent",
            actor="admin",
            occurred_at=occurred_at,
            payload_fingerprint=fingerprint,
        )
    with pytest.raises(ValueError):
        CandidateContactEventState(
            id=5,
            candidate_id=8,
            event_key="evt",
            event_type="willingness_changed",
            actor="admin",
            occurred_at=occurred_at,
            payload_fingerprint="G" * 64,
        )
    with pytest.raises(ValueError):
        CandidateContactPoolState(
            pool_id=3,
            case_no="CASE-1",
            candidates=(),
            events=(changed, added),
        )


def test_candidate_projection_ignores_irrelevant_legacy_event_payloads():
    events = [
        {
            "event_type": "candidates_added",
            "payload": "",
            "occurred_at": datetime(2026, 8, 12, tzinfo=timezone.utc),
        },
        {
            "event_type": "info_1_sent",
            "payload": '{"delivery_status":"queued"}',
            "occurred_at": datetime(2026, 8, 12, 1, tzinfo=timezone.utc),
        },
    ]

    willingness, reason, information = _candidate_projection(events)

    assert willingness == "pending"
    assert reason is None
    assert information["1"] == {"status": "queued", "sent_at": "2026-08-12T01:00:00+00:00"}


def test_coverage_fingerprint_is_stable_for_fresh_availability_facts():
    candidate = {
        "staff_id": 531,
        "case_period_start": "2026-12-06",
        "case_period_end": "2026-12-20",
        "required_service_dates": ["2026-12-06", "2026-12-07"],
        "supported_service_dates": ["2026-12-06", "2026-12-07"],
        "source_scheduling_version": 9,
    }

    assert _coverage_fingerprint("115000015", candidate) == _coverage_fingerprint(
        "115000015", candidate
    )


def test_manual_information_preview_binds_candidate_version_and_evidence():
    occurred_at = datetime(2026, 8, 24, 10, 0, tzinfo=timezone.utc)
    candidate = CandidateContactEntryState(
        id=8,
        staff_id=531,
        service_start_date=date(2026, 9, 1),
        service_end_date=date(2026, 9, 3),
        status="active",
        created_at=occurred_at,
        staff_name="王小美",
        willingness="pending",
        reason=None,
        information=CandidateInformationState(),
    )
    state = CandidateContactPoolState(
        pool_id=3,
        case_no="CASE-1",
        candidates=(candidate,),
        events=(
            CandidateContactEventState(
                id=11,
                candidate_id=None,
                event_key="evt-added",
                event_type="candidates_added",
                actor="admin",
                occurred_at=occurred_at,
                payload_fingerprint="a" * 64,
            ),
        ),
    )

    preview = _manual_information_preview(
        state,
        8,
        1,
        "phone",
        "已透過電話逐項說明粗篩案況",
        "admin",
    )

    assert preview["expected_version"] == 11
    assert preview["staff_id"] == 531
    assert preview["current_status"] is None
    assert preview["apply_allowed"] is True
    assert len(preview["preview_fingerprint"]) == 64

    selected = CandidateContactPoolState(
        pool_id=3,
        case_no="CASE-1",
        candidates=(
            CandidateContactEntryState(
                id=8,
                staff_id=531,
                service_start_date=date(2026, 9, 1),
                service_end_date=date(2026, 9, 3),
                status="selected",
                created_at=occurred_at,
                staff_name="王小美",
                willingness="willing",
                reason=None,
                information=CandidateInformationState(),
            ),
        ),
    )
    with pytest.raises(ValueError, match="read_only"):
        _manual_information_preview(
            selected, 8, 1, "phone", "電話確認", "admin"
        )


def test_candidate_projection_preserves_manual_confirmation_as_distinct_delivery_fact():
    occurred_at = datetime(2026, 8, 24, 11, 0, tzinfo=timezone.utc)
    _, _, information = _candidate_projection(
        [
            {
                "event_type": "info_1_sent",
                "payload": json.dumps(
                    {
                        "delivery_status": "manually_confirmed",
                        "confirmation_method": "phone",
                        "reason": "電話確認",
                    }
                ),
                "occurred_at": occurred_at,
            }
        ]
    )

    assert information["1"] == {
        "status": "manually_confirmed",
        "sent_at": occurred_at.isoformat(),
    }


def test_query_pool_returns_typed_full_projection_and_closes_resources(monkeypatch):
    pool = {"id": 3, "case_no": "CASE-1"}
    created_at = datetime(2026, 8, 22, 10, 0, tzinfo=timezone.utc)
    sent_at = datetime(2026, 8, 22, 10, 1, tzinfo=timezone.utc)
    entries = [
        {
            "id": 8,
            "staff_id": 7,
            "service_start_date": date(2026, 9, 1),
            "service_end_date": date(2026, 9, 3),
            "status": "active",
            "created_at": created_at,
            "staff_name": "王小美",
        }
    ]
    events = [
        {
            "id": 11,
            "candidate_id": 8,
            "event_type": "info_1_sent",
            "event_key": "evt-info",
            "actor": "admin",
            "payload": json.dumps({"delivery_status": "queued"}),
            "occurred_at": sent_at,
        },
        {
            "id": 12,
            "candidate_id": 8,
            "event_type": "willingness_changed",
            "event_key": "evt-willingness",
            "actor": "admin",
            "payload": json.dumps({"willingness": "willing", "reason": None}),
            "occurred_at": sent_at,
        },
    ]

    class FakeCursor:
        def __init__(self):
            self.fetchall_calls = 0
            self.closed = False

        def execute(self, query, params):
            del query, params

        def fetchone(self):
            return pool

        def fetchall(self):
            self.fetchall_calls += 1
            return entries if self.fetchall_calls == 1 else events

        def close(self):
            self.closed = True

        def commit(self):
            raise AssertionError("query_pool must not commit")

        def rollback(self):
            raise AssertionError("query_pool must not rollback")

    class FakeConnection:
        def __init__(self, cursor):
            self._cursor = cursor
            self.closed = False

        def cursor(self):
            return self._cursor

        def close(self):
            self.closed = True

        def commit(self):
            raise AssertionError("query_pool must not commit")

        def rollback(self):
            raise AssertionError("query_pool must not rollback")

    fake_cursor = FakeCursor()
    fake_connection = FakeConnection(fake_cursor)
    monkeypatch.setattr(workflow, "get_connection", lambda: fake_connection)

    result = workflow.query_pool("CASE-1")

    assert isinstance(result, CandidateContactPoolState)
    assert result.pool_id == 3
    assert result.case_no == "CASE-1"
    assert isinstance(result.candidates, tuple)
    assert len(result.candidates) == 1
    entry = result.candidates[0]
    assert isinstance(entry, CandidateContactEntryState)
    assert entry.service_start_date == date(2026, 9, 1)
    assert entry.service_end_date == date(2026, 9, 3)
    assert entry.created_at == created_at
    assert isinstance(entry.information, CandidateInformationState)
    assert isinstance(entry.information.information_1, CandidateInformationDelivery)
    assert entry.information.information_1.status == "queued"
    assert entry.information.information_1.sent_at == sent_at
    assert entry.willingness == "willing"
    assert entry.reason is None
    assert len(result.events) == 2
    assert [event.id for event in result.events] == [11, 12]
    assert result.events[0].event_key == "evt-info"
    assert result.events[0].actor == "admin"
    assert result.events[0].payload_fingerprint == fingerprint_payload(
        {"delivery_status": "queued"}
    ).value
    assert len(result.events[1].payload_fingerprint) == 64
    assert not hasattr(result.events[0], "payload")
    assert fake_cursor.closed is True
    assert fake_connection.closed is True
