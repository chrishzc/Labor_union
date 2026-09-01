"""建立 OPS96-SCHED-C-001 的 Scheduling UI 驗收資料。

This is a bounded, no-auth TestClient scenario.  It deliberately uses the
public typed import, matching, assignment-plan, actual-start and
leave-substitution APIs; it does not seed owner roots with SQL.
"""

from __future__ import annotations

from datetime import date
import json
import os
from pathlib import Path
import re
import sys
from tempfile import TemporaryDirectory

import pandas as pd
from fastapi.testclient import TestClient


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import scripts.run_task96_hob_route_a as route_a


CASE_NO = "OPS96-SCHED-C-001"
SCENARIO_ID = "OPS96-SCHED-C-001"
SERVICE_DATES = ("2026-09-07", "2026-09-08", "2026-09-09", "2026-09-10", "2026-09-11")
STAFF_IDENTITIES = ("A123456789", "B123456789")
STAFF_NAMES = ("OPS96 C 段月嫂一", "OPS96 C 段月嫂二")
STAFF_PHONES = ("0922960011", "0922960012")
STAFF_EMAILS = ("ops96-c-staff-1@example.test", "ops96-c-staff-2@example.test")
STAFF_BANK_ACCOUNTS = ("0096000000000101", "0096000000000102")
STAFF_SOURCE_IDENTITIES = ("OPS96-SCHED-C-STAFF-001", "OPS96-SCHED-C-STAFF-002")
CLIENT_NAME = "OPS96 C 段合成客戶"
CLIENT_PHONE = "0911960001"
CLIENT_EMAIL = "ops96-sched-c-client@example.test"
CLIENT_SOURCE_IDENTITY = "OPS96-SCHED-C-CLIENT-001"
SOURCE_REVISION = "OPS96-SCHED-C-001-r1"
COMMAND_PREFIX = "ops96-sched-c-001"
ACTOR = "development-bypass"
XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _require_safe_environment() -> str:
    expected = {
        "APP_ENV": "development",
        "ACCESS_CONTROL_PROFILE": "local_bypass",
        "ENABLE_ADMIN_AUTH": "false",
    }
    mismatches = {
        key: {"expected": value, "observed": os.getenv(key, "")}
        for key, value in expected.items()
        if os.getenv(key, "").lower() != value
    }
    database = os.getenv("DB_DATABASE", "")
    if re.fullmatch(r"lu_test_[a-z0-9_]+", database) is None:
        mismatches["DB_DATABASE"] = {"expected": "lu_test_*", "observed": database}
    if not os.getenv("DB_PASSWORD"):
        mismatches["DB_PASSWORD"] = {"expected": "present", "observed": "missing"}
    if mismatches:
        raise RuntimeError(f"OPS96_SCHED_C_ENVIRONMENT_MISMATCH:{json.dumps(mismatches)}")
    return database


def _data(response, operation: str) -> dict[str, object]:
    if response.status_code not in {200, 202}:
        raise RuntimeError(f"{operation}_failed:{response.status_code}:{response.text[:1200]}")
    payload = response.json()
    value = payload.get("data")
    if not isinstance(value, dict):
        raise RuntimeError(f"{operation}_response_invalid")
    return value


def _list_data(response, operation: str) -> list[object]:
    if response.status_code != 200:
        raise RuntimeError(f"{operation}_failed:{response.status_code}:{response.text[:1200]}")
    value = response.json().get("data")
    if not isinstance(value, list):
        raise RuntimeError(f"{operation}_response_invalid")
    return value


