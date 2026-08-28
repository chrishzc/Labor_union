"""
File: run_task96_payout001_scenario.py
Description: 以正式 owner commands 建立並驗證 PAYOUT-001 no-auth canonical runtime scenario。
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import date
import json
from pathlib import Path
import sys
from unittest.mock import patch

from fastapi.testclient import TestClient


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import scripts.run_task96_hob_route_a as route_a


SCENARIO_ID = "PAYOUT-001-EXACT-001"
CASE_NO = "115960411"
STAFF_IDENTITY = "B123456789"
STAFF_BANK_ACCOUNT = "0096000000000011"
CLIENT_NAME = "Task96 PAYOUT 合成客戶"
STAFF_NAME = "Task96 PAYOUT 合成月嫂"
COMMAND_PREFIX = "task96-payout-001-exact-001"


@contextmanager
def _scenario_configuration():
    with patch.multiple(
        route_a,
        SCENARIO_ID=SCENARIO_ID,
        CASE_NO=CASE_NO,
        STAFF_IDENTITY=STAFF_IDENTITY,
        STAFF_BANK_ACCOUNT=STAFF_BANK_ACCOUNT,
        CLIENT_NAME=CLIENT_NAME,
        STAFF_NAME=STAFF_NAME,
        CLIENT_PHONE="0911000411",
        STAFF_PHONE="0922000411",
        CLIENT_EMAIL="task96-payout-client@example.test",
        STAFF_EMAIL="task96-payout-staff@example.test",
        STAFF_SOURCE_IDENTITY="TASK96-PAYOUT-STAFF-001",
        CLIENT_SOURCE_IDENTITY="TASK96-PAYOUT-CLIENT-001",
        DEPOSIT_SOURCE_IDENTITY="TASK96-PAYOUT-DEP-001",
        PAYOUT_SOURCE_IDENTITY="TASK96-PAYOUT-BANK-001",
        SOURCE_REVISION="PAYOUT-001-EXACT-001-r1",
        COMMAND_IDENTITY_PREFIX=COMMAND_PREFIX,
    ):
        yield


def _setup_owner_roots(client: TestClient) -> dict[str, object]:
    hcm_preview, hcm_apply = route_a._preview_apply_workbook(
        client,
        name="hcm",
        content=route_a._hcm_workbook(),
        preview_path="/api/v1/case-import/hcm/workbooks/preview",
        apply_path="/api/v1/case-import/hcm/workbooks/apply",
    )
    staff_preview, staff_apply = route_a._preview_apply_workbook(
        client,
        name="staff",
        content=route_a._staff_workbook(),
        preview_path="/api/v1/case-import/staff-historical/workbooks/preview",
        apply_path="/api/v1/case-import/staff-historical/workbooks/apply",
        form={"source_revision": "PAYOUT-001-EXACT-001-r1"},
        command_version=3,
    )
    client_preview, client_apply = route_a._preview_apply_client_beclass(client)
    service_dates_preview, service_dates_apply = route_a._confirm_service_dates(client)
    order = route_a._require_success(
        client.get(f"/api/v1/orders/{CASE_NO}"),
        "payout001_order_readback",
    )
    staff_page = route_a._require_success(
        client.get("/api/v1/staff/summaries", params={"page_size": 200}),
        "payout001_staff_readback",
    )
    staff_items = staff_page.get("items")
    selected_staff = (
        [item for item in staff_items if item.get("name") == STAFF_NAME]
        if isinstance(staff_items, list)
        else []
    )
    if len(selected_staff) != 1:
        raise RuntimeError("payout001_staff_identity_not_unique")
    staff_id = int(selected_staff[0]["id"])
    client_region = route_a._ensure_client_region(client, int(order["client_id"]))
    staff_preferences = route_a._ensure_staff_preferences(client, staff_id)
    matching = route_a._run_stage_02(client, staff_id)
    commitment = route_a._run_stage_03(client, int(matching["plan_id"]))
    assignment = route_a._run_stage_04(client, int(matching["plan_id"]), staff_id)
    actual_start = route_a._run_stage_05(client)
    service_completion = route_a._run_stage_06(client)
    with patch.object(
        route_a,
        "COMMAND_IDENTITY_PREFIX",
        f"{COMMAND_PREFIX}-due-date-r4",
    ):
        payroll = route_a._ensure_payroll_obligation(client, staff_id)
    obligation = payroll.get("obligation")
    if (
        not isinstance(obligation, dict)
        or obligation.get("balance_ntd", 0) <= 0
        or obligation.get("payout_status") in {"completed", "cancelled"}
    ):
        raise RuntimeError(f"payout001_open_obligation_missing:{payroll}")
    return {
        "staff_id": staff_id,
        "obligation_identity": obligation["obligation_identity"],
        "amount_due_ntd": obligation["amount_due_ntd"],
        "hcm": {"ready": hcm_preview.get("ready_count"), "created": hcm_apply.get("inserted_count")},
        "staff": {"ready": staff_preview.get("created_count"), "created": staff_apply.get("created_count")},
        "client": {"ready": client_preview.get("create_count"), "created": client_apply.get("created_count")},
        "service_dates": service_dates_apply.get("service_dates") or service_dates_apply.get("current_dates"),
        "service_dates_preview_fingerprint": service_dates_preview.get("preview_fingerprint"),
        "client_region": client_region,
        "staff_preferences_version": staff_preferences.get("version"),
        "matching": matching,
        "commitment": commitment,
        "assignment": assignment,
        "actual_start": actual_start,
        "service_completion": service_completion,
        "payroll": payroll,
    }


def _ensure_outgoing_bank_fact(client: TestClient) -> dict[str, object]:
    ingest_identity = f"{COMMAND_PREFIX}:staff-payout-ingest:v1"
    ingest = route_a._require_success(
        client.post(
            "/api/v1/finance-import/workbooks/ingest",
            files={
                "workbook": (
                    "task96-payout001-exact.xlsx",
                    route_a._finance_staff_payout_workbook(),
                    route_a.XLSX_MEDIA_TYPE,
                )
            },
            headers={
                "Idempotency-Key": ingest_identity,
                "X-Correlation-ID": ingest_identity,
            },
        ),
        "payout001_finance_ingest",
    )
    batch = route_a._require_success(
        client.post(
            "/api/v1/finance-import/batches/preview",
            json={"batch_identity": str(ingest["batch_identity"])},
            headers={"X-Correlation-ID": f"{SCENARIO_ID}:finance-preview:v1"},
        ),
        "payout001_finance_preview",
    )
    rows = batch.get("rows")
    if not isinstance(rows, list) or len(rows) != 1:
        raise RuntimeError(f"payout001_finance_row_invalid:{batch}")
    row = rows[0]
    row_identity = str(row.get("row_identity", ""))
    row_id_text = row_identity.removeprefix("finance-import-row:")
    if (
        row.get("amount_ntd") != 12000
        or row.get("classification_type") != "staff_payout"
        or not row_id_text.isdigit()
        or int(row_id_text) <= 0
    ):
        raise RuntimeError(f"payout001_finance_fact_invalid:{row}")
    return {
        "batch_identity": str(ingest["batch_identity"]),
        "finance_import_row_id": int(row_id_text),
        "row_identity": row_identity,
        "amount_ntd": row["amount_ntd"],
    }


def _scan_staff_payables() -> dict[str, int]:
    from infrastructure.mysql.mysql_adapter import get_connection
    from shared_kernel.business_time import current_business_instant
    from subsystems.anomalies.staff_payables_anomaly_source import (
        StaffPayablesAnomalyScanCursors,
        consume_staff_payables_anomaly_sources,
    )

    connection = get_connection()
    cursors = StaffPayablesAnomalyScanCursors.start()
    projected_count = 0
    active_count = 0
    pages = 0
    try:
        while True:
            result = consume_staff_payables_anomaly_sources(
                connection,
                as_of=current_business_instant().date(),
                maximum_items=100,
                cursors=cursors,
            )
            if not result.succeeded:
                raise RuntimeError(f"payout001_source_scan_failed:{result.error}")
            projected_count += result.projected_count
            active_count += result.active_count
            pages += 1
            cursors = result.cursors
            if (
                cursors.overdue_after_obligation_identity is None
                and cursors.late_change_after_event_id is None
                and cursors.bank_master_after_staff_id is None
            ):
                break
            if pages >= 100:
                raise RuntimeError("payout001_source_scan_page_limit")
    finally:
        connection.close()
    return {"pages": pages, "projected_count": projected_count, "active_count": active_count}


def _find_payout_alert(client: TestClient, *, active_only: bool) -> dict[str, object]:
    response = client.get(
        "/api/v1/anomalies",
        params={
            "active_only": str(active_only).lower(),
            "include_snapshot": "false",
            "limit": 200,
            "offset": 0,
        },
    )
    if response.status_code != 200:
        raise RuntimeError(
            f"payout001_anomaly_list_failed:{response.status_code}:{response.text[:1000]}"
        )
    envelope = response.json()
    summaries = envelope.get("data")
    if not envelope.get("success") or not isinstance(summaries, list):
        raise RuntimeError("payout001_anomaly_list_invalid")
    matches = [
        item
        for item in summaries
        if item.get("definition_code") == "PAYOUT-001"
        and item.get("source_identity")
    ]
    exact = [item for item in matches if item.get("source_identity") == _obligation_identity(client)]
    if len(exact) != 1:
        raise RuntimeError(f"payout001_alert_identity_invalid:{matches}")
    return exact[0]


def _obligation_identity(client: TestClient) -> str:
    staff_id = _staff_id(client)
    query = route_a._require_success(
        client.get(f"/api/v1/staff-payables/{staff_id}"),
        "payout001_staff_payables_identity_query",
    )
    obligations = [item for item in query.get("obligations", []) if item.get("case_no") == CASE_NO]
    if len(obligations) != 1:
        raise RuntimeError(f"payout001_obligation_identity_invalid:{query}")
    return str(obligations[0]["obligation_identity"])


def _staff_id(client: TestClient) -> int:
    page = route_a._require_success(
        client.get("/api/v1/staff/summaries", params={"page_size": 200}),
        "payout001_staff_identity_query",
    )
    matches = [item for item in page.get("items", []) if item.get("name") == STAFF_NAME]
    if len(matches) != 1:
        raise RuntimeError(f"payout001_staff_identity_invalid:{matches}")
    return int(matches[0]["id"])


def prepare_scenario() -> dict[str, object]:
    route_a._require_safe_environment()
    from api.main import app

    with _scenario_configuration(), TestClient(app) as client:
        roots = _setup_owner_roots(client)
        bank_fact = _ensure_outgoing_bank_fact(client)
        scan = _scan_staff_payables()
        alert = _find_payout_alert(client, active_only=True)
        if not alert.get("predicate_active") or alert.get("workflow_status") == "resolved":
            raise RuntimeError(f"payout001_alert_not_active:{alert}")
        detail = route_a._require_success(
            client.get(f"/api/v1/anomalies/{alert['fingerprint']}"),
            "payout001_anomaly_detail",
        )
    return {
        "scenario_id": SCENARIO_ID,
        "phase": "prepared",
        "business_date": date.today().isoformat(),
        "database": route_a.DATABASE,
        "case_no": CASE_NO,
        "roots": roots,
        "bank_fact": bank_fact,
        "scan": scan,
        "alert": alert,
        "detail": detail,
    }


def verify_terminal() -> dict[str, object]:
    route_a._require_safe_environment()
    from api.main import app

    with _scenario_configuration(), TestClient(app) as client:
        scan = _scan_staff_payables()
        alert = _find_payout_alert(client, active_only=False)
        staff_id = _staff_id(client)
        query = route_a._require_success(
            client.get(f"/api/v1/staff-payables/{staff_id}"),
            "payout001_terminal_staff_payables_query",
        )
        obligations = [item for item in query.get("obligations", []) if item.get("case_no") == CASE_NO]
        if (
            len(obligations) != 1
            or obligations[0].get("balance_ntd") != 0
            or obligations[0].get("payout_status") != "completed"
            or alert.get("predicate_active")
            or alert.get("workflow_status") != "resolved"
        ):
            raise RuntimeError(
                f"payout001_terminal_readback_mismatch:{json.dumps({'obligations': obligations, 'alert': alert}, ensure_ascii=False, default=str)}"
            )
    return {
        "scenario_id": SCENARIO_ID,
        "phase": "verified",
        "database": route_a.DATABASE,
        "case_no": CASE_NO,
        "staff_id": staff_id,
        "scan": scan,
        "obligation": obligations[0],
        "alert": alert,
    }


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Task 96 PAYOUT-001 canonical scenario.")
    parser.add_argument("--phase", choices=("prepare", "verify"), required=True)
    return parser.parse_args()


if __name__ == "__main__":
    arguments = _arguments()
    result = prepare_scenario() if arguments.phase == "prepare" else verify_terminal()
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, default=str))
