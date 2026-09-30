"""Real HTTP/owner/MySQL proof for independent registry edits and later bootstrap."""

from argparse import Namespace
from datetime import date
import os

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from api.dependencies.admin_auth import (
    require_persisted_admin, require_registry_reader, require_registry_writer,
    require_system_admin,
)
from api.routes.client_registry import router as registry_router
from api.routes.case_architecture_bootstrap import router as bootstrap_router
from api.routes.order_intake_terms_bootstrap import router as intake_router
from infrastructure.mysql import mysql_adapter
from scripts.bootstrap_disposable_mysql_schema import bootstrap
from subsystems.access.authentication_session import AdminPrincipal

DATABASE = os.getenv("LABOR_UNION_TEST_MYSQL_DATABASE")
pytestmark = pytest.mark.skipif(not DATABASE, reason="requires disposable localhost development MySQL")


@pytest.fixture(scope="module")
def registry_database():
    host = os.environ["LABOR_UNION_TEST_MYSQL_HOST"]
    assert host in {"localhost", "127.0.0.1"}
    assert os.getenv("APP_ENV") == "development"
    database = f"{DATABASE}_registry"
    bootstrap(Namespace(host=host, port=int(os.environ["LABOR_UNION_TEST_MYSQL_PORT"]),
        user=os.environ["LABOR_UNION_TEST_MYSQL_USER"], password=os.environ["LABOR_UNION_TEST_MYSQL_PASSWORD"],
        database=database, confirm_database=database))
    with pytest.MonkeyPatch.context() as patch:
        patch.setitem(mysql_adapter.DB_CONFIG, "database", database)
        yield database


def create_app():
    app = FastAPI()
    for router in (registry_router, bootstrap_router, intake_router):
        app.include_router(router)
    principal = AdminPrincipal(id=None, username="local_bypass", display_name="Synthetic test", role="system_admin")
    for dependency in (require_persisted_admin, require_registry_reader, require_registry_writer, require_system_admin):
        app.dependency_overrides[dependency] = lambda: principal
    return app


def post(client, path, body, key):
    response = client.post(path, json=body, headers={"Idempotency-Key": key, "X-Correlation-ID": key})
    assert response.status_code == 200, response.text
    return response.json()["data"]


def seed_case(case_no, start_date):
    connection = mysql_adapter.get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("INSERT INTO clients(case_no,name,identity_status,service_type,created_at) VALUES (%s,'Synthetic Client','一般市民','連續服務','2026-09-01')", (case_no,))
            client_id = cursor.lastrowid
            cursor.execute("INSERT INTO orders(case_no,client_id,status,lifecycle_version,start_date,service_days,service_hours_per_day,floor_fee,requires_cooking,service_start_time,service_end_time,service_end_day_offset) VALUES (%s,%s,'待補件',0,%s,NULL,8,0,0,'09:00:00','17:00:00',0)", (case_no, client_id, start_date))
            cursor.execute("INSERT INTO beclass_records(bound_case_no,record_origin,survey_details) VALUES (%s,'admin_manual',%s)", (case_no, '{"特殊計費:胎數":"單胞胎"}'))
        connection.commit()
    finally:
        connection.close()


def assert_no_downstream(case_no):
    connection = mysql_adapter.get_connection()
    try:
        with connection.cursor() as cursor:
            for table in ("scheduling_aggregates", "client_finance_accounts", "payroll_case_accounts", "client_obligations", "staff_obligations"):
                cursor.execute(f"SELECT COUNT(*) AS n FROM {table} WHERE case_no=%s", (case_no,))
                assert cursor.fetchone()["n"] == 0, table
    finally:
        connection.close()