def _configure_route_a() -> None:
    # Reuse only deterministic workbook/finance/job helpers; all route calls
    # below remain this runner's independent case and command identities.
    route_a.SCENARIO_ID = SCENARIO_ID
    route_a.CASE_NO = CASE_NO
    route_a.CLIENT_NAME = CLIENT_NAME
    route_a.CLIENT_PHONE = CLIENT_PHONE
    route_a.CLIENT_EMAIL = CLIENT_EMAIL
    route_a.CLIENT_SOURCE_IDENTITY = CLIENT_SOURCE_IDENTITY
    route_a.SERVICE_DATES = SERVICE_DATES
    route_a.SOURCE_REVISION = SOURCE_REVISION
    route_a.COMMAND_IDENTITY_PREFIX = COMMAND_PREFIX
    route_a.DEPOSIT_SOURCE_IDENTITY = "OPS96-SCHED-C-001-DEP-001"
    route_a.STAFF_NAME = STAFF_NAMES[0]
    route_a.STAFF_IDENTITY = STAFF_IDENTITIES[0]
    route_a.STAFF_PHONE = STAFF_PHONES[0]
    route_a.STAFF_EMAIL = STAFF_EMAILS[0]
    route_a.STAFF_BANK_ACCOUNT = STAFF_BANK_ACCOUNTS[0]


def _staff_workbook() -> bytes:
    rows = []
    for index in range(2):
        rows.append(
            {
                "查詢序號": STAFF_SOURCE_IDENTITIES[index],
                "報名時間": "2026-08-20",
                "IP位址": "",
                "姓名": STAFF_NAMES[index],
                "身分證字號": STAFF_IDENTITIES[index],
                "行動電話": STAFF_PHONES[index],
                "EMAIL": STAFF_EMAILS[index],
                "出生年": 79,
                "月": 1,
                "日": 2 + index,
                "縣市": "新竹市",
                "地址": f"OPS96 測試路 {index + 1} 號",
                "銀行帳號": STAFF_BANK_ACCOUNTS[index],
                "銀行代3碼+分行代號4碼": "8120001",
                "[其它].1": "新竹市",
                "8小時": "Y",
                "葷食": "Y",
                "機車": "Y",
                "週休2日": "Y",
                "單胞胎": "Y",
            }
        )
    return route_a._canonical_xlsx(pd.DataFrame(rows), "OPS96-SCHED-C-Staff")


def _assert_fresh(client: TestClient) -> bool:
    response = client.get(f"/api/v1/orders/{CASE_NO}")
    if response.status_code == 404:
        return True
    if response.status_code == 200:
        value = response.json().get("data")
        if isinstance(value, dict) and value.get("case_no") == CASE_NO:
            return False
    raise RuntimeError(f"OPS96_SCHED_C_CASE_NOT_FRESH:{response.status_code}:{response.text[:400]}")


def _import_roots(client: TestClient) -> dict[str, object]:
    hcm_preview, hcm_apply = route_a._preview_apply_workbook(
        client,
        name="ops96-sched-c-hcm",
        content=route_a._hcm_workbook(),
        preview_path="/api/v1/case-import/hcm/workbooks/preview",
        apply_path="/api/v1/case-import/hcm/workbooks/apply",
    )
    staff_preview, staff_apply = route_a._preview_apply_workbook(
        client,
        name="ops96-sched-c-staff",
        content=_staff_workbook(),
        preview_path="/api/v1/case-import/staff-historical/workbooks/preview",
        apply_path="/api/v1/case-import/staff-historical/workbooks/apply",
        form={"source_revision": SOURCE_REVISION},
        command_version=2,
    )
    client_preview, client_apply = route_a._preview_apply_client_beclass(client)
    dates_preview, dates_apply = route_a._confirm_service_dates(client)
    if dates_apply.get("service_dates") not in (list(SERVICE_DATES), None):
        if dates_apply.get("current_dates") != list(SERVICE_DATES):
            raise RuntimeError(f"service_dates_readback_mismatch:{dates_apply}")
    staff_page = route_a._require_success(
        client.get("/api/v1/staff/summaries", params={"page_size": 200}),
        "staff_readback",
    )
    items = staff_page.get("items")
    if not isinstance(items, list):
        raise RuntimeError("staff_readback_items_invalid")
    selected = [item for item in items if item.get("name") in STAFF_NAMES]
    if len(selected) != 2 or {item.get("name") for item in selected} != set(STAFF_NAMES):
        raise RuntimeError(f"staff_identity_readback_invalid:{selected}")
    staff_by_name = {item["name"]: int(item["id"]) for item in selected}
    return {
        "hcm": {"ready": hcm_preview.get("ready_count"), "created": hcm_apply.get("inserted_count")},
        "staff": {"ready": staff_preview.get("created_count"), "created": staff_apply.get("created_count")},
        "client": {"ready": client_preview.get("create_count"), "created": client_apply.get("created_count")},
        "service_dates": dates_apply.get("service_dates") or dates_apply.get("current_dates"),
        "service_dates_preview_fingerprint": dates_preview.get("preview_fingerprint"),
        "staff_ids": [staff_by_name[name] for name in STAFF_NAMES],
    }


