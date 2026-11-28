"""Isolated localhost MySQL E2E verification for PR #425 (STAR Cases 1, 2, 3, 5)."""

from __future__ import annotations

from argparse import Namespace
from collections.abc import Iterator
from contextlib import closing, contextmanager
from datetime import date, timedelta
import hashlib
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
from threading import Thread
from time import monotonic, sleep
from urllib.error import URLError
from urllib.parse import urlsplit
from urllib.request import urlopen
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pymysql
import pytest

from api.dependencies.admin_auth import require_admin
from api.dependencies.finance_import import get_finance_import_query_service
from api.dependencies.staff_payout import build_staff_payout_application
from api.routes.accounting_differences import router as accounting_differences_router
from api.routes.finance_import import router as finance_import_router
from domains.payroll.calculation import DEFAULT_PAYROLL_POLICY_VERSION, PayrollPolicyKind
from domains.staff_payables.historical_payout import (
    HistoricalStaffConfirmationKind,
    HistoricalStaffPayoutIntent,
    HistoricalStaffSourceAvailability,
)
from domains.staff_payables.reconciliation import StaffPayoutEventType
from infrastructure.mysql import mysql_adapter
from infrastructure.mysql.accounting_workspace_repository import build_accounting_workspace
from infrastructure.mysql.accounts_payable_export_sources import MySqlStaffPayableExportSource
from infrastructure.mysql.client_registry_query_repository import load_registry_payment_estimates
from infrastructure.mysql.historical_staff_payout_repository import (
    HistoricalStaffPayoutMySqlUnitOfWork,
    MySqlHistoricalStaffPayoutRepository,
)
from infrastructure.mysql.subsidy_confirmation_repository import match_client_subsidy_month
from scripts.bootstrap_disposable_mysql_schema import bootstrap
from shared_kernel.identities import (
    ActorContext,
    CorrelationId,
    ExpectedVersion,
    IdempotencyKey,
)
from subsystems.access.authentication_session import AdminPrincipal, hash_admin_password
from subsystems.finance_import.query import FinanceImportQueryService
from subsystems.payroll.historical_baseline_obligation_sync import synchronize_historical_payroll
from subsystems.staff_payables.historical_payment_settlement import HistoricalStaffPayoutWorkflow
from subsystems.staff_payables.payout_reconciliation import (
    StaffPayoutApplyRequest,
    StaffPayoutReconciliationError,
    StaffPayoutSelection,
)


def _fingerprint(tag: str) -> str:
    return hashlib.sha256(tag.encode("utf-8")).hexdigest()


@pytest.fixture(scope="module")
def mysql_connection() -> Iterator[pymysql.connections.Connection]:
    config = mysql_adapter._database_config_from_environment()
    assert os.getenv("APP_ENV", "development") == "development"
    assert config["host"] in {"127.0.0.1", "localhost"}
    database_name = f"lu_test_pr425_{uuid4().hex[:12]}"
    bootstrap(
        Namespace(
            host=config["host"],
            port=config["port"],
            user=config["user"],
            password=config["password"],
            database=database_name,
            confirm_database=database_name,
        )
    )
    previous_config = mysql_adapter.DB_CONFIG.copy()
    mysql_adapter.DB_CONFIG.update({**config, "database": database_name})
    connection = mysql_adapter.get_connection()
    try:
        yield connection
    finally:
        try:
            connection.close()
        finally:
            mysql_adapter.DB_CONFIG.clear()
            mysql_adapter.DB_CONFIG.update(previous_config)
            cleanup_conn = pymysql.connect(
                host=config["host"],
                port=config["port"],
                user=config["user"],
                password=config["password"],
                charset="utf8mb4",
                autocommit=True,
            )
            try:
                with cleanup_conn.cursor() as cursor:
                    cursor.execute(f"DROP DATABASE IF EXISTS `{database_name}`")
            finally:
                cleanup_conn.close()


def _seed_rate_policy(cursor, policy_version: str = "pr425-rate-300", hourly_rate: int = 300) -> None:
    cursor.execute(
        "INSERT INTO payroll_rate_policies(policy_version,policy_kind,hourly_rate_ntd,effective_from) "
        "VALUES(%s,'citizen',%s,'2026-01-01') "
        "ON DUPLICATE KEY UPDATE hourly_rate_ntd=VALUES(hourly_rate_ntd)",
        (policy_version, hourly_rate),
    )


def _seed_historical_case(
    cursor,
    *,
    case_no: str,
    client_name: str,
    identity_status: str = "一般市民",
    service_days: int = 20,
    hours_per_day: int = 8,
    floor_fee: int = 0,
    staff_specs: tuple[dict[str, object], ...] = (),
    policy_version: str = "pr425-rate-300",
    hourly_rate: int = 300,
    start_day: date = date(2026, 8, 1),
    end_day: date = date(2026, 8, 20),
) -> tuple[int, list[dict[str, int]]]:
    _seed_rate_policy(cursor, policy_version, hourly_rate)
    cursor.execute(
        "INSERT INTO clients(case_no,name,identity_status,service_type,created_at) "
        "VALUES(%s,%s,%s,'連續服務','2026-07-01')",
        (case_no, client_name, identity_status),
    )
    client_id = int(cursor.lastrowid)
    cursor.execute(
        "INSERT INTO orders("
        "case_no,client_id,status,lifecycle_version,start_date,end_date,"
        "actual_start_date,actual_end_date,service_days,service_hours_per_day,"
        "floor_fee,requires_cooking,service_start_time,service_end_time,service_end_day_offset"
        ") VALUES(%s,%s,'歷史訂單－服務完成',1,%s,%s,%s,%s,%s,%s,%s,0,'09:00:00','17:00:00',0)",
        (case_no, client_id, start_day, end_day, start_day, end_day, service_days, hours_per_day, floor_fee),
    )
    cursor.execute("INSERT INTO client_finance_accounts(case_no) VALUES(%s)", (case_no,))
    cursor.execute(
        "INSERT INTO order_lifecycle_state_events(case_no,trigger_event,before_status,after_status,"
        "actor,business_date,expected_version,idempotency_key,facts_snapshot) "
        "VALUES(%s,'historical_order_adoption','洽談中','歷史訂單－服務完成',"
        "'synthetic',%s,0,%s,'{}')",
        (case_no, end_day, f"{case_no}:lifecycle"),
    )
    lifecycle_event_id = int(cursor.lastrowid)
    cursor.execute(
        "INSERT INTO historical_order_adoption_receipts("
        "idempotency_key,command_fingerprint,source_event_identity,source_fingerprint,"
        "preview_fingerprint,case_no,outcome,expected_version,resulting_version,"
        "lifecycle_event_id,assignment_count,result_snapshot,actor,reason,correlation_id"
        ") VALUES(%s,%s,%s,%s,%s,%s,'adopted',0,1,%s,%s,'{}','synthetic','pr425 fixture',%s)",
        (
            f"{case_no}:adopt",
            _fingerprint(f"{case_no}:cmd"),
            f"{case_no}:source",
            _fingerprint(f"{case_no}:src"),
            _fingerprint(f"{case_no}:prv"),
            case_no,
            lifecycle_event_id,
            len(staff_specs),
            f"{case_no}:corr",
        ),
    )
    receipt_id = int(cursor.lastrowid)

    created_staff: list[dict[str, int]] = []
    generation_id: int | None = None
    for idx, spec in enumerate(staff_specs, start=1):
        staff_name = str(spec["name"])
        identity_card = str(spec["identity_card"])
        cursor.execute("SELECT id FROM staff WHERE identity_card=%s", (identity_card,))
        existing_staff = cursor.fetchone()
        if existing_staff:
            staff_id = int(existing_staff["id"])
        else:
            cursor.execute(
                "INSERT INTO staff(name,identity_card) VALUES(%s,%s)",
                (staff_name, identity_card),
            )
            staff_id = int(cursor.lastrowid)
        if spec.get("with_bank_account", True):
            cursor.execute("SELECT id FROM staff_bank_accounts WHERE staff_id=%s AND is_primary=1", (staff_id,))
            if cursor.fetchone() is None:
                cursor.execute(
                    "INSERT INTO staff_bank_accounts(staff_id,bank_code,branch_code,account_no,is_primary) "
                    "VALUES(%s,'807','0011',%s,1)",
                    (staff_id, f"ACCT-{staff_id:04d}"),
                )
        cursor.execute("INSERT IGNORE INTO staff_payable_accounts(staff_id,aggregate_version) VALUES(%s,0)", (staff_id,))
        a_start = spec.get("start_date", start_day)
        a_end = spec.get("end_date", end_day)
        cursor.execute(
            "INSERT INTO case_staff_assignments("
            "case_no,staff_id,assignment_sequence,assigned_start_date,assigned_end_date,status"
            ") VALUES(%s,%s,%s,%s,%s,'completed')",
            (case_no, staff_id, idx, a_start, a_end),
        )
        assignment_id = int(cursor.lastrowid)
        rate = int(spec.get("hourly_rate", hourly_rate))
        if spec.get("with_rate_snapshot", True):
            snapshot_version = str(spec.get("policy_version", policy_version))
            snapshot_kind = PayrollPolicyKind(str(spec.get("policy_kind", PayrollPolicyKind.CITIZEN)))
            cursor.execute(
                "INSERT INTO assignment_payroll_rate_snapshots("
                "assignment_id,policy_version,policy_kind,hourly_rate_ntd,source_identity_status"
                ") VALUES(%s,%s,%s,%s,%s)",
                (assignment_id, snapshot_version, snapshot_kind.value, rate, identity_status),
            )
        cursor.execute(
            "INSERT INTO historical_order_pairing_evidence("
            "receipt_id,caregiver_ordinal,staff_name,staff_id,resolution,"
            "source_start_date,source_end_date,assignment_id,issue_codes"
            ") VALUES(%s,%s,%s,%s,'assignment_candidate',%s,%s,%s,'[]')",
            (receipt_id, idx, staff_name, staff_id, a_start, a_end, assignment_id),
        )
        schedule_days = int(spec.get("schedule_days", 0))
        if schedule_days > 0:
            if generation_id is None:
                cursor.execute("INSERT INTO scheduling_aggregates(case_no,aggregate_version,generation_counter) VALUES(%s,1,1)", (case_no,))
                cursor.execute(
                    "INSERT INTO scheduling_generations(case_no,generation_number,resulting_aggregate_version,"
                    "status,effective_marker,created_by,change_reason) VALUES(%s,1,1,'effective',1,'synthetic','pr425 fixture')",
                    (case_no,),
                )
                generation_id = int(cursor.lastrowid)
                cursor.execute("UPDATE scheduling_aggregates SET effective_generation_id=%s WHERE case_no=%s", (generation_id, case_no))
            schedule_base = a_start if isinstance(a_start, date) else start_day
            cursor.executemany(
                "INSERT INTO staff_schedule(case_no,generation_id,assignment_id,staff_id,work_date,is_work_day,effective_marker) "
                "VALUES(%s,%s,%s,%s,%s,1,1)",
                [
                    (case_no, generation_id, assignment_id, staff_id, schedule_base + timedelta(days=offset))
                    for offset in range(schedule_days)
                ],
            )
        created_staff.append({"staff_id": staff_id, "assignment_id": assignment_id})
    return client_id, created_staff


