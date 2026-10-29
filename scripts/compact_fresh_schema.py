"""Render final fresh DDL from an owned synthetic source; load hash-bound results."""

import hashlib
import json
from pathlib import Path
import re
from uuid import uuid4

import pymysql

from scripts.fresh_schema_policy import POLICY_PATH, retired_fresh_tables
from scripts.schema_assembly import DEFAULT_ASSEMBLY_PATH, load_schema_assembly
from scripts.sql_statements import split_sql
from scripts.verify_validation_schema_manifest import (
    DEFAULT_MANIFEST_PATH, _effective_database_objects, load_manifest, verify_manifest,
)


ROOT = Path(__file__).resolve().parents[1]
SQL_PATH = ROOT / "db/fresh_schema/labor_union_fresh_current.sql"
MANIFEST_PATH = ROOT / "db/fresh_schema/labor_union_fresh_current.json"


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _source_bindings():
    load_schema_assembly()
    if verify_manifest(load_manifest()):
        raise ValueError("historical source assembly is not current")
    return {
        "assembly_sha256": _sha(DEFAULT_ASSEMBLY_PATH),
        "validation_manifest_sha256": _sha(DEFAULT_MANIFEST_PATH),
        "retirement_policy_sha256": _sha(POLICY_PATH),
    }


def load_compact_plan():
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    if manifest.get("contract") != "labor-union-compact-fresh-schema/v1":
        raise ValueError("invalid compact fresh schema contract")
    sql_bytes = SQL_PATH.read_bytes()
    if manifest["source_bindings"] != _source_bindings() or manifest["sql_sha256"] != hashlib.sha256(sql_bytes).hexdigest():
        raise ValueError("compact fresh baseline is stale; regenerate from the current sources")
    sql = sql_bytes.decode("utf-8")
    statements = split_sql(sql)
    if len(statements) != manifest["statement_count"]:
        raise ValueError("compact fresh statement inventory does not match manifest")
    allowed = re.compile(
        r"(?:CREATE\s+(?:TABLE|TRIGGER|OR\s+REPLACE\s+VIEW)\b|INSERT\s+INTO\b|SET\s+FOREIGN_KEY_CHECKS\s*=\s*[01]\s*$)",
        re.I,
    )
    if any(not allowed.match(s) for s in statements):
        raise ValueError("compact fresh schema contains historical/database control statements")
    expected = _effective_database_objects([SQL_PATH])
    if expected["tables"] & retired_fresh_tables():
        raise ValueError("compact fresh schema revives a retired table")
    if {k: len(v) for k, v in expected.items()} != manifest["objects"]:
        raise ValueError("compact fresh object inventory does not match manifest")
    return {
        "assembly_id": manifest["profile_id"], "release_id": manifest["release_id"],
        "schema_parts": [SQL_PATH.name], "expected": expected,
        "steps": [{"artifact": SQL_PATH.name, "ordinal": i, "sql": s}
                  for i, s in enumerate(statements, 1)],
    }


def _without_definer(sql):
    return re.sub(r"\bDEFINER\s*=\s*`[^`]*`@`[^`]*`\s*", "", sql, flags=re.I)


