"""Temporary read-only diagnosis for Historical Orders workbook Preview failures.

This probe deliberately performs no Apply and no transaction commit.  It first
builds the historical row candidate without Actual Start delegation, then runs
the production Preview path and prints the exact scheduling roots involved in
any blocker.
"""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
import json
from pathlib import Path
import sys
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from infrastructure.mysql.historical_actual_start_date_planner import (
    MySqlHistoricalActualStartDatePlanner,
)
from infrastructure.mysql.historical_order_adoption_cancellation_decorator import (
    MySqlHistoricalOrderAdoptionCancellationDecorator,
)
from infrastructure.mysql.historical_assignment_writer import (
    MySqlHistoricalAssignmentWriter,
)
from infrastructure.mysql.mysql_adapter import get_connection
from infrastructure.mysql.order_actual_start_repository import (
    MySqlOrderActualStartRepository,
)
from shared_kernel.clock import SystemBusinessClock
from subsystems.orders.actual_start_workflow import (
    ActualStartWorkflow,
    ActualStartWorkflowError,
)
from subsystems.orders.historical_actual_start_rebuild import (
    HistoricalActualStartRebuilder,
)
from subsystems.orders.historical_adoption_workflow import (
    HistoricalOrderAdoptionWorkflow,
    HistoricalPairingResolution,
)
from subsystems.orders.historical_order_workbook import (
    load_historical_order_workbook,
)


def main() -> int:
    arguments = _arguments()
    workbook = load_historical_order_workbook(str(arguments.workbook))
    connection = get_connection()
    counts: Counter[str] = Counter()
    try:
        repository = MySqlHistoricalOrderAdoptionCancellationDecorator(connection)
        writer = MySqlHistoricalAssignmentWriter(connection)
        planner = MySqlHistoricalActualStartDatePlanner(connection)
        actual_repository = MySqlOrderActualStartRepository(connection)
        actual_workflow = ActualStartWorkflow(
            actual_repository,
            _forbid_unit_of_work,
            SystemBusinessClock(),
        )
        raw_workflow = HistoricalOrderAdoptionWorkflow(
            repository,
            _forbid_unit_of_work,
            writer,
        )
        production_workflow = HistoricalOrderAdoptionWorkflow(
            repository,
            _forbid_unit_of_work,
            writer,
            HistoricalActualStartRebuilder(actual_workflow, planner),
        )

        for row in workbook.rows:
            if arguments.case_no and row.case_no != arguments.case_no:
                continue
            record = _base_record(row)
            try:
                raw_preview = raw_workflow.preview(row)
                record["historical_candidate"] = _historical_candidate(raw_preview)
                record["database_scheduling"] = _scheduling_snapshot(
                    connection,
                    raw_preview.case_no,
                )
                record["incompatibilities"] = _incompatibilities(record)
                production_workflow.preview(row)
            except ActualStartWorkflowError as error:
                counts[error.error.code] += 1
                record["result"] = "blocked"
                record["error"] = {
                    "category": error.error.category.value,
                    "code": error.error.code,
                    "domain_blockers": list(error.error.domain_blockers),
                }
                _print(record)
                if not arguments.all_rows:
                    break
            except Exception as error:  # diagnostic boundary: retain exact class/code
                code = str(error) or type(error).__name__
                counts[code] += 1
                record["result"] = "error"
                record["error"] = {
                    "type": type(error).__name__,
                    "code": code,
                }
                _print(record)
                if not arguments.all_rows:
                    break
            else:
                counts["preview_ok"] += 1
                if arguments.all_rows:
                    record["result"] = "preview_ok"
                    _print(record)
    finally:
        connection.close()

    _print(
        {
            "summary": dict(sorted(counts.items())),
            "workbook_rows": len(workbook.rows),
            "sheet_identity": workbook.sheet_identity,
        }
    )
    return 0 if not counts or set(counts) == {"preview_ok"} else 1


def _arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument("workbook", type=Path)
    parser.add_argument("--case-no")
    parser.add_argument("--all-rows", action="store_true")
    return parser.parse_args()


def _forbid_unit_of_work():
    raise AssertionError("diagnostic Preview must not open a Unit of Work")


def _base_record(row) -> dict[str, Any]:
    return {
        "source_row": row.source_row,
        "case_identity": _mask_case(row.case_no),
        "source_status": (
            None if row.asserted_status is None else row.asserted_status.value
        ),
        "source_start_date": _value(row.actual_start_date),
        "source_end_date": _value(row.actual_end_date),
        "source_issue_codes": list(row.issue_codes),
    }


def _historical_candidate(preview) -> dict[str, Any]:
    return {
        "outcome": preview.outcome.value,
        "before_status": preview.before_status,
        "after_status": preview.after_status,
        "date_patch": [
            [field, _value(value)] for field, value in preview.date_patch
        ],
        "issue_codes": list(preview.issue_codes),
        "pairings": [
            {
                "ordinal": pairing.ordinal,
                "staff_id": pairing.staff_id,
                "start_date": _value(pairing.start_date),
                "end_date": _value(pairing.end_date),
                "resolution": pairing.resolution.value,
                "is_actual_start_source": (
                    pairing.resolution
                    is HistoricalPairingResolution.ASSIGNMENT_CANDIDATE
                ),
                "issue_codes": list(pairing.issue_codes),
            }
            for pairing in preview.pairings
        ],
    }


