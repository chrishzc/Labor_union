"""Issue #337 real HTTP/Application/MySQL acceptance for empty service time."""

from argparse import Namespace
from datetime import date, datetime, time
import os
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pymysql

from api.dependencies.admin_auth import require_system_admin
from api.dependencies.admin_auth import require_persisted_admin
from api.dependencies.order_intake_terms_bootstrap import get_order_intake_terms_bootstrap_application
from api.dependencies.order_terms import OrderTermsApplication, get_order_terms_application
from api.routes.order_intake_terms_bootstrap import router as intake_terms_router
from api.routes.order_terms import router
from domains.bootstrap.case_architecture import CaseArchitectureBootstrapIntent, ClientPaymentTermsRootFacts
from domains.case_import.case_import import (
    CaseImportIntent,
    ClientImportAttribute,
    ImportedOrderRootFacts,
)
from infrastructure.mysql.case_import_repository import CaseImportMySqlUnitOfWork, MySqlCaseImportRepository
from infrastructure.mysql.mysql_adapter import DB_CONFIG
from infrastructure.mysql.order_intake_terms_bootstrap_repository import MySqlOrderIntakeTermsBootstrapRepository
from infrastructure.mysql.order_terms_repository import MySqlOrderTermsRepository
from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
from scripts.bootstrap_disposable_mysql_schema import bootstrap
from shared_kernel.clock import FixedBusinessClock, TAIPEI_TIME_ZONE
from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
from shared_kernel.money import MoneyNTD
from subsystems.case_import.case_import_workflow import ApplyCaseImport, CaseImportWorkflow
from subsystems.orders.terms_workflow import OrderTermsWorkflow
from subsystems.orders.order_intake_terms_bootstrap import OrderIntakeTermsBootstrapApplication


_DATABASE = f"lu_test_issue337_terms_{os.getpid()}"
_CASE_NO = "ISSUE-337-MYSQL"


def _arguments() -> Namespace:
    assert DB_CONFIG["host"] in {"127.0.0.1", "localhost"}
    return Namespace(
        host=DB_CONFIG["host"],
        port=DB_CONFIG["port"],
        user=DB_CONFIG["user"],
        password=DB_CONFIG["password"],
        database=_DATABASE,
        confirm_database=_DATABASE,
    )


def _connect():
    return pymysql.connect(
        host=DB_CONFIG["host"],
        port=DB_CONFIG["port"],
        user=DB_CONFIG["user"],
        password=DB_CONFIG["password"],
        database=_DATABASE,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False,
    )


def _drop_database() -> None:
    assert _DATABASE.startswith("lu_test_issue337_terms_")
    connection = pymysql.connect(
        host=DB_CONFIG["host"],
        port=DB_CONFIG["port"],
        user=DB_CONFIG["user"],
        password=DB_CONFIG["password"],
        charset="utf8mb4",
        autocommit=True,
    )
    try:
        with connection.cursor() as cursor:
            cursor.execute(f"DROP DATABASE IF EXISTS `{_DATABASE}`")
    finally:
        connection.close()


def _intent() -> CaseImportIntent:
    start_date = date(2026, 10, 1)
    payment_terms = ClientPaymentTermsRootFacts(
        "issue337-client-policy-v1",
        MoneyNTD(400),
        5,
        date(2026, 9, 20),
        start_date,
    )
    attributes = tuple(sorted(
        (
            ClientImportAttribute("case_no", _CASE_NO),
            ClientImportAttribute("created_at", datetime(2026, 9, 1, 9, 0)),
            ClientImportAttribute("identity_status", "一般市民"),
            ClientImportAttribute("name", "Issue 337 合成客戶"),
            ClientImportAttribute("service_time", "09:00-17:00"),
        ),
        key=lambda attribute: attribute.name,
    ))
    order = ImportedOrderRootFacts(
        _CASE_NO,
        5,
        8,
        start_date,
        date(2026, 10, 5),
        time(9),
        time(17),
        0,
        False,
    )
    return CaseImportIntent(
        _CASE_NO,
        attributes,
        order,
        CaseArchitectureBootstrapIntent(
            _CASE_NO,
            payment_terms,
            "issue337-approved-rates-v1",
        ),
    )


