"""G03/G04 real MySQL proof for canonical Orders cancellation boundaries."""

from __future__ import annotations

from argparse import Namespace
from datetime import datetime
import os

import pytest

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


def test_g03_mid_service_multi_caregiver_cancellation_updates_each_domain_once():
    bootstrap(_arguments())
    _seed_in_service_case(settled_client_and_unpaid_staff=True)
    workflow, connection = _workflow()

    from domains.orders.cancellation import ConfirmedServiceDay
    from shared_kernel.identities import (
        ActorContext,
        CorrelationId,
        ExpectedVersion,
        IdempotencyKey,
    )
    from subsystems.orders.cancellation_workflow import OrderCancellationApplyRequest

    confirmed_days = (
        ConfirmedServiceDay(_date(1), 1),
        ConfirmedServiceDay(_date(2), 2),
    )
    preview = workflow.preview("G03-CASE", confirmed_days)
    request = OrderCancellationApplyRequest(
        "G03-CASE",
        confirmed_days,
        ExpectedVersion(preview.order_version),
        ExpectedVersion(preview.scheduling_version),
        ExpectedVersion(preview.client_finance_version),
        ExpectedVersion(preview.payroll_version),
        preview.fingerprint,
        IdempotencyKey("g03-mid-service-cancellation"),
        ActorContext("g03-test"),
        "client ended service after confirmed days",
        CorrelationId("g03-mid-service-cancellation"),
    )

    try:
        receipt = workflow.apply(request)
        assert workflow.apply(request) == receipt
        assert receipt.official_service_day_count == 2
        assert receipt.official_service_hours == 16
        assert receipt.cancelled_assignment_ids == (1, 2)
    finally:
        connection.close()
    _assert_cross_domain_result()
    _assert_no_cross_domain_auto_netting()


def test_g04_full_service_cancellation_is_blocked_without_writes():
    bootstrap(_arguments())
    _seed_in_service_case(completed_with_payroll=True)
    workflow, connection = _workflow()

    from domains.orders.cancellation import (
        CancellationCandidateError,
        ConfirmedServiceDay,
    )

    before = _write_counts()
    payroll_before = _payroll_snapshot()
    try:
        with pytest.raises(CancellationCandidateError) as error:
            workflow.preview(
                "G03-CASE",
                (
                    ConfirmedServiceDay(_date(1), 1),
                    ConfirmedServiceDay(_date(2), 2),
                    ConfirmedServiceDay(_date(3), 1),
                    ConfirmedServiceDay(_date(4), 2),
                ),
            )
    finally:
        connection.close()
    assert error.value.blocker.value == "order_cancellation_after_full_service"
    assert _write_counts() == before
    assert _payroll_snapshot() == payroll_before


def test_g03_panel_uses_real_http_preview_and_apply(monkeypatch):
    bootstrap(_arguments())
    _seed_in_service_case(settled_client_and_unpaid_staff=True)
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("ENABLE_ADMIN_AUTH", "false")
    monkeypatch.setenv("INTERNAL_API_KEY", "g03-ui-key")

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from api.routes.order_cancellation import router
    from ui.api_clients.order_cancellation_api_client import (
        OrderCancellationApiClient,
    )
    from ui.pages.order import cancellation_panel

    application = FastAPI()
    application.include_router(router)
    display = _CancellationPanelDisplay()
    monkeypatch.setattr(cancellation_panel, "st", display)
    with TestClient(application) as http_client:
        client = OrderCancellationApiClient(
            base_url="http://g03-ui.test",
            headers={"X-Internal-API-Key": "g03-ui-key"},
            session=_CancellationTestClientSession(http_client),
        )
        display.button_values["cancellation_preview_btn_G03-CASE"] = True
        cancellation_panel.render_order_cancellation_panel("G03-CASE", client)
        display.button_values["cancellation_preview_btn_G03-CASE"] = False
        display.button_values["cancellation_apply_G03-CASE"] = True
        cancellation_panel.render_order_cancellation_panel("G03-CASE", client)

    assert display.errors == []
    assert display.rerun_called is True
    _assert_cross_domain_result()
    _assert_no_cross_domain_auto_netting()