def _scheduling_snapshot(connection, case_no: str | None) -> dict[str, Any] | None:
    if case_no is None:
        return None
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT o.start_date,o.actual_start_date,o.actual_end_date,o.status,"
            "o.lifecycle_version,aggregate.aggregate_version,"
            "aggregate.generation_counter,aggregate.effective_generation_id "
            "FROM orders o LEFT JOIN scheduling_aggregates aggregate "
            "ON aggregate.case_no=o.case_no WHERE o.case_no=%s",
            (case_no,),
        )
        order = cursor.fetchone()
        if order is None:
            return {"order_found": False}
        generation_id = order.get("effective_generation_id")
        assignments = ()
        if generation_id is not None:
            cursor.execute(
                "SELECT id,staff_id,assignment_sequence,assigned_start_date,"
                "assigned_end_date,status FROM case_staff_assignments "
                "WHERE generation_id=%s AND status NOT IN ('cancelled','replaced') "
                "ORDER BY assignment_sequence,id",
                (generation_id,),
            )
            assignments = tuple(cursor.fetchall())
        cursor.execute(
            "SELECT id,staff_id,assignment_sequence,assigned_start_date,"
            "assigned_end_date,status FROM case_staff_assignments "
            "WHERE case_no=%s AND generation_id IS NULL "
            "AND status NOT IN ('cancelled','replaced') "
            "ORDER BY assignment_sequence,id",
            (case_no,),
        )
        generationless = tuple(cursor.fetchall())
        presence = {
            "client_finance_account": _exists(
                cursor, "client_finance_accounts", case_no
            ),
            "client_payment_terms": _exists(
                cursor, "client_payment_terms", case_no
            ),
            "payroll_case_account": _exists(
                cursor, "payroll_case_accounts", case_no
            ),
            "payroll_case_policy": _exists(
                cursor, "case_payroll_rate_policy_snapshots", case_no
            ),
        }
    root_date = order.get("actual_start_date") or order.get("start_date")
    first_assignment_start = (
        assignments[0].get("assigned_start_date") if assignments else None
    )
    return {
        "order_found": True,
        "order_planned_start_date": _value(order.get("start_date")),
        "lifecycle_actual_start_date": _value(order.get("actual_start_date")),
        "actual_end_date": _value(order.get("actual_end_date")),
        "order_status": order.get("status"),
        "lifecycle_version": order.get("lifecycle_version"),
        "derived_root_date": _value(root_date),
        "aggregate_version": order.get("aggregate_version"),
        "generation_number": order.get("generation_counter"),
        "effective_generation_id": generation_id,
        "first_assignment_start_date": _value(first_assignment_start),
        "root_matches_first_assignment": (
            None
            if first_assignment_start is None
            else first_assignment_start == root_date
        ),
        "formal_assignments": [
            {
                "assignment_id": assignment.get("id"),
                "staff_id": assignment.get("staff_id"),
                "sequence": assignment.get("assignment_sequence"),
                "assigned_start_date": _value(
                    assignment.get("assigned_start_date")
                ),
                "assigned_end_date": _value(assignment.get("assigned_end_date")),
                "status": assignment.get("status"),
            }
            for assignment in assignments
        ],
        "generationless_assignments": [
            {
                "assignment_id": assignment.get("id"),
                "staff_id": assignment.get("staff_id"),
                "sequence": assignment.get("assignment_sequence"),
                "assigned_start_date": _value(
                    assignment.get("assigned_start_date")
                ),
                "assigned_end_date": _value(assignment.get("assigned_end_date")),
                "status": assignment.get("status"),
            }
            for assignment in generationless
        ],
        "bootstrap_roots": presence,
    }


def _exists(cursor, table: str, case_no: str) -> bool:
    allowed = {
        "client_finance_accounts",
        "client_payment_terms",
        "payroll_case_accounts",
        "case_payroll_rate_policy_snapshots",
    }
    if table not in allowed:
        raise ValueError("diagnostic_table_not_allowed")
    cursor.execute(f"SELECT 1 AS present FROM {table} WHERE case_no=%s LIMIT 1", (case_no,))
    return cursor.fetchone() is not None


def _incompatibilities(record: dict[str, Any]) -> list[str]:
    candidate = record.get("historical_candidate") or {}
    database = record.get("database_scheduling") or {}
    issues: list[str] = []
    if database.get("root_matches_first_assignment") is False:
        issues.append("database_formal_schedule_root_mismatch")
    pairings = candidate.get("pairings") or []
    actual_start_sources = [
        pairing for pairing in pairings if pairing.get("is_actual_start_source")
    ]
    if (
        record.get("source_status") == "deposit_paid"
        and record.get("source_start_date")
        and not actual_start_sources
    ):
        issues.append("historical_actual_start_has_no_assignment_candidate")
    missing_roots = [
        name
        for name, present in (database.get("bootstrap_roots") or {}).items()
        if not present
    ]
    issues.extend(f"missing_{name}" for name in missing_roots)
    return issues


def _mask_case(case_no: str | None) -> str | None:
    if not case_no:
        return None
    return f"***{case_no[-4:]}"


def _value(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if is_dataclass(value):
        return asdict(value)
    return value


def _print(value: dict[str, Any]) -> None:
    print(json.dumps(value, ensure_ascii=False, sort_keys=True, default=str))


if __name__ == "__main__":
    raise SystemExit(main())