def _seed(connection) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            "INSERT INTO payroll_rate_policies "
            "(policy_version,policy_kind,hourly_rate_ntd,effective_from) "
            "VALUES ('issue337-approved-rates-v1','citizen',300,'2026-01-01')"
        )
    connection.commit()
    intent = _intent()
    workflow = CaseImportWorkflow(
        MySqlCaseImportRepository(connection),
        lambda: CaseImportMySqlUnitOfWork(connection),
    )
    preview = workflow.preview(intent, CorrelationId("issue337-import-preview"))
    workflow.apply(ApplyCaseImport(
        intent,
        ExpectedVersion(0),
        preview.fingerprint,
        IdempotencyKey("issue337-import"),
        ActorContext("issue337-acceptance"),
        "create isolated acceptance roots",
        CorrelationId("issue337-import"),
    ))
    with connection.cursor() as cursor:
        cursor.execute(
            "UPDATE orders SET service_start_time=NULL,service_end_time=NULL,"
            "service_end_day_offset=NULL WHERE case_no=%s",
            (_CASE_NO,),
        )
        assert cursor.rowcount == 1
    connection.commit()


def _seed_effective_assignment(connection) -> int:
    service_dates = tuple(date(2026, 10, day) for day in range(1, 6))
    with connection.cursor() as cursor:
        cursor.execute(
            "INSERT INTO staff(name,status) VALUES (%s,'active')",
            ("Issue 338 合成月嫂",),
        )
        staff_id = int(cursor.lastrowid)
        cursor.execute(
            "INSERT INTO scheduling_generations "
            "(case_no,generation_number,resulting_aggregate_version,status,effective_marker,"
            "created_by,change_reason) VALUES (%s,1,1,'effective',1,%s,%s)",
            (_CASE_NO, "issue338-acceptance", "initial effective assignment"),
        )
        generation_id = int(cursor.lastrowid)
        cursor.execute(
            "UPDATE scheduling_aggregates SET aggregate_version=1,generation_counter=1,"
            "effective_generation_id=%s WHERE case_no=%s",
            (generation_id, _CASE_NO),
        )
        assert cursor.rowcount == 1
        cursor.execute(
            "INSERT INTO case_staff_assignments "
            "(case_no,generation_id,candidate_key,staff_id,assignment_sequence,"
            "assigned_start_date,assigned_end_date,floor_fee_allocated,status) "
            "VALUES (%s,%s,%s,%s,1,%s,%s,0,'planned')",
            (
                _CASE_NO,
                generation_id,
                f"{_CASE_NO}:g1:a1",
                staff_id,
                service_dates[0],
                service_dates[-1],
            ),
        )
        assignment_id = int(cursor.lastrowid)
        for service_date in service_dates:
            cursor.execute(
                "INSERT INTO staff_schedule "
                "(case_no,staff_id,assignment_id,generation_id,work_date,is_work_day,"
                "is_double_pay,effective_marker) VALUES (%s,%s,%s,%s,%s,1,0,1)",
                (_CASE_NO, staff_id, assignment_id, generation_id, service_date),
            )
            cursor.execute(
                "INSERT INTO scheduling_effective_occupancy "
                "(staff_id,occupancy_date,generation_id,assignment_id,occupancy_type) "
                "VALUES (%s,%s,%s,%s,'assignment_interval')",
                (staff_id, service_date, generation_id, assignment_id),
            )
        for day in range(6, 13):
            buffer_date = date(2026, 10, day)
            cursor.execute(
                "INSERT INTO scheduling_buffer_days "
                "(generation_id,assignment_id,staff_id,buffer_date,status,active_marker) "
                "VALUES (%s,%s,%s,%s,'active',1)",
                (generation_id, assignment_id, staff_id, buffer_date),
            )
            cursor.execute(
                "INSERT INTO scheduling_effective_occupancy "
                "(staff_id,occupancy_date,generation_id,assignment_id,occupancy_type) "
                "VALUES (%s,%s,%s,%s,'buffer')",
                (staff_id, buffer_date, generation_id, assignment_id),
            )
        cursor.execute(
            "INSERT INTO assignment_payroll_rate_snapshots "
            "(assignment_id,policy_version,policy_kind,hourly_rate_ntd,source_identity_status) "
            "VALUES (%s,'issue337-approved-rates-v1','citizen',300,'fixture')",
            (assignment_id,),
        )
    connection.commit()
    return assignment_id


