"""Execute the NAS initializer against one explicitly configured, disposable MySQL DB."""

import json
import difflib
import os
import re
import secrets
from uuid import uuid4

import pymysql
import pytest

from scripts import initialize_nas_schema as nas
from scripts.fresh_schema_policy import retired_fresh_tables


pytestmark = pytest.mark.skipif(
    not os.getenv("LABOR_UNION_TEST_MYSQL_DATABASE"), reason="requires explicit disposable MySQL",
)


def test_real_permissions_and_enabled_roles_are_checked_before_schema_writes(tmp_path):
    config = {
        "host": os.environ["LABOR_UNION_TEST_MYSQL_HOST"],
        "port": int(os.environ["LABOR_UNION_TEST_MYSQL_PORT"]),
        "user": os.environ["LABOR_UNION_TEST_MYSQL_USER"],
        "password": os.environ["LABOR_UNION_TEST_MYSQL_PASSWORD"], "charset": "utf8mb4",
    }
    assert config["host"] in {"127.0.0.1", "localhost"}
    database = os.environ["LABOR_UNION_TEST_MYSQL_DATABASE"] + "_admit"
    assert re.fullmatch(r"lu_test_[a-z0-9_]+", database)
    suffix = uuid4().hex[:10]
    username, role = "lu_test_nas_" + suffix, "lu_test_role_" + suffix + "`q"
    password = secrets.token_urlsafe(24)
    server = pymysql.connect(**config, autocommit=True)
    created_database = created_user = created_role = False
    try:
        with server.cursor() as cursor:
            cursor.execute(f"CREATE DATABASE `{database}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
            created_database = True
            cursor.execute("CREATE USER %s@'%%' IDENTIFIED BY %s", (username, password))
            created_user = True
            cursor.execute(f"GRANT SELECT,INSERT,CREATE,REFERENCES,CREATE VIEW,SHOW VIEW ON `{database}`.* TO %s@'%%'", (username,))
            cursor.execute(f"GRANT CREATE,DROP ON `{database}`.`v_order_details` TO %s@'%%'", (username,))
        applicant = {**config, "database": database, "user": username, "password": password}
        plan = nas.schema_plan()
        with pytest.raises(nas.InitializationBlocked, match="缺少資料庫權限 TRIGGER"):
            nas.initialize(applicant, plan, apply=True, receipt_root=tmp_path)
        with server.cursor() as cursor:
            cursor.execute("CREATE ROLE %s@'%%'", (role,))
            created_role = True
            cursor.execute(f"GRANT TRIGGER ON `{database}`.* TO %s@'%%'", (role,))
            cursor.execute("GRANT %s@'%%' TO %s@'%%'", (role, username))
            cursor.execute("SET DEFAULT ROLE %s@'%%' TO %s@'%%'", (role, username))
            cursor.execute("SELECT @@log_bin AND NOT @@log_bin_trust_function_creators")
            binary_log_restricts_triggers = bool(cursor.fetchone()[0])
        # The quoted role must be decoded/requoted correctly. In a restrictive
        # server the next blocker is binary logging, not a missing TRIGGER grant.
        if binary_log_restricts_triggers:
            with pytest.raises(nas.InitializationBlocked, match="binary log"):
                nas.initialize(applicant, plan, receipt_root=tmp_path)
        else:
            assert nas.initialize(applicant, plan, receipt_root=tmp_path)["preflight"] == "passed"
        with server.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=%s", (database,))
            assert cursor.fetchone() == (0,)
        assert not list(tmp_path.iterdir())
    finally:
        with server.cursor() as cursor:
            if created_user:
                cursor.execute("DROP USER %s@'%%'", (username,))
            if created_role:
                cursor.execute("DROP ROLE %s@'%%'", (role,))
            if created_database:
                cursor.execute(f"DROP DATABASE `{database}`")
        server.close()


def test_full_fresh_seed_nonempty_and_replay_guards(tmp_path):
    config = {
        "host": os.environ["LABOR_UNION_TEST_MYSQL_HOST"],
        "port": int(os.environ["LABOR_UNION_TEST_MYSQL_PORT"]),
        "user": os.environ["LABOR_UNION_TEST_MYSQL_USER"],
        "password": os.environ["LABOR_UNION_TEST_MYSQL_PASSWORD"],
        "database": os.environ["LABOR_UNION_TEST_MYSQL_DATABASE"], "charset": "utf8mb4",
    }
    assert config["host"] in {"127.0.0.1", "localhost"}
    target = config["database"]
    assert re.fullmatch(r"lu_test_[a-z0-9_]+", target)
    server = pymysql.connect(**{k: v for k, v in config.items() if k != "database"}, autocommit=True)
    created = False
    try:
        with server.cursor() as cursor:
            # No IF NOT EXISTS: never take ownership of a pre-existing database.
            cursor.execute(f"CREATE DATABASE `{target}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
            created = True
            cursor.execute(f"USE `{target}`")
            cursor.execute("CREATE TABLE synthetic_existing(id INT PRIMARY KEY)")
            cursor.execute("INSERT INTO synthetic_existing VALUES (73)")
            plan = nas.schema_plan()
            with pytest.raises(nas.InitializationBlocked, match="not empty") as incomplete:
                nas.initialize(config, plan, apply=True, receipt_root=tmp_path)
            assert "現有結構尚未通過完整版本查核" in str(incomplete.value)
            cursor.execute("SELECT id FROM synthetic_existing")
            assert cursor.fetchone() == (73,)
            cursor.execute("DROP TABLE synthetic_existing")
            cursor.execute("CREATE VIEW synthetic_existing_view AS SELECT 73 AS id")
            with pytest.raises(nas.InitializationBlocked, match="not empty"):
                nas.initialize(config, plan, apply=True, receipt_root=tmp_path)
            cursor.execute("DROP VIEW synthetic_existing_view")
            assert nas.initialize(config, plan, receipt_root=tmp_path)["status"] == "ready"
            result = nas.initialize(config, plan, apply=True, receipt_root=tmp_path)
            assert result["status"] == "passed" and result["schema"] == "current"
            cursor.execute("SELECT COUNT(*) FROM payroll_rate_policies")
            assert cursor.fetchone()[0] > 0
            with pytest.raises(nas.InitializationBlocked, match="not empty") as existing:
                nas.initialize(config, plan, apply=True, receipt_root=tmp_path)
            assert "現有結構已通過完整版本查核" in str(existing.value)
            events = [json.loads(line) for line in open(result["journal"], encoding="utf-8")]
            assert events[-1]["event"] == "passed"
            assert sum(e["event"] == "applied" for e in events) == len(plan["steps"])
    finally:
        if created:
            with server.cursor() as cursor:
                cursor.execute(f"DROP DATABASE `{target}`")
        server.close()


def test_confirmed_reset_rebuilds_partial_database_and_preserves_other_databases(tmp_path):
    config = {
        "host": os.environ["LABOR_UNION_TEST_MYSQL_HOST"],
        "port": int(os.environ["LABOR_UNION_TEST_MYSQL_PORT"]),
        "user": os.environ["LABOR_UNION_TEST_MYSQL_USER"],
        "password": os.environ["LABOR_UNION_TEST_MYSQL_PASSWORD"],
        "database": os.environ["LABOR_UNION_TEST_MYSQL_DATABASE"] + "_reset", "charset": "utf8mb4",
    }
    assert config["host"] in {"127.0.0.1", "localhost"}
    target = config["database"]
    neighbor = target + "_neighbor"
    assert re.fullmatch(r"lu_test_[a-z0-9_]+", target)
    server = pymysql.connect(**{k: v for k, v in config.items() if k != "database"}, autocommit=True)
    owned = []
    try:
        with server.cursor() as cursor:
            for database in (target, neighbor):
                cursor.execute(f"CREATE DATABASE `{database}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
                owned.append(database)
            cursor.execute(f"CREATE TABLE `{target}`.old_test_data(id INT PRIMARY KEY)")
            cursor.execute(f"INSERT INTO `{target}`.old_test_data VALUES (73)")
            cursor.execute(f"CREATE VIEW `{target}`.old_test_view AS SELECT id FROM `{target}`.old_test_data")
            cursor.execute(f"CREATE PROCEDURE `{target}`.old_test_routine() SELECT 1")
            cursor.execute(f"CREATE EVENT `{target}`.old_test_event ON SCHEDULE EVERY 1 DAY DISABLE DO SELECT 1")
            cursor.execute(f"CREATE TABLE `{neighbor}`.kept(id INT PRIMARY KEY)")
            cursor.execute(f"INSERT INTO `{neighbor}`.kept VALUES (89)")
            cursor.execute(f"CREATE TABLE `{neighbor}`.incoming_fk(id INT, FOREIGN KEY(id) REFERENCES `{target}`.old_test_data(id))")
        plan = nas.schema_plan()
        with pytest.raises(nas.InitializationBlocked, match="其他資料庫有外鍵"):
            nas.initialize(config, plan, apply=True, reset=True, confirm_reset=lambda _: pytest.fail("must block before confirmation"), receipt_root=tmp_path)
        with server.cursor() as cursor:
            cursor.execute(f"DROP TABLE `{neighbor}`.incoming_fk")
        result = nas.initialize(config, plan, apply=True, reset=True, confirm_reset=lambda _: False, receipt_root=tmp_path)
        assert result["status"] == "cancelled" and not list(tmp_path.iterdir())
        with server.cursor() as cursor:
            cursor.execute(f"SELECT id FROM `{target}`.old_test_data")
            assert cursor.fetchone() == (73,)
        result = nas.initialize(config, plan, apply=True, reset=True, confirm_reset=lambda _: True, receipt_root=tmp_path)
        assert result["status"] == "passed" and result["schema"] == "current"
        with server.cursor() as cursor:
            cursor.execute("SELECT table_name FROM information_schema.tables WHERE table_schema=%s", (target,))
            names = {row[0] for row in cursor.fetchall()}
            assert names == plan["expected"]["tables"] | plan["expected"]["views"]
            cursor.execute("SELECT COUNT(*) FROM information_schema.routines WHERE routine_schema=%s", (target,))
            assert cursor.fetchone() == (0,)
            cursor.execute("SELECT COUNT(*) FROM information_schema.events WHERE event_schema=%s", (target,))
            assert cursor.fetchone() == (0,)
            cursor.execute(f"SELECT COUNT(*) FROM `{target}`.payroll_rate_policies")
            assert cursor.fetchone()[0] > 0
            cursor.execute(f"SELECT id FROM `{neighbor}`.kept")
            assert cursor.fetchone() == (89,)
        events = [json.loads(line) for line in open(result["journal"], encoding="utf-8")]
        assert sum(event["event"] == "reset_applied" for event in events) == 3
        assert events[-1]["event"] == "passed"
    finally:
        with server.cursor() as cursor:
            for database in reversed(owned):
                cursor.execute(f"DROP DATABASE `{database}`")
        server.close()


def test_reset_reports_metadata_lock_timeout_without_retry_or_data_loss(tmp_path):
    config = {
        "host": os.environ["LABOR_UNION_TEST_MYSQL_HOST"],
        "port": int(os.environ["LABOR_UNION_TEST_MYSQL_PORT"]),
        "user": os.environ["LABOR_UNION_TEST_MYSQL_USER"],
        "password": os.environ["LABOR_UNION_TEST_MYSQL_PASSWORD"],
        "database": os.environ["LABOR_UNION_TEST_MYSQL_DATABASE"] + "_mdl", "charset": "utf8mb4",
    }
    assert config["host"] in {"127.0.0.1", "localhost"}
    target = config["database"]
    assert re.fullmatch(r"lu_test_[a-z0-9_]+", target)
    server = pymysql.connect(**{key: value for key, value in config.items() if key != "database"}, autocommit=True)
    owner = None
    created = False
    try:
        with server.cursor() as cursor:
            cursor.execute(f"CREATE DATABASE `{target}`")
            created = True
            cursor.execute(f"CREATE TABLE `{target}`.held_test_data(id INT PRIMARY KEY)")
            cursor.execute(f"INSERT INTO `{target}`.held_test_data VALUES (73)")
        owner = pymysql.connect(**config, autocommit=False)
        with owner.cursor() as cursor:
            cursor.execute("SELECT id FROM held_test_data")
            assert cursor.fetchone() == (73,)
        with pytest.raises(nas.InitializationBlocked) as failure:
            nas.initialize(config, nas.schema_plan(), apply=True, reset=True, confirm_reset=lambda _: True, receipt_root=tmp_path)
        message = str(failure.value)
        assert "MySQL errno: 1205" in message and "等待其他連線釋放鎖逾時" in message
        assert "Reset operation: drop_database" in message
        owner.rollback()
        with server.cursor() as cursor:
            cursor.execute(f"SELECT id FROM `{target}`.held_test_data")
            assert cursor.fetchone() == (73,)
        events = [json.loads(line) for line in next(tmp_path.glob("*/journal.jsonl")).read_text(encoding="utf-8").splitlines()]
        assert sum(event["event"] == "reset_prepared" for event in events) == 1
        assert not any(event["event"] == "reset_applied" for event in events)
    finally:
        if owner is not None:
            owner.close()
        if created:
            with server.cursor() as cursor:
                cursor.execute(f"DROP DATABASE `{target}`")
        server.close()


def _metadata_and_seeds(server, database):
    """Independent engine oracle: full final DDL plus effective seeded values."""
    metadata, seeds = {}, {}
    with server.cursor(pymysql.cursors.DictCursor) as cursor:
        cursor.execute(f"USE `{database}`")
        cursor.execute("SELECT table_name,column_name,ordinal_position,column_type,is_nullable,column_default,extra,generation_expression,character_set_name,collation_name,column_comment FROM information_schema.columns WHERE table_schema=%s ORDER BY table_name,ordinal_position", (database,))
        for row in cursor.fetchall():
            row = {k.lower(): v for k, v in row.items()}
            if row["table_name"] not in retired_fresh_tables():
                metadata[("COLUMN", row["table_name"], row["column_name"])] = row
        cursor.execute("SHOW FULL TABLES")
        objects = [(list(row.values())[0], list(row.values())[1]) for row in cursor.fetchall()]
        for name, kind in objects:
            if name in retired_fresh_tables():
                continue
            cursor.execute(f"SHOW CREATE {'TABLE' if kind == 'BASE TABLE' else 'VIEW'} `{name}`")
            ddl = list(cursor.fetchone().values())[1]
            ddl = re.sub(r"\sAUTO_INCREMENT=\d+", "", ddl).replace(f"`{database}`.", "")
            # MySQL may repeat an explicit character set after replaying its
            # own SHOW CREATE. The collation already determines that charset;
            # compare actual column charset/collation independently above.
            ddl = re.sub(r"\bCHARACTER SET ([a-zA-Z0-9]+) (?=COLLATE \1_[a-zA-Z0-9_]+)", "", ddl)
            metadata[(kind, name)] = re.sub(r"\bDEFINER=`[^`]*`@`[^`]*`\s*", "", ddl)
            if kind != "BASE TABLE":
                continue
            cursor.execute("SELECT column_name AS name,extra AS extra,column_default AS default_value FROM information_schema.columns WHERE table_schema=%s AND table_name=%s", (database, name))
            omitted = {r["name"] for r in cursor.fetchall() if
                       ("GENERATED" in r["extra"].upper() and "DEFAULT_GENERATED" not in r["extra"].upper())
                       or str(r["default_value"]).lower().startswith("current_timestamp")}
            cursor.execute(f"SELECT * FROM `{name}`")
            seeds[name] = sorted(json.dumps({k: v for k, v in r.items() if k not in omitted}, sort_keys=True, default=str)
                                 for r in cursor.fetchall())
        cursor.execute("SELECT trigger_name AS name,event_object_table AS owner,event_manipulation AS event,action_timing AS timing,action_statement AS body FROM information_schema.triggers WHERE trigger_schema=%s", (database,))
        for row in cursor.fetchall():
            if row["owner"] not in retired_fresh_tables():
                metadata[("TRIGGER", row["name"])] = {k: str(v).replace(f"`{database}`.", "") for k, v in row.items()}
    return metadata, seeds


def test_compact_matches_retained_schema_and_seeds_without_rebuilding_retired_tables(tmp_path):
    config = {
        "host": os.environ["LABOR_UNION_TEST_MYSQL_HOST"],
        "port": int(os.environ["LABOR_UNION_TEST_MYSQL_PORT"]),
        "user": os.environ["LABOR_UNION_TEST_MYSQL_USER"],
        "password": os.environ["LABOR_UNION_TEST_MYSQL_PASSWORD"], "charset": "utf8mb4",
    }
    assert config["host"] in {"127.0.0.1", "localhost"}
    prefix = os.environ["LABOR_UNION_TEST_MYSQL_DATABASE"]
    assert re.fullmatch(r"lu_test_[a-z0-9_]{1,25}", prefix)
    server = pymysql.connect(**config, autocommit=True)
    created = []
    try:
        source, target = prefix + "_old", prefix + "_new"
        for database, plan in ((source, nas.source_schema_plan()), (target, nas.schema_plan())):
            with server.cursor() as cursor:
                cursor.execute(f"CREATE DATABASE `{database}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
                created.append(database)
            assert nas.initialize({**config, "database": database}, plan, apply=True, receipt_root=tmp_path)["schema"] == "current"
        before = _metadata_and_seeds(server, source)
        after = _metadata_and_seeds(server, target)
        differences = {str(key): list(difflib.unified_diff(str(value).splitlines(), str(after[0].get(key)).splitlines()))
                       for key, value in before[0].items() if value != after[0].get(key)}
        if differences:
            (tmp_path / "metadata_differences.json").write_text(json.dumps(differences, ensure_ascii=False, indent=2), encoding="utf-8")
        assert before[0] == after[0], "retained final metadata changed: " + str(list(differences.items())[:1])
        assert before[1] == after[1], "effective canonical system seeds changed"
        with server.cursor() as cursor:
            cursor.execute("SELECT table_name FROM information_schema.tables WHERE table_schema=%s", (target,))
            assert not {r[0] for r in cursor.fetchall()} & retired_fresh_tables()
            cursor.execute(f"USE `{source}`")
            cursor.execute("INSERT INTO access_control_apply_receipts(idempotency_key,command_fingerprint,receipt_json) VALUES ('synthetic-preservation',%s,'{}')", ("a" * 64,))
            cursor.execute("SELECT * FROM access_control_apply_receipts")
            legacy_rows = cursor.fetchall()
            cursor.execute("SHOW CREATE TABLE access_control_apply_receipts")
            legacy_ddl = cursor.fetchall()
        nas._verify_current({**config, "database": source})
        assert _metadata_and_seeds(server, source) == before
        with server.cursor() as cursor:
            cursor.execute(f"USE `{source}`")
            cursor.execute("SELECT * FROM access_control_apply_receipts")
            assert cursor.fetchall() == legacy_rows
            cursor.execute("SHOW CREATE TABLE access_control_apply_receipts")
            assert cursor.fetchall() == legacy_ddl
            # Verify that retirement projection still rejects retained drift.
            cursor.execute(f"USE `{target}`")
            cursor.execute("ALTER TABLE clients MODIFY COLUMN email VARCHAR(50) NULL")
        from scripts.update_local_database import LocalDatabaseUpdateError
        with pytest.raises(LocalDatabaseUpdateError):
            nas._verify_current({**config, "database": target})
    finally:
        with server.cursor() as cursor:
            for database in reversed(created):
                cursor.execute(f"DROP DATABASE `{database}`")
        server.close()
