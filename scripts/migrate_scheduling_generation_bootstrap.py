"""Bootstrap verified legacy Scheduling rows into generation one."""

from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pymysql

from domains.scheduling.bootstrap import (
    ExternalStaffOccupancyFact,
    LegacyAssignmentBootstrapFact,
    LegacyOrderSchedulingFacts,
    LegacyScheduleBootstrapFact,
    SchedulingBootstrapDecision,
    SchedulingBootstrapFacts,
    evaluate_scheduling_bootstrap,
)
from infrastructure.mysql.scheduling_bootstrap_writer import (
    append_scheduling_bootstrap_reviews,
    persist_scheduling_bootstrap,
)
from scripts.migrate_order_lifecycle_control_facts import validate_backup
from infrastructure.mysql.mysql_adapter import DB_CONFIG


MIGRATION_ID = "scheduling_generation_bootstrap_v1"
MIGRATION_ACTOR = f"migration:{MIGRATION_ID}"


def build_plan(connection, *, lock: bool = False) -> dict[str, object]:
    facts_by_case = _load_facts_by_case(connection, lock=lock)
    decisions = _evaluate_dataset(facts_by_case)
    cases = [
        _case_plan(case_no, facts_by_case, decisions)
        for case_no in decisions
    ]
    return {
        "migration": MIGRATION_ID,
        "database": DB_CONFIG["database"],
        "dataset_fingerprint": _fingerprint(cases),
        "cases": cases,
        "eligible_count": sum(item["outcome"] == "eligible" for item in cases),
        "review_count": sum(item["outcome"] == "review" for item in cases),
    }


def _load_facts_by_case(connection, *, lock: bool):
    with connection.cursor() as cursor:
        orders = _load_orders(cursor, lock)
        assignments = _load_assignments(cursor, lock)
        schedules = _load_schedules(cursor, lock)
    case_numbers = sorted(set(assignments) | set(schedules))
    return {
        case_no: SchedulingBootstrapFacts(
            orders[case_no],
            tuple(assignments.get(case_no, ())),
            tuple(schedules.get(case_no, ())),
        )
        for case_no in case_numbers
    }


def _load_orders(cursor, lock):
    sql = (
        "SELECT case_no,service_days,service_hours_per_day,actual_start_date "
        "FROM orders ORDER BY case_no"
    )
    cursor.execute(_lock_sql(sql, lock))
    return {
        row["case_no"]: LegacyOrderSchedulingFacts(
            row["case_no"],
            int(row["service_days"] or 0),
            int(row["service_hours_per_day"] or 0),
            row["actual_start_date"] is not None,
        )
        for row in cursor.fetchall()
    }


def _load_assignments(cursor, lock):
    sql = (
        "SELECT id,case_no,staff_id,assignment_sequence,assigned_start_date,"
        "assigned_end_date,actual_hours,generation_id "
        "FROM case_staff_assignments "
        "WHERE status NOT IN ('cancelled','replaced') ORDER BY case_no,id"
    )
    cursor.execute(_lock_sql(sql, lock))
    grouped = defaultdict(list)
    for row in cursor.fetchall():
        grouped[row["case_no"]].append(_assignment_fact(row))
    return grouped


def _assignment_fact(row):
    value = row["actual_hours"]
    return LegacyAssignmentBootstrapFact(
        int(row["id"]),
        row["case_no"],
        int(row["staff_id"]),
        int(row["assignment_sequence"]),
        row["assigned_start_date"],
        row["assigned_end_date"],
        Decimal(str(value)) if value is not None else None,
        int(row["generation_id"]) if row["generation_id"] is not None else None,
    )


def _load_schedules(cursor, lock):
    sql = (
        "SELECT id,case_no,staff_id,assignment_id,work_date,is_work_day,"
        "generation_id FROM staff_schedule "
        "WHERE effective_marker=1 ORDER BY case_no,id"
    )
    cursor.execute(_lock_sql(sql, lock))
    grouped = defaultdict(list)
    for row in cursor.fetchall():
        grouped[row["case_no"]].append(_schedule_fact(row))
    return grouped