def _seed_bank_batch(cursor, *, format_id: str = "sinopac") -> int:
    cursor.execute(
        "INSERT INTO finance_import_batches(format_id,source_file,sheet_name,header_row,row_count,status) "
        "VALUES(%s,'pr425.xlsx','Sheet1',1,1,'staged')",
        (format_id,),
    )
    return int(cursor.lastrowid)


def _seed_bank_row(
    cursor,
    *,
    batch_id: int,
    format_id: str,
    direction: str,
    amount_ntd: int,
    tx_date: date,
    counterparty_name: str,
    memo: str,
    classification_type: str,
    disposition: str,
    reason: str,
    matched_staff_id: int | None = None,
    target_identities: list[str] | None = None,
    reconciliation_status: str = "pending",
    source_reference: str | None = None,
) -> int:
    fingerprint = _fingerprint(f"bank:{uuid4().hex}")
    debit = amount_ntd if direction == "outgoing" else None
    credit = amount_ntd if direction == "incoming" else None
    matched_json = json.dumps([matched_staff_id] if matched_staff_id is not None else [])
    targets_json = json.dumps(
        target_identities if target_identities is not None else ([f"staff:{matched_staff_id}"] if matched_staff_id is not None else [])
    )
    cursor.execute(
        "INSERT INTO finance_import_rows("
        "dedup_fingerprint,batch_id,format_id,source_file,sheet_name,source_row,source_reference,"
        "transaction_date,debit,credit,direction,currency,memo,counterparty_name,"
        "bank_references,warnings,raw_payload,matched_identity_ids,"
        "classification_type,classification_reason,reconciliation_status"
        ") VALUES(%s,%s,%s,'pr425.xlsx','Sheet1',2,%s,%s,%s,%s,%s,'TWD',%s,%s,'{}','[]','{}',%s,%s,%s,%s)",
        (
            fingerprint,
            batch_id,
            format_id,
            source_reference or f"REF-{uuid4().hex[:8]}",
            tx_date,
            debit,
            credit,
            direction,
            memo,
            counterparty_name,
            matched_json,
            classification_type,
            reason,
            reconciliation_status,
        ),
    )
    row_id = int(cursor.lastrowid)
    cursor.execute(
        "INSERT INTO finance_import_occurrences(batch_id,finance_import_row_id,source_file,sheet_name,source_row) "
        "VALUES(%s,%s,'pr425.xlsx','Sheet1',%s)",
        (batch_id, row_id, row_id + 1),
    )
    cursor.execute(
        "INSERT INTO finance_import_classification_events("
        "batch_id,finance_import_row_id,classification_version,canonical_fact_version,"
        "classification_type,disposition,decision_facts_fingerprint,target_identities,"
        "evidence,available_actions,actor,reason"
        ") VALUES(%s,%s,1,1,%s,%s,%s,%s,'[]','[]','synthetic',%s)",
        (
            batch_id,
            row_id,
            classification_type,
            disposition,
            _fingerprint(f"evt:{row_id}"),
            targets_json,
            reason,
        ),
    )
    return row_id


def _seed_client_full_payment(cursor, *, case_no: str, client_name: str, amount_ntd: int, tx_date: date) -> tuple[str, int]:
    ob_id = f"client:{case_no}:deposit"
    cursor.execute(
        "INSERT INTO client_obligation_events("
        "obligation_identity,case_no,obligation_type,direction,event_type,"
        "before_amount_ntd,after_amount_ntd,after_due_date,source_event_identity,"
        "expected_account_version,idempotency_key,actor,reason"
        ") VALUES(%s,%s,'deposit','receivable_from_client','established',0,%s,%s,%s,0,%s,'synthetic','full client bill')",
        (ob_id, case_no, amount_ntd, tx_date, ob_id, f"key:{ob_id}"),
    )
    ob_event_id = int(cursor.lastrowid)
    cursor.execute(
        "INSERT INTO client_obligations("
        "obligation_identity,case_no,obligation_type,direction,amount_due_ntd,due_date,status,current_event_id,projection_version"
        ") VALUES(%s,%s,'deposit','receivable_from_client',0,%s,'settled',%s,0)",
        (ob_id, case_no, tx_date, ob_event_id),
    )
    batch_id = _seed_bank_batch(cursor, format_id="sinopac")
    bank_row_id = _seed_bank_row(
        cursor,
        batch_id=batch_id,
        format_id="sinopac",
        direction="incoming",
        amount_ntd=amount_ntd,
        tx_date=tx_date,
        counterparty_name=client_name,
        memo=f"收款 {case_no[-6:]}",
        classification_type="client_receipt",
        disposition="existing",
        reason="client_receipt_reconciled",
        target_identities=[f"case:{case_no}"],
        reconciliation_status="reconciled",
    )
    cursor.execute(
        "INSERT INTO client_ledger_entries("
        "case_no,finance_import_row_id,entry_type,amount_ntd,occurred_on,reconciliation_reference,idempotency_key,actor,reason"
        ") VALUES(%s,%s,'receipt',%s,%s,'CLIENT-PAID',%s,'synthetic','client paid full')",
        (case_no, bank_row_id, amount_ntd, tx_date, f"ledger:{case_no}"),
    )
    ledger_id = int(cursor.lastrowid)
    cursor.execute(
        "INSERT INTO client_ledger_obligation_allocations(ledger_entry_id,obligation_identity,amount_ntd,allocation_ordinal) "
        "VALUES(%s,%s,%s,1)",
        (ledger_id, ob_id, amount_ntd),
    )
    return ob_id, bank_row_id


def _snapshot_tables(connection, *, case_nos: tuple[str, ...], staff_ids: tuple[int, ...], bank_row_ids: tuple[int, ...] = ()) -> dict[str, list[dict[str, object]]]:
    case_placeholders = ",".join("%s" for _ in case_nos)
    staff_placeholders = ",".join("%s" for _ in staff_ids)
    with connection.cursor() as cursor:
        queries: list[tuple[str, str, tuple[object, ...]]] = [
            ("client_obligations", f"SELECT obligation_identity,case_no,obligation_type,amount_due_ntd,due_date,status,projection_version FROM client_obligations WHERE case_no IN ({case_placeholders}) ORDER BY obligation_identity", case_nos),
            ("client_ledger_entries", f"SELECT id,case_no,finance_import_row_id,entry_type,amount_ntd,occurred_on FROM client_ledger_entries WHERE case_no IN ({case_placeholders}) ORDER BY id", case_nos),
            ("client_ledger_allocations", f"SELECT a.id,a.ledger_entry_id,a.obligation_identity,a.amount_ntd FROM client_ledger_obligation_allocations a JOIN client_obligations o ON o.obligation_identity=a.obligation_identity WHERE o.case_no IN ({case_placeholders}) ORDER BY a.id", case_nos),
            ("government_subsidy_entries", "SELECT id,amount_ntd,paid_on FROM government_subsidy_period_entries ORDER BY id", ()),
            ("staff_obligations", f"SELECT obligation_identity,case_no,staff_id,amount_due_ntd,due_date,status,payroll_version FROM staff_obligations WHERE case_no IN ({case_placeholders}) ORDER BY obligation_identity", case_nos),
            ("staff_obligation_events", f"SELECT id,obligation_identity,event_type,due_date FROM staff_obligation_events WHERE case_no IN ({case_placeholders}) ORDER BY id", case_nos),
            ("staff_obligation_installments", f"SELECT i.obligation_identity,i.funding_kind,i.amount_ntd,i.due_date FROM staff_obligation_installments i JOIN staff_obligations o ON o.obligation_identity=i.obligation_identity WHERE o.case_no IN ({case_placeholders}) ORDER BY i.obligation_identity,i.funding_kind", case_nos),
            ("staff_payout_events", f"SELECT id,staff_id,finance_import_row_id,event_type,amount_ntd,occurred_on FROM staff_payout_events WHERE staff_id IN ({staff_placeholders}) ORDER BY id", staff_ids),
            ("staff_payout_links", f"SELECT l.id,l.payout_event_id,l.obligation_identity,l.allocated_amount_ntd FROM staff_payout_obligation_links l JOIN staff_obligations o ON o.obligation_identity=l.obligation_identity WHERE o.case_no IN ({case_placeholders}) ORDER BY l.id", case_nos),
            ("orders", f"SELECT case_no,status,lifecycle_version,staff_payment_due_date FROM orders WHERE case_no IN ({case_placeholders}) ORDER BY case_no", case_nos),
            ("payroll_case_accounts", f"SELECT case_no,aggregate_version FROM payroll_case_accounts WHERE case_no IN ({case_placeholders}) ORDER BY case_no", case_nos),
            ("payroll_apply_receipts", f"SELECT id,idempotency_key,resulting_payroll_version FROM payroll_apply_receipts WHERE case_no IN ({case_placeholders}) ORDER BY id", case_nos),
            ("payroll_outbox", f"SELECT id,intent_key,intent_type,status FROM payroll_outbox WHERE case_no IN ({case_placeholders}) ORDER BY id", case_nos),
        ]
        if bank_row_ids:
            bank_placeholders = ",".join("%s" for _ in bank_row_ids)
            queries.append(("bank_rows", f"SELECT id,reconciliation_status,classification_type,debit,credit FROM finance_import_rows WHERE id IN ({bank_placeholders}) ORDER BY id", bank_row_ids))
        result: dict[str, list[dict[str, object]]] = {}
        for name, sql, params in queries:
            cursor.execute(sql, params)
            result[name] = list(cursor.fetchall())
        return result