class _CancellationTestClientSession:
    def __init__(self, client) -> None:
        self._client = client

    def request(self, method, url, **kwargs):
        path = url.replace("http://g03-ui.test", "", 1)
        kwargs.pop("timeout", None)
        return _CancellationResponseAdapter(
            self._client.request(method, path, **kwargs)
        )


class _CancellationResponseAdapter:
    def __init__(self, response) -> None:
        self._response = response
        self.ok = response.is_success
        self.status_code = response.status_code

    def json(self):
        return self._response.json()


class _CancellationPanelDisplay:
    def __init__(self) -> None:
        self.session_state = {}
        self.button_values = {}
        self.errors = []
        self.rerun_called = False

    def markdown(self, *_args, **_kwargs) -> None:
        pass

    def caption(self, *_args, **_kwargs) -> None:
        pass

    def info(self, *_args, **_kwargs) -> None:
        pass

    def checkbox(self, _label, *, key, **_kwargs) -> bool:
        return key in {
            "cancellation_day_G03-CASE_2026-08-01_1",
            "cancellation_day_G03-CASE_2026-08-02_2",
        }

    def button(self, _label, *, key, **_kwargs) -> bool:
        return self.button_values.get(key, False)

    def text_input(self, *_args, **_kwargs) -> str:
        return "client ended service after confirmed days"

    def error(self, message) -> None:
        self.errors.append(message)

    def success(self, *_args, **_kwargs) -> None:
        pass

    def rerun(self) -> None:
        self.rerun_called = True


def test_terms_workflow_recovery_applies_one_canonical_cross_domain_change():
    bootstrap(_arguments())
    _seed_in_service_case(settled_client_and_unpaid_staff=True)
    workflow, connection = _terms_workflow()

    from datetime import time

    from domains.orders.terms import OrderTerms, ServiceTimeTerms
    from shared_kernel.identities import (
        ActorContext,
        CorrelationId,
        ExpectedVersion,
        IdempotencyKey,
    )
    from shared_kernel.money import MoneyNTD
    from subsystems.orders.terms_workflow import OrderTermsApplyRequest

    proposed_terms = OrderTerms(
        _date(1), 4, 9, MoneyNTD(400), ServiceTimeTerms(time(9), time(18), 0)
    )
    preview = workflow.preview("G03-CASE", proposed_terms)
    request = OrderTermsApplyRequest(
        "G03-CASE",
        proposed_terms,
        ExpectedVersion(preview.order_version),
        ExpectedVersion(preview.scheduling_version),
        ExpectedVersion(preview.client_finance_version),
        ExpectedVersion(preview.payroll_version),
        preview.fingerprint,
        IdempotencyKey("terms-workflow-recovery"),
        ActorContext("terms-recovery-test"),
        "increase confirmed daily service hours",
        CorrelationId("terms-workflow-recovery"),
    )

    try:
        receipt = workflow.apply(request)
        assert workflow.apply(request) == receipt
    finally:
        connection.close()

    assert receipt.order_version == 1
    assert receipt.scheduling_version == 2
    assert receipt.client_finance_version == 2
    assert receipt.payroll_version == 2
    assert _terms_recovery_write_counts() == {
        "client_outbox": 1,
        "orders_outbox": 1,
        "payroll_outbox": 1,
        "terms_event": 1,
        "terms_receipt": 1,
    }


