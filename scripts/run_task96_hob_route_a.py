"""
File: route_a_runtime.py
Description: 以合成來源和正式 no-auth API 重建 Task 96 HOB-F Route A 完整 command lineage。
"""

from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
import json
import os
from pathlib import Path
import re
import sys
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

import pandas as pd
from fastapi.testclient import TestClient


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


SCENARIO_ID = "HOB-F04-ROUTE-A-001"
CASE_NO = "115960401"
DATABASE = "lu_test_task96_scenarios_20260827"
STAFF_IDENTITY = "A123456789"
STAFF_BANK_ACCOUNT = "0096000000000001"
CLIENT_NAME = "Task96 合成客戶"
STAFF_NAME = "Task96 合成月嫂"
CLIENT_PHONE = "0911000401"
STAFF_PHONE = "0922000401"
CLIENT_EMAIL = "task96-client@example.test"
STAFF_EMAIL = "task96-staff@example.test"
STAFF_SOURCE_IDENTITY = "TASK96-STAFF-001"
CLIENT_SOURCE_IDENTITY = "TASK96-CLIENT-001"
DEPOSIT_SOURCE_IDENTITY = "TASK96-DEP-001"
PAYOUT_SOURCE_IDENTITY = "TASK96-PAYOUT-001"
SOURCE_REVISION = "HOB-F04-ROUTE-A-001-r2"
COMMAND_IDENTITY_PREFIX = "hob-f04-route-a-001"
ACTOR = "development-bypass"
SERVICE_DATES = (
    "2026-07-01",
    "2026-07-02",
    "2026-07-03",
    "2026-07-06",
    "2026-07-07",
)
STAFF_PREFERENCE_VALUES = [
    {
        "preference_key": "daily_service_hours",
        "value": {"kind": "integer_set", "values": [8]},
    },
    {
        "preference_key": "preferred_service_days",
        "value": {"kind": "integer_range", "minimum": 1, "maximum": 60},
    },
]
XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
STAFF_CONTRACT_FIXTURE = (
    PROJECT_ROOT / "validation/fixtures/contract_signing/staff_contract_upload.xlsx"
)
CLIENT_CONTRACT_FIXTURE = (
    PROJECT_ROOT / "validation/fixtures/contract_signing/client_contract_upload.xlsx"
)
_ZIP_TIMESTAMP = (2026, 8, 27, 0, 0, 0)
_SOURCE_MODIFIED_AT = b"2026-08-27T12:46:36Z"


def _require_safe_environment() -> None:
    expected = {
        "APP_ENV": "development",
        "ACCESS_CONTROL_PROFILE": "local_bypass",
        "ENABLE_ADMIN_AUTH": "false",
        "DB_DATABASE": DATABASE,
    }
    observed = {key: os.getenv(key, "").strip() for key in expected}
    mismatches = {
        key: {"expected": value, "observed": observed[key]}
        for key, value in expected.items()
        if observed[key].lower() != value.lower()
    }
    if mismatches:
        raise RuntimeError(f"task96_route_a_environment_mismatch:{json.dumps(mismatches, ensure_ascii=False)}")
    if not os.getenv("DB_PASSWORD"):
        raise RuntimeError("task96_route_a_database_credential_missing")


def _canonical_xlsx(frame: pd.DataFrame, sheet_name: str) -> bytes:
    raw = BytesIO()
    with pd.ExcelWriter(raw, engine="openpyxl") as writer:
        frame.to_excel(writer, sheet_name=sheet_name, index=False)
        properties = writer.book.properties
        fixed = datetime(2026, 8, 27, tzinfo=timezone.utc)
        properties.created = fixed
        properties.modified = fixed
        properties.creator = "Task 96 validation"
        properties.lastModifiedBy = "Task 96 validation"
    source = BytesIO(raw.getvalue())
    target = BytesIO()
    with ZipFile(source, "r") as current, ZipFile(target, "w", ZIP_DEFLATED) as canonical:
        for name in sorted(current.namelist()):
            content = current.read(name)
            if name == "docProps/core.xml":
                content = re.sub(
                    rb"<dcterms:modified[^>]*>[^<]+</dcterms:modified>",
                    b'<dcterms:modified xsi:type="dcterms:W3CDTF">'
                    + _SOURCE_MODIFIED_AT
                    + b"</dcterms:modified>",
                    content,
                )
            info = ZipInfo(name, _ZIP_TIMESTAMP)
            info.compress_type = ZIP_DEFLATED
            info.external_attr = 0o600 << 16
            canonical.writestr(info, content)
    return target.getvalue()


def _hcm_workbook() -> bytes:
    row = {
        "案件狀態": "洽談中",
        "查詢序號(案件編號)": CASE_NO,
        "報名時間(建檔)": "2026/06/01",
        "IP位址": "192.0.2.96",
        "姓名": CLIENT_NAME,
        "性別": "女",
        "行動電話": CLIENT_PHONE,
        "縣市": "新竹市",
        "身分資格": "一般市民",
        "服務時間": "8 小時 09:00 17:00",
        "預產期/預計服務開始月份": "2026/06/15",
        "預計服務日期": SERVICE_DATES[0].replace("-", "/"),
        "希望服務天數": 5,
        "居住型態": "大樓",
        "生產方式": "自然產",
        "服務方式": "週休2日",
        "寶寶資訊": "Task96 去識別合成來源",
    }
    return _canonical_xlsx(pd.DataFrame([row]), "Task96-HCM")


def _staff_workbook() -> bytes:
    row = {
        "查詢序號": STAFF_SOURCE_IDENTITY,
        "報名時間": "2026-06-01",
        "IP位址": "",
        "姓名": STAFF_NAME,
        "身分證字號": STAFF_IDENTITY,
        "行動電話": STAFF_PHONE,
        "EMAIL": STAFF_EMAIL,
        "出生年": 79,
        "月": 1,
        "日": 2,
        "縣市": "新竹市",
        "地址": "測試路 96 號",
        "銀行帳號": STAFF_BANK_ACCOUNT,
        "銀行代3碼+分行代號4碼": "8120001",
        "北區": "Y",
        "8小時": "Y",
        "葷食": "Y",
        "機車": "Y",
        "週休2日": "Y",
        "單胞胎": "Y",
    }
    return _canonical_xlsx(pd.DataFrame([row]), "Task96-Staff")