def _bank_api_client(connection) -> TestClient:
    app = FastAPI()
    app.include_router(finance_import_router)
    app.include_router(accounting_differences_router)
    app.dependency_overrides[require_admin] = lambda: AdminPrincipal(
        id=1,
        username="pr425-verifier",
        display_name="PR425 Verifier",
        role="system_admin",
        capabilities=frozenset({"all"}),
    )

    def _query_service():
        return FinanceImportQueryService(
            connection,
            match_client_month=lambda *args, **kwargs: match_client_subsidy_month(connection, *args, **kwargs),
            load_payment_estimates=load_registry_payment_estimates,
        )

    app.dependency_overrides[get_finance_import_query_service] = _query_service
    return TestClient(app)


def test_historical_baseline_sync_admin_entry_reads_back_undated_48000_once(mysql_connection):
    case_no = "115000432"
    with mysql_connection.cursor() as cursor:
        _, staff = _seed_historical_case(
            cursor,
            case_no=case_no,
            client_name="Historical payroll baseline fixture",
            service_days=20,
            hours_per_day=8,
            staff_specs=({"name": "Historical baseline caregiver", "identity_card": "F223456043"},),
        )
    mysql_connection.commit()
    staff_id = staff[0]["staff_id"]
    assignment_id = staff[0]["assignment_id"]
    accounting_url = f"/api/v1/finance-import/cases/{case_no}/accounting"
    sync_url = f"/api/v1/orders/{case_no}/payroll/sync-historical-baseline-obligations"
    snapshot_scope = {"case_nos": (case_no,), "staff_ids": (staff_id,)}
    before = _snapshot_tables(mysql_connection, **snapshot_scope)
    mysql_connection.commit()
    assert before["staff_obligations"] == []

    with _bank_api_client(mysql_connection) as client:
        check = client.get(accounting_url)
        assert check.status_code == 200, check.text
        queried = check.json()["data"]
        assert queried["scheme"] in {"unknown", "waiting"}
        assert queried["staff_items"] == []
        availability = queried["staff_accounting_availability"]
        assert len(availability) == 1
        assert availability[0]["assignment_id"] == assignment_id
        assert availability[0]["staff_id"] == staff_id
        assert availability[0]["status"] == "not_established"
        assert availability[0]["estimated_amount_ntd"] == 48000
        assert _snapshot_tables(mysql_connection, **snapshot_scope) == before
        mysql_connection.commit()

        sync = client.post(sync_url)
        assert sync.status_code == 200, sync.text
        receipt = sync.json()["data"]
        assert receipt["scanned_orders"] == receipt["created_count"] == 1
        assert len(receipt["details"]) == 1
        detail = receipt["details"][0]
        assert detail["case_no"] == case_no
        assert detail["action"] == "created"
        assert detail["staff_id"] == staff_id
        assert detail["assignment_id"] == assignment_id
        identity = detail["obligation_identity"]
        assert detail["amount_ntd"] == 48000
        assert detail["due_date"] is None
        assert detail["payment_arrangement_pending"] is True

        readback = client.get(accounting_url)
        assert readback.status_code == 200, readback.text
        after = readback.json()["data"]
        assert len(after["staff_items"]) == 1
        payable = after["staff_items"][0]
        assert payable["identity"] == identity
        assert payable["expected_ntd"] == payable["remaining_ntd"] == 48000
        assert payable["actual_ntd"] == 0
        assert payable["has_payment"] is False
        assert payable["due_date"] is None
        assert payable.get("funding_portions", []) in (None, [])
        assert not any(item["item_identity"] == identity for item in after["transactions"])
        availability = after["staff_accounting_availability"]
        assert len(availability) == 1
        assert availability[0]["status"] == "formal"
        assert availability[0]["assignment_id"] == assignment_id
        assert availability[0]["staff_id"] == staff_id
        assert availability[0]["obligation_identities"] == [identity]
        assert availability[0]["recorded_due_date"] is None
        assert "historical_payroll_funding_source_missing" in availability[0]["pending_reasons"]

        after_sync = _snapshot_tables(mysql_connection, **snapshot_scope)
        mysql_connection.commit()
        assert len(after_sync["staff_obligations"]) == 1
        assert len(after_sync["staff_obligation_events"]) == 1
        payroll_writes = {
            "staff_obligations", "staff_obligation_events",
            "payroll_case_accounts", "payroll_apply_receipts", "payroll_outbox",
        }
        assert {key: rows for key, rows in after_sync.items() if key not in payroll_writes} == {
            key: rows for key, rows in before.items() if key not in payroll_writes
        }
        assert len(after_sync["payroll_apply_receipts"]) == 1

        repeat = client.post(sync_url)
        assert repeat.status_code == 200, repeat.text
        replay = repeat.json()["data"]
        assert replay["created_count"] == replay["updated_count"] == 0
        assert replay["details"][0]["reason"] == "already_synced"
        assert replay["details"][0]["obligation_identity"] == identity
        assert _snapshot_tables(mysql_connection, **snapshot_scope) == after_sync
        mysql_connection.commit()


@pytest.mark.parametrize(
    "case_no,has_assignment,has_rate_snapshot,accounting_closed,reason",
    [
        ("115000433", False, True, False, "historical_payroll_unique_assignment_required"),
        ("115000434", True, False, False, "payroll_rate_policy_not_found"),
        ("115000435", True, True, True, "historical_payroll_settled_source_required"),
    ],
)
def test_historical_baseline_sync_admin_entry_requires_proven_sources(
    mysql_connection, case_no, has_assignment, has_rate_snapshot, accounting_closed, reason
):
    with mysql_connection.cursor() as cursor:
        _seed_historical_case(
            cursor,
            case_no=case_no,
            client_name="Historical payroll missing evidence fixture",
            staff_specs=(
                {
                    "name": "Missing evidence caregiver",
                    "identity_card": "F223456044",
                    "with_rate_snapshot": has_rate_snapshot,
                },
            ) if has_assignment else (),
        )
        if accounting_closed:
            cursor.execute(
                "UPDATE orders SET status='歷史訂單－帳務完成' WHERE case_no=%s",
                (case_no,),
            )
    mysql_connection.commit()
    with _bank_api_client(mysql_connection) as client:
        response = client.post(f"/api/v1/orders/{case_no}/payroll/sync-historical-baseline-obligations")
        assert response.status_code == 200, response.text
        result = response.json()["data"]
        assert result["scanned_orders"] == result["skipped_count"] == 1
        assert result["created_count"] == result["updated_count"] == 0
        assert result["details"][0]["reason"] == reason
        account = client.get(f"/api/v1/finance-import/cases/{case_no}/accounting")
        assert account.status_code == 200, account.text
        assert account.json()["data"]["staff_items"] == []
    with mysql_connection.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) AS count FROM staff_obligation_events WHERE case_no=%s", (case_no,))
        assert cursor.fetchone()["count"] == 0
    mysql_connection.commit()


@contextmanager
def _browser_payroll_app(tmp_path):
    import uvicorn

    with socket.socket() as api_socket, socket.socket() as vite_probe:
        api_socket.bind(("127.0.0.1", 0))
        vite_probe.bind(("127.0.0.1", 0))
        api_port = api_socket.getsockname()[1]
        vite_port = vite_probe.getsockname()[1]
        vite_probe.close()
        api_url = f"http://127.0.0.1:{api_port}"
        app_url = f"http://127.0.0.1:{vite_port}"
        server = uvicorn.Server(uvicorn.Config(
            "api.main:app", host="127.0.0.1", port=api_port, lifespan="off", access_log=False,
        ))
        backend = Thread(target=server.run, kwargs={"sockets": [api_socket]}, daemon=True)
        backend.start()
        log_path = tmp_path / "vite.log"
        try:
            _wait_for_http(f"{api_url}/health")
            with log_path.open("w", encoding="utf-8") as log, subprocess.Popen(
                ["node", "node_modules/vite/bin/vite.js", "--host", "127.0.0.1", "--port", str(vite_port), "--strictPort"],
                cwd=Path.cwd() / "ui_react",
                env={
                    **{key: value for key, value in os.environ.items() if key != "VITE_PUBLIC_PATH_PREFIX"},
                    "VITE_DEV_API_TARGET": api_url,
                },
                stdout=log, stderr=subprocess.STDOUT,
            ) as vite:
                try:
                    try:
                        _wait_for_http(f"{app_url}/admin/")
                    except RuntimeError as error:
                        raise RuntimeError(f"{error}\n{log_path.read_text(encoding='utf-8')}") from error
                    yield app_url
                finally:
                    if vite.poll() is None:
                        vite.terminate()
                        try:
                            vite.wait(timeout=10)
                        except subprocess.TimeoutExpired:
                            vite.kill()
                            vite.wait(timeout=10)
        finally:
            server.should_exit = True
            backend.join(timeout=10)