@pytest.mark.parametrize("start_date", [None, date(2026, 10, 1)])
def test_partial_registry_edits_then_real_terms_repair_and_bootstrap(registry_database, start_date):
    case_no = "REG-ENGINE-NO-START" if start_date is None else "REG-ENGINE-NO-DAYS"
    seed_case(case_no, start_date)
    with TestClient(create_app()) as client:
        base = f"/api/v1/admin/registries/clients/{case_no}"
        status_path = f"/api/v1/cases/{case_no}/architecture-bootstrap/status"
        blockers = client.get(status_path).json()["data"]["domain_blockers"]
        assert blockers == (["missing_start_date", "missing_service_days"] if start_date is None else ["missing_service_days"])
        for field, value in (("name", "Synthetic Updated"), ("phone", "0912345678"), ("address", "Synthetic Address")):
            detail_response = client.get(base)
            assert detail_response.status_code == 200, detail_response.text
            detail = detail_response.json()["data"]
            assert detail["finance"]["status"] == "not_ready"
            body = {"changes": {field: value}, "expected_version": detail["client"]["version"]}
            preview = post(client, base + "/profile/preview", body, f"{case_no}-{field}-preview")
            command = {**body, "preview_fingerprint": preview["preview_fingerprint"], "reason": "Synthetic single field edit"}
            key = f"{case_no}-{field}"
            saved = post(client, base + "/profile/apply", command, key)
            assert saved["readback"][field] == value and saved["changed_fields"] == [field]
            assert post(client, base + "/profile/apply", command, key)["replayed"]
            assert client.get(base).json()["data"]["client"]["values"][field] == value
            assert_no_downstream(case_no)
        body = {"changes": {"multi_birth_count": "雙胞胎"}, "expected_version": 0}
        preview = post(client, base + "/beclass/preview", body, case_no + "-birth-preview")
        command = {**body, "preview_fingerprint": preview["preview_fingerprint"], "reason": "Synthetic twins correction"}
        saved = post(client, base + "/beclass/apply", command, case_no + "-birth")
        assert saved["readback"]["multi_birth_count"] == "雙胞胎"
        assert post(client, base + "/beclass/apply", command, case_no + "-birth")["replayed"]
        assert_no_downstream(case_no)
        assert client.get(status_path).json()["data"]["domain_blockers"] == blockers
        repair = f"/api/v1/orders/{case_no}/intake-terms-bootstrap"
        intent = {"proposed_start_date": "2026-10-01", "proposed_service_days": 5}
        preview = post(client, repair + "/preview", intent, case_no + "-terms-preview")
        post(client, repair + "/apply", {**intent, "expected_lifecycle_version": preview["lifecycle_version"], "preview_fingerprint": preview["preview_fingerprint"], "reason": "Synthetic terms repair"}, case_no + "-terms")
        status = client.get(status_path).json()["data"]
        assert status["domain_blockers"] == []
        root = f"/api/v1/cases/{case_no}/architecture-bootstrap"
        intent = status["recommendation"]
        preview = post(client, root + "/preview", intent, case_no + "-bootstrap-preview")
        assert preview["payroll_policy_kind"] == "twins" and preview["payroll_hourly_rate_ntd"] == 450
        command = {**intent, "expected_order_version": preview["order_version"], "preview_fingerprint": preview["preview_fingerprint"], "reason": "Synthetic first use bootstrap"}
        saved = post(client, root + "/apply", command, case_no + "-bootstrap")
        assert saved["bootstrap_created"]
        assert post(client, root + "/apply", command, case_no + "-bootstrap") == saved
        assert client.get(status_path).json()["data"]["ready"]
        detail = client.get(base).json()["data"]
        assert detail["client"]["values"]["phone"] == "0912345678"
        assert detail["beclass"]["values"]["multi_birth_count"] == "雙胞胎"
        # Existing finance + no formal assignment follows the other corrected branch.
        body = {"changes": {"multi_birth_count": "單胞胎"}, "expected_version": detail["beclass"]["version"]}
        preview = post(client, base + "/beclass/preview", body, case_no + "-singleton-preview")
        post(client, base + "/beclass/apply", {**body, "preview_fingerprint": preview["preview_fingerprint"], "reason": "Synthetic existing account correction"}, case_no + "-singleton")
    connection = mysql_adapter.get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT policy_kind,hourly_rate_ntd FROM case_payroll_rate_policy_snapshots WHERE case_no=%s", (case_no,))
            assert cursor.fetchone() == {"policy_kind": "twins", "hourly_rate_ntd": 450}
            cursor.execute("SELECT client_hourly_rate_ntd FROM client_payment_terms WHERE case_no=%s", (case_no,))
            assert cursor.fetchone()["client_hourly_rate_ntd"] == 300
            cursor.execute("SELECT COUNT(*) AS n FROM staff_obligations WHERE case_no=%s", (case_no,))
            assert cursor.fetchone()["n"] == 0
    finally:
        connection.close()