def test_g02_actual_start_correction_updates_each_domain_once():
    bootstrap(_arguments())
    _seed_in_service_case(settled_client_and_unpaid_staff=True)
    workflow, connection = _actual_start_workflow()

    from shared_kernel.identities import (
        ActorContext,
        CorrelationId,
        ExpectedVersion,
        IdempotencyKey,
    )
    from subsystems.orders.actual_start_workflow import ActualStartApplyRequest

    preview = workflow.preview("G03-CASE", _date(2))
    request = ActualStartApplyRequest(
        "G03-CASE",
        _date(2),
        ExpectedVersion(preview.order_version),
        ExpectedVersion(preview.scheduling_version),
        ExpectedVersion(preview.client_finance_version),
        ExpectedVersion(preview.payroll_version),
        preview.fingerprint,
        IdempotencyKey("g02-actual-start-correction"),
        ActorContext("g02-test"),
        "correct confirmed actual start by one day",
        CorrelationId("g02-actual-start-correction"),
    )

    try:
        receipt = workflow.apply(request)
        assert workflow.apply(request) == receipt
    finally:
        connection.close()

    assert receipt.order_version == 1
    assert receipt.scheduling_version == 2
    assert receipt.client_finance_version == 2
    assert receipt.payroll_version == 2
    assert _actual_start_write_counts() == {
        "actual_start_event": 1,
        "actual_start_receipt": 1,
        "client_outbox": 1,
        "orders_outbox": 1,
        "payroll_outbox": 1,
    }


def test_g01_terms_panel_uses_real_http_preview_and_apply(monkeypatch):
    bootstrap(_arguments())
    _seed_in_service_case(settled_client_and_unpaid_staff=True)
    _configure_ui_api_environment(monkeypatch, "g01-ui-key")

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from api.dependencies.order_terms import (
        OrderTermsApplication,
        get_order_terms_application,
    )
    from api.routes.order_terms import router
    from ui.api_clients.order_terms_api_client import OrderTermsApiClient
    from ui.pages.order import terms_panel

    application = FastAPI()
    application.include_router(router)
    workflow, connection = _terms_workflow()
    application.dependency_overrides[get_order_terms_application] = lambda: (
        OrderTermsApplication(connection, workflow._repository, workflow)
    )
    display = _TermsPanelDisplay()
    monkeypatch.setattr(terms_panel, "st", display)
    try:
        with TestClient(application) as http_client:
            client = OrderTermsApiClient(
                base_url="http://g01-ui.test",
                headers={"X-Internal-API-Key": "g01-ui-key"},
                session=_TestClientSession(http_client, "http://g01-ui.test"),
            )
            terms_panel.render_order_terms_panel("G03-CASE", client)
            display.button_values["terms_apply_G03-CASE"] = True
            terms_panel.render_order_terms_panel("G03-CASE", client)
    finally:
        connection.close()

    assert display.errors == []
    assert display.rerun_called is True
    assert _terms_recovery_write_counts() == {
        "client_outbox": 1,
        "orders_outbox": 1,
        "payroll_outbox": 1,
        "terms_event": 1,
        "terms_receipt": 1,
    }


def test_g02_actual_start_panel_uses_real_http_preview_and_apply(monkeypatch):
    bootstrap(_arguments())
    _seed_in_service_case(settled_client_and_unpaid_staff=True)
    _configure_ui_api_environment(monkeypatch, "g02-ui-key")

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from api.dependencies.order_actual_start import (
        ActualStartApplication,
        get_actual_start_application,
    )
    from api.routes.order_actual_start import router
    from ui.api_clients.order_actual_start_api_client import ActualStartApiClient
    from ui.pages.order import actual_start_panel

    application = FastAPI()
    application.include_router(router)
    application.dependency_overrides[
        get_actual_start_application
    ] = _fixed_actual_start_application
    display = _ActualStartPanelDisplay()
    monkeypatch.setattr(actual_start_panel, "st", display)
    with TestClient(application) as http_client:
        session = _TestClientSession(http_client, "http://g02-ui.test")
        client = ActualStartApiClient(
            base_url="http://g02-ui.test",
            headers={"X-Internal-API-Key": "g02-ui-key"},
            session=session,
        )
        actual_start_panel.render_actual_start_panel("G03-CASE", client)
        display.button_values["actual_start_apply_G03-CASE"] = True
        actual_start_panel.render_actual_start_panel("G03-CASE", client)

    assert session.failed_bodies == []
    assert display.errors == []
    assert display.rerun_called is True
    assert _actual_start_write_counts() == {
        "actual_start_event": 1,
        "actual_start_receipt": 1,
        "client_outbox": 1,
        "orders_outbox": 1,
        "payroll_outbox": 1,
    }