def _client_beclass_workbook() -> bytes:
    row = {
        "查詢序號": CLIENT_SOURCE_IDENTITY,
        "報名時間": "2026-06-01",
        "姓名": CLIENT_NAME,
        "Email": CLIENT_EMAIL,
        "出生年": 79,
        "月": 1,
        "日": 2,
        "行動電話": CLIENT_PHONE,
        "縣市": "新竹市",
        "地址": "測試路 96 號",
        "補助款退款:銀行代號+分行代號": "",
        "銀行帳號": "",
        "月子餐點調理喜好/飲食習慣：": "葷食",
    }
    return _canonical_xlsx(pd.DataFrame([row]), "Task96-Client")


def _finance_deposit_workbook() -> bytes:
    row = {
        "序號": DEPOSIT_SOURCE_IDENTITY,
        "交易日期": "2026/06/05",
        "交易時間": "09:06:04",
        "帳務日期": "2026/06/05",
        "摘要": "Task96 合成訂金",
        "支出金額": "",
        "存入金額": 12000,
        "帳戶餘額": 12000,
        "備註": f"{SCENARIO_ID} synthetic deposit",
    }
    return _canonical_xlsx(pd.DataFrame([row]), "交易明細查詢")


def _finance_staff_payout_workbook() -> bytes:
    row = {
        "序號": PAYOUT_SOURCE_IDENTITY,
        "交易日期": "2026/07/15",
        "交易時間": "09:07:15",
        "帳務日期": "2026/07/15",
        "摘要": "Task96 合成月嫂薪資",
        "支出金額": 12000,
        "存入金額": "",
        "帳戶餘額": 0,
        "備註": f"{STAFF_NAME},{STAFF_BANK_ACCOUNT}",
    }
    return _canonical_xlsx(pd.DataFrame([row]), "交易明細查詢")


def _require_success(response, operation: str) -> dict[str, object]:
    if response.status_code not in {200, 202}:
        raise RuntimeError(
            f"{operation}_failed:{response.status_code}:{response.text[:1000]}"
        )
    envelope = response.json()
    data = envelope.get("data")
    if not isinstance(data, dict):
        raise RuntimeError(f"{operation}_invalid_response")
    return data


def _preview_apply_workbook(
    client: TestClient,
    *,
    name: str,
    content: bytes,
    preview_path: str,
    apply_path: str,
    form: dict[str, str] | None = None,
    command_version: int = 1,
) -> tuple[dict[str, object], dict[str, object]]:
    files = {"workbook": (f"{name}.xlsx", content, XLSX_MEDIA_TYPE)}
    preview = _require_success(
        client.post(preview_path, files=files, data=form or {}),
        f"{name}_preview",
    )
    fingerprint = preview.get("preview_fingerprint")
    if not isinstance(fingerprint, str) or len(fingerprint) != 64:
        raise RuntimeError(f"{name}_preview_fingerprint_invalid")
    apply = _require_success(
        client.post(
            apply_path,
            files=files,
            data=form or {},
            headers={
                "Idempotency-Key": f"{SCENARIO_ID}:{name}:apply:v{command_version}",
                "X-Correlation-ID": f"{SCENARIO_ID}:{name}:apply:v{command_version}",
                "X-Preview-Fingerprint": fingerprint,
            },
        ),
        f"{name}_apply",
    )
    return preview, apply


def _preview_apply_client_beclass(
    client: TestClient,
) -> tuple[dict[str, object], dict[str, object]]:
    content = _client_beclass_workbook()
    files = {"workbook": ("client-beclass.xlsx", content, XLSX_MEDIA_TYPE)}
    preview = _require_success(
        client.post(
            "/api/v1/case-import/client-beclass/workbooks/preview",
            files=files,
        ),
        "client_beclass_preview",
    )
    fingerprint = preview.get("preview_fingerprint")
    if not isinstance(fingerprint, str) or len(fingerprint) != 64:
        raise RuntimeError("client_beclass_preview_fingerprint_invalid")
    command_identity = f"{SCENARIO_ID}:client-beclass:apply:v1"
    apply = _require_success(
        client.post(
            "/api/v1/case-import/client-beclass/workbooks/apply",
            files=files,
            data={"preview_fingerprint": fingerprint},
            headers={
                "Idempotency-Key": command_identity,
                "X-Correlation-ID": command_identity,
            },
        ),
        "client_beclass_apply",
    )
    return preview, apply


def _confirm_service_dates(
    client: TestClient,
) -> tuple[dict[str, object], dict[str, object]]:
    path = f"/api/v1/orders/{CASE_NO}/service-dates"
    current = _require_success(client.get(path), "service_dates_query")
    dates = list(SERVICE_DATES)
    selectable = current.get("selectable_dates")
    if (
        current.get("contracted_service_days") != len(dates)
        or not isinstance(selectable, list)
        or not set(dates) <= set(selectable)
    ):
        raise RuntimeError("service_dates_candidate_invalid")
    if current.get("current_dates") == dates:
        return current, current
    correlation = f"{SCENARIO_ID}:service-dates:v1"
    preview = _require_success(
        client.post(
            f"{path}/preview",
            json={"service_dates": dates},
            headers={"X-Correlation-ID": correlation},
        ),
        "service_dates_preview",
    )
    apply = _require_success(
        client.post(
            f"{path}/apply",
            json={
                "service_dates": dates,
                "expected_order_version": preview["order_version"],
                "expected_scheduling_version": preview["scheduling_version"],
                "preview_fingerprint": preview["preview_fingerprint"],
                "reason": "Task 96 HOB-F Route A 合成情境確認服務日期",
            },
            headers={
                "Idempotency-Key": correlation,
                "X-Correlation-ID": correlation,
            },
        ),
        "service_dates_apply",
    )
    return preview, apply


def _ensure_client_region(
    client: TestClient,
    client_id: int,
) -> dict[str, object]:
    path = f"/api/v1/admin/data-browser/clients/{client_id}/source-correction"
    preview = _require_success(
        client.post(f"{path}/preview", json={"updates": {"address": "北區"}}),
        "client_region_preview",
    )
    changes = preview.get("changes")
    if not isinstance(changes, dict):
        raise RuntimeError("client_region_preview_invalid")
    if not changes:
        return {"result": "existing", "changed_fields": []}
    identity = f"{SCENARIO_ID}:client-region:v1"
    return _require_success(
        client.post(
            f"{path}/apply",
            json={
                "updates": {"address": "北區"},
                "preview_fingerprint": preview["preview_fingerprint"],
                "reason": "Task 96 HOB-F Route A 合成媒合區域",
            },
            headers={"Idempotency-Key": identity},
        ),
        "client_region_apply",
    )