def _wait_for_http(url):
    deadline = monotonic() + 45
    while monotonic() < deadline:
        try:
            with urlopen(url, timeout=2) as response:
                if response.status == 200:
                    return
        except (URLError, TimeoutError):
            sleep(0.2)
    raise RuntimeError(f"Loopback service did not become ready: {url}")


@pytest.mark.skipif(os.getenv("PAYROLL_BROWSER_E2E") != "1", reason="requires the dedicated CI Chromium step")
def test_historical_payroll_via_real_browser(mysql_connection, monkeypatch, tmp_path):
    from playwright.sync_api import expect, sync_playwright

    password = secrets.token_urlsafe(32)
    for name, value in {
        "PYTHON_DOTENV_DISABLED": "1",
        "APP_ENV": "development",
        "ACCESS_CONTROL_PROFILE": "local_developer_session",
        "ENABLE_ADMIN_AUTH": "true",
        "DEV_ROOT_USERNAME": "payroll-browser-fixture",
        "DEV_ROOT_PASSWORD": password,
    }.items():
        monkeypatch.setenv(name, value)

    single, missing, partial = "115994301", "115994302", "115994303"
    names = ("Browser payroll employee", "Browser missing rate", "Browser partial employee", "Browser missing service")
    with mysql_connection.cursor() as cursor:
        cursor.execute(
            "INSERT INTO admin_users(username,password_hash,display_name,role) "
            "VALUES(%s,%s,'Browser Payroll Verifier','system_admin')",
            ("payroll-browser-fixture", hash_admin_password(password)),
        )
        cursor.execute("INSERT INTO admin_root_account(singleton_key,admin_user_id) VALUES(1,%s)", (cursor.lastrowid,))
        _, single_staff = _seed_historical_case(
            cursor, case_no=single, client_name="Browser single case",
            staff_specs=({"name": names[0], "identity_card": "F223456091"},),
        )
        _, missing_staff = _seed_historical_case(
            cursor, case_no=missing, client_name="Browser missing rate case",
            staff_specs=({"name": names[1], "identity_card": "F223456092", "with_rate_snapshot": False},),
        )
        _, partial_staff = _seed_historical_case(
            cursor, case_no=partial, client_name="Browser partial case",
            staff_specs=(
                {"name": names[2], "identity_card": "F223456093", "schedule_days": 12},
                {"name": names[3], "identity_card": "F223456094", "start_date": date(2026, 8, 13)},
            ),
        )
    mysql_connection.commit()

    def snapshot(case_no, staff):
        result = _snapshot_tables(
            mysql_connection, case_nos=(case_no,), staff_ids=tuple(row["staff_id"] for row in staff),
        )
        mysql_connection.commit()
        return result

    with _browser_payroll_app(tmp_path) as base, sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        api_responses = []
        page_errors = []

        def record_api_response(response):
            path = urlsplit(response.url).path
            if response.url.startswith(f"{base}/") and "/api/" in path:
                api_responses.append((response.request.method, path, response.status))

        page.on("response", record_api_response)
        page.on("pageerror", lambda error: page_errors.append(error.name))
        try:
            # Start with a same-origin API document so React does not mount before the session is stored.
            page.goto(f"{base}/api/v1/admin/auth/development-session", wait_until="domcontentloaded")
            session_status = page.evaluate("""async () => {
                const response = await fetch('/api/v1/admin/auth/development-session', {method: 'POST'});
                if (response.ok) {
                    const {data} = await response.json();
                    sessionStorage.setItem('union_admin_session_token', data.access_token);
                    sessionStorage.setItem('union_admin_session_user', JSON.stringify(data.admin));
                }
                return response.status;
            }""")
            assert session_status == 200

            def open_review(case_no, recipient, before_ready):
                page.goto(f"{base}/admin/?payroll_e2e_case={case_no}#finance?case_no={case_no}", wait_until="domcontentloaded")
                drawer = page.get_by_role("dialog", name=f"案件帳務 · {case_no}")
                expect(drawer.get_by_text(before_ready, exact=False)).to_be_visible(timeout=20000)
                drawer.get_by_text("查未列入原因", exact=True).click()
                drawer.get_by_role("button", name="查核歷史月嫂款").click()
                entry = drawer.locator("strong", has_text=f"{case_no} · {recipient}").locator("..")
                entry.get_by_role("button", name="處理這筆款項").click()
                return drawer.get_by_role("region", name="歷史月嫂款查核")

            def synchronize(case_no, review):
                path = f"/api/v1/orders/{case_no}/payroll/sync-historical-baseline-obligations"
                with page.expect_response(lambda response: response.url.endswith(path) and response.request.method == "POST") as request:
                    review.get_by_role("button", name="同步月嫂應付").click()
                response = request.value
                assert response.status == 200
                return response.json()["data"]

            def accounting(case_no):
                return page.evaluate("""async (caseNo) => {
                    const token = sessionStorage.getItem('union_admin_session_token');
                    const response = await fetch('/api/v1/finance-import/cases/' + caseNo + '/accounting', {
                        headers: {Authorization: 'Bearer ' + token}
                    });
                    if (!response.ok) throw new Error('Accounting GET status ' + response.status);
                    return (await response.json()).data;
                }""", case_no)

            before = snapshot(single, single_staff)
            review = open_review(single, names[0], "薪資試算 NT$ 48,000，尚未建帳。")
            estimate = accounting(single)
            assert estimate["staff_items"] == []
            assert estimate["staff_accounting_availability"][0]["estimated_amount_ntd"] == 48000
            assert before == snapshot(single, single_staff)
            result = synchronize(single, review)
            assert result["created_count"] == 1
            detail = result["details"][0]
            identity = detail["obligation_identity"]
            assert detail["staff_id"] == single_staff[0]["staff_id"]
            assert detail["assignment_id"] == single_staff[0]["assignment_id"]
            expect(review.get_by_text(f"{names[0]} · 正式應付 NT$ 48,000 · 付款安排待確認")).to_be_visible()
            readback = accounting(single)
            assert len(readback["staff_items"]) == 1
            payable = readback["staff_items"][0]
            assert payable["identity"] == identity and payable["expected_ntd"] == 48000
            assert payable["due_date"] is None and not payable.get("funding_portions")
            assert payable["actual_ntd"] == 0 and payable["has_payment"] is False
            assert not any(tx["item_identity"] == identity for tx in readback["transactions"])
            after = snapshot(single, single_staff)
            repeat = synchronize(single, review)
            assert repeat["created_count"] == repeat["updated_count"] == 0
            assert repeat["details"][0]["obligation_identity"] == identity
            expect(review.get_by_text(f"{names[0]} · 正式應付 NT$ 48,000 · 付款安排待確認")).to_be_visible()
            assert after == snapshot(single, single_staff)

            before = snapshot(missing, missing_staff)
            review = open_review(missing, names[1], "應付來源待核對")
            result = synchronize(missing, review)
            assert result["created_count"] == 0
            assert result["details"][0]["reason"] == "payroll_rate_policy_not_found"
            expect(review.get_by_role("status")).to_contain_text("月嫂費率")
            assert accounting(missing)["staff_items"] == []
            assert before == snapshot(missing, missing_staff)

            review = open_review(partial, names[2], "薪資試算 NT$ 28,800，尚未建帳。")
            result = synchronize(partial, review)
            items = {item["staff_id"]: item for item in result["details"][0]["items"]}
            assert items[partial_staff[0]["staff_id"]]["action"] == "created"
            assert items[partial_staff[1]["staff_id"]]["reason"] == "historical_payroll_service_basis_missing"
            expect(review.get_by_text(f"{names[2]} · 正式應付 NT$ 28,800 · 付款安排待確認")).to_be_visible()
            expect(review.get_by_text(f"{names[3]} · 請查核可證實之月嫂服務天數及每日服務時數。")).to_be_visible()
            readback = accounting(partial)
            assert [item["expected_ntd"] for item in readback["staff_items"]] == [28800]
            assert {item["staff_id"]: item["status"] for item in readback["staff_accounting_availability"]} == {
                partial_staff[0]["staff_id"]: "formal", partial_staff[1]["staff_id"]: "needs_review",
            }
        except Exception:
            document = urlsplit(page.url)
            print(f"Browser document path: {document.path}#{document.fragment.split('?')[0]}")
            print(f"Browser API responses (method, path, status): {api_responses[-30:]}")
            print(f"Browser JavaScript error types: {page_errors[-10:]}")
            try:
                print(f"Browser visible text:\n{page.locator('body').inner_text(timeout=2000)[:3500]}")
            except Exception:
                print("Browser document text unavailable.")
            raise
        finally:
            browser.close()


