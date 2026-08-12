"""Append the privacy-safe invalid Case Import scenario to a test dataset."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

import pymysql


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from domains.case_import.beclass_import_review import BeClassImportSourceKind, build_review_identity
from subsystems.case_import.beclass_review_intake import (
    masked_review_identifier,
    record_invalid_beclass_row,
)


SCENARIO_ID = "UI-CI-INVALID-001"
_DATABASE_PATTERN = re.compile(r"lu_test_dataset_[a-z0-9_]+")
_SOURCE_DIGEST = hashlib.sha256(SCENARIO_ID.encode("utf-8")).hexdigest()
_ROOT_TABLES = ("clients", "orders", "client_finance_accounts")


def run(arguments) -> dict[str, object]:
    _require_dataset_database(arguments.database)
    connection = _connect(arguments)
    try:
        before_counts = _root_counts(connection)
        review_identity = _record_invalid_root(connection)
        connection.commit()
        replay_identity = _record_invalid_root(connection)
        conflict_code = _require_payload_conflict(connection)
        after_counts = _root_counts(connection)
    finally:
        connection.close()
    return {
        "scenario_id": SCENARIO_ID,
        "database": arguments.database,
        "review_identity": review_identity,
        "replay_identity": replay_identity,
        "payload_conflict": conflict_code,
        "root_counts_before": before_counts,
        "root_counts_after": after_counts,
    }


def _record_invalid_root(connection) -> str:
    return record_invalid_beclass_row(
        connection,
        source_kind=BeClassImportSourceKind.CLIENT,
        source_content_digest=_SOURCE_DIGEST,
        source_sheet="WP56-UI-CI",
        source_row=1,
        masked_identifier=masked_review_identifier(BeClassImportSourceKind.CLIENT, None, SCENARIO_ID),
        source_payload={"query_no": None, "validation_marker": "missing_query_no"},
        issue_codes=("missing_query_no",),
    )


def _require_payload_conflict(connection) -> str:
    try:
        record_invalid_beclass_row(
            connection,
            source_kind=BeClassImportSourceKind.CLIENT,
            source_content_digest=_SOURCE_DIGEST,
            source_sheet="WP56-UI-CI",
            source_row=1,
            masked_identifier=masked_review_identifier(BeClassImportSourceKind.CLIENT, None, SCENARIO_ID),
            source_payload={"query_no": None, "validation_marker": "changed_payload"},
            issue_codes=("missing_query_no",),
        )
    except RuntimeError as error:
        if str(error) == "beclass_import_review_source_conflict":
            return str(error)
        raise
    raise RuntimeError("invalid Case Import payload conflict was not rejected")


def _root_counts(connection) -> dict[str, int]:
    with connection.cursor() as cursor:
        return {
            table_name: _table_count(cursor, table_name)
            for table_name in _ROOT_TABLES
        }


def _table_count(cursor, table_name: str) -> int:
    cursor.execute(f"SELECT COUNT(*) AS count FROM `{table_name}`")
    return int(cursor.fetchone()["count"])


def _connect(arguments):
    return pymysql.connect(
        host=arguments.host,
        port=arguments.port,
        user=arguments.user,
        password=arguments.password,
        database=arguments.database,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False,
    )


def _require_dataset_database(database: str) -> None:
    if not _DATABASE_PATTERN.fullmatch(database):
        raise ValueError("database must match lu_test_dataset_[a-z0-9_]+")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", required=True)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--user", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--database", required=True)
    print(json.dumps(run(parser.parse_args()), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