def _scheduling_snapshot(connection):
    connection.commit()
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT aggregate_version,generation_counter,effective_generation_id "
            "FROM scheduling_aggregates WHERE case_no=%s",
            (_CASE_NO,),
        )
        aggregate = dict(cursor.fetchone())
        counts = {}
        for name, statement in {
            "generations": "SELECT COUNT(*) AS total FROM scheduling_generations WHERE case_no=%s",
            "assignments": "SELECT COUNT(*) AS total FROM case_staff_assignments WHERE case_no=%s",
            "schedules": "SELECT COUNT(*) AS total FROM staff_schedule WHERE case_no=%s AND effective_marker=1",
            "buffers": (
                "SELECT COUNT(*) AS total FROM scheduling_buffer_days buffer "
                "JOIN case_staff_assignments assignment ON assignment.id=buffer.assignment_id "
                "WHERE assignment.case_no=%s AND buffer.active_marker=1"
            ),
            "occupancy": (
                "SELECT COUNT(*) AS total FROM scheduling_effective_occupancy occupancy "
                "JOIN scheduling_generations generation ON generation.id=occupancy.generation_id "
                "WHERE generation.case_no=%s"
            ),
            "rebuild_events": "SELECT COUNT(*) AS total FROM scheduling_rebuild_events WHERE case_no=%s",
            "scheduling_receipts": "SELECT COUNT(*) AS total FROM scheduling_command_receipts WHERE case_no=%s",
            "notification_invalidations": (
                "SELECT COUNT(*) AS total FROM scheduling_rebuild_notification_outbox outbox "
                "JOIN scheduling_rebuild_events event ON event.id=outbox.rebuild_event_id "
                "WHERE event.case_no=%s"
            ),
        }.items():
            cursor.execute(statement, (_CASE_NO,))
            counts[name] = int(cursor.fetchone()["total"])
        cursor.execute(
            "SELECT id,generation_id,candidate_key,staff_id,assignment_sequence,"
            "assigned_start_date,assigned_end_date,status FROM case_staff_assignments "
            "WHERE case_no=%s ORDER BY id",
            (_CASE_NO,),
        )
        assignments = tuple(dict(row) for row in cursor.fetchall())
    return aggregate, counts, assignments


def _seed_without_downstream_roots(connection) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            "INSERT INTO clients(case_no,name,identity_status) VALUES (%s,%s,%s)",
            (_CASE_NO, "Issue 337 無下游 roots", "一般市民"),
        )
        client_id = int(cursor.lastrowid)
        cursor.execute(
            "INSERT INTO orders(case_no,client_id,status,lifecycle_version,start_date,end_date,"
            "service_days,service_hours_per_day,requires_cooking,floor_fee,service_start_time,"
            "service_end_time,service_end_day_offset) "
            "VALUES (%s,%s,'洽談中',3,'2026-10-01','2026-10-05',5,8,0,0,NULL,NULL,NULL)",
            (_CASE_NO, client_id),
        )
    connection.commit()