def _prepare_matching(client: TestClient, staff_ids: list[int]) -> tuple[int, dict[str, object]]:
    active_response = client.get(f"/api/v1/orders/{CASE_NO}/matching-plans/active")
    if active_response.status_code == 200:
        active = route_a._require_success(active_response, "matching_active_plan_resume")
        plan = active.get("plan")
        segments = active.get("segments")
        if isinstance(plan, dict) and isinstance(segments, list) and len(segments) == 2:
            plan_id = int(plan["id"])
            return plan_id, {"plan_id": plan_id, "segments": segments, "status": plan.get("status")}
    for staff_id in staff_ids:
        route_a._ensure_staff_preferences(client, staff_id)
    for staff_id in staff_ids:
        # The contact-pool contract requires each candidate to prove full
        # case coverage.  Segmentation is selected only by the later plan.
        start, end = SERVICE_DATES[0], SERVICE_DATES[-1]
        pool_path = f"/api/v1/orders/{CASE_NO}/candidate-contact-pool"
        pool = route_a._require_success(client.get(pool_path), "candidate_pool_query")
        candidates = pool.get("candidates")
        if not isinstance(candidates, list):
            raise RuntimeError("candidate_pool_invalid")
        candidate = next((item for item in candidates if int(item.get("staff_id", 0)) == staff_id), None)
        if candidate is None:
            added = route_a._require_success(
                client.post(
                    f"{pool_path}/candidates",
                    json={"actor": ACTOR, "event_key": f"{SCENARIO_ID}:candidate:{staff_id}", "candidates": [{"staff_id": staff_id, "start_date": start, "end_date": end}]},
                ),
                "candidate_pool_add",
            )
            candidate_id = int(added["candidate_ids"][0])
        else:
            candidate_id = int(candidate["id"])
        pool = route_a._require_success(client.get(pool_path), "candidate_pool_readback")
        candidate = next(item for item in pool["candidates"] if int(item["id"]) == candidate_id)
        information = candidate.get("information") or {}
        if information.get("1") is None and information.get("information_1") is None:
            preview = route_a._require_success(
                client.post(f"{pool_path}/candidates/{candidate_id}/information/manual-confirmation/preview", json={"info_type": 1, "confirmation_method": "phone", "reason": "OPS96 C 段候選資訊確認", "actor": ACTOR}),
                "candidate_information_preview",
            )
            route_a._require_success(
                client.post(
                    f"{pool_path}/candidates/{candidate_id}/information/manual-confirmation",
                    json={"info_type": 1, "confirmation_method": "phone", "reason": "OPS96 C 段候選資訊確認", "actor": ACTOR, "event_key": f"{SCENARIO_ID}:candidate-info:{staff_id}", "expected_version": preview["expected_version"], "preview_fingerprint": preview["preview_fingerprint"]},
                ),
                "candidate_information_apply",
            )
        if candidate.get("willingness") != "willing":
            route_a._require_success(
                client.put(
                    f"{pool_path}/candidates/{candidate_id}/willingness",
                    json={"actor": ACTOR, "event_key": f"{SCENARIO_ID}:candidate-willing:{staff_id}", "willingness": "willing", "reason": "OPS96 C 段候選接案意願"},
                ),
                "candidate_willingness_apply",
            )
    segments = [
        {"staff_id": staff_ids[0], "start_date": SERVICE_DATES[0], "end_date": SERVICE_DATES[2]},
        {"staff_id": staff_ids[1], "start_date": SERVICE_DATES[3], "end_date": SERVICE_DATES[4]},
    ]
    availability = route_a._require_success(
        client.post(f"/api/v1/orders/{CASE_NO}/caregiver-segment-availability/search", json={"segment_count": 2, "segment_drafts": segments, "as_of": "2026-09-01"}),
        "matching_availability",
    )
    if availability.get("feasibility") != "complete" or availability.get("conflicts"):
        raise RuntimeError(f"matching_availability_not_complete:{availability}")
    created = route_a._require_success(
        client.post(f"/api/v1/orders/{CASE_NO}/matching-plans", json={"segments": segments, "created_by": ACTOR, "as_of": "2026-09-01"}),
        "matching_plan_create",
    )
    plan_id = int(created["plan_id"])
    state = route_a._matching_contact_state(client, plan_id)
    for segment in state["segments"]:
        if segment.get("willingness") != "willing":
            version = int(state["plan"]["communication_version"])
            route_a._require_success(
                client.put(
                    f"/api/v1/orders/{CASE_NO}/matching-plans/{plan_id}/segments/{segment['segment_id']}/willingness",
                    json={"event_key": f"{SCENARIO_ID}:plan-willing:{segment['segment_id']}", "actor": ACTOR, "willingness": "willing", "expected_version": version, "reason": "OPS96 C 段月嫂確認意願"},
                ),
                "matching_willingness",
            )
            state = route_a._matching_contact_state(client, plan_id)
    if state.get("customer_profiles_manual_confirmation") is None:
        version = int(state["plan"]["communication_version"])
        body = {"actor": ACTOR, "confirmation_method": "phone", "reason": "OPS96 C 段客戶收到雙段履歷", "expected_version": version}
        preview = route_a._require_success(client.post(f"/api/v1/orders/{CASE_NO}/matching-plans/{plan_id}/resumes/manual-confirmation/preview", json=body), "matching_profiles_preview")
        route_a._require_success(client.post(f"/api/v1/orders/{CASE_NO}/matching-plans/{plan_id}/resumes/manual-confirmation", json={**body, "event_key": f"{SCENARIO_ID}:profiles", "preview_fingerprint": preview["preview_fingerprint"]}), "matching_profiles_apply")
        state = route_a._matching_contact_state(client, plan_id)
    if state.get("customer_decision") != "accepted":
        route_a._require_success(
            client.put(
                f"/api/v1/orders/{CASE_NO}/matching-plans/{plan_id}/customer-decision",
                json={"event_key": f"{SCENARIO_ID}:customer-accepted", "actor": ACTOR, "decision": "accepted", "expected_version": state["plan"]["communication_version"], "reason": "OPS96 C 段客戶接受雙段媒合"},
            ),
            "matching_customer_decision",
        )
    return plan_id, {"plan_id": plan_id, "segments": segments, "status": "accepted"}


