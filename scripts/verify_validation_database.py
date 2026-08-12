"""Read-only postcheck for an explicitly named disposable validation database."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

import pymysql


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.verify_validation_schema_manifest import (
    expected_database_objects,
    load_manifest,
    verify_database_objects,
    verify_manifest,
)


def verify_database(arguments) -> dict[str, object]:
    database = _require_disposable_database(arguments.database)
    manifest = load_manifest(arguments.manifest)
    manifest_errors = verify_manifest(manifest)
    if manifest_errors:
        raise RuntimeError("schema manifest invalid: " + "; ".join(manifest_errors))
    connection = pymysql.connect(
        host=arguments.host, port=arguments.port, user=arguments.user,
        password=arguments.password, database=database, charset="utf8mb4",
    )
    try:
        with connection.cursor() as cursor:
            object_errors = verify_database_objects(
                cursor, database, expected_database_objects(manifest)
            )
            cursor.execute("SHOW COLUMNS FROM orders LIKE 'contract_identity'")
            contract_identity_present = cursor.fetchone() is not None
            cursor.execute("SELECT COUNT(*) FROM v_order_details")
            view_row_count = cursor.fetchone()[0]
            cursor.execute(
                "SELECT COUNT(*) FROM information_schema.triggers WHERE trigger_schema=%s",
                (database,),
            )
            trigger_count = cursor.fetchone()[0]
    finally:
        connection.close()
    errors = list(object_errors)
    if not contract_identity_present:
        errors.append("orders.contract_identity is missing")
    if trigger_count < manifest["postcheck"]["minimum_trigger_count"]:
        errors.append("trigger count is below release minimum")
    return {
        "valid": not errors,
        "database": database,
        "release_id": manifest["release_id"],
        "errors": errors,
        "contract_identity_present": contract_identity_present,
        "v_order_details_row_count": view_row_count,
        "trigger_count": trigger_count,
    }


def _require_disposable_database(database: str) -> str:
    if not re.fullmatch(r"lu_test_[a-z0-9_]+", database):
        raise ValueError("database must start with lu_test_")
    return database


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default=os.getenv("DB_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("DB_PORT", "3306")))
    parser.add_argument("--user", default=os.getenv("DB_USER", "root"))
    parser.add_argument("--password", default=os.getenv("DB_PASSWORD", "1234"))
    parser.add_argument("--database", required=True)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=PROJECT_ROOT / "db" / "cutover_releases" / "labor_union_validation_schema_v1.json",
    )
    result = verify_database(parser.parse_args())
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