def _snapshot(connection):
    connection.commit()
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT start_date,end_date,service_days,service_hours_per_day,requires_cooking,"
            "floor_fee,service_start_time,service_end_time,service_end_day_offset,lifecycle_version "
            "FROM orders WHERE case_no=%s",
            (_CASE_NO,),
        )
        order = dict(cursor.fetchone())
        counts = {}
        for name, statement in {
            "terms_events": "SELECT COUNT(*) AS total FROM order_terms_change_events WHERE case_no=%s",
            "terms_receipts": "SELECT COUNT(*) AS total FROM order_terms_apply_receipts WHERE case_no=%s",
            "lifecycle_events": "SELECT COUNT(*) AS total FROM order_lifecycle_state_events WHERE case_no=%s",
            "command_claims": (
                "SELECT COUNT(*) AS total FROM application_command_claims "
                "WHERE command_family='orders_terms' AND aggregate_identity=%s"
            ),
        }.items():
            cursor.execute(statement, (_CASE_NO,))
            counts[name] = int(cursor.fetchone()["total"])
    return order, counts


def _client(connection) -> TestClient:
    repository = MySqlOrderTermsRepository(connection)
    application = OrderTermsApplication(
        connection,
        repository,
        OrderTermsWorkflow(
            repository,
            lambda: MySqlUnitOfWork(connection),
            FixedBusinessClock(datetime(2026, 9, 22, 12, tzinfo=TAIPEI_TIME_ZONE)),
        ),
    )
    app = FastAPI()
    app.include_router(router)
    app.include_router(intake_terms_router)
    app.dependency_overrides[require_system_admin] = lambda: SimpleNamespace(username="issue337-admin")
    app.dependency_overrides[require_persisted_admin] = lambda: SimpleNamespace(username="issue337-admin")
    app.dependency_overrides[get_order_terms_application] = lambda: application
    intake_repository = MySqlOrderIntakeTermsBootstrapRepository(connection)
    app.dependency_overrides[get_order_intake_terms_bootstrap_application] = lambda: OrderIntakeTermsBootstrapApplication(
        intake_repository,
        lambda: MySqlUnitOfWork(connection),
    )
    return TestClient(app)


def _data(response, expected_status=200):
    assert response.status_code == expected_status, response.text
    return response.json()["data"]


def _preview(client, terms):
    return _data(client.post(
        f"/api/v1/orders/{_CASE_NO}/terms/preview",
        json={"proposed_terms": terms},
        headers={"X-Correlation-ID": "issue337-preview"},
    ))


def _apply(client, query, preview, terms, key):
    requires_formal_apply = preview["requires_formal_apply"]
    return client.post(
        f"/api/v1/orders/{_CASE_NO}/terms/apply",
        json={
            "proposed_terms": terms,
            "expected_order_version": query["order_version"],
            "expected_scheduling_version": query["scheduling_version"],
            "expected_client_finance_version": query["client_finance_version"],
            "expected_payroll_version": query["payroll_version"],
            "preview_fingerprint": preview["preview_fingerprint"],
            "requires_formal_apply": requires_formal_apply,
            **(
                {"reason": "Issue 337 disposable acceptance"}
                if requires_formal_apply
                else {}
            ),
        },
        headers={
            "X-Correlation-ID": key,
            **({"Idempotency-Key": key} if requires_formal_apply else {}),
        },
    )