def _complete_contract_and_schedule(client: TestClient, plan_id: int) -> dict[str, object]:
    # A prior interrupted run can leave the plan proposed after contracts were
    # recorded.  Finish the typed contact-state gate before locking dates.
    contact_path = f"/api/v1/orders/{CASE_NO}/matching-plans/{plan_id}/contact-state"
    contact = route_a._require_success(client.get(contact_path), "matching_contact_resume")
    for segment in contact.get("segments", []):
        if segment.get("willingness") == "willing":
            continue
        route_a._require_success(
            client.put(
                f"/api/v1/orders/{CASE_NO}/matching-plans/{plan_id}/segments/{segment['segment_id']}/willingness",
                json={"event_key": f"{SCENARIO_ID}:resume-willing:{segment['segment_id']}", "actor": ACTOR, "willingness": "willing", "expected_version": contact["plan"]["communication_version"], "reason": "OPS96 C 段月嫂確認意願"},
            ),
            "matching_resume_willingness",
        )
        contact = route_a._require_success(client.get(contact_path), "matching_contact_after_willing")
    if contact.get("customer_profiles_manual_confirmation") is None:
        body = {"actor": ACTOR, "confirmation_method": "phone", "reason": "OPS96 C 段客戶收到雙段履歷", "expected_version": contact["plan"]["communication_version"]}
        preview = route_a._require_success(client.post(f"/api/v1/orders/{CASE_NO}/matching-plans/{plan_id}/resumes/manual-confirmation/preview", json=body), "matching_resume_profiles_preview")
        route_a._require_success(client.post(f"/api/v1/orders/{CASE_NO}/matching-plans/{plan_id}/resumes/manual-confirmation", json={**body, "event_key": f"{SCENARIO_ID}:resume-profiles", "preview_fingerprint": preview["preview_fingerprint"]}), "matching_resume_profiles_apply")
        contact = route_a._require_success(client.get(contact_path), "matching_contact_after_profiles")
    if contact.get("customer_decision") != "accepted":
        route_a._require_success(client.put(f"/api/v1/orders/{CASE_NO}/matching-plans/{plan_id}/customer-decision", json={"event_key": f"{SCENARIO_ID}:resume-customer-accepted", "actor": ACTOR, "decision": "accepted", "expected_version": contact["plan"]["communication_version"], "reason": "OPS96 C 段客戶接受雙段媒合"}), "matching_resume_customer_decision")
    base = f"/api/v1/orders/{CASE_NO}/contract-signing"
    status = route_a._require_success(client.get(base), "contract_signing_query")
    for segment in status.get("staff_segments", []):
        if int(segment.get("segment_id", 0)) <= 0 or segment.get("signed_received"):
            continue
        reason = "OPS96 C 段紙本合約人工確認"
        preview = route_a._require_success(client.post(f"{base}/staff-segments/{segment['segment_id']}/manual-attestation/preview", json={"confirmation_method": "paper", "reason": reason}), "staff_contract_preview")
        route_a._require_success(
            client.post(
                f"{base}/staff-segments/{segment['segment_id']}/manual-attestation",
                files={"document": (route_a.STAFF_CONTRACT_FIXTURE.name, route_a.STAFF_CONTRACT_FIXTURE.read_bytes(), XLSX_MEDIA_TYPE)},
                data={"confirmation_method": "paper", "reason": reason, "preview_fingerprint": preview["preview_fingerprint"]},
                headers={"Idempotency-Key": f"{SCENARIO_ID}:contract-staff:{segment['segment_id']}", "X-Correlation-ID": f"{SCENARIO_ID}:contract-staff:{segment['segment_id']}"},
            ),
            "staff_contract_apply",
        )
    status = route_a._require_success(client.get(base), "contract_signing_after_staff")
    if not status.get("client_signed_received"):
        reason = "OPS96 C 段客戶紙本合約人工確認"
        preview = route_a._require_success(client.post(f"{base}/client/manual-attestation/preview", json={"confirmation_method": "paper", "reason": reason}), "client_contract_preview")
        route_a._require_success(
            client.post(
                f"{base}/client/manual-attestation",
                files={"document": (route_a.CLIENT_CONTRACT_FIXTURE.name, route_a.CLIENT_CONTRACT_FIXTURE.read_bytes(), XLSX_MEDIA_TYPE)},
                data={"confirmation_method": "paper", "reason": reason, "preview_fingerprint": preview["preview_fingerprint"]},
                headers={"Idempotency-Key": f"{SCENARIO_ID}:contract-client", "X-Correlation-ID": f"{SCENARIO_ID}:contract-client"},
            ),
            "client_contract_apply",
        )
    confirmation_path = f"/api/v1/orders/{CASE_NO}/matching-plans/{plan_id}/schedule-confirmation"
    confirmation = route_a._require_success(client.get(confirmation_path), "schedule_confirmation_query")
    if confirmation.get("snapshot_status") not in {"manual_ready", "sent"}:
        preview = route_a._require_success(client.post(f"{confirmation_path}/manual-preview"), "schedule_confirmation_preview")
        confirmation = route_a._require_success(
            client.post(f"{confirmation_path}/manual-apply", json={"confirmed_service_date_version": preview["confirmed_service_date_version"], "preview_fingerprint": preview["preview_fingerprint"], "reason": "OPS96 C 段雙方日期表人工確認"}, headers={"Idempotency-Key": f"{SCENARIO_ID}:schedule-manual"}),
            "schedule_confirmation_apply",
        )
    recipients = confirmation.get("recipients")
    if not isinstance(recipients, list) or len(recipients) != 3:
        raise RuntimeError(f"schedule_confirmation_recipients_invalid:{confirmation}")
    for recipient in recipients:
        if recipient.get("confirmation_status") in {"confirmed", "manually_confirmed"}:
            continue
        recipient_id = int(recipient["recipient_snapshot_id"])
        route_a._require_success(
            client.put(f"/api/v1/orders/schedule-confirmation/recipients/{recipient_id}", json={"value": "manually_confirmed", "reason": "OPS96 C 段雙方日期表人工確認"}, headers={"Idempotency-Key": f"{SCENARIO_ID}:recipient:{recipient_id}"}),
            "schedule_recipient_confirm",
        )
    final = route_a._require_success(client.get(confirmation_path), "schedule_confirmation_readback")
    if not final.get("gate_passed"):
        raise RuntimeError(f"schedule_confirmation_gate_not_passed:{final}")
    return {"commitment_id": status.get("commitment_id"), "recipient_count": len(recipients), "gate_passed": True}


