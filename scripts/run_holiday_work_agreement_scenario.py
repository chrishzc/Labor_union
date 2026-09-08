"""Exercise national-holiday work agreements through the public typed APIs.

The runner creates only a fresh synthetic case in an explicitly selected
``lu_test_*`` database.  It verifies that an arbitrary calendar request cannot
work a holiday, a current dual agreement can, and a later decline supersedes
that agreement immediately.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys

from fastapi.testclient import TestClient


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import scripts.run_task96_hob_route_a as route_a
import scripts.run_task96_scheduling_lane_c as lane


CASE_NO = "HOLIDAY-WORK-AGREEMENT-20260302"
SCENARIO_ID = "HOLIDAY-WORK-AGREEMENT-20260302"
SERVICE_DATES = (
    "2026-02-27",
    "2026-03-03",
    "2026-03-04",
    "2026-03-05",
    "2026-03-06",
)
HOLIDAY_DATE = "2026-03-02"
ACTOR = "development-bypass"


def _configure_lane() -> None:
    lane.CASE_NO = CASE_NO
    lane.SCENARIO_ID = SCENARIO_ID
    lane.SERVICE_DATES = SERVICE_DATES
    lane.STAFF_IDENTITIES = ("C123456789", "D123456789")
    lane.STAFF_NAMES = ("國定假日驗收月嫂一", "國定假日驗收月嫂二")
    lane.STAFF_PHONES = ("0922030201", "0922030202")
    lane.STAFF_EMAILS = (
        "holiday-work-staff-1@example.test",
        "holiday-work-staff-2@example.test",
    )
    lane.STAFF_BANK_ACCOUNTS = ("020260302000001", "020260302000002")
    lane.STAFF_SOURCE_IDENTITIES = (
        "HOLIDAY-WORK-STAFF-001",
        "HOLIDAY-WORK-STAFF-002",
    )
    lane.CLIENT_NAME = "國定假日雙方同意驗收客戶"
    lane.CLIENT_PHONE = "0912030201"
    lane.CLIENT_EMAIL = "holiday-work-client@example.test"
    lane.CLIENT_SOURCE_IDENTITY = "HOLIDAY-WORK-CLIENT-001"
    lane.SOURCE_REVISION = "HOLIDAY-WORK-20260302-r1"
    lane.COMMAND_PREFIX = "holiday-work-20260302"
    lane.HCM_REPORTED_AT = "2026/02/20"
    lane.STAFF_REPORTED_AT = "2026-02-20"
    lane.MATCHING_AS_OF = "2026-02-20"
    lane._configure_route_a()


def _schedule(client: TestClient, *, arbitrary_work_date: bool = False) -> dict[str, object]:
    body: dict[str, object] = {
        "case_no": CASE_NO,
        "actual_start_date": SERVICE_DATES[0],
        "target_service_days": 5,
        "service_mode": "週休2日",
    }
    if arbitrary_work_date:
        body["custom_work_dates"] = [HOLIDAY_DATE]
    return lane._data(
        client.post("/api/v1/orders/calculate-schedule", json=body),
        "holiday_schedule_calculation",
    )


def _ensure_holiday(client: TestClient) -> dict[str, object]:
    """Create the declared synthetic holiday through its Q/P/A boundary."""
    command = {
        "action": "upsert",
        "holiday_date": HOLIDAY_DATE,
        "holiday_name": "驗收國定假日",
        "is_double_pay_default": False,
        "from_date": HOLIDAY_DATE,
        "to_date": HOLIDAY_DATE,
    }
    correlation_id = f"{SCENARIO_ID}:holiday:v1"
    preview = lane._data(
        client.post(
            "/api/v1/holidays/preview",
            json=command,
            headers={"X-Correlation-ID": correlation_id},
        ),
        "holiday_preview",
    )
    receipt = lane._data(
        client.post(
            "/api/v1/holidays/apply",
            json={
                **command,
                "expected_calendar_version": preview["command"]["expected_calendar_version"],
                "preview_fingerprint": preview["preview_fingerprint"],
                "reason": "建立僅供國定假日雙方同意情境的合成假日。",
            },
            headers={
                "Idempotency-Key": f"{SCENARIO_ID}:holiday:v1",
                "X-Correlation-ID": correlation_id,
            },
        ),
        "holiday_apply",
    )
    return receipt


def _holiday_worked(result: dict[str, object]) -> bool:
    holidays = result.get("national_holidays_found")
    if not isinstance(holidays, list):
        raise RuntimeError(f"national_holiday_readback_invalid:{result}")
    matched = [item for item in holidays if isinstance(item, dict) and item.get("date") == HOLIDAY_DATE]
    if len(matched) != 1:
        raise RuntimeError(f"expected_holiday_missing:{holidays}")
    return bool(matched[0].get("is_worked"))


def _participants(state: dict[str, object], *, second_decision: str) -> list[dict[str, object]]:
    segments = state.get("segments")
    if not isinstance(segments, list) or len(segments) != 2:
        raise RuntimeError(f"holiday_matching_segments_invalid:{state}")
    return [
        {"participant_role": "customer", "segment_id": None, "decision": "accepted"},
        {
            "participant_role": "caregiver",
            "segment_id": int(segments[0]["segment_id"]),
            "decision": "accepted",
        },
        {
            "participant_role": "caregiver",
            "segment_id": int(segments[1]["segment_id"]),
            "decision": second_decision,
        },
    ]


def _record_agreement(
    client: TestClient,
    *,
    plan_id: int,
    state: dict[str, object],
    event_key: str,
    second_decision: str,
) -> dict[str, object]:
    plan = state.get("plan")
    if not isinstance(plan, dict):
        raise RuntimeError(f"holiday_matching_plan_invalid:{state}")
    body = {
        "actor": ACTOR,
        "expected_version": int(plan["communication_version"]),
        "holiday_date": HOLIDAY_DATE,
        "reason": "逐一確認客戶與兩位月嫂對 2026-03-02 國定假日上班的協調結果。",
        "participant_decisions": _participants(
            state, second_decision=second_decision
        ),
    }
    path = f"/api/v1/orders/{CASE_NO}/matching-plans/{plan_id}/holiday-work-agreements"
    preview = lane._data(client.post(f"{path}/preview", json=body), "holiday_agreement_preview")
    receipt = lane._data(
        client.post(
            path,
            json={
                **body,
                "event_key": event_key,
                "preview_fingerprint": preview["preview_fingerprint"],
            },
        ),
        "holiday_agreement_apply",
    )
    return receipt


def run() -> dict[str, object]:
    database = lane._require_safe_environment()
    _configure_lane()
    os.environ["REACT_ADMIN_RUNTIME_PROFILE"] = "source"
    os.environ["REACT_ADMIN_CURRENT_ARTIFACT_DIR"] = ""
    os.environ["REACT_ADMIN_PREVIOUS_ARTIFACT_DIR"] = ""
    os.environ["REACT_ADMIN_ACTIVE_SELECTOR"] = ""
    from api.main import app

    with TestClient(app) as client:
        if not lane._assert_fresh(client):
            raise RuntimeError("holiday_work_scenario_case_must_be_fresh")
        holiday = _ensure_holiday(client)
        payment_destination = lane._ensure_client_payment_destination(client)
        roots = lane._import_roots(client)
        browser_fixture = os.getenv("HOLIDAY_WORK_BROWSER_FIXTURE", "").strip() == "1"
        plan_id, matching = lane._prepare_matching(
            client,
            list(roots["staff_ids"]),
            accept_customer=not browser_fixture,
        )
        contact_path = f"/api/v1/orders/{CASE_NO}/matching-plans/{plan_id}/contact-state"
        state = lane._data(client.get(contact_path), "holiday_contact_state")

        if browser_fixture:
            if state.get("customer_decision") not in {None, "pending"}:
                raise RuntimeError(f"holiday_browser_fixture_not_proposed:{state}")
            result = {
                "case_no": CASE_NO,
                "database": database,
                "holiday": holiday,
                "payment_destination": payment_destination,
                "plan_id": plan_id,
                "matching": matching,
                "fixture_status": "proposed_for_browser_agreement",
            }
            print(json.dumps(result, ensure_ascii=False, sort_keys=True, default=str))
            return result

        arbitrary = _schedule(client, arbitrary_work_date=True)
        if _holiday_worked(arbitrary) or arbitrary.get("actual_end_date") != "2026-03-06":
            raise RuntimeError(f"arbitrary_holiday_work_was_not_rejected:{arbitrary}")

        accepted = _record_agreement(
            client,
            plan_id=plan_id,
            state=state,
            event_key=f"{SCENARIO_ID}:accepted",
            second_decision="accepted",
        )
        after_accepted = _schedule(client)
        if not _holiday_worked(after_accepted) or after_accepted.get("actual_end_date") != "2026-03-05":
            raise RuntimeError(f"accepted_holiday_work_was_not_read_back:{after_accepted}")

        declined = _record_agreement(
            client,
            plan_id=plan_id,
            state=state,
            event_key=f"{SCENARIO_ID}:declined",
            second_decision="declined",
        )
        after_declined = _schedule(client)
        if _holiday_worked(after_declined) or after_declined.get("actual_end_date") != "2026-03-06":
            raise RuntimeError(f"declined_holiday_work_was_not_revoked:{after_declined}")

    result = {
        "case_no": CASE_NO,
        "database": database,
        "holiday": holiday,
        "payment_destination": payment_destination,
        "plan_id": plan_id,
        "arbitrary_holiday_work_rejected": True,
        "accepted_agreement": accepted,
        "accepted_schedule_end_date": after_accepted["actual_end_date"],
        "declined_agreement": declined,
        "declined_schedule_end_date": after_declined["actual_end_date"],
    }
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, default=str))
    return result


if __name__ == "__main__":
    run()