def test_assigned_birth_corrections_keep_next_operations_readable(registry_database, pytestconfig):
    from datetime import datetime
    from pathlib import Path
    import runpy
    from infrastructure.mysql.assignment_plan_repository import MySqlAssignmentPlanRepository
    from infrastructure.mysql.assignment_plan_impact_ports import (
        MySqlClientFinanceAssignmentImpactPort, MySqlOrdersAssignmentImpactPort,
        MySqlPayrollAssignmentImpactPort,
    )
    from infrastructure.mysql.order_terms_read_model import load_preview_facts
    from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
    from subsystems.scheduling.assignment_plan_workflow import (
        AssignmentPlanWorkflow, AssignmentPlanPreviewRequest, AssignmentPlanApplyRequest,
    )
    from domains.scheduling.assignment_plan import AssignmentPlanIntent, AssignmentPlanSegmentIntent
    from shared_kernel.clock import FixedBusinessClock, TAIPEI_TIME_ZONE
    from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
    # Reuse the existing canonical paid-deposit/contract/lock fixture unchanged.
    fixture_path = Path(pytestconfig.rootpath) / "tests" / "test_assignment_plan_durable_mysql_e2e.py"
    fixture = runpy.run_path(str(fixture_path))
    connection = mysql_adapter.get_connection()
    try:
        staff_id = fixture["_seed_waiting_lock_case"](connection)
        clock = FixedBusinessClock(datetime(2026, 7, 31, 9, tzinfo=TAIPEI_TIME_ZONE))
        workflow = AssignmentPlanWorkflow(MySqlAssignmentPlanRepository(connection),
            MySqlClientFinanceAssignmentImpactPort(connection), MySqlPayrollAssignmentImpactPort(connection),
            MySqlOrdersAssignmentImpactPort(connection, clock), lambda: MySqlUnitOfWork(connection))
        intent = AssignmentPlanIntent((AssignmentPlanSegmentIntent(staff_id, date(2026, 8, 1), date(2026, 8, 2), (date(2026, 8, 1), date(2026, 8, 2))),))
        preview_request = AssignmentPlanPreviewRequest("AP-DURABLE-1", intent, CorrelationId("birth-assigned-preview"))
        preview = workflow.preview(preview_request)
        request = AssignmentPlanApplyRequest("AP-DURABLE-1", intent,
            ExpectedVersion(preview.order_version), ExpectedVersion(preview.scheduling_version),
            ExpectedVersion(preview.client_finance_version), ExpectedVersion(preview.payroll_version),
            preview.fingerprint, IdempotencyKey("birth-assigned"), ActorContext("engine-test"),
            "Synthetic correction setup", CorrelationId("birth-assigned"))
        receipt = workflow.apply(request)
        assert workflow.apply(request) == receipt
        with TestClient(create_app()) as client:
            path = "/api/v1/admin/registries/clients/AP-DURABLE-1/beclass"
            for version, birth_count in enumerate(("雙胞胎", "單胞胎", "雙胞胎")):
                body = {"changes": {"multi_birth_count": birth_count}, "expected_version": version}
                key = f"assigned-birth-{version}"
                preview = post(client, path + "/preview", body, key + "-preview")
                command = {**body, "preview_fingerprint": preview["preview_fingerprint"], "reason": "Synthetic assigned birth correction"}
                saved = post(client, path + "/apply", command, key)
                assert saved["readback"]["multi_birth_count"] == birth_count
                assert post(client, path + "/apply", command, key)["replayed"]
                connection.rollback()  # End the observer's previous read snapshot.
                with connection.cursor() as cursor:
                    facts = load_preview_facts(cursor, "AP-DURABLE-1")
                    assert len(facts.payroll.existing_obligations) == 1
                    assert facts.payroll.existing_obligations[0].outstanding_amount.amount == (7200 if birth_count == "雙胞胎" else 4800)
                workflow.preview(preview_request)  # The next formal action still works.
        with connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) AS n FROM staff_obligations WHERE case_no='AP-DURABLE-1' AND status='cancelled'")
            assert cursor.fetchone()["n"] == 3
            cursor.execute("SELECT hourly_rate_ntd FROM assignment_payroll_rate_snapshots s JOIN case_staff_assignments a ON a.id=s.assignment_id WHERE a.case_no='AP-DURABLE-1'")
            assert all(row["hourly_rate_ntd"] == 300 for row in cursor.fetchall())
    finally:
        connection.close()
