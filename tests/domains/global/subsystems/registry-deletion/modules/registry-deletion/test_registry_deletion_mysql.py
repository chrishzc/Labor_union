"""Opt-in localhost engine proof. Creates a new owned lu_test_* fixture; never resets/drops.

REGISTRY_DELETION_MYSQL=1 uses the configured development connection in memory.
Canonical table DDL and bounded representative relations are
installed in the new fixture; no existing database data is read or changed.
"""

import os
from pathlib import Path
import re
from threading import Event, Thread
from uuid import uuid4

import pymysql
import pytest

from infrastructure.mysql.mysql_adapter import DB_CONFIG
from scripts.init_db import load_schema_paths
from infrastructure.mysql.nas_mutations import PROCEDURES
from infrastructure.mysql.registry_deletion_repository import MySqlRegistryDeletionRepository
from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
from shared_kernel.identities import ActorContext
from subsystems.registry_deletion import RegistryDeletionApplication, RegistryDeletionConflict

pytestmark = pytest.mark.skipif(os.getenv("REGISTRY_DELETION_MYSQL") != "1", reason="explicit localhost deletion-engine opt-in required")


@pytest.fixture(scope="module")
def engine():
    assert os.getenv("APP_ENV", "development") == "development"
    assert DB_CONFIG["host"] in {"127.0.0.1", "localhost", "::1"}
    name = "lu_test_registry_delete_" + uuid4().hex[:12]
    print("owned_engine_fixture=" + name)
    config = dict(DB_CONFIG, database=None, cursorclass=pymysql.cursors.DictCursor, connect_timeout=5, read_timeout=10, write_timeout=10)
    con = pymysql.connect(**config)
    ddl = Path("db/fresh_schema/labor_union_fresh_current.sql").read_text(encoding="utf-8")
    with con.cursor() as cursor:
        cursor.execute("SELECT schema_name FROM information_schema.schemata WHERE schema_name=%s", (name,))
        assert cursor.fetchone() is None
        cursor.execute(f"CREATE DATABASE `{name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
        cursor.execute(f"USE `{name}`")
        load_schema_paths(cursor, [Path("db/fresh_schema/labor_union_fresh_current.sql")])
        cursor.execute("SELECT COUNT(*) AS n FROM information_schema.TRIGGERS WHERE TRIGGER_SCHEMA=DATABASE()")
        assert cursor.fetchone()["n"] >= 350
        procedure = "lu_nas_delete_unsigned_case_v2"
        parameters, body, _ = PROCEDURES[procedure]
        cursor.execute(f"CREATE PROCEDURE `{procedure}`({parameters}) SQL SECURITY INVOKER BEGIN {body} END")
    con.commit(); con.close()
    config["database"] = name
    return config


@pytest.fixture
def connection(engine):
    con = pymysql.connect(**engine)
    with con.cursor() as cursor:
        cursor.execute("SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ")
    yield con
    con.rollback(); con.close()


def seed_staff(con):
    with con.cursor() as cursor:
        cursor.execute("INSERT INTO staff(name) VALUES ('Deletion fixture')")
        result = cursor.lastrowid
    con.commit()
    return result


def seed_case(con, *, staff=None):
    identity = "RD-" + uuid4().hex[:12]
    with con.cursor() as cursor:
        cursor.execute("INSERT INTO clients(case_no,name) VALUES (%s,'Deletion fixture')", (identity,))
        client = cursor.lastrowid
        cursor.execute("INSERT INTO orders(case_no,client_id,staff_id) VALUES (%s,%s,%s)", (identity, client, staff))
    con.commit()
    return identity, client


def app(con):
    return RegistryDeletionApplication(MySqlRegistryDeletionRepository(con), lambda: MySqlUnitOfWork(con))


def delete(application, kind, identity, key=None):
    preview = application.preview(kind, str(identity))
    return application.apply(kind, str(identity), expected_version=preview.version,
        expected_client_version=preview.client_version, key=key or uuid4().hex,
        actor=ActorContext("admin:1", ()), correlation="registry-deletion-engine")


def relations(con, case, client, staff):
    with con.cursor() as c:
        c.execute("INSERT INTO staff_bookings(staff_id,client_id,start_date,end_date) VALUES (%s,%s,'2026-10-29','2026-10-30')", (staff, client))
        c.execute("INSERT INTO client_finance_accounts(case_no) VALUES (%s)", (case,))
        c.execute("INSERT INTO staff_schedule(staff_id,case_no,work_date) VALUES (%s,%s,'2026-10-29')", (staff, case))
        c.execute("INSERT INTO caregiver_matching_plans(case_no,start_date,end_date,created_by) VALUES (%s,'2026-10-29','2026-10-30','fixture')", (case,))
        plan = c.lastrowid
        c.execute("INSERT INTO caregiver_matching_plan_segments(plan_id,segment_order,staff_id,assigned_start_date,assigned_end_date) VALUES (%s,1,%s,'2026-10-29','2026-10-30')", (plan, staff))
        segment = c.lastrowid
        obligation = uuid4().hex
        c.execute("INSERT INTO client_obligation_events(obligation_identity,case_no,obligation_type,direction,event_type,before_amount_ntd,after_amount_ntd,source_event_identity,expected_account_version,idempotency_key,actor,reason) VALUES (%s,%s,'deposit','receivable_from_client','established',0,100,%s,0,%s,'fixture','fixture')", (obligation, case, uuid4().hex, uuid4().hex))
        event = c.lastrowid
        c.execute("INSERT INTO client_obligations(obligation_identity,case_no,obligation_type,direction,amount_due_ntd,status,current_event_id,projection_version) VALUES (%s,%s,'deposit','receivable_from_client',100,'open',%s,1)", (obligation, case, event))
        derived = uuid4().hex
        c.execute("INSERT INTO client_obligation_events(obligation_identity,case_no,obligation_type,direction,event_type,before_amount_ntd,after_amount_ntd,source_event_identity,expected_account_version,idempotency_key,actor,reason,source_obligation_identity) VALUES (%s,%s,'adjustment','receivable_from_client','established',0,100,%s,0,%s,'fixture','fixture',%s)", (derived, case, uuid4().hex, uuid4().hex, obligation))
        derived_event = c.lastrowid
        c.execute("INSERT INTO client_obligations(obligation_identity,case_no,obligation_type,direction,amount_due_ntd,status,current_event_id,projection_version,source_obligation_identity) VALUES (%s,%s,'adjustment','receivable_from_client',100,'open',%s,1,%s)", (derived, case, derived_event, obligation))
    con.commit()
    return plan, segment


def sign(con, case, plan, segment, scope):
    with con.cursor() as c:
        c.execute("INSERT INTO media_assets(category,storage_key,mime_type,file_size,sha256) VALUES ('contract',%s,'application/pdf',1,%s)", (uuid4().hex, "a" * 64))
        asset = c.lastrowid
        target = uuid4().hex
        c.execute("INSERT INTO contract_document_versions(case_no,document_scope,document_role,matching_plan_id,matching_segment_id,document_target_key,media_asset_id,version_number,created_by,template_key,template_sha256,mapping_sha256,facts_snapshot_sha256) VALUES (%s,%s,'template_generated',%s,%s,%s,%s,1,'fixture','template',%s,%s,%s)", (case, scope, plan, segment if scope == "staff_segment" else None, target, asset, "a"*64, "a"*64, "a"*64))
        source = c.lastrowid
        c.execute("INSERT INTO contract_document_versions(case_no,document_scope,document_role,matching_plan_id,matching_segment_id,document_target_key,media_asset_id,version_number,created_by,source_document_version_id) VALUES (%s,%s,'signed_return',%s,%s,%s,%s,2,'fixture',%s)", (case, scope, plan, segment if scope == "staff_segment" else None, target, asset, source))
        document = c.lastrowid
        c.execute("INSERT INTO contract_signing_events(case_no,document_version_id,matching_plan_id,matching_segment_id,event_type,event_key,actor,payload) VALUES (%s,%s,%s,%s,'signed_received',%s,'fixture',JSON_OBJECT())", (case, document, plan, segment if scope == "staff_segment" else None, uuid4().hex))
    con.commit()


def draft_task(con, case, plan, segment):
    with con.cursor() as c:
        c.execute("INSERT INTO media_assets(category,storage_key,mime_type,file_size,sha256) VALUES ('contract',%s,'application/pdf',1,%s)", (uuid4().hex, "a"*64))
        asset = c.lastrowid
        c.execute("INSERT INTO contract_document_versions(case_no,document_scope,document_role,matching_plan_id,matching_segment_id,document_target_key,media_asset_id,version_number,created_by,template_key,template_sha256,mapping_sha256,facts_snapshot_sha256) VALUES (%s,'staff_segment','template_generated',%s,%s,%s,%s,1,'fixture','template',%s,%s,%s)", (case, plan, segment, uuid4().hex, asset, "a"*64, "a"*64, "a"*64))
        document = c.lastrowid
        c.execute("INSERT INTO line_delivery_tasks(recipient_type,recipient_identity,message_kind,payload_snapshot,payload_fingerprint,scheduled_at_utc,source_aggregate_type,source_aggregate_identity,idempotency_key,correlation_id) VALUES ('user','synthetic','text',JSON_OBJECT('type','text','text','Synthetic'),%s,'2026-10-29','contract_document_version',%s,%s,%s)", ("a"*64, f"{case}:{document}", uuid4().hex, uuid4().hex))
        task = c.lastrowid
    con.commit()
    return task, asset


@pytest.mark.parametrize("nas", [False, True])
def test_unsigned_relations_deleted_while_other_case_and_staff_remain(connection, monkeypatch, nas):
    monkeypatch.setenv("DEPLOYMENT_PROFILE", "nas" if nas else "development")
    staff = seed_staff(connection)
    case, client = seed_case(connection, staff=staff)
    plan, segment = relations(connection, case, client, staff)
    task, asset = draft_task(connection, case, plan, segment)
    other, other_client = seed_case(connection)
    other_plan, other_segment = relations(connection, other, other_client, seed_staff(connection))
    other_task, _ = draft_task(connection, other, other_plan, other_segment)
    application = app(connection)
    assert not application.preview("case", case).blockers
    key = uuid4().hex
    assert delete(application, "case", case, key).deleted
    assert application.apply("case", case, expected_version=0, expected_client_version=0, key=key,
        actor=ActorContext("admin:1", ()), correlation="replay").replayed
    with connection.cursor() as c:
        for table in ("orders", "staff_schedule", "client_finance_accounts", "client_obligations", "client_obligation_events", "caregiver_matching_plans"):
            c.execute(f"SELECT 1 FROM `{table}` WHERE case_no=%s", (case,)); assert c.fetchone() is None
            c.execute(f"SELECT 1 FROM `{table}` WHERE case_no=%s", (other,)); assert c.fetchone() is not None
        c.execute("SELECT 1 FROM caregiver_matching_plan_segments WHERE id=%s", (segment,)); assert c.fetchone() is None
        c.execute("SELECT 1 FROM clients WHERE id=%s", (client,)); assert c.fetchone() is None
        c.execute("SELECT 1 FROM staff WHERE id=%s", (staff,)); assert c.fetchone() is not None
        c.execute("SELECT 1 FROM line_delivery_tasks WHERE id=%s", (task,)); assert c.fetchone() is None
        c.execute("SELECT 1 FROM line_delivery_tasks WHERE id=%s", (other_task,)); assert c.fetchone() is not None
        c.execute("SELECT 1 FROM media_assets WHERE id=%s", (asset,)); assert c.fetchone() is not None
        c.execute("SELECT @@foreign_key_checks AS enabled"); assert c.fetchone()["enabled"] == 1


@pytest.mark.parametrize("nas", [False, True])
@pytest.mark.parametrize("scope", ["staff_segment", "client_contract", "order_completion"])
def test_signed_return_or_completion_blocks_everything_including_old_plan(connection, monkeypatch, nas, scope):
    monkeypatch.setenv("DEPLOYMENT_PROFILE", "nas" if nas else "development")
    staff = seed_staff(connection)
    case, client = seed_case(connection)
    plan, segment = relations(connection, case, client, staff)
    if scope == "order_completion":
        with connection.cursor() as c:
            c.execute("INSERT INTO order_contract_flow_events(case_no,contract_identity,event_type,actor,reason,idempotency_key) VALUES (%s,%s,'contract_completed','fixture','fixture',%s)", (case, uuid4().hex, uuid4().hex))
        connection.commit()
    else:
        sign(connection, case, plan, segment, scope)
        with connection.cursor() as c:
            c.execute("UPDATE caregiver_matching_plans SET is_active=NULL,status='superseded' WHERE id=%s", (plan,))
        connection.commit()
    assert app(connection).preview("case", case).blockers
    if nas:
        with connection.cursor() as c:
            with pytest.raises(pymysql.err.OperationalError, match="registry_deletion_signed"):
                c.callproc("lu_nas_delete_unsigned_case_v2", (case, 0, client, 0, "blocked-fixture"))
        connection.rollback()
    with pytest.raises(RegistryDeletionConflict, match="signed"):
        delete(app(connection), "case", case)
    with connection.cursor() as c:
        c.execute("SELECT 1 FROM orders WHERE case_no=%s", (case,)); assert c.fetchone() is not None
        c.execute("SELECT 1 FROM client_obligations WHERE case_no=%s", (case,)); assert c.fetchone() is not None


@pytest.mark.parametrize("nas", [False, True])
def test_shared_client_and_other_order_are_preserved(connection, monkeypatch, nas):
    monkeypatch.setenv("DEPLOYMENT_PROFILE", "nas" if nas else "development")
    first, client = seed_case(connection)
    second, _ = seed_case(connection)
    with connection.cursor() as c:
        c.execute("UPDATE orders SET client_id=%s WHERE case_no=%s", (client, second))
    connection.commit()
    assert delete(app(connection), "case", second).deleted
    with connection.cursor() as c:
        c.execute("SELECT 1 FROM clients WHERE id=%s", (client,)); assert c.fetchone() is not None
        c.execute("SELECT 1 FROM orders WHERE case_no=%s", (first,)); assert c.fetchone() is not None


@pytest.mark.parametrize("nas", [False, True])
def test_receipt_failure_rolls_back_all_relations_and_claim(connection, monkeypatch, nas):
    monkeypatch.setenv("DEPLOYMENT_PROFILE", "nas" if nas else "development")
    staff = seed_staff(connection)
    case, client = seed_case(connection)
    relations(connection, case, client, staff)
    class FailedAudit(MySqlRegistryDeletionRepository):
        def save_receipt(self, *_): raise RuntimeError("fixture audit unavailable")
    application = RegistryDeletionApplication(FailedAudit(connection), lambda: MySqlUnitOfWork(connection))
    key = uuid4().hex
    with pytest.raises(RuntimeError, match="audit unavailable"):
        delete(application, "case", case, key)
    with connection.cursor() as c:
        for table in ("orders", "client_obligations", "client_obligation_events", "caregiver_matching_plans"):
            c.execute(f"SELECT 1 FROM `{table}` WHERE case_no=%s", (case,)); assert c.fetchone() is not None
        c.execute("SELECT 1 FROM application_command_claims WHERE idempotency_key=%s", (key,)); assert c.fetchone() is None


def test_signed_insert_cannot_race_locked_guard(connection, engine):
    case, _ = seed_case(connection)
    started, finished = Event(), Event()
    outcome = []
    def insert_completion():
        other = pymysql.connect(**engine)
        try:
            with other.cursor() as c:
                c.execute("SET SESSION innodb_lock_wait_timeout=1")
                started.set()
                c.execute("INSERT INTO order_contract_flow_events(case_no,contract_identity,event_type,actor,reason,idempotency_key) VALUES (%s,%s,'contract_completed','fixture','fixture',%s)", (case, uuid4().hex, uuid4().hex))
            other.commit(); outcome.append("inserted")
        except pymysql.err.OperationalError as error:
            outcome.append(error.args[0]); other.rollback()
        finally:
            other.close(); finished.set()
    with MySqlUnitOfWork(connection):
        assert not MySqlRegistryDeletionRepository(connection).load("case", case, for_update=True).blockers
        thread = Thread(target=insert_completion); thread.start()
        assert started.wait(3) and finished.wait(5)
        thread.join(1)
        assert outcome == [1205]


@pytest.mark.parametrize("mode", ["no_context", "fake_key", "wrong_case", "signed"])
def test_full_database_guards_reject_outside_the_active_unsigned_case(connection, mode):
    staff = seed_staff(connection)
    case, client = seed_case(connection)
    plan, segment = relations(connection, case, client, staff)
    key = uuid4().hex
    if mode == "signed": sign(connection, case, plan, segment, "staff_segment")
    with connection.cursor() as c:
        if mode in ("wrong_case", "signed"):
            c.execute("INSERT INTO application_command_claims(idempotency_key,command_family,aggregate_identity,command_fingerprint,correlation_id) VALUES (%s,'registry_delete/v1',%s,%s,'guard-probe')", (key, 'case:'+('OTHER' if mode=='wrong_case' else case), 'a'*64))
        if mode != "no_context":
            c.execute("SET @registry_delete_key=%s,@registry_delete_case=%s,@registry_delete_client=%s,@registry_delete_client_owned=1,@registry_delete_tasks='[]'", (key,case,client))
        with pytest.raises(pymysql.err.OperationalError) as caught:
            c.execute("DELETE FROM client_obligation_events WHERE case_no=%s", (case,))
        assert caught.value.args[0] == 1644
        c.execute("SET @registry_delete_key=NULL,@registry_delete_case=NULL,@registry_delete_client=NULL,@registry_delete_client_owned=NULL,@registry_delete_tasks=NULL")
    connection.rollback()


def test_authorized_context_cannot_modify_history_and_is_cleared_on_rollback(connection):
    staff = seed_staff(connection)
    case, client = seed_case(connection)
    relations(connection, case, client, staff)
    class AttemptHistoryRewrite(MySqlRegistryDeletionRepository):
        def delete(self, target):
            with self._connection.cursor() as c:
                c.execute("SET @registry_delete_key=%s,@registry_delete_case=%s,@registry_delete_client=%s,@registry_delete_client_owned=1,@registry_delete_tasks='[]'", (self._command_key,case,client))
                try:
                    c.execute("UPDATE client_obligation_events SET after_amount_ntd=after_amount_ntd+1 WHERE case_no=%s", (case,))
                finally:
                    c.execute("SET @registry_delete_key=NULL,@registry_delete_case=NULL,@registry_delete_client=NULL,@registry_delete_client_owned=NULL,@registry_delete_tasks=NULL")
    application = RegistryDeletionApplication(AttemptHistoryRewrite(connection), lambda: MySqlUnitOfWork(connection))
    with pytest.raises(pymysql.err.OperationalError) as caught:
        delete(application, "case", case)
    assert caught.value.args[0] == 1644
    with connection.cursor() as c:
        c.execute("SELECT @registry_delete_key AS context")
        assert c.fetchone()["context"] is None
        c.execute("SELECT COUNT(*) AS n FROM client_obligation_events WHERE case_no=%s", (case,))
        assert c.fetchone()["n"] == 2


def test_legacy_event_guard_reproduces_failure_and_scoped_guard_fixes_it(connection):
    from scripts.sql_statements import split_sql
    staff = seed_staff(connection)
    case, client = seed_case(connection)
    relations(connection, case, client, staff)
    name = "trg_client_obligation_events_before_update"
    statement = next(s for s in split_sql(Path("db/schema_parts/1060_registry_case_deletion_guards.sql").read_text(encoding="utf-8")) if s.startswith("CREATE TRIGGER `" + name + "`"))
    with connection.cursor() as c:
        c.execute("DROP TRIGGER `" + name + "`")
        c.execute("CREATE TRIGGER `" + name + "` BEFORE UPDATE ON client_obligation_events FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='client_obligation_events records cannot be updated'")
    try:
        with pytest.raises(pymysql.err.OperationalError) as caught:
            delete(app(connection), "case", case)
        assert caught.value.args[0] == 1644
    finally:
        with connection.cursor() as c:
            c.execute("DROP TRIGGER `" + name + "`")
            c.execute(statement)
    assert delete(app(connection), "case", case).deleted
    with connection.cursor() as c:
        c.execute("SELECT @registry_delete_key AS context")
        assert c.fetchone()["context"] is None