def test_empty_service_time_round_trips_through_http_application_and_mysql():
    bootstrap(_arguments())
    connection = _connect()
    try:
        _seed(connection)
        client = _client(connection)
        query = _data(client.get(f"/api/v1/orders/{_CASE_NO}/terms"))
        assert query["terms"]["service_time"] == {
            "start_time": None,
            "end_time": None,
            "end_day_offset": None,
        }
        before = _snapshot(connection)

        changed = {**query["terms"], "planned_start_date": "2026-10-02"}
        preview = _preview(client, changed)
        assert preview["requires_formal_apply"] is False
        assert _snapshot(connection) == before
        receipt = _data(_apply(client, query, preview, changed, "issue337-empty-apply"))
        readback = _data(client.get(f"/api/v1/orders/{_CASE_NO}/terms"))
        after, permanent_counts = _snapshot(connection)

        assert receipt["order_version"] == query["order_version"] + 1
        assert receipt["scheduling_version"] == query["scheduling_version"]
        assert receipt["scheduling_generation"] == query["scheduling_generation"]
        assert readback["terms"] == changed
        assert after["service_start_time"] is None
        assert after["service_end_time"] is None
        assert after["service_end_day_offset"] is None
        assert after["service_days"] == before[0]["service_days"]
        assert after["service_hours_per_day"] == before[0]["service_hours_per_day"]
        assert after["requires_cooking"] == before[0]["requires_cooking"]
        assert after["floor_fee"] == before[0]["floor_fee"]
        assert permanent_counts == before[1]

        complete = {
            **readback["terms"],
            "service_hours_per_day": 8,
            "service_time": {
                "start_time": "21:00:00",
                "end_time": "05:00:00",
                "end_day_offset": 1,
            },
        }
        complete_preview = _preview(client, complete)
        _data(_apply(client, readback, complete_preview, complete, "issue337-complete-apply"))
        complete_readback = _data(client.get(f"/api/v1/orders/{_CASE_NO}/terms"))
        assert complete_readback["terms"]["service_time"] == complete["service_time"]

        failed_before = _snapshot(connection)
        partial = {
            **complete_readback["terms"],
            "service_time": {
                "start_time": "09:00:00",
                "end_time": None,
                "end_day_offset": 0,
            },
        }
        response = client.post(
            f"/api/v1/orders/{_CASE_NO}/terms/preview",
            json={"proposed_terms": partial},
            headers={"X-Correlation-ID": "issue337-partial"},
        )
        assert response.status_code == 422, response.text
        assert _snapshot(connection) == failed_before
    finally:
        connection.close()
        _drop_database()


def test_empty_service_time_survives_date_change_without_downstream_roots():
    bootstrap(_arguments())
    connection = _connect()
    try:
        _seed_without_downstream_roots(connection)
        client = _client(connection)
        preview = _data(client.post(
            f"/api/v1/orders/{_CASE_NO}/intake-terms-bootstrap/preview",
            json={"proposed_start_date": "2026-10-02", "proposed_service_days": 5},
        ))
        assert preview["apply_allowed"] is True
        assert preview["changed_fields"] == ["start_date"]

        receipt = _data(client.post(
            f"/api/v1/orders/{_CASE_NO}/intake-terms-bootstrap/apply",
            json={
                "proposed_start_date": "2026-10-02",
                "proposed_service_days": 5,
                "expected_lifecycle_version": preview["lifecycle_version"],
                "preview_fingerprint": preview["preview_fingerprint"],
                "reason": "Issue 337 no-root acceptance",
            },
            headers={
                "Idempotency-Key": "issue337-no-root-apply",
                "X-Correlation-ID": "issue337-no-root-apply",
            },
        ))
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT start_date,service_days,service_hours_per_day,requires_cooking,floor_fee,"
                "service_start_time,service_end_time,service_end_day_offset,lifecycle_version "
                "FROM orders WHERE case_no=%s",
                (_CASE_NO,),
            )
            order = dict(cursor.fetchone())
            counts = {}
            for name, table in {
                "scheduling": "scheduling_aggregates",
                "finance": "client_finance_accounts",
                "payroll": "payroll_case_accounts",
            }.items():
                cursor.execute(f"SELECT COUNT(*) AS total FROM {table} WHERE case_no=%s", (_CASE_NO,))
                counts[name] = int(cursor.fetchone()["total"])

        assert receipt["lifecycle_version"] == 4
        assert order == {
            "start_date": date(2026, 10, 2),
            "service_days": 5,
            "service_hours_per_day": 8.0,
            "requires_cooking": False,
            "floor_fee": 0,
            "service_start_time": None,
            "service_end_time": None,
            "service_end_day_offset": None,
            "lifecycle_version": 4,
        }
        assert counts == {"scheduling": 0, "finance": 0, "payroll": 0}
    finally:
        connection.close()
        _drop_database()