def _ensure_staff_preferences(
    client: TestClient,
    staff_id: int,
) -> dict[str, object]:
    path = f"/api/v1/scheduling/staff-matching-preferences/staff/{staff_id}"
    current = _require_success(client.get(path), "staff_preferences_query")
    if current.get("values") == STAFF_PREFERENCE_VALUES:
        return current
    preview = _require_success(
        client.post(f"{path}/preview", json={"values": STAFF_PREFERENCE_VALUES}),
        "staff_preferences_preview",
    )
    identity = f"{SCENARIO_ID}:staff-preferences:v1"
    return _require_success(
        client.post(
            f"{path}/apply",
            json={
                "values": STAFF_PREFERENCE_VALUES,
                "expected_version": preview["version"],
                "preview_fingerprint": preview["preview_fingerprint"],
                "reason": "Task 96 HOB-F Route A 合成媒合偏好",
            },
            headers={
                "Idempotency-Key": identity,
                "X-Correlation-ID": identity,
            },
        ),
        "staff_preferences_apply",
    )


def _matching_contact_state(
    client: TestClient,
    plan_id: int,
) -> dict[str, object]:
    return _require_success(
        client.get(
            f"/api/v1/orders/{CASE_NO}/matching-plans/{plan_id}/contact-state"
        ),
        "matching_contact_state",
    )


def _run_stage_02(
    client: TestClient,
    staff_id: int,
) -> dict[str, object]:
    segments = [
        {
            "staff_id": staff_id,
            "start_date": SERVICE_DATES[0],
            "end_date": SERVICE_DATES[-1],
        }
    ]
    active_response = client.get(f"/api/v1/orders/{CASE_NO}/matching-plans/active")
    if active_response.status_code == 200:
        active = _require_success(active_response, "matching_active_plan")
        plan = {"plan_id": active["plan"]["id"], "result": "existing"}
    else:
        if active_response.status_code != 404:
            _require_success(active_response, "matching_active_plan")
        availability = _require_success(
            client.post(
                f"/api/v1/orders/{CASE_NO}/caregiver-segment-availability/search",
                json={
                    "segment_count": 1,
                    "segment_drafts": segments,
                    "as_of": "2026-06-01",
                },
            ),
            "matching_availability",
        )
        if availability.get("feasibility") != "complete" or availability.get("conflicts"):
            raise RuntimeError("matching_availability_not_complete")
        plan = _require_success(
            client.post(
                f"/api/v1/orders/{CASE_NO}/matching-plans",
                json={
                    "segments": segments,
                    "created_by": ACTOR,
                    "as_of": "2026-06-01",
                },
            ),
            "matching_plan_create",
        )
    plan_id = int(plan["plan_id"])
    state = _matching_contact_state(client, plan_id)
    state_segments = state.get("segments")
    if not isinstance(state_segments, list) or len(state_segments) != 1:
        raise RuntimeError("matching_contact_segments_invalid")
    segment = state_segments[0]
    if segment.get("willingness") != "willing":
        version = int(state["plan"]["communication_version"])
        _require_success(
            client.put(
                f"/api/v1/orders/{CASE_NO}/matching-plans/{plan_id}/segments/{segment['segment_id']}/willingness",
                json={
                    "event_key": f"{SCENARIO_ID}:willing:v1",
                    "actor": ACTOR,
                    "willingness": "willing",
                    "expected_version": version,
                    "reason": "Task 96 HOB-F Route A 合成 Staff 確認意願",
                },
            ),
            "matching_willingness",
        )
        state = _matching_contact_state(client, plan_id)
    if state.get("customer_profiles_manual_confirmation") is None:
        version = int(state["plan"]["communication_version"])
        body = {
            "actor": ACTOR,
            "confirmation_method": "phone",
            "reason": "Task 96 HOB-F Route A 合成人工履歷送達",
            "expected_version": version,
        }
        preview = _require_success(
            client.post(
                f"/api/v1/orders/{CASE_NO}/matching-plans/{plan_id}/resumes/manual-confirmation/preview",
                json=body,
            ),
            "matching_profiles_preview",
        )
        _require_success(
            client.post(
                f"/api/v1/orders/{CASE_NO}/matching-plans/{plan_id}/resumes/manual-confirmation",
                json={
                    **body,
                    "event_key": f"{SCENARIO_ID}:profiles:v1",
                    "preview_fingerprint": preview["preview_fingerprint"],
                },
            ),
            "matching_profiles_apply",
        )
        state = _matching_contact_state(client, plan_id)
    if state.get("customer_decision") != "accepted":
        version = int(state["plan"]["communication_version"])
        _require_success(
            client.put(
                f"/api/v1/orders/{CASE_NO}/matching-plans/{plan_id}/customer-decision",
                json={
                    "event_key": f"{SCENARIO_ID}:customer-accepted:v1",
                    "actor": ACTOR,
                    "decision": "accepted",
                    "expected_version": version,
                    "reason": "Task 96 HOB-F Route A 合成客戶接受媒合",
                },
            ),
            "matching_customer_decision",
        )
        state = _matching_contact_state(client, plan_id)
    return {
        "stage": "stage-02-matching",
        "plan_id": plan_id,
        "plan_result": plan.get("result"),
        "plan_status": state["plan"]["status"],
        "communication_version": state["plan"]["communication_version"],
        "willingness": state["segments"][0]["willingness"],
        "customer_profiles_status": state.get("customer_profiles_status"),
        "customer_profiles_manual_confirmation": (
            state.get("customer_profiles_manual_confirmation") is not None
        ),
        "customer_decision": state.get("customer_decision"),
    }