def _configure_ui_api_environment(monkeypatch, api_key) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("ENABLE_ADMIN_AUTH", "false")
    monkeypatch.setenv("INTERNAL_API_KEY", api_key)


def _fixed_actual_start_application():
    from infrastructure.mysql.mysql_adapter import get_connection
    from infrastructure.mysql.order_actual_start_repository import (
        MySqlOrderActualStartRepository,
    )
    from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
    from shared_kernel.clock import FixedBusinessClock, TAIPEI_TIME_ZONE
    from subsystems.orders.actual_start_workflow import ActualStartWorkflow
    from api.dependencies.order_actual_start import ActualStartApplication

    connection = get_connection()
    repository = MySqlOrderActualStartRepository(connection)
    workflow = ActualStartWorkflow(
        repository,
        lambda: MySqlUnitOfWork(connection),
        FixedBusinessClock(datetime(2026, 8, 4, 9, tzinfo=TAIPEI_TIME_ZONE)),
    )
    try:
        yield ActualStartApplication(repository, workflow)
    finally:
        connection.close()


class _TestClientSession:
    def __init__(self, client, base_url) -> None:
        self._client = client
        self._base_url = base_url
        self.failed_bodies = []

    def request(self, method, url, **kwargs):
        path = url.replace(self._base_url, "", 1)
        kwargs.pop("timeout", None)
        response = self._client.request(method, path, **kwargs)
        if not response.is_success:
            self.failed_bodies.append(response.json())
        return _CancellationResponseAdapter(response)


class _TermsPanelDisplay:
    def __init__(self) -> None:
        self.session_state = {}
        self.button_values = {}
        self.errors = []
        self.rerun_called = False

    def markdown(self, *_args, **_kwargs) -> None:
        pass

    def caption(self, *_args, **_kwargs) -> None:
        pass

    def info(self, *_args, **_kwargs) -> None:
        pass

    def date_input(self, _label, *, value, **_kwargs):
        return value

    def number_input(self, _label, *, value, **_kwargs):
        return 9 if _label == "每日服務時數" else value

    def time_input(self, _label, *, value, **_kwargs):
        return value

    def selectbox(self, _label, options, *, index, **_kwargs):
        return options[index]

    def text_input(self, *_args, **_kwargs) -> str:
        return "increase confirmed daily service hours"

    def button(self, _label, *, key, **_kwargs) -> bool:
        return self.button_values.get(key, False)

    def error(self, message) -> None:
        self.errors.append(message)

    def success(self, *_args, **_kwargs) -> None:
        pass

    def rerun(self) -> None:
        self.rerun_called = True


class _ActualStartPanelDisplay:
    def __init__(self) -> None:
        self.session_state = {}
        self.button_values = {}
        self.errors = []
        self.rerun_called = False

    def markdown(self, *_args, **_kwargs) -> None:
        pass

    def caption(self, *_args, **_kwargs) -> None:
        pass

    def info(self, *_args, **_kwargs) -> None:
        pass

    def date_input(self, *_args, **_kwargs):
        return _date(2)

    def text_input(self, *_args, **_kwargs) -> str:
        return "correct confirmed actual start by one day"

    def button(self, _label, *, key, **_kwargs) -> bool:
        return self.button_values.get(key, False)

    def error(self, message) -> None:
        self.errors.append(message)

    def success(self, *_args, **_kwargs) -> None:
        pass

    def rerun(self) -> None:
        self.rerun_called = True


def _workflow():
    from infrastructure.mysql.mysql_adapter import get_connection
    from infrastructure.mysql.order_cancellation_repository import (
        MySqlOrderCancellationRepository,
    )
    from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
    from shared_kernel.clock import FixedBusinessClock, TAIPEI_TIME_ZONE
    from subsystems.orders.cancellation_workflow import OrderCancellationWorkflow

    connection = get_connection()
    return OrderCancellationWorkflow(
        MySqlOrderCancellationRepository(connection),
        lambda: MySqlUnitOfWork(connection),
        FixedBusinessClock(datetime(2026, 8, 4, 9, tzinfo=TAIPEI_TIME_ZONE)),
    ), connection