def _schedule_fact(row):
    return LegacyScheduleBootstrapFact(
        int(row["id"]),
        row["case_no"],
        int(row["staff_id"]),
        int(row["assignment_id"]) if row["assignment_id"] is not None else None,
        row["work_date"],
        bool(row["is_work_day"]),
        int(row["generation_id"]) if row["generation_id"] is not None else None,
    )


def _lock_sql(sql: str, lock: bool) -> str:
    return f"{sql} FOR UPDATE" if lock else sql


def _evaluate_dataset(facts_by_case):
    preliminary = {
        case_no: evaluate_scheduling_bootstrap(facts)
        for case_no, facts in facts_by_case.items()
    }
    return {
        case_no: evaluate_scheduling_bootstrap(
            _with_external_occupancy(case_no, facts, facts_by_case, preliminary)
        )
        for case_no, facts in facts_by_case.items()
    }


def _with_external_occupancy(case_no, facts, all_facts, preliminary):
    occupancy = list(_assignment_occupancy(case_no, all_facts))
    occupancy.extend(_candidate_buffer_occupancy(case_no, preliminary))
    return SchedulingBootstrapFacts(
        facts.order,
        facts.assignments,
        facts.schedules,
        tuple(occupancy),
    )


def _assignment_occupancy(case_no, facts_by_case):
    for other_case, facts in facts_by_case.items():
        if other_case == case_no:
            continue
        for assignment in facts.assignments:
            if not _has_valid_interval(assignment):
                continue
            for item in _inclusive_dates(
                assignment.assigned_start_date,
                assignment.assigned_end_date,
            ):
                yield ExternalStaffOccupancyFact(
                    assignment.staff_id,
                    item,
                    other_case,
                )


def _candidate_buffer_occupancy(case_no, preliminary):
    for other_case, decision in preliminary.items():
        if other_case == case_no or decision.candidate is None:
            continue
        for assignment in decision.candidate.assignments:
            for item in assignment.buffer_dates:
                yield ExternalStaffOccupancyFact(
                    assignment.staff_id,
                    item,
                    other_case,
                )


def _has_valid_interval(assignment) -> bool:
    return (
        isinstance(assignment.assigned_start_date, date)
        and isinstance(assignment.assigned_end_date, date)
        and assignment.assigned_end_date >= assignment.assigned_start_date
    )


def _inclusive_dates(start_date, end_date):
    return tuple(
        start_date + timedelta(days=offset)
        for offset in range((end_date - start_date).days + 1)
    )


def _case_plan(case_no, facts_by_case, decisions):
    facts = facts_by_case[case_no]
    decision = decisions[case_no]
    return {
        "case_no": case_no,
        "outcome": "eligible" if decision.candidate else "review",
        "issue_codes": [item.value for item in decision.issues],
        "assignment_ids": [item.assignment_id for item in facts.assignments],
        "schedule_ids": [item.schedule_id for item in facts.schedules],
    }


def _fingerprint(value) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def apply_plan(connection, expected_plan) -> dict[str, object]:
    fresh_plan = build_plan(connection, lock=True)
    _require_matching_plan(expected_plan, fresh_plan)
    facts_by_case = _load_facts_by_case(connection, lock=False)
    decisions = _evaluate_dataset(facts_by_case)
    generations = _persist_decisions(connection, facts_by_case, decisions)
    return {**fresh_plan, "generations": generations}


def _require_matching_plan(expected, fresh) -> None:
    for key in ("migration", "database", "dataset_fingerprint", "cases"):
        if expected.get(key) != fresh.get(key):
            raise RuntimeError(f"scheduling bootstrap plan changed: {key}")


def _persist_decisions(connection, facts_by_case, decisions):
    generations = {}
    with connection.cursor() as cursor:
        for case_no, decision in decisions.items():
            if decision.candidate is not None:
                generations[case_no] = persist_scheduling_bootstrap(
                    cursor,
                    decision.candidate,
                    MIGRATION_ACTOR,
                )
                continue
            append_scheduling_bootstrap_reviews(
                cursor,
                case_no,
                decision.issues,
                _review_evidence(facts_by_case[case_no], decision),
                MIGRATION_ACTOR,
            )
    return generations