def _run_stage_03(
    client: TestClient,
    plan_id: int,
) -> dict[str, object]:
    base = f"/api/v1/orders/{CASE_NO}/contract-signing"
    status = _require_success(client.get(base), "contract_signing_query")
    staff_segments = [
        item
        for item in status.get("staff_segments", [])
        if int(item["segment_id"]) > 0
    ]
    if len(staff_segments) != 1:
        raise RuntimeError("contract_signing_staff_segments_invalid")
    segment = staff_segments[0]
    segment_id = int(segment["segment_id"])
    if not segment.get("signed_received"):
        reason = "Task 96 HOB-F Route A 合成月嫂紙本簽署驗證"
        preview = _require_success(
            client.post(
                f"{base}/staff-segments/{segment_id}/manual-attestation/preview",
                json={"confirmation_method": "paper", "reason": reason},
            ),
            "staff_contract_manual_preview",
        )
        identity = f"{SCENARIO_ID}:staff-contract:v1"
        _require_success(
            client.post(
                f"{base}/staff-segments/{segment_id}/manual-attestation",
                files={
                    "document": (
                        STAFF_CONTRACT_FIXTURE.name,
                        STAFF_CONTRACT_FIXTURE.read_bytes(),
                        XLSX_MEDIA_TYPE,
                    )
                },
                data={
                    "confirmation_method": "paper",
                    "reason": reason,
                    "preview_fingerprint": preview["preview_fingerprint"],
                },
                headers={
                    "Idempotency-Key": identity,
                    "X-Correlation-ID": identity,
                },
            ),
            "staff_contract_manual_apply",
        )
        status = _require_success(client.get(base), "contract_signing_staff_readback")
    if status.get("commitment_id") is None:
        raise RuntimeError("precontract_commitment_not_created")
    if not status.get("client_signed_received"):
        reason = "Task 96 HOB-F Route A 合成客戶紙本簽署驗證"
        preview = _require_success(
            client.post(
                f"{base}/client/manual-attestation/preview",
                json={"confirmation_method": "paper", "reason": reason},
            ),
            "client_contract_manual_preview",
        )
        identity = f"{SCENARIO_ID}:client-contract:v1"
        _require_success(
            client.post(
                f"{base}/client/manual-attestation",
                files={
                    "document": (
                        CLIENT_CONTRACT_FIXTURE.name,
                        CLIENT_CONTRACT_FIXTURE.read_bytes(),
                        XLSX_MEDIA_TYPE,
                    )
                },
                data={
                    "confirmation_method": "paper",
                    "reason": reason,
                    "preview_fingerprint": preview["preview_fingerprint"],
                },
                headers={
                    "Idempotency-Key": identity,
                    "X-Correlation-ID": identity,
                },
            ),
            "client_contract_manual_apply",
        )
        status = _require_success(client.get(base), "contract_signing_client_readback")
    if not status.get("client_signed_received") or not status.get("contract_identity"):
        raise RuntimeError("contract_signing_not_complete")
    return {
        "stage": "stage-03-commitment",
        "plan_id": plan_id,
        "segment_id": segment_id,
        "commitment_id": status["commitment_id"],
        "staff_signed_received": status["staff_segments"][0]["signed_received"],
        "client_signed_received": status["client_signed_received"],
        "contract_identity": status["contract_identity"],
        "document_count": len(status.get("documents", [])),
    }


def _confirm_matching_schedule(
    client: TestClient,
    plan_id: int,
) -> dict[str, object]:
    path = f"/api/v1/orders/{CASE_NO}/matching-plans/{plan_id}/schedule-confirmation"
    state = _require_success(client.get(path), "matching_schedule_query")
    if state.get("gate_passed"):
        return state
    if state.get("snapshot_status") not in {"manual_ready", "sent"}:
        preview = _require_success(
            client.post(f"{path}/manual-preview"),
            "matching_schedule_manual_preview",
        )
        identity = f"{SCENARIO_ID}:schedule-snapshot:v1"
        state = _require_success(
            client.post(
                f"{path}/manual-apply",
                json={
                    "confirmed_service_date_version": preview[
                        "confirmed_service_date_version"
                    ],
                    "preview_fingerprint": preview["preview_fingerprint"],
                    "reason": "Task 96 HOB-F Route A 合成雙方日期確認",
                },
                headers={"Idempotency-Key": identity},
            ),
            "matching_schedule_manual_apply",
        )
    recipients = state.get("recipients")
    if not isinstance(recipients, list) or len(recipients) != 2:
        raise RuntimeError("matching_schedule_recipients_invalid")
    for recipient in recipients:
        if recipient.get("confirmation_status") in {"confirmed", "manually_confirmed"}:
            continue
        recipient_id = int(recipient["recipient_snapshot_id"])
        identity = f"{SCENARIO_ID}:schedule-recipient:{recipient_id}:v1"
        _require_success(
            client.put(
                f"/api/v1/orders/schedule-confirmation/recipients/{recipient_id}",
                json={
                    "value": "manually_confirmed",
                    "reason": "Task 96 HOB-F Route A 合成雙方人工確認",
                },
                headers={"Idempotency-Key": identity},
            ),
            "matching_schedule_recipient_confirm",
        )
    state = _require_success(client.get(path), "matching_schedule_gate_readback")
    if not state.get("gate_passed"):
        raise RuntimeError("matching_schedule_gate_not_passed")
    return state


def _assignment_matches(query: dict[str, object], staff_id: int) -> bool:
    assignments = query.get("assignments")
    return (
        isinstance(assignments, list)
        and len(assignments) == 1
        and assignments[0].get("staff_id") == staff_id
        and assignments[0].get("assigned_start_date") == SERVICE_DATES[0]
        and assignments[0].get("assigned_end_date") == SERVICE_DATES[-1]
        and assignments[0].get("official_service_dates") == list(SERVICE_DATES)
    )


def _run_one_durable_job() -> bool:
    from infrastructure.mysql.background_job_repository import BackgroundJobRepository
    from infrastructure.mysql.mysql_adapter import get_connection
    from api.dependencies.durable_job_handlers import default_job_handlers
    from subsystems.jobs.durable_job_worker import DurableJobWorker

    connection = get_connection()
    try:
        return DurableJobWorker(
            BackgroundJobRepository(connection),
            connection,
            default_job_handlers(),
            f"{SCENARIO_ID}:worker:v1",
            retry_delay_seconds=0,
        ).recover_and_run_once()
    finally:
        connection.close()


