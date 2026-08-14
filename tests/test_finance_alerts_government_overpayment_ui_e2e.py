"""
File: test_finance_alerts_government_overpayment_ui_e2e.py
Description: 驗證異常警示UI與政府補助溢付Preview／Apply流程。
"""

from __future__ import annotations

from argparse import Namespace
from datetime import date
import importlib
import os

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from scripts.bootstrap_disposable_mysql_schema import bootstrap
from tests.test_government_subsidy_overpayment_disposable_mysql_e2e import _seed_overpayment
from tests.test_government_subsidy_durable_mysql_e2e import _seed_receiptable_batch


DATABASE = os.getenv("LABOR_UNION_TEST_MYSQL_DATABASE")
pytestmark = pytest.mark.skipif(not DATABASE, reason="requires an explicitly configured disposable lu_test_* MySQL database")


@pytest.fixture(autouse=True)
def _use_disposable_database(monkeypatch):
    from infrastructure.mysql import mysql_adapter

    monkeypatch.setattr(mysql_adapter, "DB_CONFIG", {
        "host": os.environ["LABOR_UNION_TEST_MYSQL_HOST"],
        "port": int(os.environ["LABOR_UNION_TEST_MYSQL_PORT"]),
        "user": os.environ["LABOR_UNION_TEST_MYSQL_USER"],
        "password": os.environ["LABOR_UNION_TEST_MYSQL_PASSWORD"],
        "database": DATABASE,
        "charset": "utf8mb4",
    })


def test_anomaly_selection_drives_government_return_preview_then_apply(monkeypatch):
    bootstrap(_arguments())
    batch_id, _item_id, source_row_id = _seed_receiptable_batch()
    identity = _seed_overpayment(batch_id, source_row_id, "ui", 500)
    _seed_payer_account()
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("ENABLE_ADMIN_AUTH", "false")
    monkeypatch.setenv("LEGACY_SHARED_KEY", "finance-alert-ui-key")

    from api.routes.government_subsidy import router
    from api.schemas.anomaly_recovery import RecoveryActionView
    import api.dependencies.admin_auth as admin_auth
    from ui.api_clients.government_subsidy_api_client import GovernmentSubsidyApiClient

    panel = importlib.import_module("ui.pages.06_finance_alerts")
    display = _Display()
    app = FastAPI()
    app.include_router(router)
    with TestClient(app) as http_client:
        monkeypatch.setattr(admin_auth, "has_required_capability", lambda *_args: True)
        monkeypatch.setattr(panel, "st", display)
        session = _Session(http_client)
        monkeypatch.setattr(panel, "GovernmentSubsidyApiClient", lambda **_kwargs: GovernmentSubsidyApiClient(base_url="http://finance-alert.test", headers={"X-Legacy-Shared-Key": "finance-alert-ui-key"}, session=session))
        panel._select_recovery(_summary(), RecoveryActionView(
            action_key="dispose_government_subsidy_overpayment",
            label="處置政府補助溢撥",
            owning_domain="government_subsidy",
            preview_operation="PreviewGovernmentSubsidyOverpaymentDisposition",
            apply_operation="ApplyGovernmentSubsidyOverpaymentDisposition",
            requires_preview=True,
            form_schema_key="government_subsidy.overpayment.disposition.v1",
            source_binding_keys=["overpayment_identity", "overpayment_version"],
            source_bindings={"overpayment_identity": identity, "overpayment_version": 1},
            required_operator_inputs=["reason", "evidence"],
            required_capability="government_subsidy.overpayment.disposition",
            completion_predicate="government_overpayment_disposition_completed",
            action_contract_version=1,
        ))
        display.buttons[f"government_disposition_{identity}_preview_button"] = True
        panel._render_selected_finance_recovery()
        display.buttons[f"government_disposition_{identity}_preview_button"] = False
        display.buttons[f"government_disposition_{identity}_apply"] = True
        panel._render_selected_finance_recovery()

    assert display.errors == [], session.last_response.json()
    assert display.rerun_called is True
    _assert_return_payable(identity)


