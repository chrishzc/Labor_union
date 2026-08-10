"""G14 real HTTP and Streamlit-panel flow on isolated MySQL."""

from __future__ import annotations

from argparse import Namespace
from datetime import date
import os

import pymysql
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from scripts.bootstrap_disposable_mysql_schema import bootstrap


DATABASE = os.getenv("LABOR_UNION_TEST_MYSQL_DATABASE")
pytestmark = pytest.mark.skipif(
    not DATABASE,
    reason="requires an explicitly configured disposable lu_test_* MySQL database",
)

CASE_NO = "G14-UI-CASE"


def _arguments() -> Namespace:
    return Namespace(
        host=os.environ["LABOR_UNION_TEST_MYSQL_HOST"],
        port=int(os.environ["LABOR_UNION_TEST_MYSQL_PORT"]),
        user=os.environ["LABOR_UNION_TEST_MYSQL_USER"],
        password=os.environ["LABOR_UNION_TEST_MYSQL_PASSWORD"],
        database=DATABASE,
        confirm_database=DATABASE,
    )


def _connection() -> pymysql.Connection:
    return pymysql.connect(
        host=os.environ["LABOR_UNION_TEST_MYSQL_HOST"],
        port=int(os.environ["LABOR_UNION_TEST_MYSQL_PORT"]),
        user=os.environ["LABOR_UNION_TEST_MYSQL_USER"],
        password=os.environ["LABOR_UNION_TEST_MYSQL_PASSWORD"],
        database=DATABASE,
        charset="utf8mb4",
        autocommit=False,
        cursorclass=pymysql.cursors.DictCursor,
    )


def test_g14_panel_uses_real_http_preview_and_apply(monkeypatch):
    bootstrap(_arguments())
    _seed_settled_deposit()
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("ENABLE_ADMIN_AUTH", "false")
    monkeypatch.setenv("INTERNAL_API_KEY", "g14-ui-key")

    from api.routes.client_deposit_reversal import router
    from ui.api_clients.client_deposit_reversal_api_client import (
        ClientDepositReversalApiClient,
    )
    from ui.pages.order import client_deposit_reversal_panel as panel

    app = FastAPI()
    app.include_router(router)
    display = _PanelDisplay()
    monkeypatch.setattr(panel, "st", display)
    with TestClient(app) as http_client:
        client = ClientDepositReversalApiClient(
            base_url="http://g14-ui.test",
            headers={"X-Internal-API-Key": "g14-ui-key"},
            session=_TestClientSession(http_client),
        )
        monkeypatch.setattr(panel, "_client", lambda: client)
        display.button_values[_preview_button_key()] = True
        panel.render_client_deposit_reversal_panel(CASE_NO)
        display.button_values[_preview_button_key()] = False
        display.button_values[_apply_button_key()] = True
        panel.render_client_deposit_reversal_panel(CASE_NO)

    assert display.errors == []
    assert display.rerun_called is True
    assert f"deposit_reversal_preview:{CASE_NO}" not in display.session_state
    _assert_reversal_persisted()


def _preview_button_key() -> str:
    return f"deposit_reversal_preview_{CASE_NO}"


def _apply_button_key() -> str:
    return f"deposit_reversal_apply_{CASE_NO}"


