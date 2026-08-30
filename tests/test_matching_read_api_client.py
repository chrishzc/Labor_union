from datetime import date

import pytest

from ui.api_clients.matching_read_api_client import (
    MatchingReadApiClient,
    MatchingReadApiError,
)


class _Response:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.ok = status_code < 400

    def json(self):
        return self._payload


class _Session:
    def __init__(self, payloads):
        self._payloads = iter(payloads)
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return _Response(next(self._payloads))


def _active_plan_payload():
    return {
        "plan": {
            "id": 3,
            "case_no": "CASE-97",
            "version": 1,
            "status": "proposed",
            "is_active": 1,
            "order_status": "洽談中",
            "client_line_user_id": None,
        },
        "segments": [
            {
                "segment_id": 4,
                "segment_order": 1,
                "staff_id": 8,
                "assigned_start_date": "2026-09-01",
                "assigned_end_date": "2026-09-07",
                "staff_name": "測試月嫂",
                "staff_line_user_id": None,
                "willingness": "pending",
                "info_1_sent": False,
                "info_2_sent": False,
                "resume_sent": False,
            }
        ],
        "all_willing": False,
        "availability_lock": None,
        "deposit": None,
    }


def _contact_state_payload():
    return {
        "plan": {
            "id": 3,
            "case_no": "CASE-97",
            "communication_version": 2,
            "status": "proposed",
            "is_active": 1,
        },
        "segments": [
            {
                "segment_id": 4,
                "segment_order": 1,
                "staff_id": 8,
                "staff_name": "測試月嫂",
                "assigned_start_date": "2026-09-01",
                "assigned_end_date": "2026-09-07",
                "willingness": "pending",
                "info_1_status": None,
                "info_2_status": None,
            }
        ],
        "all_willing": False,
        "customer_decision": "pending",
        "customer_profiles_status": None,
        "customer_profiles_manual_confirmation": None,
    }


def _pool_payload():
    return {
        "pool_id": 5,
        "case_no": "CASE-97",
        "candidates": [
            {
                "id": 6,
                "staff_id": 8,
                "service_start_date": "2026-09-01",
                "service_end_date": "2026-09-07",
                "status": "active",
                "created_at": "2026-08-30T01:00:00Z",
                "staff_name": "測試月嫂",
                "willingness": "pending",
                "reason": None,
                "information": {},
            }
        ],
    }


def _availability_payload():
    return {
        "case_no": "CASE-97",
        "planned_start_date": "2026-09-01",
        "planned_end_date": "2026-09-07",
        "feasibility": "complete",
        "complete_combinations": [],
        "segment_candidates": [],
        "candidate_options": [],
        "conflicts": [],
    }


def test_matching_read_client_validates_all_matching_read_models():
    session = _Session(
        [
            {"success": True, "data": _active_plan_payload()},
            {"success": True, "data": _contact_state_payload()},
            {"success": True, "data": _pool_payload()},
            {"success": True, "data": _availability_payload()},
        ]
    )
    client = MatchingReadApiClient(
        base_url="http://api.test/",
        headers={"Authorization": "Bearer test"},
        session=session,
    )

    active = client.active_plan(" CASE-97 ")
    contact = client.contact_state("CASE-97", 3)
    pool = client.candidate_contact_pool("CASE-97")
    availability = client.search_availability(
        "CASE-97",
        segment_count=1,
        segment_drafts=[{"start_date": date(2026, 9, 1), "end_date": date(2026, 9, 7)}],
        as_of=date(2026, 8, 30),
    )

    assert active.plan.id == 3
    assert contact.segments[0].staff_id == 8
    assert pool.candidates[0].staff_name == "測試月嫂"
    assert availability.planned_start_date == date(2026, 9, 1)
    assert session.calls[-1][2]["json"]["as_of"] == "2026-08-30"


def test_matching_read_client_rejects_response_contract_drift():
    malformed = {**_active_plan_payload(), "raw_database_row": {"secret": "no"}}
    client = MatchingReadApiClient(
        base_url="http://api.test",
        headers={},
        session=_Session([{"success": True, "data": malformed}]),
    )

    with pytest.raises(MatchingReadApiError) as error:
        client.active_plan("CASE-97")

    assert error.value.code == "matching_read_invalid_response"