def _ensure_deposit_root(client: TestClient) -> dict[str, object]:
    receipt_path = f"/api/v1/orders/{CASE_NO}/client-finance/receipt-reconciliation"
    receipt_facts = _require_success(client.get(receipt_path), "client_receipt_query")
    deposit_obligations = [
        item
        for item in receipt_facts.get("obligations", [])
        if item.get("payment_stage") == "deposit"
    ]
    if not deposit_obligations:
        return {"result": "existing", "account_version": receipt_facts["account_version"]}
    if len(deposit_obligations) != 1 or deposit_obligations[0].get("amount_due_ntd") != 12000:
        raise RuntimeError("deposit_obligation_invalid")
    workbook = _finance_deposit_workbook()
    identity = f"{SCENARIO_ID}:finance-ingest:v1"
    ingest = _require_success(
        client.post(
            "/api/v1/finance-import/workbooks/ingest",
            files={
                "workbook": (
                    "task96-deposit.xlsx",
                    workbook,
                    XLSX_MEDIA_TYPE,
                )
            },
            headers={
                "Idempotency-Key": identity,
                "X-Correlation-ID": identity,
            },
        ),
        "finance_deposit_ingest",
    )
    batch_identity = str(ingest["batch_identity"])
    preview = _require_success(
        client.post(
            "/api/v1/finance-import/batches/preview",
            json={"batch_identity": batch_identity},
            headers={"X-Correlation-ID": f"{SCENARIO_ID}:finance-preview:v1"},
        ),
        "finance_deposit_batch_preview",
    )
    rows = preview.get("rows")
    if not isinstance(rows, list) or len(rows) != 1 or rows[0].get("amount_ntd") != 12000:
        raise RuntimeError("finance_deposit_row_invalid")
    from infrastructure.mysql.anomaly_runtime import build_anomaly_runtime
    from infrastructure.mysql.mysql_adapter import get_connection
    from subsystems.finance_import.finance_import_anomaly_consumer import (
        consume_finance_import_anomaly_events,
    )

    anomaly_connection = get_connection()
    try:
        projected = consume_finance_import_anomaly_events(
            anomaly_connection, runtime=build_anomaly_runtime()
        )
    finally:
        anomaly_connection.close()
    if projected.failed_count:
        raise RuntimeError("finance_deposit_anomaly_projection_failed")
    selection = {
        "row_identity": rows[0]["row_identity"],
        "classification_type": "client_receipt",
        "target_obligation_identities": [deposit_obligations[0]["obligation_identity"]],
        "reason": "Task 96 HOB-F Route A 合成訂金已核對",
        "evidence": [
            f"scenario:{SCENARIO_ID}",
            f"synthetic-bank-row:{DEPOSIT_SOURCE_IDENTITY}",
        ],
    }
    correction = _require_success(
        client.post(
            "/api/v1/finance-import/corrections/preview",
            json=selection,
            headers={"X-Correlation-ID": f"{SCENARIO_ID}:finance-correction-preview:v1"},
        ),
        "finance_deposit_correction_preview",
    )
    apply_identity = f"{COMMAND_IDENTITY_PREFIX}:finance-correction:v1"
    accepted = _require_success(
        client.post(
            "/api/v1/finance-import/corrections/apply",
            json={
                **selection,
                "expected_batch_version": correction["batch_version"],
                "expected_canonical_fact_version": correction["canonical_fact_version"],
                "expected_alert_version": correction["alert_version"],
                "preview_fingerprint": correction["preview_fingerprint"],
            },
            headers={
                "Idempotency-Key": apply_identity,
                "X-Correlation-ID": apply_identity,
            },
        ),
        "finance_deposit_correction_apply",
    )
    _run_one_durable_job()
    job_id = str(accepted["job_id"])
    outcome = _require_success(
        client.get(f"/api/v1/finance-import/jobs/{job_id}/correction-outcome"),
        "finance_deposit_correction_outcome",
    )
    if outcome.get("status") != "succeeded":
        raise RuntimeError(f"finance_deposit_job_not_succeeded:{outcome}")
    receipt_facts = _require_success(client.get(receipt_path), "client_receipt_readback")
    if any(
        item.get("payment_stage") == "deposit"
        for item in receipt_facts.get("obligations", [])
    ):
        raise RuntimeError("deposit_obligation_not_reconciled")
    return {
        "result": "created",
        "batch_identity": batch_identity,
        "row_identity": rows[0]["row_identity"],
        "job_id": job_id,
        "account_version": receipt_facts["account_version"],
    }


def _run_stage_04(
    client: TestClient,
    plan_id: int,
    staff_id: int,
) -> dict[str, object]:
    assignment_path = f"/api/v1/orders/{CASE_NO}/assignment-plan"
    query = _require_success(client.get(assignment_path), "assignment_plan_query")
    if _assignment_matches(query, staff_id):
        return {
            "stage": "stage-04-assignment",
            "result": "existing",
            "plan_id": plan_id,
            "assignment": query["assignments"][0],
            "scheduling_generation": query["scheduling_generation"],
        }
    deposit = _ensure_deposit_root(client)
    schedule = _confirm_matching_schedule(client, plan_id)
    lock_identity = f"{SCENARIO_ID}:waiting-lock:v1"
    contact_state = _matching_contact_state(client, plan_id)
    if contact_state["plan"]["status"] == "accepted":
        from infrastructure.mysql.mysql_adapter import get_connection
        from subsystems.scheduling.availability_lock_acquisition_workflow import (
            acquire_caregiver_availability_lock,
        )

        recovery_connection = get_connection()
        try:
            with recovery_connection.cursor() as cursor:
                cursor.execute(
                    "SELECT payload FROM caregiver_availability_lock_events "
                    "WHERE event_key=%s",
                    (lock_identity,),
                )
                event = cursor.fetchone()
        finally:
            recovery_connection.close()
        if not isinstance(event, dict):
            raise RuntimeError("waiting_lock_recovery_event_missing")
        payload = json.loads(event["payload"])
        preview_fingerprint = payload.get("preview_fingerprint")
        if not isinstance(preview_fingerprint, str):
            raise RuntimeError("waiting_lock_recovery_fingerprint_missing")
        lock = acquire_caregiver_availability_lock(
            CASE_NO,
            plan_id,
            lock_identity,
            ACTOR,
            preview_fingerprint,
        )
    else:
        lock_path = (
            f"/api/v1/orders/{CASE_NO}/matching-plans/{plan_id}/"
            "waiting-deposit-lock/acquire"
        )
        lock_preview = _require_success(
            client.post(f"{lock_path}/preview"),
            "waiting_deposit_lock_preview",
        )
        if not lock_preview.get("apply_allowed"):
            raise RuntimeError("waiting_deposit_lock_not_allowed")
        lock = _require_success(
            client.post(
                f"{lock_path}/apply",
                json={"preview_fingerprint": lock_preview["preview_fingerprint"]},
                headers={
                    "Idempotency-Key": lock_identity,
                    "X-Correlation-ID": lock_identity,
                },
            ),
            "waiting_deposit_lock_apply",
        )
    segments = [
        {
            "staff_id": staff_id,
            "assigned_start_date": SERVICE_DATES[0],
            "assigned_end_date": SERVICE_DATES[-1],
            "official_service_dates": list(SERVICE_DATES),
        }
    ]
    preview = _require_success(
        client.post(
            f"{assignment_path}/preview",
            json={"segments": segments},
            headers={"X-Correlation-ID": f"{SCENARIO_ID}:assignment-preview:v1"},
        ),
        "assignment_plan_preview",
    )
    identity = f"{COMMAND_IDENTITY_PREFIX}:assignment-apply:v1"
    accepted = _require_success(
        client.post(
            f"{assignment_path}/apply",
            json={
                "segments": segments,
                "expected_order_version": preview["order_version"],
                "expected_scheduling_version": preview["scheduling_version"],
                "expected_client_finance_version": preview["client_finance_version"],
                "expected_payroll_version": preview["payroll_version"],
                "preview_fingerprint": preview["preview_fingerprint"],
                "reason": "Task 96 HOB-F Route A 合成正式 assignment",
            },
            headers={
                "Idempotency-Key": identity,
                "X-Correlation-ID": identity,
            },
        ),
        "assignment_plan_apply",
    )
    job_id = str(accepted["job_id"])
    _run_one_durable_job()
    job = _require_success(client.get(f"/api/v1/jobs/{job_id}"), "assignment_job")
    if job.get("status") != "succeeded":
        raise RuntimeError(f"assignment_job_not_succeeded:{job}")
    query = _require_success(client.get(assignment_path), "assignment_plan_readback")
    if not _assignment_matches(query, staff_id):
        raise RuntimeError("assignment_plan_readback_mismatch")
    return {
        "stage": "stage-04-assignment",
        "result": "created",
        "plan_id": plan_id,
        "schedule_snapshot_id": schedule["snapshot_id"],
        "waiting_lock_id": lock["lock_id"],
        "deposit": deposit,
        "job_id": job_id,
        "assignment": query["assignments"][0],
        "scheduling_generation": query["scheduling_generation"],
    }