def _seed_settled_deposit() -> None:
    connection = _connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("INSERT INTO clients(case_no,name) VALUES (%s,'G14 UI Client')", (CASE_NO,))
            client_id = int(cursor.lastrowid)
            cursor.execute(
                "INSERT INTO orders(case_no,client_id,status) VALUES (%s,%s,'訂單成立')",
                (CASE_NO, client_id),
            )
            cursor.execute(
                "INSERT INTO client_finance_accounts(case_no,aggregate_version) VALUES (%s,1)",
                (CASE_NO,),
            )
            cursor.execute(
                "INSERT INTO client_obligation_events "
                "(obligation_identity,case_no,obligation_type,direction,event_type,"
                "before_amount_ntd,after_amount_ntd,before_due_date,after_due_date,"
                "source_event_identity,source_obligation_identity,expected_account_version,"
                "idempotency_key,actor,reason) VALUES "
                "(%s,%s,'deposit','receivable_from_client','established',0,2000,NULL,"
                "'2026-08-01','g14-ui-root',NULL,0,'g14-ui-root','test','fixture')",
                (f"{CASE_NO}:deposit", CASE_NO),
            )
            event_id = int(cursor.lastrowid)
            cursor.execute(
                "INSERT INTO client_obligations "
                "(obligation_identity,case_no,obligation_type,direction,source_obligation_identity,"
                "amount_due_ntd,due_date,status,current_event_id,projection_version) VALUES "
                "(%s,%s,'deposit','receivable_from_client',NULL,0,'2026-08-01','settled',%s,1)",
                (f"{CASE_NO}:deposit", CASE_NO, event_id),
            )
            cursor.execute(
                "INSERT INTO client_ledger_entries "
                "(case_no,finance_import_row_id,entry_type,amount_ntd,occurred_on,"
                "reconciliation_reference,reversal_of_entry_id,idempotency_key,actor,reason) "
                "VALUES (%s,NULL,'receipt',2000,'2026-08-01',%s,NULL,'g14-ui-receipt','test','fixture')",
                (CASE_NO, "a" * 64),
            )
            cursor.execute(
                "INSERT INTO client_ledger_obligation_allocations "
                "(ledger_entry_id,obligation_identity,amount_ntd,allocation_ordinal) "
                "VALUES (1,%s,2000,1)",
                (f"{CASE_NO}:deposit",),
            )
            cursor.execute(
                "INSERT INTO client_deposit_settlement_projection "
                "(case_no,deposit_obligation_identity,settlement_state,contracted_amount_ntd,"
                "allocated_net_amount_ntd,settlement_identity,source_fingerprint,"
                "projection_version,latest_ledger_entry_id) VALUES "
                "(%s,%s,'settled',2000,2000,%s,%s,1,1)",
                (CASE_NO, f"{CASE_NO}:deposit", "a" * 64, "b" * 64),
            )
        connection.commit()
    finally:
        connection.close()


def _assert_reversal_persisted() -> None:
    connection = _connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT entry_type,amount_ntd,reversal_of_entry_id FROM client_ledger_entries "
                "WHERE case_no=%s ORDER BY id",
                (CASE_NO,),
            )
            assert cursor.fetchall() == [
                {"entry_type": "receipt", "amount_ntd": 2000, "reversal_of_entry_id": None},
                {"entry_type": "reversal", "amount_ntd": 2000, "reversal_of_entry_id": 1},
            ]
            cursor.execute("SELECT COUNT(*) AS count FROM client_payments")
            assert cursor.fetchone() == {"count": 0}
    finally:
        connection.close()


class _TestClientSession:
    def __init__(self, client: TestClient) -> None:
        self._client = client

    def post(self, url, **kwargs):
        path = url.replace("http://g14-ui.test", "", 1)
        kwargs.pop("timeout", None)
        return _ResponseAdapter(self._client.post(path, **kwargs))


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
        self.button_values = {}
        self.errors = []
        self.rerun_called = False

    def markdown(self, *_args, **_kwargs) -> None:
        pass

    def caption(self, *_args, **_kwargs) -> None:
        pass

    def number_input(self, *_args, **_kwargs) -> int:
        return 1

    def date_input(self, *_args, **_kwargs) -> date:
        return date(2026, 8, 4)

    def button(self, _label, *, key) -> bool:
        return self.button_values.get(key, False)

    def json(self, *_args, **_kwargs) -> None:
        pass

    def text_input(self, *_args, **_kwargs) -> str:
        return "bank return confirmed"

    def success(self, *_args, **_kwargs) -> None:
        pass

    def error(self, message) -> None:
        self.errors.append(message)

    def rerun(self) -> None:
        self.rerun_called = True