def test_star_case1_sync_bank_candidate_api_reconcile_and_readback_mysql(mysql_connection):
    case_no = "115000425"
    staff_name = "Case1 Caregiver"
    with mysql_connection.cursor() as cursor:
        _, staff_list = _seed_historical_case(
            cursor,
            case_no=case_no,
            client_name="Case1 Client",
            identity_status="一般市民",
            service_days=20,
            hours_per_day=8,
            staff_specs=({"name": staff_name, "identity_card": "F223456001", "hourly_rate": 300},),
            hourly_rate=300,
        )
        staff_id = staff_list[0]["staff_id"]
        cursor.execute(
            "INSERT INTO client_legacy_virtual_accounts(case_no,virtual_account,source_content_digest,source_row,created_by) "
            "VALUES(%s,'99781699150425',%s,2,'synthetic')",
            (case_no, _fingerprint("va-425")),
        )
        _, client_bank_row_id = _seed_client_full_payment(
            cursor, case_no=case_no, client_name="Case1 Client", amount_ntd=48000, tx_date=date(2026, 8, 10)
        )
        batch_id = _seed_bank_batch(cursor, format_id="sinopac")
        sinopac_row_id = _seed_bank_row(
            cursor,
            batch_id=batch_id,
            format_id="sinopac",
            direction="outgoing",
            amount_ntd=47985,
            tx_date=date(2026, 8, 25),
            counterparty_name=staff_name,
            memo="薪資 150425 內扣手續費15",
            classification_type="staff_payout",
            disposition="manual_review",
            reason="outgoing_staff_payout_missing_obligation",
            matched_staff_id=staff_id,
        )
    mysql_connection.commit()

    bank_ids = (client_bank_row_id, sinopac_row_id)
    before = _snapshot_tables(mysql_connection, case_nos=(case_no,), staff_ids=(staff_id,), bank_row_ids=bank_ids)
    assert before["staff_obligations"] == []

    sync_result = synchronize_historical_payroll(mysql_connection, case_no, dry_run=False)
    mysql_connection.commit()
    assert sync_result["action"] == "created"
    assert sync_result["amount_ntd"] == 48000
    assert sync_result["due_date"] is None

    with mysql_connection.cursor() as cursor:
        cursor.execute(
            "SELECT obligation_identity,staff_id,amount_due_ntd,due_date,status FROM staff_obligations WHERE case_no=%s",
            (case_no,),
        )
        created_row = cursor.fetchone()
    assert created_row is not None
    obligation_identity = str(created_row["obligation_identity"])
    assert created_row == {
        "obligation_identity": obligation_identity,
        "staff_id": staff_id,
        "amount_due_ntd": 48000,
        "due_date": None,
        "status": "open",
    }

    client = _bank_api_client(mysql_connection)
    response = client.get(
        "/api/v1/finance-import/bank-transactions",
        params={"bank": "sinopac", "direction": "outgoing", "transaction_status": "pending", "row_id": sinopac_row_id},
    )
    assert response.status_code == 200
    items = response.json()["data"]["items"]
    assert len(items) == 1
    tx_view = items[0]
    assert tx_view["row_id"] == sinopac_row_id
    assert tx_view["amount_ntd"] == 47985
    assert tx_view["reconciliation_target"] is not None
    assert tx_view["reconciliation_target"]["case_no"] == case_no
    assert tx_view["reconciliation_target"]["staff_id"] == staff_id
    assert tx_view["reconciliation_target"]["requires_selection"] is True
    assert obligation_identity in tx_view["reconciliation_target"]["obligation_identities"]

    payout_app = build_staff_payout_application(mysql_connection)
    selection = StaffPayoutSelection(
        event_type=StaffPayoutEventType.PAYOUT,
        bank_fact_identities=(str(sinopac_row_id),),
        obligation_identities=(obligation_identity,),
    )
    preview = payout_app.preview(selection, CorrelationId("case1-preview"))
    assert preview.candidate.obligation_total.amount == 48000
    assert preview.candidate.bank_total.amount == 47985
    assert preview.candidate.transfer_fee.amount == 15

    receipt = payout_app.apply(
        StaffPayoutApplyRequest(
            selection=selection,
            expected_staff_payables_version=ExpectedVersion(preview.staff_payables_version),
            expected_bank_facts_version=ExpectedVersion(preview.bank_facts_version),
            preview_fingerprint=preview.fingerprint,
            idempotency_key=IdempotencyKey("case1-apply-1"),
            actor=ActorContext("pr425-test"),
            reason="STAR Case 1 Sinopac payout with 15 fee",
            correlation_id=CorrelationId("case1-apply"),
        )
    )
    assert receipt.resulting_status.value == "completed"

    workspace = build_accounting_workspace(mysql_connection).query(case_no)
    assert workspace.payable_ntd == 48000
    assert workspace.remaining_out_ntd == 0
    assert workspace.subsidy_ntd == 12000
    assert workspace.scheme == "unknown"
    assert workspace.ongoing_completed is False
    assert workspace.subsidy_plan is not None and workspace.subsidy_plan.selected_scheme is None
    assert "historical_payroll_funding_source_missing" in workspace.staff_accounting_availability[0].pending_reasons
    assert workspace.cash_by_flow is not None and workspace.cash_by_flow["PS"] == 47985
    assert len(workspace.staff_items) == 1
    assert workspace.staff_items[0].expected_ntd == 48000
    assert workspace.staff_items[0].remaining_ntd == 0
    assert workspace.staff_items[0].settled is True
    assert workspace.customer_fully_received is True
    staff_txs = [tx for tx in workspace.transactions if tx.kind == "payout"]
    assert len(staff_txs) == 1
    assert staff_txs[0].bank_amount_ntd == 47985
    assert staff_txs[0].transfer_fee_ntd == 15

    after = _snapshot_tables(mysql_connection, case_nos=(case_no,), staff_ids=(staff_id,), bank_row_ids=bank_ids)
    assert after["client_obligations"] == before["client_obligations"]
    assert after["client_ledger_entries"] == before["client_ledger_entries"]
    assert after["client_ledger_allocations"] == before["client_ledger_allocations"]
    assert after["government_subsidy_entries"] == before["government_subsidy_entries"] == []
    assert after["orders"] == before["orders"]
    assert after["bank_rows"] == before["bank_rows"]
    assert after["bank_rows"][1]["debit"] == 47985
    assert len(after["staff_payout_events"]) == 1
    assert after["staff_payout_events"][0]["amount_ntd"] == 47985
    assert len(after["staff_payout_links"]) == 1
    assert after["staff_payout_links"][0]["allocated_amount_ntd"] == 48000

    posted_resp = client.get(
        "/api/v1/finance-import/bank-transactions",
        params={"bank": "sinopac", "direction": "outgoing", "transaction_status": "all", "row_id": sinopac_row_id},
    )
    assert posted_resp.status_code == 200
    assert posted_resp.json()["data"]["items"][0]["status"] == "posted"


