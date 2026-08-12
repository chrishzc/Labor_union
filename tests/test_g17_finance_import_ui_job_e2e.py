"""G17 proof that the Finance Import panel never reports a job as complete early."""

from __future__ import annotations

from argparse import Namespace
from contextlib import nullcontext
import os

import pandas as pd
import pytest
import requests
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


def test_g17_panel_shows_pending_until_the_independent_worker_succeeds(tmp_path, monkeypatch):
    bootstrap(_arguments())
    _configure_test_auth(monkeypatch)
    display, panel, client, session = _panel_and_client(monkeypatch)
    preview = _ingest_and_preview(client, panel, display, tmp_path)

    panel._apply_batch(client, preview, "G17 durable UI flow")
    command = display.session_state[panel._BATCH_APPLY_STATE_KEY]
    assert display.success_messages == []
    assert command["job_id"] is None

    panel._retry_batch_apply(client, command)
    assert command["job_id"]
    assert session.apply_idempotency_keys == [
        command["idempotency_key"], command["idempotency_key"]
    ]

    panel._refresh_batch_apply_status(client, command)
    assert command["terminal"] is False
    assert display.success_messages == []
    assert _run_durable_worker() is True

    raw_status = client._session.request(
        "GET",
        f"http://g17.test/api/v1/jobs/{command['job_id']}",
        headers={"X-Legacy-Shared-Key": "g17-internal-key"},
    )
    assert raw_status.ok, raw_status.json()
    completed_status = client.get_job_status(command["job_id"])
    assert completed_status.status == "succeeded", completed_status.model_dump()
    panel._refresh_batch_apply_status(client, command)
    assert command["terminal"] is True
    assert display.success_messages == ["正式入帳已完成。"]


def _configure_test_auth(monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("ENABLE_ADMIN_AUTH", "false")
    monkeypatch.setenv("LEGACY_SHARED_KEY", "g17-internal-key")


def _panel_and_client(monkeypatch):
    from api.routes.finance_import import router as finance_import_router
    from api.routes.jobs import router as jobs_router
    from ui.api_clients.finance_import_api_client import FinanceImportApiClient
    from ui.pages.finance_import import panel

    display = _PanelDisplay()
    monkeypatch.setattr(panel, "st", display)
    application = FastAPI()
    application.include_router(finance_import_router)
    application.include_router(jobs_router)
    http_client = TestClient(application)
    session = _TestClientSession(http_client, lose_first_apply_response=True)
    client = FinanceImportApiClient(
        base_url="http://g17.test",
        headers={"X-Legacy-Shared-Key": "g17-internal-key"},
        session=session,
    )
    return display, panel, client, session


def _ingest_and_preview(client, panel, display, tmp_path):
    workbook = tmp_path / "g17-taishin.xlsx"
    pd.DataFrame(
        [["說明"], ["序號", "交易日期", "交易時間", "帳務日期", "摘要", "支出金額", "存入金額", "帳戶餘額", "備註"], ["0001", "2026/08/04", "09:08:07", "2026/08/04", "轉帳", "300", "", "9000", "待人工確認"]]
    ).to_excel(workbook, sheet_name="交易明細", index=False, header=False)
    receipt = client.ingest_workbook(
        workbook.name, workbook.read_bytes(), idempotency_key="g17-ingest", correlation_id="g17-ingest"
    )
    panel._preview_batch(client, receipt.batch_identity)
    assert display.errors == []
    return display.session_state["finance_import_batch_preview"]


def _run_durable_worker():
    from infrastructure.mysql.background_job_repository import BackgroundJobRepository
    from infrastructure.mysql.mysql_adapter import get_connection
    from subsystems.jobs.durable_job_worker import DurableJobWorker, default_job_handlers

    connection = get_connection()
    try:
        worker = DurableJobWorker(BackgroundJobRepository(connection), default_job_handlers(), "g17-worker", retry_delay_seconds=0)
        return worker.recover_and_run_once()
    finally:
        connection.close()


class _TestClientSession:
    def __init__(self, client, *, lose_first_apply_response=False):
        self._client = client
        self._lose_first_apply_response = lose_first_apply_response
        self.apply_idempotency_keys = []

    def request(self, method, url, **kwargs):
        kwargs.pop("timeout", None)
        path = url.replace("http://g17.test", "", 1)
        response = _ResponseAdapter(self._client.request(method, path, **kwargs))
        if method == "POST" and path.endswith("/batches/apply"):
            self.apply_idempotency_keys.append(kwargs["headers"]["Idempotency-Key"])
            if self._lose_first_apply_response:
                self._lose_first_apply_response = False
                raise requests.ConnectionError("simulated response loss")
        return response


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
        self.info_messages = []
        self.success_messages = []

    def error(self, message):
        self.errors.append(message)

    def spinner(self, _message):
        return nullcontext()

    def info(self, message):
        self.info_messages.append(message)

    def success(self, message):
        self.success_messages.append(message)

    def warning(self, message):
        self.errors.append(message)

    def json(self, _payload):
        return None