def test_general_terms_date_change_round_trips_without_downstream_roots():
    """Issue #336: the general Terms path must not bootstrap Finance or Payroll."""

    bootstrap(_arguments())
    connection = _connect()
    try:
        _seed_without_downstream_roots(connection)
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO scheduling_aggregates(case_no) VALUES (%s)",
                (_CASE_NO,),
            )
        connection.commit()
        client = _client(connection)
        query = _data(client.get(f"/api/v1/orders/{_CASE_NO}/terms"))
        assert query["client_finance_version"] is None
        assert query["payroll_version"] is None

        changed = {**query["terms"], "planned_start_date": "2026-10-02"}
        preview = _preview(client, changed)
        assert preview["client_finance_version"] is None
        assert preview["payroll_version"] is None
        assert preview["client_finance_impact"] is None
        assert preview["payroll_impact"] is None

        receipt = _data(_apply(
            client,
            query,
            preview,
            changed,
            "issue336-general-terms-no-roots",
        ))
        readback = _data(client.get(f"/api/v1/orders/{_CASE_NO}/terms"))

        assert receipt["client_finance_version"] is None
        assert receipt["payroll_version"] is None
        assert readback["terms"]["planned_start_date"] == "2026-10-02"
        assert readback["client_finance_version"] is None
        assert readback["payroll_version"] is None
        with connection.cursor() as cursor:
            for table in ("client_finance_accounts", "payroll_case_accounts"):
                cursor.execute(
                    f"SELECT COUNT(*) AS total FROM {table} WHERE case_no=%s",
                    (_CASE_NO,),
                )
                assert int(cursor.fetchone()["total"]) == 0
    finally:
        connection.close()
        _drop_database()


def test_assigned_hours_change_keeps_effective_scheduling_and_real_assignment_identity():
    """Issue #338: a Finance/Payroll impact does not imply Scheduling replacement."""

    bootstrap(_arguments())
    connection = _connect()
    try:
        _seed(connection)
        assignment_id = _seed_effective_assignment(connection)
        client = _client(connection)
        query = _data(client.get(f"/api/v1/orders/{_CASE_NO}/terms"))
        before = _scheduling_snapshot(connection)

        changed = {**query["terms"], "service_hours_per_day": 4.5}
        preview = _preview(client, changed)
        assert preview["requires_formal_apply"] is True
        receipt = _data(_apply(
            client,
            query,
            preview,
            changed,
            "issue338-hours-no-scheduling-replacement",
        ))
        readback = _data(client.get(f"/api/v1/orders/{_CASE_NO}/terms"))
        after = _scheduling_snapshot(connection)

        assert after == before
        assert receipt["scheduling_version"] == query["scheduling_version"]
        assert receipt["scheduling_generation"] == query["scheduling_generation"]
        assert receipt["cancelled_assignment_ids"] == []
        assert receipt["created_assignment_keys"] == []
        assert readback["terms"]["service_hours_per_day"] == 4.5
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT scheduling_command_receipt_id FROM order_terms_apply_receipts "
                "WHERE idempotency_key=%s",
                ("issue338-hours-no-scheduling-replacement",),
            )
            assert cursor.fetchone()["scheduling_command_receipt_id"] is None
            cursor.execute(
                "SELECT assignment_id FROM staff_obligations "
                "WHERE case_no=%s ORDER BY obligation_identity DESC LIMIT 1",
                (_CASE_NO,),
            )
            assert cursor.fetchone()["assignment_id"] == assignment_id
    finally:
        connection.close()
        _drop_database()
