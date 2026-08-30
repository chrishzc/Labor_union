"""
File: adopt_historical_orders.py
Description: 預設唯讀預演 Historical Order Adoption，明確確認後才逐列呼叫 typed Apply。
"""

from __future__ import annotations

import argparse
from collections import Counter
import json
import os
from pathlib import Path
import sys

from dotenv import load_dotenv
import pymysql

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from infrastructure.mysql.historical_order_adoption_repository import MySqlHistoricalOrderAdoptionRepository
from infrastructure.mysql.historical_assignment_writer import MySqlHistoricalAssignmentWriter
from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
from shared_kernel.fingerprints import PreviewFingerprint
from subsystems.orders.historical_adoption_workflow import (
    HistoricalOrderAdoptionRequest,
    HistoricalOrderAdoptionWorkflow,
)
from subsystems.orders.historical_order_workbook import load_historical_order_workbook


def run_historical_order_adoption(
    workbook_path: str,
    *,
    sheet: str | None = None,
    apply: bool = False,
    confirm_database: str | None = None,
    actor: str = "historical-order-operator",
    reason: str = "one-time historical order adoption",
) -> dict[str, object]:
    load_dotenv()
    database = _required_environment("DB_DATABASE")
    if apply:
        _authorize_apply(database, confirm_database)
    workbook = load_historical_order_workbook(workbook_path, sheet)
    connection = _connect(database)
    try:
        return _process_workbook(connection, workbook, apply, actor, reason)
    finally:
        connection.close()


def _process_workbook(connection, workbook, apply, actor, reason):
    repository = MySqlHistoricalOrderAdoptionRepository(connection)
    workflow = HistoricalOrderAdoptionWorkflow(
        repository,
        lambda: MySqlUnitOfWork(connection),
        MySqlHistoricalAssignmentWriter(connection),
    )
    outcomes: Counter[str] = Counter()
    review_rows = 0
    assignment_count = 0
    replayed_rows = 0
    for row in workbook.rows:
        preview = workflow.preview(row)
        outcomes[preview.outcome.value] += 1
        review_rows += int(preview.outcome.value != "unmatched_case" and bool(preview.issue_codes))
        if not apply:
            continue
        receipt = workflow.apply(_request(row, preview.fingerprint, actor, reason))
        replayed_rows += int(receipt.replayed)
        if not receipt.replayed:
            assignment_count += receipt.assignment_count
    return {
        "status": "applied" if apply else "preview",
        "database": _required_environment("DB_DATABASE"),
        "sheet": workbook.sheet_name,
        "source_digest": workbook.content_digest,
        "source_rows": len(workbook.rows),
        "outcomes": dict(sorted(outcomes.items())),
        "review_rows": review_rows,
        "assignments_created": assignment_count,
        "replayed_rows": replayed_rows,
        "invariant_holds": sum(outcomes.values()) == len(workbook.rows),
    }


def _request(row, fingerprint, actor, reason):
    source_suffix = row.source_identity.rsplit(":", 1)[-1]
    return HistoricalOrderAdoptionRequest(
        row,
        fingerprint,
        f"historical-order-adoption:{row.source_fingerprint}:{source_suffix}",
        actor,
        reason,
        f"historical-order:{row.source_fingerprint[:24]}:{source_suffix}",
    )


def _connect(database):
    return pymysql.connect(
        host=_required_environment("DB_HOST"),
        port=int(os.getenv("DB_PORT", "3306")),
        user=_required_environment("DB_USER"),
        password=_required_environment("DB_PASSWORD"),
        database=database,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False,
    )


def _authorize_apply(database, confirmation):
    allowed = {item.strip() for item in os.getenv("HISTORICAL_IMPORT_ALLOWED_DATABASES", "").split(",") if item.strip()}
    if database not in allowed:
        raise RuntimeError("historical_order_database_target_not_allowed")
    if confirmation != database:
        raise RuntimeError("historical_order_database_confirmation_required")
    # The existing CLI contract has no prior-preview receipt, backup receipt,
    # connected-host verification, or post-apply verification.  Keep the
    # typed workflow available to its canonical API caller, but never let this
    # operator entrypoint perform a production-capable mutation.
    raise RuntimeError("historical_order_apply_guard_contract_incomplete")


def _required_environment(name):
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"historical_order_{name.casefold()}_required")
    return value


def _parser():
    parser = argparse.ArgumentParser(description="Preview or apply typed Historical Order Adoption.")
    parser.add_argument("workbook", type=Path)
    parser.add_argument("--sheet")
    parser.add_argument("--dry-run", action="store_true", help="Explicitly request the default read-only preview.")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-database")
    parser.add_argument("--actor", default="historical-order-operator")
    parser.add_argument("--reason", default="one-time historical order adoption")
    return parser


def main(arguments: list[str] | None = None) -> int:
    options = _parser().parse_args(arguments)
    try:
        result = run_historical_order_adoption(
            str(options.workbook),
            sheet=options.sheet,
            apply=options.apply,
            confirm_database=options.confirm_database,
            actor=options.actor,
            reason=options.reason,
        )
    except Exception as error:
        print(json.dumps({"status": "blocked", "error": str(error)}, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))


__all__ = ["main", "run_historical_order_adoption"]