def _arguments() -> Namespace:
    return Namespace(host=os.environ["LABOR_UNION_TEST_MYSQL_HOST"], port=int(os.environ["LABOR_UNION_TEST_MYSQL_PORT"]), user=os.environ["LABOR_UNION_TEST_MYSQL_USER"], password=os.environ["LABOR_UNION_TEST_MYSQL_PASSWORD"], database=DATABASE, confirm_database=DATABASE)


def _seed_payer_account() -> None:
    from infrastructure.mysql.mysql_adapter import get_connection

    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("INSERT INTO government_payer_receiving_accounts (payer_identity,bank_code,account_number,account_name,effective_from,reason,evidence_reference,created_by) VALUES ('hccg','004','GOV-UI-ACCOUNT','新竹市政府','2026-01-01','fixture','notice','test')")
        connection.commit()
    finally:
        connection.close()


def _assert_return_payable(identity: str) -> None:
    from infrastructure.mysql.mysql_adapter import get_connection

    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT status,remaining_amount_ntd,projection_version FROM government_subsidy_overpayments WHERE overpayment_identity=%s", (identity,))
            assert cursor.fetchone() == {"status": "return_payable", "remaining_amount_ntd": 500, "projection_version": 2}
            cursor.execute("SELECT COUNT(*) count FROM government_overpayment_return_payables WHERE overpayment_identity=%s", (identity,))
            assert cursor.fetchone() == {"count": 1}
    finally:
        connection.close()


def _summary():
    from api.schemas.anomaly_registry import AnomalySummaryView

    return AnomalySummaryView(fingerprint="a" * 64, definition_code="GOVSUB-006", source_domain="government_subsidy", source_identity="government-overpayment-ui", source_version=1, workflow_status="open", workflow_version=1, severity="warning", predicate_active=True)


def test_hcm_duplicate_application_has_operator_facing_warning_label():
    from api.schemas.anomaly_registry import AnomalySummaryView

    panel = importlib.import_module("ui.pages.06_finance_alerts")
    summary = AnomalySummaryView(
        fingerprint="b" * 64,
        definition_code="IMPORT-004",
        source_domain="case_import",
        source_identity="hcm-review:test",
        source_version=1,
        workflow_status="open",
        workflow_version=1,
        severity="warning",
        predicate_active=True,
        display_snapshot={"issue_codes": ["hcm_identity:hcm_duplicate_application"]},
    )

    assert panel._display_alert_label(summary) == "疑似重複申請，請公會人員確認"


class _Session:
    def __init__(self, client): self._client = client; self.last_response = None

    def request(self, method, url, **kwargs):
        kwargs.pop("timeout", None)
        path = url.replace("http://finance-alert.test", "", 1)
        self.last_response = self._client.request(method, path, **kwargs)
        return _Response(self.last_response)


class _Response:
    def __init__(self, response): self._response = response; self.ok = response.is_success; self.status_code = response.status_code

    def json(self): return self._response.json()


class _Display:
    def __init__(self): self.session_state = {}; self.buttons = {}; self.errors = []; self.rerun_called = False

    def button(self, _label, *, key, **_kwargs): return self.buttons.get(key, False)
    def radio(self, *_args, **_kwargs): return "return"
    def text_input(self, label, **_kwargs): return "notice" if "證據" in label else ""
    def text_area(self, *_args, **_kwargs): return "return approved"
    def date_input(self, *_args, **_kwargs): return date(2026, 8, 15)
    def markdown(self, *_args, **_kwargs): pass
    def caption(self, *_args, **_kwargs): pass
    def divider(self): pass
    def info(self, *_args, **_kwargs): pass
    def success(self, *_args, **_kwargs): pass
    def error(self, message): self.errors.append(str(message))
    def rerun(self): self.rerun_called = True