def _run_stage_05(client: TestClient) -> dict[str, object]:
    path = f"/api/v1/orders/{CASE_NO}/actual-start"
    query = _require_success(client.get(path), "actual_start_query")
    if query.get("current_actual_start_date") == SERVICE_DATES[0]:
        return {
            "stage": "stage-05-in-service",
            "result": "existing",
            "actual_start_date": query["current_actual_start_date"],
            "service_data_lock_formed": query["service_data_locked"],
            "order_version": query["order_version"],
            "scheduling_version": query["scheduling_version"],
            "client_finance_version": query["client_finance_version"],
            "payroll_version": query["payroll_version"],
        }
    preview = _require_success(
        client.post(
            f"{path}/preview",
            json={"new_actual_start_date": SERVICE_DATES[0]},
            headers={"X-Correlation-ID": f"{SCENARIO_ID}:actual-start-preview:v1"},
        ),
        "actual_start_preview",
    )
    identity = f"{COMMAND_IDENTITY_PREFIX}:actual-start-apply:v1"
    receipt = _require_success(
        client.post(
            f"{path}/apply",
            json={
                "new_actual_start_date": SERVICE_DATES[0],
                "expected_order_version": preview["order_version"],
                "expected_scheduling_version": preview["scheduling_version"],
                "expected_client_finance_version": preview[
                    "client_finance_version"
                ],
                "expected_payroll_version": preview["payroll_version"],
                "preview_fingerprint": preview["preview_fingerprint"],
                "reason": "Task 96 HOB-F Route A 合成正式 actual start",
            },
            headers={
                "Idempotency-Key": identity,
                "X-Correlation-ID": identity,
            },
        ),
        "actual_start_apply",
    )
    readback = _require_success(client.get(path), "actual_start_readback")
    if (
        readback.get("current_actual_start_date") != SERVICE_DATES[0]
        or receipt.get("lifecycle_status") != "服務中"
        or receipt.get("official_service_day_count") != len(SERVICE_DATES)
    ):
        raise RuntimeError(
            f"actual_start_readback_mismatch:{json.dumps({'receipt': receipt, 'readback': readback}, ensure_ascii=False, default=str)}"
        )
    return {
        "stage": "stage-05-in-service",
        "result": "created",
        "actual_start_date": readback["current_actual_start_date"],
        "actual_end_date": preview["actual_end_date"],
        "lifecycle_status": receipt["lifecycle_status"],
        "service_data_lock_formed": receipt["service_data_lock_formed"],
        "official_service_day_count": receipt["official_service_day_count"],
        "official_service_hours": receipt["official_service_hours"],
        "order_version": receipt["order_version"],
        "scheduling_version": receipt["scheduling_version"],
        "client_finance_version": receipt["client_finance_version"],
        "payroll_version": receipt["payroll_version"],
        "preview_fingerprint": receipt["preview_fingerprint"],
    }


def _historical_completion(client: TestClient) -> dict[str, object]:
    return _require_success(
        client.get(
            f"/api/v1/orders/{CASE_NO}/historical-completion",
            headers={
                "X-Correlation-ID": f"{SCENARIO_ID}:historical-completion-query:v1"
            },
        ),
        "historical_completion_query",
    )


def _run_stage_06(client: TestClient) -> dict[str, object]:
    order = _require_success(
        client.get(f"/api/v1/orders/{CASE_NO}"),
        "service_completion_order_query",
    )
    if order.get("order_status") == "訂單完成":
        completion = _historical_completion(client)
        if any(
            alert.get("owner") in {"orders", "scheduling"}
            for alert in completion.get("active_alerts", [])
        ):
            raise RuntimeError(
                f"service_completion_owner_readback_blocked:{json.dumps(completion, ensure_ascii=False)}"
            )
        return {
            "stage": "stage-06-service-complete",
            "result": "existing",
            "order_status": order["order_status"],
            "owner_projection": completion,
        }
    evaluation_at = "2026-07-07T17:01:00+08:00"
    path = f"/api/v1/orders/{CASE_NO}/service-completion"
    preview = _require_success(
        client.post(
            f"{path}/preview",
            json={"evaluation_at": evaluation_at},
            headers={
                "X-Correlation-ID": f"{SCENARIO_ID}:service-completion-preview:v1"
            },
        ),
        "service_completion_preview",
    )
    identity = f"{COMMAND_IDENTITY_PREFIX}:service-completion-apply:v1"
    receipt = _require_success(
        client.post(
            f"{path}/apply",
            json={
                "expected_order_version": preview["expected_order_version"],
                "evaluation_at": evaluation_at,
                "reason": "Task 96 HOB-F Route A 正式服務完成",
                "preview_fingerprint": preview["fingerprint"],
            },
            headers={
                "Idempotency-Key": identity,
                "X-Correlation-ID": identity,
            },
        ),
        "service_completion_apply",
    )
    order = _require_success(
        client.get(f"/api/v1/orders/{CASE_NO}"),
        "service_completion_order_readback",
    )
    completion = _historical_completion(client)
    if (
        order.get("order_status") != "訂單完成"
        or any(
            alert.get("owner") in {"orders", "scheduling"}
            for alert in completion.get("active_alerts", [])
        )
    ):
        raise RuntimeError(
            f"service_completion_readback_mismatch:{json.dumps({'receipt': receipt, 'order': order, 'completion': completion}, ensure_ascii=False, default=str)}"
        )
    return {
        "stage": "stage-06-service-complete",
        "result": "created",
        "order_status": order["order_status"],
        "completion_instant": receipt["completion_instant"],
        "evaluation_at": receipt["evaluation_at"],
        "order_version": receipt["order_version"],
        "lifecycle_event_id": receipt["lifecycle_event_id"],
        "owner_projection": completion,
    }


