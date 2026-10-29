"""Real isolated MySQL evidence for annual issuance and registration approval."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import os
import hashlib
import json
from pathlib import Path
from uuid import uuid4

import pymysql
import pytest

from infrastructure.mysql.mysql_adapter import _database_config_from_environment
from infrastructure.mysql.non_citizen_case_number_repository import allocate_non_citizen_case_number
from scripts.initialize_nas_schema import initialize, source_schema_plan


pytestmark = pytest.mark.skipif(os.getenv("NON_CITIZEN_MYSQL") != "1", reason="explicit isolated localhost qualification")


class _PrivateDatabaseConfig(dict):
    def __repr__(self):
        return "<isolated localhost test configuration; credentials redacted>"


def _bootstrap_schema(config, name, receipt_root):
    # Capture and verify the current source plan. Other workspace tasks may
    # legitimately be regenerating the shared compact cache at the same time.
    baseline = os.getenv("NON_CITIZEN_SCHEMA_BASELINE")
    if baseline:
        # Explicit fixed input for a scoped run, never a runtime fallback.
        from scripts.sql_statements import split_sql
        from scripts.verify_validation_schema_manifest import _effective_database_objects
        root = Path(baseline)
        manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
        sql_path = root / "schema.sql"
        assert hashlib.sha256(sql_path.read_bytes()).hexdigest() == manifest["sql_sha256"]
        statements = split_sql(sql_path.read_text(encoding="utf-8"))
        assert len(statements) == manifest["statement_count"]
        plan = {"assembly_id": manifest["profile_id"], "release_id": manifest["release_id"],
                "schema_parts": [sql_path.name], "expected": _effective_database_objects([sql_path]),
                "steps": [{"artifact": sql_path.name, "ordinal": i, "sql": sql} for i, sql in enumerate(statements, 1)]}
    else:
        plan = source_schema_plan()
    server = {k: v for k, v in config.items() if k not in {"database", "cursorclass"}}
    assert name.startswith(("lu_test_non_citizen_", "lu_test_nc_preserve_source_"))
    with pymysql.connect(**server, autocommit=True) as connection:
        with connection.cursor() as cursor:
            cursor.execute(f"CREATE DATABASE `{name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
    if baseline:
        from scripts.verify_validation_schema_manifest import verify_database_objects
        with pymysql.connect(**{**config, "database": name, "autocommit": True}) as connection:
            with connection.cursor() as cursor:
                for step in plan["steps"]:
                    cursor.execute(step["sql"])
                assert not verify_database_objects(cursor, name, plan["expected"])
    else:
        initialization_config = {key: value for key, value in config.items() if key != "cursorclass"}
        initialize({**initialization_config, "database": name}, plan, apply=True, receipt_root=receipt_root)


@pytest.fixture(scope="module")
def nc_database(tmp_path_factory):
    config = _database_config_from_environment()
    assert config["host"] in {"127.0.0.1", "localhost"}
    assert os.getenv("APP_ENV", "development") == "development"
    name = "lu_test_non_citizen_" + uuid4().hex[:12]
    target = _PrivateDatabaseConfig({**config, "database": name, "cursorclass": pymysql.cursors.DictCursor})
    try:
        _bootstrap_schema(config, name, tmp_path_factory.mktemp("non_citizen_schema"))
        yield target
    finally:
        assert name.startswith("lu_test_non_citizen_")
        with pymysql.connect(**{k: v for k, v in target.items() if k != "database"}) as connection:
            with connection.cursor() as cursor:
                cursor.execute(f"DROP DATABASE `{name}`")


def test_real_fresh_counter_and_approval_year(nc_database):
    with pymysql.connect(**nc_database) as connection:
        before = datetime(2026, 12, 31, 15, 59, tzinfo=timezone.utc)
        after = datetime(2026, 12, 31, 16, 0, tzinfo=timezone.utc)
        assert allocate_non_citizen_case_number(connection, before) == "A115001"
        assert allocate_non_citizen_case_number(connection, before) == "A115002"
        assert allocate_non_citizen_case_number(connection, after) == "A116001"
        connection.rollback()


def test_real_concurrent_allocations_are_unique(nc_database):
    def issue(_):
        with pymysql.connect(**nc_database) as connection:
            number = allocate_non_citizen_case_number(connection, datetime(2026, 10, 29, tzinfo=timezone.utc))
            connection.commit()
            return number
    with ThreadPoolExecutor(max_workers=2) as executor:
        assert set(executor.map(issue, range(2))) == {"A115001", "A115002"}


def test_real_failed_transaction_does_not_commit_counter(nc_database):
    instant = datetime(2027, 10, 29, tzinfo=timezone.utc)
    with pymysql.connect(**nc_database) as connection:
        assert allocate_non_citizen_case_number(connection, instant) == "A116001"
        connection.rollback()
    with pymysql.connect(**nc_database) as connection:
        assert allocate_non_citizen_case_number(connection, instant) == "A116001"
        connection.rollback()


def _registration_intent():
    from domains.case_import.provisional_registration import ProvisionalRegistrationIntent
    return ProvisionalRegistrationIntent(
        line_user_id="U-nc-" + uuid4().hex, name="Synthetic non-citizen applicant", phone="0900000000",
        expected_date="2026-11-01", service_days=10, address="合成測試地址", gender="女",
        email="synthetic@example.test", birth_date="1990-01-01", tel=None, ext=None, city="新竹縣",
        zip_code=None, id_number=None, liff_config_revision=None,
        registration_kind="non_citizen", service_start_date="2026-11-02", service_time="8小時 08:00-17:00",
        residence_type="公寓", delivery_type="自然產", notes="無", line_id="無", service_type="連續服務", baby_info="合成測試寶寶",
        survey_details={"服務時間內是否有其他寶寶":"無", "是否需要下廚":"需要下廚",
                        "補助款退款:銀行代號+分行代號":"0000000", "銀行帳號":"000000000000"},
    )


def _submit(connection):
    from infrastructure.mysql.provisional_registration_repository import MySqlProvisionalRegistrationRepository
    from domains.case_import.provisional_registration import build_provisional_registration_candidate
    repository = MySqlProvisionalRegistrationRepository(connection, now=lambda: datetime(2026, 10, 29, 5, tzinfo=timezone.utc))
    receipt = repository.apply(build_provisional_registration_candidate(_registration_intent()))
    assert receipt.client_id is None and receipt.case_no is None
    connection.commit()
    return repository, receipt.registration_id


def test_submission_then_approval_creates_complete_case_once(nc_database):
    with pymysql.connect(**nc_database) as connection:
        repository, registration_id = _submit(connection)
        receipt = repository.approve(registration_id, 1, "synthetic-admin")
        assert receipt.case_no.startswith("A115")
        connection.commit()
        snapshot = repository.load_application(registration_id)
        assert snapshot.case_no == receipt.case_no and snapshot.approved_at_utc is not None
        with connection.cursor() as cursor:
            cursor.execute("SELECT o.client_id,o.service_days,o.service_hours_per_day,c.identity_status "
                           "FROM orders o JOIN clients c ON c.id=o.client_id WHERE o.case_no=%s", (receipt.case_no,))
            row = cursor.fetchone()
            assert row["client_id"] == receipt.client_id
            assert row["service_days"] == 10 and row["service_hours_per_day"] == 8
            assert row["identity_status"] == "非市民"
            cursor.execute("SELECT deposit_service_days FROM client_payment_terms WHERE case_no=%s", (receipt.case_no,))
            assert cursor.fetchone()["deposit_service_days"] == 5
        replay = repository.approve(registration_id, 1, "another-admin")
        assert replay.replayed and replay.case_no == receipt.case_no
        connection.rollback()


def test_approval_downstream_failure_rolls_back_complete_case(nc_database, monkeypatch):
    with pymysql.connect(**nc_database) as connection:
        repository, registration_id = _submit(connection)
        issue = repository._issue_non_citizen_case
        issued = []
        def fail_after_roots(*args):
            issued.append(issue(*args))
            raise RuntimeError("synthetic failure after case roots")
        monkeypatch.setattr(repository, "_issue_non_citizen_case", fail_after_roots)
        with pytest.raises(RuntimeError, match="synthetic failure"):
            repository.approve(registration_id, 1, "synthetic-admin")
        connection.rollback()
        snapshot = repository.load_application(registration_id)
        assert snapshot.client_id is None and snapshot.case_no is None and snapshot.version == 1
        with connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) AS count FROM orders WHERE case_no=%s", (issued[0],))
            assert cursor.fetchone()["count"] == 0


def test_concurrent_approval_of_same_application_returns_one_case(nc_database):
    with pymysql.connect(**nc_database) as connection:
        _, registration_id = _submit(connection)
    def approve(_):
        from infrastructure.mysql.provisional_registration_repository import MySqlProvisionalRegistrationRepository
        with pymysql.connect(**nc_database) as connection:
            receipt = MySqlProvisionalRegistrationRepository(connection, now=lambda: datetime(2026, 10, 29, 5, tzinfo=timezone.utc)).approve(registration_id, 1, "synthetic-admin")
            connection.commit()
            return receipt
    with ThreadPoolExecutor(max_workers=2) as executor:
        receipts = list(executor.map(approve, range(2)))
    assert receipts[0].case_no == receipts[1].case_no
    assert sum(receipt.replayed for receipt in receipts) == 1


def test_line_outer_uow_approves_complete_case_and_binding(nc_database):
    from domains.line.identities import LineUserId
    from infrastructure.mysql.line_unit_of_work import ManagedLineMySqlUnitOfWork
    from infrastructure.mysql.provisional_registration_repository import MySqlProvisionalRegistrationRepository
    from shared_kernel.identities import CorrelationId
    from subsystems.line.identity_application import LineIdentityApplication
    now = lambda: datetime(2026, 10, 29, 5, tzinfo=timezone.utc)
    def uow():
        connection = pymysql.connect(**nc_database)
        unit = ManagedLineMySqlUnitOfWork(connection)
        unit.provisional_registrations = MySqlProvisionalRegistrationRepository(connection, now=now)
        return unit
    application = LineIdentityApplication(uow, now)
    intent = _registration_intent()
    user = LineUserId(intent.line_user_id)
    preview = application.preview_registration(intent, user, None)
    pending, _ = application.apply_registration(intent, user, None, preview.expected_binding_version,
                                                preview.preview_fingerprint, CorrelationId("synthetic-nc-submit"))
    assert pending.case_no is None
    receipt, binding = application.approve_registration(pending.registration_id, 1, "synthetic-admin",
                                                       CorrelationId("synthetic-nc-approve"))
    assert receipt.case_no and binding.status.value == "bound"
    assert application.registration_application(pending.registration_id).case_no == receipt.case_no


def test_approved_case_reuses_finance_contract_and_reporting(nc_database):
    from datetime import date
    from dataclasses import replace
    from domains.case_import.provisional_registration import build_provisional_registration_candidate
    from infrastructure.mysql.provisional_registration_repository import MySqlProvisionalRegistrationRepository
    from infrastructure.mysql.contract_full_preview_repository import MySqlFullContractProjectionRepository
    from infrastructure.mysql.client_payments_query_repository import MySqlClientFinanceQueryRepository
    from infrastructure.mysql.weekly_operations_report_query_adapter import MySqlWeeklyOperationsReportQueryAdapter
    from subsystems.reporting.weekly_operations_report_query import WeeklyOperationsReportQuery
    from subsystems.client_finance.virtual_account_resolution import build_client_virtual_account
    with pymysql.connect(**nc_database) as connection:
        repository = MySqlProvisionalRegistrationRepository(connection, now=lambda: datetime(2026, 12, 31, 16, tzinfo=timezone.utc))
        pending = repository.apply(build_provisional_registration_candidate(replace(_registration_intent(), service_days=30,
                    expected_date="2027-01-01", service_start_date="2027-01-02")))
        receipt = repository.approve(pending.registration_id, 1, "synthetic-admin")
        connection.commit()
        assert receipt.case_no.startswith("A116")
        facts = MySqlFullContractProjectionRepository(connection).load_client_projection(receipt.case_no).facts
        assert facts["identity_status"] == "非市民"
        assert facts["deposit_amount"] == 12800
        assert facts["first_payment_amount"] == 38400
        assert facts["second_payment_amount"] == 25600
        assert str(facts["second_payment_due_date"]) == "2027-01-17"
        assert build_client_virtual_account(receipt.case_no).startswith("99781699116")
        categories = {row.case_no: row.category for row in MySqlClientFinanceQueryRepository(connection).query_categories()}
        assert categories[receipt.case_no] == "non_citizen"
        source = MySqlWeeklyOperationsReportQueryAdapter(connection)
        query = WeeklyOperationsReportQuery(source, lambda: datetime(2027, 1, 1, tzinfo=timezone.utc))
        assert receipt.case_no not in [fact.case_no for fact in source.list_case_facts(date(2027,1,1), date(2027,12,31))]
        assert query.query_case_statistics(2027, month=1, case_category="non_citizen").summary.application_count == 1
        assert query.query_case_statistics(2026, month=12, case_category="non_citizen").summary.application_count >= 0


def test_counter_preserve_upgrade_dump_restore_and_exact_replay(tmp_path, nc_database):
    from scripts import migrate_preserved_database_additive_schema as migration
    server = {k: v for k, v in nc_database.items() if k not in {"database", "cursorclass", "charset"}}
    config = migration.DatabaseConfig(**server)
    source = "lu_test_nc_preserve_source_" + uuid4().hex[:10]
    candidate = "lu_test_nc_preserve_candidate_" + uuid4().hex[:10]
    try:
        # The current compact schema is the supported terminal schema. Omit
        # only the new empty counter to construct its exact predecessor;
        # historical numbered DDL also contains retired foreign-key sources.
        _bootstrap_schema(nc_database, source, tmp_path / "source-schema")
        with config.connect(source) as connection:
            with connection.cursor() as cursor:
                cursor.execute("DROP TABLE non_citizen_case_sequences")
                cursor.execute("INSERT INTO clients(name) VALUES ('Synthetic preservation fixture')")
                old_id = cursor.lastrowid
            connection.commit()
        container = os.getenv("NON_CITIZEN_MYSQL_CONTAINER", "mysql_db")
        migration.create_source_dump(config, source, tmp_path / "source.sql", tmp_path / "backup.json", mysql_container=container)
        migration.restore_candidate(config, source, candidate, tmp_path / "source.sql", tmp_path / "backup.json",
                                    tmp_path / "restore.json", mysql_container=container)
        sql = Path("db/schema_parts/1059_non_citizen_case_sequences.sql").read_text(encoding="utf-8")
        from scripts.sql_statements import split_sql
        with config.connect(candidate) as connection:
            with connection.cursor() as cursor:
                for _ in range(2):
                    for statement in split_sql(sql): cursor.execute(statement)
                cursor.execute("SELECT name FROM clients WHERE id=%s", (old_id,))
                assert cursor.fetchone()["name"] == "Synthetic preservation fixture"
            assert allocate_non_citizen_case_number(connection, datetime(2026, 10, 29, tzinfo=timezone.utc)) == "A115001"
            connection.commit()
        snapshot = migration._schema_snapshot(config, candidate, owned_part="1059_non_citizen_case_sequences.sql")
        assert migration._canonical_artifact_metadata_state(snapshot, "1059_non_citizen_case_sequences.sql") == "exact"
        with config.connect(source) as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT COUNT(*) AS count FROM information_schema.tables WHERE table_schema=%s "
                               "AND table_name='non_citizen_case_sequences'", (source,))
                assert cursor.fetchone()["count"] == 0
    finally:
        with config.connect() as connection:
            with connection.cursor() as cursor:
                for database in (candidate, source):
                    assert database.startswith("lu_test_nc_preserve_")
                    cursor.execute(f"DROP DATABASE IF EXISTS `{database}`")