def _terms_workflow():
    from infrastructure.mysql.mysql_adapter import get_connection
    from infrastructure.mysql.order_terms_repository import MySqlOrderTermsRepository
    from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
    from shared_kernel.clock import FixedBusinessClock, TAIPEI_TIME_ZONE
    from subsystems.orders.terms_workflow import OrderTermsWorkflow

    connection = get_connection()
    workflow = OrderTermsWorkflow(
        MySqlOrderTermsRepository(connection),
        lambda: MySqlUnitOfWork(connection),
        FixedBusinessClock(datetime(2026, 8, 4, 9, tzinfo=TAIPEI_TIME_ZONE)),
    )
    return workflow, connection


def _actual_start_workflow():
    from infrastructure.mysql.mysql_adapter import get_connection
    from infrastructure.mysql.order_actual_start_repository import (
        MySqlOrderActualStartRepository,
    )
    from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
    from shared_kernel.clock import FixedBusinessClock, TAIPEI_TIME_ZONE
    from subsystems.orders.actual_start_workflow import ActualStartWorkflow

    connection = get_connection()
    workflow = ActualStartWorkflow(
        MySqlOrderActualStartRepository(connection),
        lambda: MySqlUnitOfWork(connection),
        FixedBusinessClock(datetime(2026, 8, 4, 9, tzinfo=TAIPEI_TIME_ZONE)),
    )
    return workflow, connection


def _seed_in_service_case(*, completed_with_payroll: bool = False, settled_client_and_unpaid_staff: bool = False) -> None:
    from infrastructure.mysql.mysql_adapter import get_connection

    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO clients(case_no,name,identity_status) "
                "VALUES ('G03-CASE','G03 Client','一般市民')"
            )
            client_id = cursor.lastrowid
            cursor.execute("INSERT INTO staff(name,status) VALUES ('G03 Staff 1','active')")
            assert cursor.lastrowid == 1
            cursor.execute("INSERT INTO staff(name,status) VALUES ('G03 Staff 2','active')")
            assert cursor.lastrowid == 2
            cursor.execute(
                "INSERT INTO orders "
                "(case_no,client_id,status,lifecycle_version,start_date,service_days,"
                "service_hours_per_day,floor_fee,service_start_time,service_end_time,"
                "service_end_day_offset,actual_start_date,staff_payment_due_date) "
                "VALUES ('G03-CASE',%s,%s,0,'2026-08-01',4,8,400,'09:00:00','17:00:00',0,'2026-08-01','2026-08-15')",
                (client_id, "訂單完成" if completed_with_payroll else "服務中"),
            )
            cursor.execute(
                "INSERT INTO scheduling_generations "
                "(case_no,generation_number,resulting_aggregate_version,status,effective_marker,created_by,change_reason) "
                "VALUES ('G03-CASE',1,1,'effective',1,'g03-test','initial assignment')"
            )
            generation_id = cursor.lastrowid
            cursor.execute(
                "INSERT INTO scheduling_aggregates "
                "(case_no,aggregate_version,generation_counter,effective_generation_id) "
                "VALUES ('G03-CASE',1,1,%s)",
                (generation_id,),
            )
            _insert_assignment(cursor, generation_id, 1, 1, _date(1), _date(3), "G03-CASE:g1:a1")
            _insert_assignment(cursor, generation_id, 2, 2, _date(2), _date(4), "G03-CASE:g1:a2")
            _insert_client_finance_root(cursor, settled=settled_client_and_unpaid_staff)
            _insert_payroll_root(cursor, established=completed_with_payroll or settled_client_and_unpaid_staff)
        connection.commit()
    finally:
        connection.close()