def _review_evidence(facts, decision: SchedulingBootstrapDecision):
    return {
        "assignment_count": len(facts.assignments),
        "issue_codes": [item.value for item in decision.issues],
        "schedule_count": len(facts.schedules),
    }


def verify_receipt(connection, receipt) -> dict[str, object]:
    cases = receipt.get("cases")
    if not isinstance(cases, list):
        raise RuntimeError("scheduling bootstrap receipt cases are invalid")
    with connection.cursor() as cursor:
        results = tuple(_verify_case(cursor, item) for item in cases)
    return {
        "migration": MIGRATION_ID,
        "verified_count": len(results),
        "results": results,
    }


def _verify_case(cursor, item):
    case_no = item["case_no"]
    if item["outcome"] == "eligible":
        cursor.execute(
            "SELECT generation_counter,aggregate_version,effective_generation_id "
            "FROM scheduling_aggregates WHERE case_no=%s",
            (case_no,),
        )
        aggregate = cursor.fetchone()
        if not aggregate or int(aggregate["generation_counter"]) != 1:
            raise RuntimeError(f"scheduling bootstrap missing: {case_no}")
        return {"case_no": case_no, "outcome": "eligible"}
    _verify_review_events(cursor, item)
    return {"case_no": case_no, "outcome": "review"}


def _verify_review_events(cursor, item) -> None:
    cursor.execute(
        "SELECT issue_code FROM scheduling_bootstrap_review_events "
        "WHERE case_no=%s AND migration_identity=%s ORDER BY issue_code",
        (item["case_no"], MIGRATION_ACTOR),
    )
    actual = [row["issue_code"] for row in cursor.fetchall()]
    if actual != sorted(item["issue_codes"]):
        raise RuntimeError(f"scheduling bootstrap review drift: {item['case_no']}")


def _read_json(path_value: str) -> dict[str, object]:
    path = Path(path_value).expanduser().resolve()
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path_value: str, payload) -> None:
    path = Path(path_value).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _connection():
    return pymysql.connect(
        **DB_CONFIG,
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False,
    )


def _require_target_database(target_database: str) -> None:
    if target_database != DB_CONFIG["database"]:
        raise RuntimeError("target database does not match process DB_DATABASE")


def _run_dry_run(arguments) -> dict[str, object]:
    connection = _connection()
    try:
        payload = {**build_plan(connection), "mode": "dry-run"}
        connection.rollback()
    finally:
        connection.close()
    _write_json(arguments.receipt_path, payload)
    return payload


def _run_apply(arguments) -> dict[str, object]:
    validate_backup(arguments.backup_receipt, target_database=arguments.target_database)
    expected = _read_json(arguments.plan_receipt)
    connection = _connection()
    try:
        payload = {**apply_plan(connection, expected), "mode": "apply"}
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
    _write_json(arguments.receipt_path, payload)
    return payload


def _run_verify(arguments) -> dict[str, object]:
    receipt = _read_json(arguments.receipt_path)
    connection = _connection()
    try:
        payload = verify_receipt(connection, receipt)
        connection.rollback()
        return {**payload, "mode": "verify"}
    finally:
        connection.close()


def _parse_arguments():
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    mode.add_argument("--verify", action="store_true")
    parser.add_argument("--target-database", required=True)
    parser.add_argument("--backup-receipt")
    parser.add_argument("--plan-receipt")
    parser.add_argument("--receipt-path", required=True)
    return parser.parse_args()


def main() -> int:
    arguments = _parse_arguments()
    _require_target_database(arguments.target_database)
    if arguments.dry_run:
        result = _run_dry_run(arguments)
    elif arguments.apply:
        result = _run_apply(arguments)
    else:
        result = _run_verify(arguments)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
