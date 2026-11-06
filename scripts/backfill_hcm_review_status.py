"""Preview or backfill missing HCM review decisions from original Excel workbooks."""

from __future__ import annotations

import argparse
import hashlib
from itertools import chain
import json
import os
from pathlib import Path
import re

from openpyxl import load_workbook
import pymysql

from domains.case_import.client_import_validation import (
    HCM_REQUIRED_HEADERS,
    normalize_hcm_review_status,
)
from shared_kernel.workbook_resource_limits import validate_xlsx_workbook


def _source_rows(path: Path):
    validate_xlsx_workbook(path)
    workbook = load_workbook(path, read_only=True, data_only=True)
    try:
        candidates = []
        for sheet in workbook.worksheets:
            rows = sheet.values
            headers = tuple(str(value).strip() for value in next(rows, ()))
            if HCM_REQUIRED_HEADERS <= set(headers):
                first_data_row = next((row for row in rows if any(value is not None for value in row)), None)
                if first_data_row is not None:
                    candidates.append((headers, chain((first_data_row,), rows)))
        if len(candidates) != 1:
            raise ValueError("hcm_workbook_sheet_contract_not_unique")
        headers, rows = candidates[0]
        case_header, status_header = "查詢序號(案件編號)", "案件狀態"
        if headers.count(case_header) != 1 or headers.count(status_header) != 1:
            raise ValueError("hcm_workbook_review_columns_ambiguous")
        case_index = headers.index(case_header)
        status_index = headers.index(status_header)
        for row in rows:
            case_no = str(row[case_index] or "").strip()
            status = normalize_hcm_review_status(row[status_index])
            if case_no and status is not None and not re.fullmatch(r"A[0-9]{6}", case_no, re.I):
                yield case_no, status
    finally:
        workbook.close()


def load_source_decisions(paths: list[Path]) -> tuple[dict[str, str], dict[str, object]]:
    decisions: dict[str, set[str]] = {}
    source_digests = []
    for path in paths:
        with path.open("rb") as source:
            digest = hashlib.file_digest(source, "sha256").hexdigest()
        for case_no, status in _source_rows(path):
            decisions.setdefault(case_no, set()).add(status)
        with path.open("rb") as source:
            if digest != hashlib.file_digest(source, "sha256").hexdigest():
                raise ValueError("hcm_workbook_changed_while_reading")
        source_digests.append(digest)
    usable = {
        case_no: next(iter(statuses)) for case_no, statuses in decisions.items() if len(statuses) == 1
    }
    return usable, {
        "source_sha256": sorted(set(source_digests)),
        "conflicting_source_cases": len(decisions) - len(usable),
    }


def backfill(connection, decisions: dict[str, str], *, apply: bool) -> dict[str, int]:
    counts = dict(ready=0, updated=0, already_saved=0, saved_value_conflicts=0, case_not_found=0)
    try:
        with connection.cursor() as cursor:
            if not apply:
                cursor.execute("START TRANSACTION READ ONLY")
            lock = " FOR UPDATE" if apply else ""
            for case_no, status in sorted(decisions.items()):
                cursor.execute(
                    "SELECT id, case_no, hcm_review_status FROM clients WHERE case_no=%s" + lock,
                    (case_no,),
                )
                row = cursor.fetchone()
                if row is None or row["case_no"] != case_no:
                    counts["case_not_found"] += 1
                elif row["hcm_review_status"] == status:
                    counts["already_saved"] += 1
                elif row["hcm_review_status"] is not None:
                    counts["saved_value_conflicts"] += 1
                else:
                    counts["ready"] += 1
                    if apply:
                        cursor.execute(
                            "UPDATE clients SET hcm_review_status=%s, db_updated_at=db_updated_at "
                            "WHERE id=%s AND hcm_review_status IS NULL",
                            (status, row["id"]),
                        )
                        if cursor.rowcount != 1:
                            raise RuntimeError("hcm_review_status_changed_during_backfill")
                        counts["updated"] += 1
            cursor.execute(
                "SELECT COUNT(*) AS pending FROM clients "
                "WHERE case_no IS NOT NULL AND case_no NOT REGEXP '^A[0-9]{6}$' "
                "AND hcm_review_status IS NULL"
            )
            counts["pending_before"] = int(cursor.fetchone()["pending"]) + counts["updated"]
            counts["pending_after"] = counts["pending_before"] - counts["updated"]
        if apply:
            connection.commit()
        else:
            connection.rollback()
    except BaseException:
        connection.rollback()
        raise
    return counts


def _local_target(config: dict) -> str:
    database = config["database"]
    if (
        os.getenv("APP_ENV", "").strip().lower() != "development"
        or os.getenv("DEPLOYMENT_PROFILE", "").strip().lower() not in {"", "local"}
        or config["host"] not in {"localhost", "127.0.0.1", "::1"}
        or not re.fullmatch(r"union_db|lu_test_[a-z0-9_]+", database)
    ):
        raise ValueError("hcm_review_backfill_requires_local_development_database")
    return database


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workbooks", nargs="+", type=Path)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-database")
    args = parser.parse_args()

    from infrastructure.mysql.mysql_adapter import DB_CONFIG

    try:
        database = _local_target(DB_CONFIG)
        if args.apply and args.confirm_database != database:
            raise ValueError("hcm_review_backfill_requires_confirmed_database")
        decisions, receipt = load_source_decisions(args.workbooks)
        with pymysql.connect(**DB_CONFIG, cursorclass=pymysql.cursors.DictCursor) as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT DATABASE() AS db, CURRENT_USER() AS account")
                target = cursor.fetchone()
                if target["db"] != database:
                    raise ValueError("hcm_review_backfill_database_mismatch")
            connection.rollback()
            counts = backfill(connection, decisions, apply=args.apply)
        print(json.dumps({
            "database": database,
            "credential_class": "root" if target["account"].split("@", 1)[0] == "root" else "named",
            "mode": "apply" if args.apply else "preview",
            **receipt, **counts,
        }))
    except (OSError, ValueError, RuntimeError, pymysql.MySQLError) as error:
        # These inputs can contain private paths or connection details.
        if isinstance(error, (ValueError, RuntimeError)) and str(error).startswith(("hcm_", "xlsx_")):
            parser.exit(1, f"{error}\n")
        parser.exit(1, f"hcm_review_backfill_failed: {type(error).__name__}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