def _insert_assignment(cursor, generation_id, staff_id, sequence, first_date, second_date, key):
    cursor.execute(
        "INSERT INTO case_staff_assignments "
        "(case_no,generation_id,candidate_key,staff_id,assignment_sequence,assigned_start_date,assigned_end_date,floor_fee_allocated,status) "
        "VALUES ('G03-CASE',%s,%s,%s,%s,%s,%s,0,'planned')",
        (generation_id, key, staff_id, sequence, first_date, second_date),
    )
    assignment_id = cursor.lastrowid
    for service_date in (first_date, second_date):
        cursor.execute(
            "INSERT INTO staff_schedule "
            "(case_no,staff_id,assignment_id,generation_id,work_date,is_work_day,is_double_pay,effective_marker) "
            "VALUES ('G03-CASE',%s,%s,%s,%s,1,0,1)",
            (staff_id, assignment_id, generation_id, service_date),
        )


def _terms_recovery_write_counts():
    from infrastructure.mysql.mysql_adapter import get_connection

    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) AS count FROM client_finance_outbox")
            client_outbox = cursor.fetchone()["count"]
            cursor.execute("SELECT COUNT(*) AS count FROM orders_domain_outbox")
            orders_outbox = cursor.fetchone()["count"]
            cursor.execute("SELECT COUNT(*) AS count FROM payroll_outbox")
            payroll_outbox = cursor.fetchone()["count"]
            cursor.execute("SELECT COUNT(*) AS count FROM order_terms_change_events")
            terms_event = cursor.fetchone()["count"]
            cursor.execute("SELECT COUNT(*) AS count FROM order_terms_apply_receipts")
            terms_receipt = cursor.fetchone()["count"]
    finally:
        connection.close()
    return {
        "client_outbox": client_outbox,
        "orders_outbox": orders_outbox,
        "payroll_outbox": payroll_outbox,
        "terms_event": terms_event,
        "terms_receipt": terms_receipt,
    }


def _actual_start_write_counts():
    from infrastructure.mysql.mysql_adapter import get_connection

    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) AS count FROM order_actual_start_events")
            actual_start_event = cursor.fetchone()["count"]
            cursor.execute("SELECT COUNT(*) AS count FROM order_actual_start_apply_receipts")
            actual_start_receipt = cursor.fetchone()["count"]
            cursor.execute("SELECT COUNT(*) AS count FROM client_finance_outbox")
            client_outbox = cursor.fetchone()["count"]
            cursor.execute("SELECT COUNT(*) AS count FROM orders_domain_outbox")
            orders_outbox = cursor.fetchone()["count"]
            cursor.execute("SELECT COUNT(*) AS count FROM payroll_outbox")
            payroll_outbox = cursor.fetchone()["count"]
    finally:
        connection.close()
    return {
        "actual_start_event": actual_start_event,
        "actual_start_receipt": actual_start_receipt,
        "client_outbox": client_outbox,
        "orders_outbox": orders_outbox,
        "payroll_outbox": payroll_outbox,
    }


def _insert_client_finance_root(cursor, *, settled: bool) -> None:
    cursor.execute("INSERT INTO client_finance_accounts(case_no,aggregate_version) VALUES ('G03-CASE',%s)", (1 if settled else 0,))
    cursor.execute(
        "INSERT INTO client_payment_terms_events "
        "(case_no,policy_version,client_hourly_rate_ntd,deposit_service_days,deposit_due_date,first_payment_due_date,second_payment_due_date,expected_account_version,source_event_identity,idempotency_key,actor,reason) "
        "VALUES ('G03-CASE','g03-policy',100,2,'2026-08-15','2026-08-20',NULL,0,'g03-terms-root','g03-terms-root','g03-test','fixture')"
    )
    event_id = cursor.lastrowid
    cursor.execute(
        "INSERT INTO client_payment_terms "
        "(case_no,policy_version,client_hourly_rate_ntd,deposit_service_days,deposit_due_date,first_payment_due_date,second_payment_due_date,current_event_id) "
        "VALUES ('G03-CASE','g03-policy',100,2,'2026-08-15','2026-08-20',NULL,%s)",
        (event_id,),
    )
    if settled:
        _insert_settled_client_stages(cursor)


