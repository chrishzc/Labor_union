"""Append-only API/client/panel parity proof for a Finance Import preview."""

from __future__ import annotations

from contextlib import nullcontext
import os
from uuid import uuid4

import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


DATABASE = os.getenv("LABOR_UNION_TEST_MYSQL_DATABASE")
pytestmark = pytest.mark.skipif(
    not DATABASE or os.getenv("DB_DATABASE") != DATABASE,
    reason="requires an explicitly configured disposable lu_test_* MySQL database",
)


def test_typed_ui_preview_matches_authoritative_preview_without_formal_posting(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("ENABLE_ADMIN_AUTH", "false")
    monkeypatch.setenv("INTERNAL_API_KEY", "lu-test-finance-import-ui")
    workbook = _write_workbook(tmp_path, uuid4().hex)
    before = _formal_output_counts()
    ui_preview = _ui_preview(workbook, monkeypatch)
    direct_preview = _direct_preview(ui_preview.batch_identity)

    assert ui_preview.batch_version == direct_preview.batch_version
    assert ui_preview.preview_fingerprint == direct_preview.fingerprint.value
    assert ui_preview.apply_allowed == direct_preview.apply_allowed
    assert ui_preview.blocking_codes == list(direct_preview.blocking_codes)
    assert ui_preview.counts.model_dump() == _counts_payload(direct_preview)
    assert _formal_output_counts() == before


def _write_workbook(tmp_path, token: str):
    amount = 1_000 + int(token[:8], 16) % 1_000_000
    workbook = tmp_path / f"lu-test-finance-{token}.xlsx"
    rows = [
        ["說明"],
        ["序號", "交易日期", "交易時間", "帳務日期", "摘要", "支出金額", "存入金額", "帳戶餘額", "備註"],
        ["0001", "2026/08/10", "09:08:07", "2026/08/10", "轉帳", str(amount), "", "9000000", "待人工確認"],
    ]
    pd.DataFrame(rows).to_excel(workbook, sheet_name="交易明細", index=False, header=False)
    return workbook


def _ui_preview(workbook, monkeypatch):
    from api.routes.finance_import import router
    from ui.api_clients.finance_import_api_client import FinanceImportApiClient
    from ui.pages.finance_import import panel

    application = FastAPI()
    application.include_router(router)
    display = _PanelDisplay()
    monkeypatch.setattr(panel, "st", display)
    with TestClient(application) as http_client:
        client = FinanceImportApiClient(
            base_url="http://lu-test-finance-import-ui",
            headers={"X-Internal-API-Key": "lu-test-finance-import-ui"},
            session=_TestClientSession(http_client),
        )
        receipt = client.ingest_workbook(
            workbook.name,
            workbook.read_bytes(),
            idempotency_key=f"ingest:{workbook.stem}",
            correlation_id=f"ingest:{workbook.stem}",
        )
        panel._preview_batch(client, receipt.batch_identity)
    assert display.errors == []
    return display.session_state["finance_import_batch_preview"]


def _direct_preview(batch_identity: str):
    from api.dependencies.finance_import import build_finance_import_application
    from infrastructure.mysql.finance_import_owning_domain_composite import MySqlFinanceImportOwningDomainComposite
    from infrastructure.mysql.mysql_adapter import get_connection
    from shared_kernel.identities import CorrelationId

    connection = get_connection()
    try:
        application = build_finance_import_application(
            connection,
            MySqlFinanceImportOwningDomainComposite(connection),
        )
        return application.preview_batch(batch_identity, CorrelationId("lu-test-finance-import-direct-preview"))
    finally:
        connection.close()


def _counts_payload(plan):
    counts = plan.counts
    return {
        "source_rows": counts.source_rows,
        "canonical_created": counts.canonical_created,
        "duplicate_occurrences": counts.duplicate_occurrences,
        "ready_dispatch": counts.ready_dispatch,
        "existing": counts.existing,
        "manual_review": counts.manual_review,
        "business_pending": counts.business_pending,
        "blocked": counts.blocked,
    }


def _formal_output_counts() -> tuple[int, int, int]:
    from infrastructure.mysql.mysql_adapter import get_connection

    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            counts = []
            for table in ("client_ledger_entries", "staff_payout_events", "government_subsidy_transactions"):
                cursor.execute(f"SELECT COUNT(*) AS count FROM {table}")
                counts.append(int(cursor.fetchone()["count"]))
        return tuple(counts)
    finally:
        connection.close()


class _TestClientSession:
    def __init__(self, client) -> None:
        self._client = client

    def request(self, method, url, **kwargs):
        kwargs.pop("timeout", None)
        response = self._client.request(method, url.replace("http://lu-test-finance-import-ui", "", 1), **kwargs)
        return _ResponseAdapter(response)


class _ResponseAdapter:
    def __init__(self, response) -> None:
        self._response = response
        self.ok = response.is_success
        self.status_code = response.status_code

    def json(self):
        return self._response.json()


class _PanelDisplay:
    def __init__(self) -> None:
        self.session_state = {}
        self.errors = []

    def error(self, message) -> None:
        self.errors.append(message)

    def spinner(self, _message):
        return nullcontext()