def _ensure_payroll_obligation(
    client: TestClient,
    staff_id: int,
) -> dict[str, object]:
    preview = _require_success(
        client.post(f"/api/v1/payroll-rebuild/cases/{CASE_NO}/preview"),
        "payroll_rebuild_preview",
    )
    assignments = preview.get("assignments")
    actions = preview.get("actions")
    if not isinstance(assignments, list) or len(assignments) != 1:
        raise RuntimeError(f"payroll_rebuild_assignments_invalid:{preview}")
    assignment = assignments[0]
    if (
        assignment.get("staff_id") != staff_id
        or assignment.get("official_service_day_count") != len(SERVICE_DATES)
        or assignment.get("actual_hours") != 40
        or assignment.get("total_payable_ntd", 0) <= 0
    ):
        raise RuntimeError(f"payroll_rebuild_assignment_mismatch:{preview}")
    if isinstance(actions, list) and all(
        action.get("action") == "unchanged" for action in actions
    ):
        query = _require_success(
            client.get(f"/api/v1/staff-payables/{staff_id}"),
            "staff_payables_query_after_payroll",
        )
        obligations = [
            item
            for item in query.get("obligations", [])
            if item.get("case_no") == CASE_NO
        ]
        if len(obligations) != 1:
            raise RuntimeError(f"staff_payables_obligation_missing:{query}")
        return {
            "result": "existing",
            "payroll_version": preview["payroll_version"],
            "assignment": assignment,
            "obligation": obligations[0],
            "staff_payables_version": query["staff_payables_version"],
        }
    identity = f"{COMMAND_IDENTITY_PREFIX}:payroll-rebuild-apply:v1"
    accepted = _require_success(
        client.post(
            f"/api/v1/payroll-rebuild/cases/{CASE_NO}/apply",
            json={
                "expected_payroll_version": preview["payroll_version"],
                "preview_fingerprint": preview["preview_fingerprint"],
                "reason": "Task 96 HOB-F Route A 正式 Payroll rebuild",
            },
            headers={
                "Idempotency-Key": identity,
                "X-Correlation-ID": identity,
            },
        ),
        "payroll_rebuild_apply",
    )
    _run_one_durable_job()
    job = _require_success(
        client.get(f"/api/v1/jobs/{accepted['job_id']}"),
        "payroll_rebuild_job",
    )
    if job.get("status") != "succeeded":
        raise RuntimeError(f"payroll_rebuild_job_not_succeeded:{job}")
    query = _require_success(
        client.get(f"/api/v1/staff-payables/{staff_id}"),
        "staff_payables_query_after_payroll",
    )
    obligations = [
        item
        for item in query.get("obligations", [])
        if item.get("case_no") == CASE_NO
    ]
    if len(obligations) != 1:
        raise RuntimeError(f"staff_payables_obligation_missing:{query}")
    return {
        "result": "created",
        "job_id": accepted["job_id"],
        "payroll_version": job.get("result", {}).get("payroll_version"),
        "assignment": assignment,
        "obligation": obligations[0],
        "staff_payables_version": query["staff_payables_version"],
    }


def _ensure_staff_payout(
    client: TestClient,
    staff_id: int,
) -> dict[str, object]:
    query_path = f"/api/v1/staff-payables/{staff_id}"
    query = _require_success(client.get(query_path), "staff_payout_query")
    obligations = [
        item
        for item in query.get("obligations", [])
        if item.get("case_no") == CASE_NO
    ]
    if len(obligations) != 1:
        raise RuntimeError(f"staff_payout_obligation_invalid:{query}")
    obligation = obligations[0]
    if obligation.get("balance_ntd") == 0 and obligation.get("payout_status") == "completed":
        completion = _historical_completion(client)
        if completion.get("state") != "completed":
            raise RuntimeError(f"historical_completion_not_terminal:{completion}")
        return {
            "stage": "stage-07-settled",
            "result": "existing",
            "obligation": obligation,
            "staff_payables_version": query["staff_payables_version"],
            "owner_projection": completion,
        }
    ingest_identity = f"{COMMAND_IDENTITY_PREFIX}:staff-payout-ingest:v1"
    ingest = _require_success(
        client.post(
            "/api/v1/finance-import/workbooks/ingest",
            files={
                "workbook": (
                    "task96-staff-payout.xlsx",
                    _finance_staff_payout_workbook(),
                    XLSX_MEDIA_TYPE,
                )
            },
            headers={
                "Idempotency-Key": ingest_identity,
                "X-Correlation-ID": ingest_identity,
            },
        ),
        "staff_payout_finance_ingest",
    )
    batch_identity = str(ingest["batch_identity"])
    batch = _require_success(
        client.post(
            "/api/v1/finance-import/batches/preview",
            json={"batch_identity": batch_identity},
            headers={
                "X-Correlation-ID": f"{SCENARIO_ID}:staff-payout-finance-preview:v1"
            },
        ),
        "staff_payout_finance_preview",
    )
    rows = batch.get("rows")
    if not isinstance(rows, list) or len(rows) != 1:
        raise RuntimeError(f"staff_payout_finance_row_invalid:{batch}")
    bank_row = rows[0]
    if (
        bank_row.get("amount_ntd") != 12000
        or bank_row.get("classification_type") != "staff_payout"
    ):
        raise RuntimeError(f"staff_payout_finance_classification_invalid:{bank_row}")
    row_identity = str(bank_row.get("row_identity", ""))
    row_id_text = row_identity.removeprefix("finance-import-row:")
    if not row_id_text.isdigit() or int(row_id_text) <= 0:
        raise RuntimeError(f"staff_payout_finance_identity_invalid:{bank_row}")
    finance_import_row_id = int(row_id_text)
    selection = {
        "finance_import_row_ids": [finance_import_row_id],
        "obligation_identities": [str(obligation["obligation_identity"])],
    }
    preview = _require_success(
        client.post(
            "/api/v1/staff-payables/payout/preview",
            json=selection,
            headers={
                "X-Correlation-ID": f"{SCENARIO_ID}:staff-payout-preview:v1"
            },
        ),
        "staff_payout_preview",
    )
    candidate = preview.get("candidate")
    if (
        not isinstance(candidate, dict)
        or candidate.get("bank_total") != {"amount": 12000}
        or candidate.get("obligation_total") != {"amount": 12000}
        or candidate.get("resulting_status") != "completed"
    ):
        raise RuntimeError(f"staff_payout_candidate_invalid:{preview}")
    identity = f"{COMMAND_IDENTITY_PREFIX}:staff-payout-apply:v1"
    accepted = _require_success(
        client.post(
            "/api/v1/staff-payables/payout/apply",
            json={
                **selection,
                "expected_staff_payables_version": preview[
                    "staff_payables_version"
                ],
                "expected_bank_facts_version": preview["bank_facts_version"],
                "preview_fingerprint": preview["preview_fingerprint"],
                "reason": "Task 96 HOB-F Route A exact staff payout",
            },
            headers={
                "Idempotency-Key": identity,
                "X-Correlation-ID": identity,
            },
        ),
        "staff_payout_apply",
    )
    _run_one_durable_job()
    job = _require_success(
        client.get(f"/api/v1/jobs/{accepted['job_id']}"),
        "staff_payout_job",
    )
    if job.get("status") != "succeeded":
        raise RuntimeError(f"staff_payout_job_not_succeeded:{job}")
    readback = _require_success(client.get(query_path), "staff_payout_readback")
    settled = [
        item
        for item in readback.get("obligations", [])
        if item.get("case_no") == CASE_NO
    ]
    completion = _historical_completion(client)
    if (
        len(settled) != 1
        or settled[0].get("balance_ntd") != 0
        or settled[0].get("payout_status") != "completed"
        or completion.get("state") != "completed"
    ):
        raise RuntimeError(
            f"staff_payout_terminal_readback_mismatch:{json.dumps({'job': job, 'readback': readback, 'completion': completion}, ensure_ascii=False, default=str)}"
        )
    return {
        "stage": "stage-07-settled",
        "result": "created",
        "batch_identity": batch_identity,
        "finance_import_row_id": finance_import_row_id,
        "job_id": accepted["job_id"],
        "obligation": settled[0],
        "staff_payables_version": readback["staff_payables_version"],
        "owner_projection": completion,
    }