def test_star_case2_idempotency_duplicate_and_error_branches_zero_writes_mysql(mysql_connection):
    case_no = "115000426"
    other_case_no = "115000499"
    with mysql_connection.cursor() as cursor:
        _, s1 = _seed_historical_case(
            cursor,
            case_no=case_no,
            client_name="Case2 Client A",
            staff_specs=({"name": "Case2 Staff A", "identity_card": "F223456011"},),
        )
        _, s2 = _seed_historical_case(
            cursor,
            case_no=other_case_no,
            client_name="Case2 Client B",
            staff_specs=({"name": "Case2 Staff B", "identity_card": "F223456012"},),
        )
        staff_a = s1[0]["staff_id"]
        staff_b = s2[0]["staff_id"]
        cursor.execute(
            "INSERT INTO client_legacy_virtual_accounts(case_no,virtual_account,source_content_digest,source_row,created_by) "
            "VALUES(%s,'99781699150499',%s,2,'synthetic')",
            (other_case_no, _fingerprint("va-499")),
        )
        batch_id = _seed_bank_batch(cursor, format_id="sinopac")
        valid_bank_id = _seed_bank_row(
            cursor, batch_id=batch_id, format_id="sinopac", direction="outgoing", amount_ntd=47985,
            tx_date=date(2026, 8, 25), counterparty_name="Case2 Staff A", memo="薪資撥款",
            classification_type="staff_payout", disposition="manual_review",
            reason="outgoing_staff_payout_missing_obligation", matched_staff_id=staff_a,
        )
        wrong_staff_bank_id = _seed_bank_row(
            cursor, batch_id=batch_id, format_id="sinopac", direction="outgoing", amount_ntd=47985,
            tx_date=date(2026, 8, 25), counterparty_name="Case2 Staff B", memo="錯月嫂流水",
            classification_type="staff_payout", disposition="manual_review",
            reason="outgoing_staff_payout_missing_obligation", matched_staff_id=staff_b,
        )
        wrong_case_bank_id = _seed_bank_row(
            cursor, batch_id=batch_id, format_id="sinopac", direction="outgoing", amount_ntd=47985,
            tx_date=date(2026, 8, 25), counterparty_name="Case2 Staff A", memo="案號 150499",
            classification_type="staff_payout", disposition="manual_review",
            reason="outgoing_staff_payout_missing_obligation", matched_staff_id=staff_a,
        )
        bad_fee_bank_id = _seed_bank_row(
            cursor, batch_id=batch_id, format_id="sinopac", direction="outgoing", amount_ntd=47885,
            tx_date=date(2026, 8, 25), counterparty_name="Case2 Staff A", memo="超額手續費 115",
            classification_type="staff_payout", disposition="manual_review",
            reason="outgoing_staff_payout_missing_obligation", matched_staff_id=staff_a,
        )
        uncertain_split_bank_id = _seed_bank_row(
            cursor, batch_id=batch_id, format_id="sinopac", direction="outgoing", amount_ntd=35985,
            tx_date=date(2026, 8, 25), counterparty_name="Case2 Staff A", memo="自費分期未定 35985",
            classification_type="staff_payout", disposition="manual_review",
            reason="outgoing_staff_payout_missing_obligation", matched_staff_id=staff_a,
        )
    mysql_connection.commit()

    sync_res = synchronize_historical_payroll(mysql_connection, case_no, dry_run=False)
    mysql_connection.commit()
    assert sync_res["action"] == "created"
    split_case_no = "115000431"
    with mysql_connection.cursor() as cursor:
        cursor.execute("SELECT obligation_identity FROM staff_obligations WHERE case_no=%s", (case_no,))
        ob_a = str(cursor.fetchone()["obligation_identity"])
        _seed_historical_case(
            cursor,
            case_no=split_case_no,
            client_name="Case2 Uncertain Split Client",
            staff_specs=({"name": "Case2 Staff A", "identity_card": "F223456011"},),
        )
        cursor.execute(
            "INSERT INTO finance_case_subsidy_plan_events(case_no,version,scheme,actor,operation_key) "
            "VALUES(%s,1,'split','synthetic',%s)",
            (split_case_no, f"split-plan:{split_case_no}"),
        )
    mysql_connection.commit()
    split_sync = synchronize_historical_payroll(mysql_connection, split_case_no, dry_run=False)
    mysql_connection.commit()
    assert split_sync["action"] == "created"
    with mysql_connection.cursor() as cursor:
        cursor.execute("SELECT obligation_identity FROM staff_obligations WHERE case_no=%s", (split_case_no,))
        ob_split = str(cursor.fetchone()["obligation_identity"])
    payout_app = build_staff_payout_application(mysql_connection)

    bank_ids = (valid_bank_id, wrong_staff_bank_id, wrong_case_bank_id, bad_fee_bank_id, uncertain_split_bank_id)
    baseline = _snapshot_tables(
        mysql_connection,
        case_nos=(case_no, other_case_no, split_case_no),
        staff_ids=(staff_a, staff_b),
        bank_row_ids=bank_ids,
    )
    error_cases = [
        ("cross_staff_allocation_forbidden", StaffPayoutSelection(StaffPayoutEventType.PAYOUT, (str(wrong_staff_bank_id),), (ob_a,))),
        ("staff_memo_case_mismatch", StaffPayoutSelection(StaffPayoutEventType.PAYOUT, (str(wrong_case_bank_id),), (ob_a,))),
        ("staff_payout_amount_mismatch", StaffPayoutSelection(StaffPayoutEventType.PAYOUT, (str(bad_fee_bank_id),), (ob_a,))),
        ("staff_installment_funding_unconfirmed", StaffPayoutSelection(StaffPayoutEventType.PAYOUT, (str(uncertain_split_bank_id),), (ob_split,), confirm_subsidy_split=False)),
        ("staff_payout_amount_mismatch", StaffPayoutSelection(StaffPayoutEventType.PAYOUT, (str(uncertain_split_bank_id),), (ob_a,), confirm_subsidy_split=False)),
    ]
    for expected_code, sel in error_cases:
        with pytest.raises(StaffPayoutReconciliationError) as exc_info:
            payout_app.preview(sel, CorrelationId(f"err-{expected_code}-{uuid4().hex[:6]}"))
        assert exc_info.value.error.code == expected_code
        assert _snapshot_tables(
            mysql_connection,
            case_nos=(case_no, other_case_no, split_case_no),
            staff_ids=(staff_a, staff_b),
            bank_row_ids=bank_ids,
        ) == baseline

    hist_wf = HistoricalStaffPayoutWorkflow(
        MySqlHistoricalStaffPayoutRepository(mysql_connection),
        lambda: HistoricalStaffPayoutMySqlUnitOfWork(mysql_connection),
    )
    manual_preview = hist_wf.preview(
        HistoricalStaffPayoutIntent(
            case_no=case_no,
            staff_id=staff_a,
            confirmation_kind=HistoricalStaffConfirmationKind.PAID,
            obligation_identities=(ob_a,),
            payment_date=date(2026, 8, 25),
            payment_date_unknown_reason=None,
            source_availability=HistoricalStaffSourceAvailability.MISSING,
        )
    )
    assert "historical_staff_bank_reconciliation_required" in manual_preview.candidate.blockers
    assert _snapshot_tables(mysql_connection, case_nos=(case_no, other_case_no, split_case_no), staff_ids=(staff_a, staff_b), bank_row_ids=bank_ids) == baseline

    ok_sel = StaffPayoutSelection(StaffPayoutEventType.PAYOUT, (str(valid_bank_id),), (ob_a,))
    ok_preview = payout_app.preview(ok_sel, CorrelationId("case2-ok"))
    ok_req = StaffPayoutApplyRequest(
        selection=ok_sel,
        expected_staff_payables_version=ExpectedVersion(ok_preview.staff_payables_version),
        expected_bank_facts_version=ExpectedVersion(ok_preview.bank_facts_version),
        preview_fingerprint=ok_preview.fingerprint,
        idempotency_key=IdempotencyKey("case2-idemp-1"),
        actor=ActorContext("pr425-test"),
        reason="reconcile valid row",
        correlation_id=CorrelationId("case2-apply"),
    )
    first_receipt = payout_app.apply(ok_req)
    after_reconcile = _snapshot_tables(mysql_connection, case_nos=(case_no, other_case_no), staff_ids=(staff_a, staff_b), bank_row_ids=bank_ids)

    assert payout_app.apply(ok_req) == first_receipt
    assert _snapshot_tables(mysql_connection, case_nos=(case_no, other_case_no), staff_ids=(staff_a, staff_b), bank_row_ids=bank_ids) == after_reconcile

    dup_req = StaffPayoutApplyRequest(
        selection=ok_sel,
        expected_staff_payables_version=ExpectedVersion(first_receipt.staff_payables_version),
        expected_bank_facts_version=ExpectedVersion(first_receipt.bank_facts_version),
        preview_fingerprint=ok_preview.fingerprint,
        idempotency_key=IdempotencyKey("case2-idemp-2"),
        actor=ActorContext("pr425-test"),
        reason="duplicate attempt with new idempotency key",
        correlation_id=CorrelationId("case2-dup"),
    )
    with pytest.raises(StaffPayoutReconciliationError):
        payout_app.apply(dup_req)
    assert _snapshot_tables(mysql_connection, case_nos=(case_no, other_case_no), staff_ids=(staff_a, staff_b), bank_row_ids=bank_ids) == after_reconcile


def test_star_case3_multi_caregiver_partial_sync_and_preserve_paid_mysql(mysql_connection):
    multi_case = "115000427"
    anti_case = "115000428"
    with mysql_connection.cursor() as cursor:
        _, multi_staff = _seed_historical_case(
            cursor,
            case_no=multi_case,
            client_name="Case3 Multi Client",
            service_days=20,
            hours_per_day=8,
            staff_specs=(
                {
                    "name": "Verified Caregiver A",
                    "identity_card": "F223456021",
                    "hourly_rate": 300,
                    "start_date": date(2026, 8, 1),
                    "end_date": date(2026, 8, 12),
                    "schedule_days": 12,
                },
                {
                    "name": "Missing Schedule Caregiver B",
                    "identity_card": "F223456022",
                    "hourly_rate": 300,
                    "start_date": date(2026, 8, 13),
                    "end_date": date(2026, 8, 20),
                    "schedule_days": 0,
                },
            ),
        )
        staff_a = multi_staff[0]["staff_id"]
        staff_b = multi_staff[1]["staff_id"]

        _, anti_staff = _seed_historical_case(
            cursor,
            case_no=anti_case,
            client_name="Case3 Anti Paid Client",
            service_days=20,
            hours_per_day=8,
            staff_specs=({"name": "Paid Caregiver C", "identity_card": "F223456023", "hourly_rate": 300},),
        )
        staff_c = anti_staff[0]["staff_id"]
        assignment_c = anti_staff[0]["assignment_id"]
        anti_ob = f"legacy:service:{anti_case}:staff:{staff_c}"
        cursor.execute(
            "INSERT INTO staff_obligation_events("
            "obligation_identity,assignment_id,case_no,staff_id,obligation_kind,"
            "direction,source_obligation_identity,event_type,before_amount_ntd,"
            "after_amount_ntd,due_date,payroll_fingerprint,expected_payroll_version,"
            "resulting_payroll_version,idempotency_key,actor,reason"
            ") VALUES(%s,%s,%s,%s,'service_pay','payable_to_staff',NULL,'established',0,45000,'2026-08-25',%s,0,1,%s,'synthetic','original settled')",
            (anti_ob, assignment_c, anti_case, staff_c, _fingerprint(f"fp:{anti_ob}"), f"key:{anti_ob}"),
        )
        anti_ob_evt = int(cursor.lastrowid)
        cursor.execute(
            "INSERT INTO staff_obligations("
            "obligation_identity,assignment_id,case_no,staff_id,obligation_kind,"
            "direction,source_obligation_identity,amount_due_ntd,due_date,status,"
            "current_event_id,payroll_version,payout_history_exists"
            ") VALUES(%s,%s,%s,%s,'service_pay','payable_to_staff',NULL,45000,'2026-08-25','open',%s,1,1)",
            (anti_ob, assignment_c, anti_case, staff_c, anti_ob_evt),
        )
        cursor.execute(
            "INSERT INTO staff_payout_events("
            "staff_id,finance_import_row_id,event_type,amount_ntd,occurred_on,"
            "bank_account_identity_hash,reconciliation_reference,idempotency_key,actor,reason"
            ") VALUES(%s,NULL,'payout',45000,'2026-08-25',%s,'PAID-ORIG','paid-orig-c','synthetic','already paid')",
            (staff_c, _fingerprint("acct-c")),
        )
        payout_evt_id = int(cursor.lastrowid)
        cursor.execute(
            "INSERT INTO staff_payout_obligation_links(payout_event_id,obligation_identity,allocated_amount_ntd,allocation_ordinal) "
            "VALUES(%s,%s,45000,1)",
            (payout_evt_id, anti_ob),
        )
        cursor.execute(
            "INSERT INTO staff_payable_projections("
            "obligation_identity,staff_id,obligation_amount_ntd,net_paid_ntd,balance_ntd,status,aggregate_version,current_event_id"
            ") VALUES(%s,%s,45000,45000,0,'completed',1,%s)",
            (anti_ob, staff_c, payout_evt_id),
        )
    mysql_connection.commit()

    dry_res = synchronize_historical_payroll(mysql_connection, multi_case, dry_run=True)
    with mysql_connection.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) AS cnt FROM staff_obligations WHERE case_no=%s", (multi_case,))
        assert int(cursor.fetchone()["cnt"]) == 0
    by_staff = {int(item["staff_id"]): item for item in dry_res["items"]}
    assert by_staff[staff_a]["action"] == "created"
    assert by_staff[staff_b]["action"] == "skipped"
    assert by_staff[staff_b]["reason"] == "historical_payroll_service_basis_missing"

    mysql_connection.commit()
    with _bank_api_client(mysql_connection) as client:
        sync_url = f"/api/v1/orders/{multi_case}/payroll/sync-historical-baseline-obligations"
        committed = client.post(sync_url)
        assert committed.status_code == 200, committed.text
        apply_res = committed.json()["data"]["details"][0]
        by_staff_apply = {int(item["staff_id"]): item for item in apply_res["items"]}
        assert by_staff_apply[staff_a]["action"] == "created"
        assert by_staff_apply[staff_b]["reason"] == "historical_payroll_service_basis_missing"
        current = client.get(f"/api/v1/finance-import/cases/{multi_case}/accounting")
        assert current.status_code == 200, current.text
        current_case = current.json()["data"]
        assert [row["identity"] for row in current_case["staff_items"]] == [
            by_staff_apply[staff_a]["obligation_identity"]
        ]
        assert {
            item["staff_id"]: item["status"] for item in current_case["staff_accounting_availability"]
        } == {staff_a: "formal", staff_b: "needs_review"}
        repeated = client.post(sync_url)
        assert repeated.status_code == 200, repeated.text
        rerun_res = repeated.json()["data"]["details"][0]
    assert apply_res["action"] == "created"
    assert rerun_res["action"] == "skipped"
    by_staff_rerun = {int(item["staff_id"]): item for item in rerun_res["items"]}
    assert by_staff_rerun[staff_a]["action"] == "skipped"
    assert by_staff_rerun[staff_a]["reason"] == "already_synced"
    assert by_staff_rerun[staff_b]["action"] == "skipped"
    assert by_staff_rerun[staff_b]["reason"] == "historical_payroll_service_basis_missing"

    with mysql_connection.cursor() as cursor:
        cursor.execute("SELECT obligation_identity,staff_id,amount_due_ntd,due_date,status FROM staff_obligations WHERE case_no=%s", (multi_case,))
        multi_rows = cursor.fetchall()
    assert len(multi_rows) == 1
    assert multi_rows[0]["staff_id"] == staff_a
    assert multi_rows[0]["amount_due_ntd"] == 28800
    assert multi_rows[0]["due_date"] is None

    anti_before = _snapshot_tables(mysql_connection, case_nos=(anti_case,), staff_ids=(staff_c,))
    mysql_connection.commit()
    with _bank_api_client(mysql_connection) as client:
        preserved = client.post(f"/api/v1/orders/{anti_case}/payroll/sync-historical-baseline-obligations")
        assert preserved.status_code == 200, preserved.text
        anti_res = preserved.json()["data"]["details"][0]
    assert anti_res["action"] in {"preserved", "already_synced", "skipped"}
    assert _snapshot_tables(mysql_connection, case_nos=(anti_case,), staff_ids=(staff_c,)) == anti_before
    mysql_connection.commit()