def _insert_settled_client_stages(cursor) -> None:
    for ordinal, (stage, amount, due_date) in enumerate((("deposit", 2000, "2026-08-15"), ("first", 1600, "2026-08-20")), start=1):
        identity = f"G03-CASE:{stage}"
        cursor.execute(
            "INSERT INTO client_obligation_events "
            "(obligation_identity,case_no,obligation_type,direction,event_type,before_amount_ntd,after_amount_ntd,before_due_date,after_due_date,source_event_identity,source_obligation_identity,expected_account_version,idempotency_key,actor,reason) "
            "VALUES (%s,'G03-CASE',%s,'receivable_from_client','established',0,%s,NULL,%s,%s,NULL,0,%s,'g03-test','settled fixture')",
            (identity, stage, amount, due_date, f"g03-stage-source-{ordinal}", f"g03-stage-event-{ordinal}"),
        )
        event_id = cursor.lastrowid
        cursor.execute(
            "INSERT INTO client_obligations "
            "(obligation_identity,case_no,obligation_type,direction,source_obligation_identity,amount_due_ntd,due_date,status,current_event_id,projection_version) "
            "VALUES (%s,'G03-CASE',%s,'receivable_from_client',NULL,%s,%s,'open',%s,1)",
            (identity, stage, amount, due_date, event_id),
        )
        cursor.execute(
            "INSERT INTO client_ledger_entries "
            "(case_no,finance_import_row_id,entry_type,amount_ntd,occurred_on,reconciliation_reference,reversal_of_entry_id,idempotency_key,actor,reason) "
            "VALUES ('G03-CASE',NULL,'receipt',%s,'2026-08-01',%s,NULL,%s,'g03-test','settled fixture')",
            (amount, f"g03-receipt-{ordinal}", f"g03-receipt-{ordinal}"),
        )
        cursor.execute(
            "INSERT INTO client_ledger_obligation_allocations "
            "(ledger_entry_id,obligation_identity,amount_ntd,allocation_ordinal) VALUES (%s,%s,%s,1)",
            (cursor.lastrowid, identity, amount),
        )


def _insert_payroll_root(cursor, *, established: bool) -> None:
    cursor.execute(
        "INSERT INTO payroll_case_accounts(case_no,aggregate_version) VALUES ('G03-CASE',%s)",
        (1 if established else 0,),
    )
    cursor.execute(
        "INSERT INTO payroll_rate_policies "
        "(policy_version,policy_kind,hourly_rate_ntd,effective_from) "
        "VALUES ('g03-policy','citizen',150,'2026-01-01')"
    )
    for assignment_id in (1, 2):
        cursor.execute(
            "INSERT INTO assignment_payroll_rate_snapshots "
            "(assignment_id,policy_version,policy_kind,hourly_rate_ntd,source_identity_status) "
            "VALUES (%s,'g03-policy','citizen',150,'fixture')",
            (assignment_id,),
        )
    if established:
        _insert_established_staff_obligations(cursor)


def _insert_established_staff_obligations(cursor) -> None:
    for assignment_id, staff_id in ((1, 1), (2, 2)):
        cursor.execute(
            "INSERT INTO staff_obligation_events "
            "(obligation_identity,assignment_id,case_no,staff_id,obligation_kind,direction,source_obligation_identity,event_type,before_amount_ntd,after_amount_ntd,due_date,payroll_fingerprint,expected_payroll_version,resulting_payroll_version,idempotency_key,actor,reason) "
            "VALUES (%s,%s,'G03-CASE',%s,'service_pay','payable_to_staff',NULL,'established',0,5000,'2026-08-15',%s,0,1,%s,'g04-test','completed service fixture')",
            (f"g04-staff-{staff_id}", assignment_id, staff_id, "a" * 64, f"g04-staff-event-{staff_id}"),
        )
        event_id = cursor.lastrowid
        cursor.execute(
            "INSERT INTO staff_obligations "
            "(obligation_identity,assignment_id,case_no,staff_id,obligation_kind,direction,source_obligation_identity,amount_due_ntd,due_date,status,current_event_id,payroll_version,payout_history_exists) "
            "VALUES (%s,%s,'G03-CASE',%s,'service_pay','payable_to_staff',NULL,5000,'2026-08-15','open',%s,1,0)",
            (f"g04-staff-{staff_id}", assignment_id, staff_id, event_id),
        )


