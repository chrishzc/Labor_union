"""Append-only MySQL proof for canonical Finance Import staging and deduplication."""

from __future__ import annotations

from decimal import Decimal
import os
from uuid import uuid4

import pytest


DATABASE = os.getenv("LABOR_UNION_TEST_MYSQL_DATABASE")
pytestmark = pytest.mark.skipif(
    not DATABASE or os.getenv("DB_DATABASE") != DATABASE,
    reason="requires an explicitly configured disposable lu_test_* MySQL database",
)


def test_raw_bank_roots_create_one_canonical_row_and_two_occurrences() -> None:
    from domains.finance_import.transaction_fingerprint import build_dedup_fingerprint
    from infrastructure.mysql.mysql_adapter import get_connection
    from subsystems.finance_import.staging import stage_finance_rows

    token = uuid4().hex
    first = _normalized_row(token, 17)
    second = _normalized_row(token, 18)
    fingerprint = build_dedup_fingerprint(first)
    connection = get_connection()
    try:
        before = _formal_output_counts(connection)
        with connection.cursor() as cursor:
            first_result = stage_finance_rows(cursor, _batch(first), _identity_maps())
            second_result = stage_finance_rows(cursor, _batch(second), _identity_maps())
        connection.commit()
        _assert_staged_result(first_result, second_result, fingerprint)
        _assert_canonical_dedup(connection, fingerprint)
        assert _formal_output_counts(connection) == before
    finally:
        connection.close()


def _batch(row: dict[str, object]) -> dict[str, object]:
    return {"format_id": "taishin", "sheet_name": "交易明細", "header_row": 2, "normalized_rows": [row]}


def _identity_maps() -> dict[str, object]:
    return {"client_refund_accounts": {}, "staff_accounts": {}}


def _normalized_row(token: str, source_row: int) -> dict[str, object]:
    amount = Decimal(1_000 + int(token[:8], 16) % 1_000_000)
    return {
        "format_id": "taishin", "source_file": f"lu-test-finance-{token}.xlsx",
        "source_bank_account": "LU-TEST", "sheet_name": "交易明細", "source_row": source_row,
        "source_reference": None, "transaction_date": "2026-08-10", "transaction_time": "09:08:07",
        "posting_date": "2026-08-10", "value_date": None, "debit": amount,
        "credit": None, "direction": "outgoing", "balance": amount + Decimal("9000.00"), "currency": "TWD",
        "summary": "LU test raw bank root", "memo": "unmatched controlled fixture", "counterparty_name": None,
        "counterparty_account": f"NO-MATCH-{token}", "cancellation_code": None,
        "bank_references": {"fixture": token}, "warnings": [], "raw_payload": {"fixture": token},
    }


def _assert_staged_result(first: dict[str, object], second: dict[str, object], fingerprint: str) -> None:
    first_row = first["staged_rows"][0]
    second_row = second["staged_rows"][0]
    assert first_row["result"] == "inserted"
    assert second_row["result"] == "skipped_existing"
    assert first_row["dedup_fingerprint"] == second_row["dedup_fingerprint"] == fingerprint
    assert first_row["classification_type"] == second_row["classification_type"] == "non_business_review"
    assert first_row["reconciliation_status"] == second_row["reconciliation_status"] == "pending"


def _assert_canonical_dedup(connection, fingerprint: str) -> None:
    with connection.cursor() as cursor:
        cursor.execute("SELECT id,classification_type,reconciliation_status FROM finance_import_rows WHERE dedup_fingerprint=%s", (fingerprint,))
        row = cursor.fetchone()
        cursor.execute("SELECT COUNT(*) AS count FROM finance_import_occurrences WHERE finance_import_row_id=%s", (row["id"],))
        occurrence_count = cursor.fetchone()["count"]
    assert row["classification_type"] == "non_business_review"
    assert row["reconciliation_status"] == "pending"
    assert occurrence_count == 2


def _formal_output_counts(connection) -> tuple[int, int, int]:
    tables = ("client_ledger_entries", "staff_payout_events", "government_subsidy_transactions")
    with connection.cursor() as cursor:
        counts = []
        for table in tables:
            cursor.execute(f"SELECT COUNT(*) AS count FROM {table}")
            counts.append(int(cursor.fetchone()["count"]))
    return tuple(counts)