def test_historical_sync_two_caregivers_with_confirmed_advance_keeps_individual_due_dates(
    mysql_connection: pymysql.connections.Connection,
) -> None:
    _assert_historical_sync_with_confirmed_advance(
        mysql_connection, case_no="115000436", identity_cards=("F223456046", "F223456047"), paid_first=False,
    )


def test_historical_sync_two_caregivers_with_confirmed_advance_preserves_paid_caregiver(
    mysql_connection: pymysql.connections.Connection,
) -> None:
    _assert_historical_sync_with_confirmed_advance(
        mysql_connection, case_no="115000437", identity_cards=("F223456048", "F223456049"), paid_first=True,
    )


def test_historical_sync_two_caregivers_with_confirmed_advance_leaves_actual_funding_conflict_pending(
    mysql_connection: pymysql.connections.Connection,
) -> None:
    _assert_historical_sync_with_confirmed_advance(
        mysql_connection, case_no="115000438", identity_cards=("F223456050", "F223456051"),
        paid_first=True, paid_amount=7201, expected_new_due=None,
    )


def _paid_caregiver_rows(
    connection: (
        pymysql.connections.Connection
        | pymysql.connections.Connection[pymysql.cursors.DictCursor]
        | mysql_adapter._PooledMySqlConnection
    ),
    identity: str,
    staff_id: int,
) -> dict[str, list[dict[str, object]]]:
    queries = (
        ("staff_obligations", "obligation_identity", identity, "obligation_identity"),
        ("staff_obligation_events", "obligation_identity", identity, "id"),
        ("staff_obligation_installments", "obligation_identity", identity, "funding_kind"),
        ("staff_payout_events", "staff_id", staff_id, "id"),
        ("staff_payout_obligation_links", "obligation_identity", identity, "id"),
        ("staff_payable_projections", "obligation_identity", identity, "obligation_identity"),
    )
    with connection.cursor(pymysql.cursors.DictCursor) as cursor:
        records: dict[str, list[dict[str, object]]] = {}
        for table, key, value, order_by in queries:
            cursor.execute(f"SELECT * FROM {table} WHERE {key}=%s ORDER BY {order_by}", (value,))
            records[table] = list(cursor.fetchall())
        return records


