from datetime import datetime, timezone

from subsystems.scheduling.candidate_contact_pool_workflow import (
    _candidate_projection,
    _coverage_fingerprint,
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