def _assert_cross_domain_result() -> None:
    from infrastructure.mysql.mysql_adapter import get_connection

    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT status,lifecycle_version,actual_end_date FROM orders WHERE case_no='G03-CASE'")
            assert cursor.fetchone() == {"status": "訂單取消", "lifecycle_version": 1, "actual_end_date": _date(2)}
            cursor.execute("SELECT aggregate_version,generation_counter FROM scheduling_aggregates WHERE case_no='G03-CASE'")
            assert cursor.fetchone() == {"aggregate_version": 2, "generation_counter": 2}
            cursor.execute("SELECT aggregate_version FROM client_finance_accounts WHERE case_no='G03-CASE'")
            assert cursor.fetchone() == {"aggregate_version": 2}
            cursor.execute("SELECT aggregate_version FROM payroll_case_accounts WHERE case_no='G03-CASE'")
            assert cursor.fetchone() == {"aggregate_version": 2}
            for table_name in ("orders_domain_outbox", "client_finance_outbox", "payroll_outbox"):
                cursor.execute(f"SELECT COUNT(*) AS count FROM {table_name} WHERE case_no='G03-CASE'")
                assert cursor.fetchone() == {"count": 1}
            cursor.execute("SELECT COUNT(*) AS count FROM order_cancellation_apply_receipts WHERE case_no='G03-CASE'")
            assert cursor.fetchone() == {"count": 1}
    finally:
        connection.close()


def _assert_no_cross_domain_auto_netting() -> None:
    from infrastructure.mysql.mysql_adapter import get_connection

    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT obligation_type,direction,amount_due_ntd,status FROM client_obligations "
                "WHERE case_no='G03-CASE' ORDER BY obligation_type,obligation_identity"
            )
            assert cursor.fetchall() == [
                {"obligation_type": "deposit", "direction": "receivable_from_client", "amount_due_ntd": 2000, "status": "open"},
                {"obligation_type": "first", "direction": "receivable_from_client", "amount_due_ntd": 1600, "status": "open"},
                {"obligation_type": "refund", "direction": "payable_to_client", "amount_due_ntd": 200, "status": "open"},
                {"obligation_type": "refund", "direction": "payable_to_client", "amount_due_ntd": 1600, "status": "open"},
            ]
            cursor.execute(
                "SELECT direction,amount_due_ntd,status FROM staff_obligations "
                "WHERE case_no='G03-CASE' ORDER BY obligation_identity"
            )
            rows = cursor.fetchall()
            assert len(rows) == 4
            assert sum(row["amount_due_ntd"] for row in rows if row["status"] == "open") == 5000
            assert all(row["direction"] == "payable_to_staff" for row in rows)
    finally:
        connection.close()


def _write_counts() -> tuple[int, ...]:
    from infrastructure.mysql.mysql_adapter import get_connection

    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            return tuple(
                _count(cursor, table_name)
                for table_name in (
                    "order_cancellation_events",
                    "order_cancellation_apply_receipts",
                    "client_obligation_events",
                    "staff_obligation_events",
                    "orders_domain_outbox",
                )
            )
    finally:
        connection.close()


def _count(cursor, table_name: str) -> int:
    cursor.execute(f"SELECT COUNT(*) AS count FROM {table_name} WHERE case_no='G03-CASE'")
    return int(cursor.fetchone()["count"])


def _payroll_snapshot() -> tuple[object, ...]:
    from infrastructure.mysql.mysql_adapter import get_connection

    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT aggregate_version FROM payroll_case_accounts WHERE case_no='G03-CASE'")
            account = cursor.fetchone()
            cursor.execute(
                "SELECT obligation_identity,amount_due_ntd,status,payroll_version "
                "FROM staff_obligations WHERE case_no='G03-CASE' ORDER BY obligation_identity"
            )
            return account["aggregate_version"], tuple(cursor.fetchall())
    finally:
        connection.close()


def _date(day: int):
    from datetime import date

    return date(2026, 8, day)