def _assert_historical_sync_with_confirmed_advance(
    mysql_connection: pymysql.connections.Connection,
    *,
    case_no: str,
    identity_cards: tuple[str, str],
    paid_first: bool,
    paid_amount: int = 7200,
    expected_new_due: str | None = "2026-10-15",
) -> None:
    august_end = date(2026, 8, 31)
    september_end = date(2026, 9, 2)
    with mysql_connection.cursor() as cursor:
        _, staff = _seed_historical_case(
            cursor,
            case_no=case_no,
            client_name="Synthetic historical advance client",
            service_days=5,
            start_day=date(2026, 8, 29),
            end_day=september_end,
            staff_specs=(
                {"name": "August caregiver", "identity_card": identity_cards[0], "with_bank_account": False,
                 "end_date": august_end, "schedule_days": 3, "hourly_rate": 300},
                {
                    "name": "September caregiver",
                    "identity_card": identity_cards[1],
                    "with_bank_account": False,
                    "start_date": date(2026, 9, 1),
                    "end_date": september_end,
                    "schedule_days": 2,
                    "hourly_rate": 350,
                    "policy_version": DEFAULT_PAYROLL_POLICY_VERSION,
                    "policy_kind": PayrollPolicyKind.SUBSIDIZED_CITIZEN,
                },
            ),
        )
        pricing_rates = {"covered": 350, "excess": 300}
        cursor.execute(
            "INSERT INTO case_pricing_events(case_no,resulting_revision,pricing_json,actor,reason,created_at_utc) "
            "VALUES(%s,1,%s,'synthetic','historical confirmed terms',UTC_TIMESTAMP(6))",
            (case_no, json.dumps({"identity_name": "一般市民", "rule": "citizen", "subsidy_hours": 16,
                                  "client": pricing_rates, "payroll": pricing_rates})),
        )
        cursor.execute(
            "UPDATE orders SET pricing_override_event_id=%s,pricing_revision=1 WHERE case_no=%s",
            (cursor.lastrowid, case_no),
        )
        cursor.execute(
            "INSERT INTO client_ledger_entries(case_no,finance_import_row_id,entry_type,amount_ntd,occurred_on,"
            "reconciliation_reference,idempotency_key,actor,reason) "
            "VALUES(%s,NULL,'receipt',12800,%s,%s,%s,'synthetic','original customer advance')",
            (case_no, august_end, f"legacy-receipt:{case_no}", f"legacy-receipt:{case_no}"),
        )
        cursor.execute(
            "INSERT INTO finance_case_subsidy_plan_events(case_no,version,scheme,actor,operation_key) "
            "VALUES(%s,1,'advance','synthetic',%s)", (case_no, f"manual-advance:{case_no}"),
        )
        first_assignment = staff[0]["assignment_id"]
        first_staff = staff[0]["staff_id"]
        paid_identity = f"legacy:service:{case_no}:staff:{first_staff}"
        if paid_first:
            cursor.execute(
                "INSERT INTO staff_obligation_events("
                "obligation_identity,assignment_id,case_no,staff_id,obligation_kind,direction,event_type,"
                "before_amount_ntd,after_amount_ntd,due_date,payroll_fingerprint,expected_payroll_version,"
                "resulting_payroll_version,idempotency_key,actor,reason"
                ") VALUES(%s,%s,%s,%s,'service_pay','payable_to_staff','established',"
                "0,%s,'2026-09-15',%s,0,1,%s,'synthetic','original obligation')",
                (paid_identity, first_assignment, case_no, first_staff, paid_amount,
                 _fingerprint(paid_identity), f"obligation:{paid_identity}"),
            )
            cursor.execute(
                "INSERT INTO staff_obligations("
                "obligation_identity,assignment_id,case_no,staff_id,obligation_kind,direction,"
                "amount_due_ntd,due_date,status,current_event_id,payroll_version,payout_history_exists"
                ") VALUES(%s,%s,%s,%s,'service_pay','payable_to_staff',%s,'2026-09-15','open',%s,1,1)",
                (paid_identity, first_assignment, case_no, first_staff, paid_amount, cursor.lastrowid),
            )
            cursor.execute(
                "INSERT INTO staff_obligation_installments(obligation_identity,funding_kind,amount_ntd,due_date) "
                "VALUES(%s,'client',%s,'2026-09-15')", (paid_identity, paid_amount),
            )
            cursor.execute(
                "INSERT INTO staff_payout_events("
                "staff_id,finance_import_row_id,event_type,amount_ntd,occurred_on,bank_account_identity_hash,"
                "reconciliation_reference,idempotency_key,actor,reason"
                ") VALUES(%s,NULL,'payout',%s,'2026-09-15',%s,'PAID-ORIG',%s,'synthetic','already paid')",
                (first_staff, paid_amount, _fingerprint(f"account:{paid_identity}"), f"payout:{paid_identity}"),
            )
            payout_event_id = int(cursor.lastrowid)
            cursor.execute(
                "INSERT INTO staff_payout_obligation_links("
                "payout_event_id,obligation_identity,allocated_amount_ntd,allocation_ordinal"
                ") VALUES(%s,%s,%s,1)", (payout_event_id, paid_identity, paid_amount),
            )
            cursor.execute(
                "INSERT INTO staff_payable_projections("
                "obligation_identity,staff_id,obligation_amount_ntd,net_paid_ntd,balance_ntd,status,"
                "aggregate_version,current_event_id"
                ") VALUES(%s,%s,%s,%s,0,'completed',1,%s)",
                (paid_identity, first_staff, paid_amount, paid_amount, payout_event_id),
            )
    mysql_connection.commit()

    snapshot_scope = {"case_nos": (case_no,), "staff_ids": tuple(row["staff_id"] for row in staff)}
    expected = {
        (staff[0]["assignment_id"], staff[0]["staff_id"]): (paid_amount if paid_first else 7200, "2026-09-15"),
        (staff[1]["assignment_id"], staff[1]["staff_id"]): (5600, expected_new_due),
    }
    accounting_url = f"/api/v1/finance-import/cases/{case_no}/accounting"
    sync_url = f"/api/v1/orders/{case_no}/payroll/sync-historical-baseline-obligations"
    before = _snapshot_tables(mysql_connection, **snapshot_scope)
    paid_before = _paid_caregiver_rows(mysql_connection, paid_identity, first_staff) if paid_first else {}
    mysql_connection.commit()

    with _bank_api_client(mysql_connection) as client:
        check = client.get(accounting_url)
        assert check.status_code == 200, check.text
        initial = check.json()["data"]
        assert initial["scheme"] == "advance" and not initial["scheme_conflict"], initial
        assert initial["case_total_ntd"] == 12800 and initial["subsidy_ntd"] == 5600, initial
        initial_payables = initial["staff_items"]
        if paid_first:
            assert len(initial_payables) == 1, initial
            old_payable = initial_payables[0]
            assert (old_payable["identity"], old_payable["expected_ntd"], old_payable["due_date"],
                    old_payable["actual_ntd"], old_payable["has_payment"]) == (
                paid_identity, paid_amount, "2026-09-15", paid_amount, True,
            ), old_payable
            assert all(len(rows) == 1 for rows in paid_before.values()), paid_before
            assert _paid_caregiver_rows(mysql_connection, paid_identity, first_staff) == paid_before
        else:
            assert initial_payables == []
        assert _snapshot_tables(mysql_connection, **snapshot_scope) == before
        mysql_connection.commit()

        sync = client.post(sync_url)
        assert sync.status_code == 200, sync.text
        receipt = sync.json()["data"]
        assert receipt["scanned_orders"] == receipt["created_count"] == 1, receipt
        items = receipt["details"][0]["items"]
        assert len(items) == 2, receipt
        if paid_first:
            old_item = next(item for item in items if item["staff_id"] == first_staff)
            assert (old_item["action"], old_item["obligation_identity"]) == ("skipped", paid_identity), receipt
            assert next(item for item in items if item["staff_id"] == staff[1]["staff_id"])["action"] == "created", receipt
        else:
            assert all(item["action"] == "created" for item in items), receipt
        if expected_new_due is None:
            new_item = next(item for item in items if item["staff_id"] == staff[1]["staff_id"])
            assert new_item["payment_arrangement_pending"] is True, receipt
            assert new_item["pending_reason"] == "historical_payroll_funding_conflict", receipt
        assert {(item["assignment_id"], item["staff_id"]): item["amount_ntd"] for item in items} == {
            pair: amount for pair, (amount, _) in expected.items()
        }, receipt

        readback = client.get(accounting_url)
        assert readback.status_code == 200, readback.text
        payables = readback.json()["data"]["staff_items"]
        assert {item["identity"]: item["expected_ntd"] for item in payables} == {
            item["obligation_identity"]: item["amount_ntd"] for item in items
        }
        assert {item["identity"]: item["actual_ntd"] for item in payables if item["has_payment"]} == (
            {paid_identity: paid_amount} if paid_first else {}
        )
        assert all(not item["actual_ntd"] for item in payables if not item["has_payment"])
        if paid_first:
            assert next(item for item in payables if item["identity"] == paid_identity) == initial_payables[0]

        with closing(mysql_adapter.get_connection()) as read_connection:
            after_sync = _snapshot_tables(read_connection, **snapshot_scope)
            if paid_first:
                assert _paid_caregiver_rows(read_connection, paid_identity, first_staff) == paid_before
        assert len(after_sync["staff_obligations"]) == len(after_sync["staff_obligation_events"]) == 2
        assert {row["obligation_identity"]: (row["staff_id"], row["amount_due_ntd"])
                for row in after_sync["staff_obligations"]} == {
            item["obligation_identity"]: (item["staff_id"], item["amount_ntd"]) for item in items
        }
        for table in ("client_obligations", "client_ledger_entries", "client_ledger_allocations",
                      "staff_payout_events", "staff_payout_links", "government_subsidy_entries", "orders"):
            assert after_sync[table] == before[table], table

        expected_dates = {item["obligation_identity"]: expected[(item["assignment_id"], item["staff_id"])][1]
                          for item in items}
        assert {item["obligation_identity"]: item["due_date"] for item in items} == expected_dates, receipt
        assert {item["identity"]: item["due_date"] for item in payables} == expected_dates
        for table in ("staff_obligations", "staff_obligation_events"):
            assert {row["obligation_identity"]: str(row["due_date"]) if row["due_date"] is not None else None
                    for row in after_sync[table]} == expected_dates

        repeat = client.post(sync_url)
        assert repeat.status_code == 200, repeat.text
        replay = repeat.json()["data"]
        assert replay["created_count"] == replay["updated_count"] == 0, replay
        with closing(mysql_adapter.get_connection()) as read_connection:
            assert _snapshot_tables(read_connection, **snapshot_scope) == after_sync
            if paid_first:
                assert _paid_caregiver_rows(read_connection, paid_identity, first_staff) == paid_before


def test_star_case5_ap_export_guardrails_for_undated_and_missing_account_mysql(mysql_connection):
    undated_case = "115000429"
    no_acct_case = "115000430"
    with mysql_connection.cursor() as cursor:
        _, s_undated = _seed_historical_case(
            cursor,
            case_no=undated_case,
            client_name="Case5 Undated Client",
            staff_specs=({"name": "Case5 Staff Undated", "identity_card": "F223456031", "with_bank_account": True},),
        )
        _, s_no_acct = _seed_historical_case(
            cursor,
            case_no=no_acct_case,
            client_name="Case5 NoAcct Client",
            staff_specs=({"name": "Case5 Staff NoAcct", "identity_card": "F223456032", "with_bank_account": False},),
        )
        staff_undated = s_undated[0]["staff_id"]
        staff_no_acct = s_no_acct[0]["staff_id"]
        assign_no_acct = s_no_acct[0]["assignment_id"]
        ob_no_acct = f"service:{no_acct_case}:assignment:{assign_no_acct}"
        cursor.execute(
            "INSERT INTO staff_obligation_events("
            "obligation_identity,assignment_id,case_no,staff_id,obligation_kind,"
            "direction,source_obligation_identity,event_type,before_amount_ntd,"
            "after_amount_ntd,due_date,payroll_fingerprint,expected_payroll_version,"
            "resulting_payroll_version,idempotency_key,actor,reason"
            ") VALUES(%s,%s,%s,%s,'service_pay','payable_to_staff',NULL,'established',0,48000,'2026-08-25',%s,0,1,%s,'synthetic','dated without primary bank')",
            (ob_no_acct, assign_no_acct, no_acct_case, staff_no_acct, _fingerprint(f"fp:{ob_no_acct}"), f"key:{ob_no_acct}"),
        )
        evt_id = int(cursor.lastrowid)
        cursor.execute(
            "INSERT INTO staff_obligations("
            "obligation_identity,assignment_id,case_no,staff_id,obligation_kind,"
            "direction,source_obligation_identity,amount_due_ntd,due_date,status,"
            "current_event_id,payroll_version,payout_history_exists"
            ") VALUES(%s,%s,%s,%s,'service_pay','payable_to_staff',NULL,48000,'2026-08-25','open',%s,1,0)",
            (ob_no_acct, assign_no_acct, no_acct_case, staff_no_acct, evt_id),
        )
    mysql_connection.commit()

    synchronize_historical_payroll(mysql_connection, undated_case, dry_run=False)
    mysql_connection.commit()

    export_source = MySqlStaffPayableExportSource(mysql_connection)
    export_candidates = export_source.load(date(2026, 8, 31))
    exported_cases = {row.case_no for row in export_candidates}
    assert undated_case not in exported_cases
    assert no_acct_case not in exported_cases

    undated_audit = export_source.load_case(undated_case, date(2026, 8, 31))
    assert len(undated_audit) == 1
    assert undated_audit[0].amount_due is not None and undated_audit[0].amount_due.amount == 48000
    assert undated_audit[0].effective_due_date is None
    assert undated_audit[0].disposition in {"date_not_formed", "blocked"}

    no_acct_audit = export_source.load_case(no_acct_case, date(2026, 8, 31))
    assert len(no_acct_audit) == 1
    assert no_acct_audit[0].amount_due is not None and no_acct_audit[0].amount_due.amount == 48000
    assert no_acct_audit[0].disposition == "blocked"
    assert "帳戶" in no_acct_audit[0].reason or "account" in no_acct_audit[0].reason.lower()

    ws_undated = build_accounting_workspace(mysql_connection).query(undated_case)
    assert ws_undated.payable_ntd == 48000
    assert ws_undated.paid_ntd == 0
    assert ws_undated.staff_items[0].due_date is None
    with mysql_connection.cursor() as cursor:
        cursor.execute(
            "SELECT COUNT(*) AS cnt FROM staff_payout_events WHERE staff_id IN (%s,%s)",
            (staff_undated, staff_no_acct),
        )
        assert int(cursor.fetchone()["cnt"]) == 0
