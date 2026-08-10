"""G09 proof that the Finance Import UI client only projects typed API output."""

from __future__ import annotations

from argparse import Namespace
from contextlib import nullcontext
import os

import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from scripts.bootstrap_disposable_mysql_schema import bootstrap


DATABASE = os.getenv("LABOR_UNION_TEST_MYSQL_DATABASE")
pytestmark = pytest.mark.skipif(
    not DATABASE,
    reason="requires an explicitly configured disposable lu_test_* MySQL database",
)


def _arguments() -> Namespace:
    return Namespace(
        host=os.environ["LABOR_UNION_TEST_MYSQL_HOST"],
        port=int(os.environ["LABOR_UNION_TEST_MYSQL_PORT"]),
        user=os.environ["LABOR_UNION_TEST_MYSQL_USER"],
        password=os.environ["LABOR_UNION_TEST_MYSQL_PASSWORD"],
        database=DATABASE,
        confirm_database=DATABASE,
    )


def test_g09_ui_client_and_direct_typed_preview_have_the_same_result(tmp_path, monkeypatch):
    bootstrap(_arguments())
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("ENABLE_ADMIN_AUTH", "false")
    monkeypatch.setenv("INTERNAL_API_KEY", "g09-internal-key")
    workbook = _write_real_taishin_workbook(tmp_path)

    ui_preview = _ui_preview(workbook, monkeypatch)
    direct_plan = _direct_typed_preview(ui_preview.batch_identity)

    assert ui_preview.batch_version == direct_plan.batch_version
    assert ui_preview.preview_fingerprint == direct_plan.fingerprint.value
    assert ui_preview.apply_allowed == direct_plan.apply_allowed
    assert ui_preview.blocking_codes == list(direct_plan.blocking_codes)
    assert ui_preview.counts.model_dump() == _counts_payload(direct_plan)
    assert [row.row_identity for row in ui_preview.rows] == [
        row.row_identity for row in direct_plan.rows
    ]


def _write_real_taishin_workbook(tmp_path):
    workbook = tmp_path / "g09-taishin.xlsx"
    pd.DataFrame(
        [
            ["說明"],
            ["序號", "交易日期", "交易時間", "帳務日期", "摘要", "支出金額", "存入金額", "帳戶餘額", "備註"],
            ["0001", "2026/08/04", "09:08:07", "2026/08/04", "轉帳", "300", "", "9000", "待人工確認"],
        ]
    ).to_excel(workbook, sheet_name="交易明細", index=False, header=False)
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
            base_url="http://g09.test",
            headers={"X-Internal-API-Key": "g09-internal-key"},
            session=_TestClientSession(http_client),
        )
        receipt = client.ingest_workbook(
            workbook.name,
            workbook.read_bytes(),
            idempotency_key="g09-ingest",
            correlation_id="g09-ingest",
        )
        panel._preview_batch(client, receipt.batch_identity)
    assert display.errors == []
    return display.session_state["finance_import_batch_preview"]


def _direct_typed_preview(batch_identity):
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
        return application.preview_batch(batch_identity, CorrelationId("g09-direct-preview"))
    finally:
        connection.close()


def _counts_payload(plan):
    return {
        "source_rows": plan.counts.source_rows,
        "canonical_created": plan.counts.canonical_created,
        "duplicate_occurrences": plan.counts.duplicate_occurrences,
        "ready_dispatch": plan.counts.ready_dispatch,
        "existing": plan.counts.existing,
        "manual_review": plan.counts.manual_review,
        "business_pending": plan.counts.business_pending,
        "blocked": plan.counts.blocked,
    }


class _TestClientSession:
    def __init__(self, client):
        self._client = client

    def request(self, method, url, **kwargs):
        path = url.replace("http://g09.test", "", 1)
        kwargs.pop("timeout", None)
        return _ResponseAdapter(self._client.request(method, path, **kwargs))


class _ResponseAdapter:
    def __init__(self, response):
        self._response = response
        self.ok = response.is_success
        self.status_code = response.status_code

    def json(self):
        return self._response.json()


class _PanelDisplay:
    def __init__(self):
        self.session_state = {}
        self.errors = []

    def error(self, message):
        self.errors.append(message)

    def spinner(self, _message):
        return nullcontext()
