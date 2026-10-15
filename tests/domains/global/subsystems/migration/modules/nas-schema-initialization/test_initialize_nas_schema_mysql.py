"""Execute the NAS initializer against one explicitly configured, disposable MySQL DB."""

import json
import os
import re

import pymysql
import pytest

from scripts import initialize_nas_schema as nas


pytestmark = pytest.mark.skipif(
    not os.getenv("LABOR_UNION_TEST_MYSQL_DATABASE"), reason="requires explicit disposable MySQL",
)


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
            with pytest.raises(nas.InitializationBlocked, match="not empty"):
                nas.initialize(config, plan, apply=True, receipt_root=tmp_path)
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
            with pytest.raises(nas.InitializationBlocked, match="not empty"):
                nas.initialize(config, plan, apply=True, receipt_root=tmp_path)
            events = [json.loads(line) for line in open(result["journal"], encoding="utf-8")]
            assert events[-1]["event"] == "passed"
            assert sum(e["event"] == "applied" for e in events) == len(plan["steps"])
    finally:
        if created:
            with server.cursor() as cursor:
                cursor.execute(f"DROP DATABASE `{target}`")
        server.close()