def _apply_assignment_and_start(client: TestClient, plan_id: int, staff_ids: list[int]) -> dict[str, object]:
    route_a._ensure_deposit_root(client)
    segments = [
        {"staff_id": staff_ids[0], "assigned_start_date": SERVICE_DATES[0], "assigned_end_date": SERVICE_DATES[2], "official_service_dates": list(SERVICE_DATES[:3])},
        {"staff_id": staff_ids[1], "assigned_start_date": SERVICE_DATES[3], "assigned_end_date": SERVICE_DATES[4], "official_service_dates": list(SERVICE_DATES[3:])},
    ]
    path = f"/api/v1/orders/{CASE_NO}/assignment-plan"
    assignment = route_a._require_success(client.get(path), "assignment_plan_readback")
    if len(assignment.get("assignments", [])) != 2:
        lock_path = f"/api/v1/orders/{CASE_NO}/matching-plans/{plan_id}/waiting-deposit-lock/acquire"
        active_matching = route_a._require_success(client.get(f"/api/v1/orders/{CASE_NO}/matching-plans/active"), "matching_active_before_lock")
        existing_lock = active_matching.get("availability_lock")
        if isinstance(existing_lock, dict):
            lock_preview = {"result": "existing", "lock_id": existing_lock.get("lock_id")}
            lock = lock_preview
        else:
            lock_preview = route_a._require_success(client.post(f"{lock_path}/preview"), "waiting_lock_preview")
            lock = route_a._require_success(client.post(f"{lock_path}/apply", json={"preview_fingerprint": lock_preview["preview_fingerprint"]}, headers={"Idempotency-Key": f"{COMMAND_PREFIX}:waiting-lock", "X-Correlation-ID": f"{COMMAND_PREFIX}:waiting-lock"}), "waiting_lock_apply")
        preview = route_a._require_success(client.post(f"{path}/preview", json={"segments": segments}, headers={"X-Correlation-ID": f"{COMMAND_PREFIX}:assignment-preview"}), "assignment_plan_preview")
        accepted = route_a._require_success(
            client.post(
                f"{path}/apply",
                json={"segments": segments, "expected_order_version": preview["order_version"], "expected_scheduling_version": preview["scheduling_version"], "expected_client_finance_version": preview["client_finance_version"], "expected_payroll_version": preview["payroll_version"], "preview_fingerprint": preview["preview_fingerprint"], "reason": "OPS96 C 段雙月嫂正式多段排班"},
                headers={"Idempotency-Key": f"{COMMAND_PREFIX}:assignment-apply", "X-Correlation-ID": f"{COMMAND_PREFIX}:assignment-apply"},
            ),
            "assignment_plan_apply",
        )
        job_id = str(accepted["job_id"])
        route_a._run_one_durable_job()
        job = route_a._require_success(client.get(f"/api/v1/jobs/{job_id}"), "assignment_job")
        if job.get("status") != "succeeded":
            raise RuntimeError(f"assignment_job_not_succeeded:{job}")
        assignment = route_a._require_success(client.get(path), "assignment_plan_readback")
        if len(assignment.get("assignments", [])) != 2:
            raise RuntimeError(f"assignment_plan_segments_invalid:{assignment}")
    else:
        lock = {"result": "consumed_by_assignment"}
        lock_preview = {}
    actual_path = f"/api/v1/orders/{CASE_NO}/actual-start"
    actual_query = route_a._require_success(client.get(actual_path), "actual_start_query")
    target_actual_start = "2026-09-01"
    if actual_query.get("current_actual_start_date") == target_actual_start:
        actual = actual_query
    else:
        actual_preview = route_a._require_success(
            client.post(f"{actual_path}/preview", json={"new_actual_start_date": target_actual_start}, headers={"X-Correlation-ID": f"{COMMAND_PREFIX}:actual-start-preview"}),
            "actual_start_preview",
        )
        actual_receipt = route_a._require_success(
            client.post(
                f"{actual_path}/apply",
                json={"new_actual_start_date": target_actual_start, "expected_order_version": actual_preview["order_version"], "expected_scheduling_version": actual_preview["scheduling_version"], "expected_client_finance_version": actual_preview["client_finance_version"], "expected_payroll_version": actual_preview["payroll_version"], "preview_fingerprint": actual_preview["preview_fingerprint"], "reason": "OPS96 C 段服務中調班驗收：確認實際開工日"},
                headers={"Idempotency-Key": f"{COMMAND_PREFIX}:actual-start-correction", "X-Correlation-ID": f"{COMMAND_PREFIX}:actual-start-correction"},
            ),
            "actual_start_apply",
        )
        actual = {"query": route_a._require_success(client.get(actual_path), "actual_start_readback"), "receipt": actual_receipt}
    actual_state = actual.get("query", actual)
    actual_receipt = actual.get("receipt", {})
    order_state = route_a._require_success(client.get(f"/api/v1/orders/{CASE_NO}"), "actual_start_order_readback")
    lifecycle_status = actual_receipt.get("lifecycle_status") or order_state.get("order_status")
    if actual_state.get("current_actual_start_date") != target_actual_start or lifecycle_status != "服務中":
        raise RuntimeError(f"actual_start_readback_invalid:{actual}")
    return {"waiting_lock_id": lock.get("lock_id") or lock_preview.get("lock_id"), "assignment": assignment, "actual_start": actual}