def test_workbook_api_preview_reaches_react_without_formal_posting(tmp_path) -> None:
    """One append-only run: real workbook/API/MySQL, then replay its output through React."""
    from dataclasses import asdict
    import hashlib
    import json
    from pathlib import Path
    import shutil
    import subprocess

    import pandas as pd
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from api.dependencies.admin_auth import require_admin
    from api.dependencies.finance_import import build_finance_import_application
    from api.routes.finance_import import router
    from infrastructure.mysql.finance_import_owning_domain_composite import MySqlFinanceImportOwningDomainComposite
    from infrastructure.mysql.mysql_adapter import get_connection
    from shared_kernel.identities import CorrelationId
    from subsystems.access.authentication_session import AdminPrincipal

    root = Path(__file__).resolve().parents[1]
    npm = shutil.which("npm")
    assert npm and (root / "ui_react/node_modules/vitest/package.json").is_file(), (
        "This parity proof requires existing React test dependencies; it never installs packages."
    )
    assert DATABASE and DATABASE.startswith("lu_test_"), "Select an isolated lu_test_* database."

    def formal_counts():
        # A fresh connection observes other API connections' commits, not an old read snapshot.
        connection = get_connection()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT DATABASE() AS name")
                assert cursor.fetchone()["name"] == DATABASE
            return _formal_output_counts(connection)
        finally:
            connection.close()

    before = formal_counts()
    token = uuid4().hex
    workbook = tmp_path / f"taishin-preview-{token}.xlsx"
    amount = 1_000 + int(token[:8], 16) % 1_000_000
    pd.DataFrame([
        ["合成銀行流水驗證"],
        ["序號", "交易日期", "交易時間", "帳務日期", "摘要", "支出金額", "存入金額", "帳戶餘額", "備註"],
        [token, "2026/08/10", "09:08:07", "2026/08/10", "轉帳", amount, "", amount + 9000, f"NO-MATCH-{token}"],
    ]).to_excel(workbook, sheet_name="交易明細", index=False, header=False)
    workbook_bytes = workbook.read_bytes()
    workbook_digest = hashlib.sha256(workbook_bytes).hexdigest()
    app = FastAPI()
    app.include_router(router)
    # Authentication is a test input; ingestion, repositories and Preview are not replaced.
    app.dependency_overrides[require_admin] = lambda: AdminPrincipal(1, "finance-preview-test", "Test", "system_admin")
    with TestClient(app) as client:
        ingested = client.post(
            "/api/v1/finance-import/workbooks/ingest",
            headers={"Idempotency-Key": f"fi-preview:{token}", "X-Correlation-ID": f"fi-preview:{token}"},
            files={"workbook": (workbook.name, workbook_bytes, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
        assert ingested.status_code == 200
        intake = ingested.json()["data"]
        assert intake["source_content_digest"] == workbook_digest
        assert intake["source_row_count"] == intake["canonical_created_count"] == 1
        assert formal_counts() == before
        response = client.post(
            "/api/v1/finance-import/batches/preview",
            headers={"X-Correlation-ID": f"fi-preview:{token}"},
            json={"batch_identity": intake["batch_identity"]},
        )
        assert response.status_code == 200
    assert formal_counts() == before

    connection = get_connection()
    try:
        plan = build_finance_import_application(connection, MySqlFinanceImportOwningDomainComposite(connection)).preview_batch(
            intake["batch_identity"], CorrelationId(f"fi-preview:{token}"),
        )
        # Independent domain fields: do not reuse the route's _plan_payload implementation.
        expected = {
            "batch_identity": plan.batch_identity, "batch_version": plan.batch_version,
            "source_content_digest": plan.source_content_digest,
            "counts": asdict(plan.counts), "blocking_codes": list(plan.blocking_codes),
            "apply_allowed": plan.apply_allowed, "preview_fingerprint": plan.fingerprint.value,
        }
    finally:
        connection.close()
    assert {key: response.json()["data"][key] for key in expected} == expected
    assert expected["source_content_digest"] == workbook_digest
    assert formal_counts() == before

    exchange_path = tmp_path / "preview-exchange.json"
    exchange_path.write_text(json.dumps({
        "workbook_path": str(workbook), "workbook_sha256": workbook_digest,
        "expected_manifest_sha256": hashlib.sha256(
            (root / "validation/expected/FI-UI-PREVIEW-PARITY-003.json").read_bytes()
        ).hexdigest(),
        "ingestion_response": ingested.json(), "preview_response": response.json(), "expected": expected,
    }, ensure_ascii=False), encoding="utf-8")
    report_path = tmp_path / "react-parity-result.json"
    # The frontend needs only the synthetic exchange, not the parent's DB credentials.
    ui_environment = {
        "PATH": os.environ["PATH"], "HOME": str(tmp_path), "CI": "true",
        "TMPDIR": str(tmp_path), "TEMP": str(tmp_path), "TMP": str(tmp_path),
        "FI_PREVIEW_EXCHANGE": str(exchange_path),
    }
    if "SYSTEMROOT" in os.environ:
        ui_environment["SYSTEMROOT"] = os.environ["SYSTEMROOT"]
    result = subprocess.run(
        [npm, "--prefix", str(root / "ui_react"), "test", "--", "src/tests/finance_query_page.test.tsx",
         "-t", "same-run MySQL Preview", "--reporter=json", "--outputFile", str(report_path)],
        cwd=root, env=ui_environment, capture_output=True, text=True, timeout=120, check=False,
    )
    assert result.returncode == 0, result.stdout[-4000:] + result.stderr[-4000:]
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["numPassedTests"] == 1 and report["numFailedTests"] == 0
    assert formal_counts() == before