def run_route_a() -> dict[str, object]:
    _require_safe_environment()
    from api.main import app

    with TestClient(app) as client:
        hcm_preview, hcm_apply = _preview_apply_workbook(
            client,
            name="hcm",
            content=_hcm_workbook(),
            preview_path="/api/v1/case-import/hcm/workbooks/preview",
            apply_path="/api/v1/case-import/hcm/workbooks/apply",
        )
        staff_preview, staff_apply = _preview_apply_workbook(
            client,
            name="staff",
            content=_staff_workbook(),
            preview_path="/api/v1/case-import/staff-historical/workbooks/preview",
            apply_path="/api/v1/case-import/staff-historical/workbooks/apply",
            form={"source_revision": SOURCE_REVISION},
            command_version=3,
        )
        client_preview, client_apply = _preview_apply_client_beclass(client)
        service_dates_preview, service_dates_apply = _confirm_service_dates(client)
        order = _require_success(
            client.get(f"/api/v1/orders/{CASE_NO}"),
            "order_readback",
        )
        staff_page = _require_success(
            client.get("/api/v1/staff/summaries", params={"page_size": 200}),
            "staff_readback",
        )
        staff_items = staff_page.get("items")
        if not isinstance(staff_items, list):
            raise RuntimeError("staff_readback_items_invalid")
        selected_staff = [
            item for item in staff_items if item.get("name") == STAFF_NAME
        ]
        if len(selected_staff) != 1:
            raise RuntimeError("task96_route_a_staff_identity_not_unique")
        if order.get("case_no") != CASE_NO:
            raise RuntimeError("task96_route_a_order_identity_mismatch")
        client_region = _ensure_client_region(client, int(order["client_id"]))
        staff_preferences = _ensure_staff_preferences(
            client,
            int(selected_staff[0]["id"]),
        )
        matching = _run_stage_02(client, int(selected_staff[0]["id"]))
        commitment = _run_stage_03(client, int(matching["plan_id"]))
        assignment = _run_stage_04(
            client,
            int(matching["plan_id"]),
            int(selected_staff[0]["id"]),
        )
        actual_start = _run_stage_05(client)
        service_completion = _run_stage_06(client)
        payroll = _ensure_payroll_obligation(client, int(selected_staff[0]["id"]))
        staff_payout = _ensure_staff_payout(client, int(selected_staff[0]["id"]))
        completion = _historical_completion(client)
    return {
        "scenario_id": SCENARIO_ID,
        "database": DATABASE,
        "stage": "stage-07-settled",
        "case_no": CASE_NO,
        "staff_id": selected_staff[0]["id"],
        "hcm": {
            "ready_count": hcm_preview.get("ready_count"),
            "inserted_count": hcm_apply.get("inserted_count"),
            "replayed_workbook": hcm_apply.get("replayed_workbook"),
        },
        "staff": {
            "created_count": staff_preview.get("created_count"),
            "applied_created_count": staff_apply.get("created_count"),
            "replayed_workbook": staff_apply.get("replayed_workbook"),
        },
        "client_beclass": {
            "create_count": client_preview.get("create_count"),
            "created_count": client_apply.get("created_count"),
            "replayed_workbook": client_apply.get("replayed_workbook"),
        },
        "service_dates": {
            "dates": service_dates_apply.get("service_dates")
            or service_dates_apply.get("current_dates"),
            "confirmed_version": service_dates_apply.get("confirmed_version")
            or service_dates_apply.get("current_version"),
            "preview_fingerprint": service_dates_preview.get("preview_fingerprint"),
        },
        "client_region": client_region,
        "staff_preferences": {
            "version": staff_preferences.get("version"),
            "values": staff_preferences.get("values"),
        },
        "matching": matching,
        "commitment": commitment,
        "assignment": assignment,
        "actual_start": actual_start,
        "service_completion": service_completion,
        "payroll": payroll,
        "staff_payout": staff_payout,
        "historical_completion": completion,
        "order_status": order.get("order_status"),
    }


if __name__ == "__main__":
    print(json.dumps(run_route_a(), ensure_ascii=False, sort_keys=True))