def render_from_synthetic_source(connection, database):
    """Caller owns a freshly bootstrapped disposable DB, never an application DB."""
    if not re.fullmatch(r"lu_test_compact_source_[a-f0-9]+", database):
        raise ValueError("compact rendering requires an owned synthetic source")
    retired = retired_fresh_tables()
    chunks = ["-- Generated final fresh schema. Regenerate; do not edit by hand.",
              "-- Existing databases are never modified by this asset.", "SET FOREIGN_KEY_CHECKS=0;"]
    with connection.cursor(pymysql.cursors.DictCursor) as cursor:
        cursor.execute("SELECT table_name AS name FROM information_schema.tables WHERE table_schema=%s AND table_type='BASE TABLE' ORDER BY table_name", (database,))
        tables = [row["name"] for row in cursor.fetchall() if row["name"] not in retired]
        cursor.execute("SELECT table_name AS name,referenced_table_name AS target FROM information_schema.key_column_usage WHERE table_schema=%s AND referenced_table_schema=%s", (database, database))
        if any(row["name"] in tables and row["target"] in retired for row in cursor.fetchall()):
            raise ValueError("retained table still depends on a retired table")
        cursor.execute("SELECT table_name AS owner,column_name AS name,extra AS extra,column_default AS default_value FROM information_schema.columns WHERE table_schema=%s", (database,))
        omitted_seed_columns = {}
        for column in cursor.fetchall():
            if ("GENERATED" in column["extra"].upper() and "DEFAULT_GENERATED" not in column["extra"].upper()
                    or str(column["default_value"]).lower().startswith("current_timestamp")):
                omitted_seed_columns.setdefault(column["owner"], set()).add(column["name"])
        cursor.execute(f"USE `{database}`")
        for table in tables:
            cursor.execute(f"SHOW CREATE TABLE `{table}`")
            ddl = cursor.fetchone()["Create Table"]
            ddl = re.sub(r"\sAUTO_INCREMENT=\d+", "", ddl)
            chunks.append(ddl + ";")
        # Only canonical system seeds can exist: build_compact_baseline creates
        # and bootstraps this source itself and accepts no existing source DB.
        for table in tables:
            cursor.execute(f"SELECT * FROM `{table}`")
            rows = [{k: v for k, v in row.items() if k not in omitted_seed_columns.get(table, set())}
                    for row in cursor.fetchall()]
            for row in sorted(rows, key=lambda r: json.dumps(r, sort_keys=True, default=str)):
                columns = ",".join(f"`{name}`" for name in row)
                values = ",".join(connection.escape(value) for value in row.values())
                chunks.append(f"INSERT INTO `{table}` ({columns}) VALUES ({values});")
        cursor.execute("SELECT trigger_name AS name,event_object_table AS owner FROM information_schema.triggers WHERE trigger_schema=%s ORDER BY trigger_name", (database,))
        triggers = cursor.fetchall()
        for trigger in triggers:
            if trigger["owner"] in retired:
                continue
            cursor.execute(f"SHOW CREATE TRIGGER `{trigger['name']}`")
            ddl = _without_definer(cursor.fetchone()["SQL Original Statement"])
            chunks.append("DELIMITER $$\n" + ddl + "$$\nDELIMITER ;")
        cursor.execute("SELECT table_name AS name,view_definition AS definition FROM information_schema.views WHERE table_schema=%s ORDER BY table_name", (database,))
        for view in cursor.fetchall():
            chunks.append(f"CREATE OR REPLACE VIEW `{view['name']}` AS {view['definition']};")
    chunks.append("SET FOREIGN_KEY_CHECKS=1;")
    sql = ("\n\n".join(chunks) + "\n").replace(f"`{database}`.", "")
    for table in retired:
        if re.search(r"\b(?:FROM|JOIN|UPDATE|INTO|REFERENCES)\s+`?" + re.escape(table) + r"`?\b", sql, re.I):
            raise ValueError("retained SQL still references a retired table")
    return sql


def build_compact_baseline(server_config, *, sql_path=SQL_PATH, manifest_path=MANIFEST_PATH):
    """Build only through a newly created local lu_test_* DB; preserve all existing DBs."""
    if server_config.get("host") not in {"127.0.0.1", "localhost"}:
        raise ValueError("compact generation requires a local disposable server")
    from scripts.initialize_nas_schema import initialize, source_schema_plan
    bindings = _source_bindings()
    plan = source_schema_plan()
    database = "lu_test_compact_source_" + uuid4().hex[:16]
    config = {**server_config, "database": database}
    server_settings = {k: v for k, v in server_config.items() if k != "database"}
    connection = pymysql.connect(**server_settings, autocommit=True)
    created = False
    try:
        with connection.cursor() as cursor:
            cursor.execute(f"CREATE DATABASE `{database}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
            created = True
        initialize(config, plan, apply=True, receipt_root=ROOT / "scratch/compact_fresh_generation")
        sql = render_from_synthetic_source(connection, database)
        sql_path = Path(sql_path)
        sql_path.parent.mkdir(parents=True, exist_ok=True)
        sql_path.write_text(sql, encoding="utf-8", newline="\n")
        objects = _effective_database_objects([sql_path])
        manifest = {
            "contract": "labor-union-compact-fresh-schema/v1",
            "profile_id": "labor-union-compact-fresh-2026-10-15-v1",
            "release_id": plan["release_id"], "source_bindings": bindings,
            "sql_sha256": _sha(sql_path), "objects": {k: len(v) for k, v in objects.items()},
            "omitted_tables": sorted(retired_fresh_tables()),
            "statement_count": len(split_sql(sql)), "system_seed_policy": "canonical_synthetic_source_only",
        }
        Path(manifest_path).write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
        return manifest
    finally:
        if created:
            with connection.cursor() as cursor:
                cursor.execute(f"DROP DATABASE `{database}`")
        connection.close()