def _apply_leave_substitution(client: TestClient, staff_ids: list[int]) -> dict[str, object]:
    path = f"/api/v1/orders/{CASE_NO}/leave-substitution"
    assignments = _list_data(client.get(f"{path}/assignments"), "leave_assignments_query")
    if len(assignments) == 3:
        return {"result": "existing", "readback": assignments}
    if not isinstance(assignments, list) or len(assignments) != 2:
        raise RuntimeError(f"leave_assignments_invalid:{assignments}")
    original = next(item for item in assignments if int(item["staff_id"]) == staff_ids[0])
    schedule = original["official_schedules"][0]
    body = {"original_assignment_id": int(original["assignment_id"]), "items": [{"original_schedule_id": int(schedule["schedule_id"]), "work_date": schedule["work_date"], "resolution_type": "substitute", "substitute_staff_id": staff_ids[1], "is_double_pay": False}]}
    preview = route_a._require_success(client.post(f"{path}/preview", json=body, headers={"X-Correlation-ID": f"{SCENARIO_ID}:leave-preview"}), "leave_substitution_preview")
    if preview.get("apply_readiness", {}).get("status") != "ready":
        raise RuntimeError(f"leave_substitution_not_ready:{preview}")
    receipt = route_a._require_success(
        client.post(
            f"{path}/apply",
            json={**body, "expected_order_version": preview["order_version"], "expected_scheduling_version": preview["scheduling_version"], "expected_client_finance_version": preview["client_finance_version"], "expected_payroll_version": preview["payroll_version"], "preview_fingerprint": preview["preview_fingerprint"], "reason": "OPS96 C 段服務中請假代班正式套用"},
            headers={"Idempotency-Key": f"{COMMAND_PREFIX}:leave-apply", "X-Correlation-ID": f"{COMMAND_PREFIX}:leave-apply"},
        ),
        "leave_substitution_apply",
    )
    readback = _list_data(client.get(f"{path}/assignments"), "leave_assignments_readback")
    return {"original_assignment_id": original["assignment_id"], "schedule_id": schedule["schedule_id"], "preview_fingerprint": preview["preview_fingerprint"], "receipt": receipt, "readback": readback}


def run() -> dict[str, object]:
    database = _require_safe_environment()
    _configure_route_a()
    # The repository dotenv file may contain deployment artifact placeholders;
    # this disposable runner explicitly selects the source runtime before the
    # FastAPI module is imported.
    os.environ["REACT_ADMIN_RUNTIME_PROFILE"] = "source"
    os.environ["REACT_ADMIN_CURRENT_ARTIFACT_DIR"] = ""
    os.environ["REACT_ADMIN_PREVIOUS_ARTIFACT_DIR"] = ""
    os.environ["REACT_ADMIN_ACTIVE_SELECTOR"] = ""
    previous_archive_root = os.environ.get("CONTRACT_DOCUMENT_ARCHIVE_ROOT")
    with TemporaryDirectory(prefix="task96-contract-archive-") as archive_root:
        os.environ["CONTRACT_DOCUMENT_ARCHIVE_ROOT"] = archive_root
        try:
            from api.main import app

            with TestClient(app) as client:
                fresh = _assert_fresh(client)
                roots = _import_roots(client) if fresh else {"service_dates": list(SERVICE_DATES), "staff_ids": []}
                if not roots["staff_ids"]:
                    staff_page = route_a._require_success(client.get("/api/v1/staff/summaries", params={"page_size": 200}), "staff_resume_readback")
                    items = staff_page.get("items")
                    selected = [item for item in items if item.get("name") in STAFF_NAMES] if isinstance(items, list) else []
                    if len(selected) != 2:
                        raise RuntimeError(f"staff_resume_identity_invalid:{selected}")
                    roots["staff_ids"] = [int(next(item["id"] for item in selected if item["name"] == name)) for name in STAFF_NAMES]
                staff_ids = list(roots["staff_ids"])
                plan_id, matching = _prepare_matching(client, staff_ids)
                contract = _complete_contract_and_schedule(client, plan_id)
                assignment = _apply_assignment_and_start(client, plan_id, staff_ids)
                leave = _apply_leave_substitution(client, staff_ids)
                calendars = []
                for staff_id in staff_ids:
                    calendars.append(_data(client.get(f"/api/v1/scheduling/staff/{staff_id}/current-calendar", params={"range_start": "2026-09-01", "range_end": "2026-09-30"}), f"calendar_readback_{staff_id}"))
                assignment_readback = _data(client.get(f"/api/v1/orders/{CASE_NO}/assignment-plan"), "assignment_final_readback")
        finally:
            if previous_archive_root is None:
                os.environ.pop("CONTRACT_DOCUMENT_ARCHIVE_ROOT", None)
            else:
                os.environ["CONTRACT_DOCUMENT_ARCHIVE_ROOT"] = previous_archive_root
    result = {"case_no": CASE_NO, "database": database, "service_month": "2026-09", "service_dates": list(SERVICE_DATES), "staff_ids": staff_ids, "staff_names": list(STAFF_NAMES), "matching": matching, "contract_and_schedule": contract, "assignment": assignment, "leave_substitution": leave, "calendar_readback": calendars, "assignment_readback": assignment_readback}
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return result


if __name__ == "__main__":
    run()
