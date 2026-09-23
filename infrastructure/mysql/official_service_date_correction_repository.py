"""MySQL owner handoff for post-service official date correction."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from infrastructure.mysql.assignment_plan_repository import load_occupancy_snapshot
from infrastructure.mysql.order_terms_read_model import (
    lock_staff_mutexes,
    preflight_staff_ids,
    select_order,
    select_scheduling_aggregate,
)
from infrastructure.mysql.payroll_terms_writer import persist_actual_start_rate_snapshot_carry
from infrastructure.mysql.scheduling_replacement_writer import persist_scheduling_replacement
from shared_kernel.fingerprints import PreviewFingerprint
from subsystems.orders.official_service_date_correction_workflow import (
    OfficialAssignmentDates,
    OfficialDateFacts,
    OfficialDateReceipt,
    OfficialDateSelection,
)


_FAMILY = "orders_official_service_date_correction"


class MySqlOfficialServiceDateCorrectionRepository:
    def __init__(self, connection) -> None:
        self._connection = connection

    def load(self, case_no: str, *, lock: bool = False) -> OfficialDateFacts:
        suffix = " FOR UPDATE" if lock else ""
        with self._connection.cursor() as cursor:
            order = select_order(cursor, case_no, lock=lock)
            aggregate = select_scheduling_aggregate(cursor, case_no, lock=lock)
            if lock:
                staff_ids = preflight_staff_ids(cursor, case_no)
                lock_staff_mutexes(cursor, staff_ids)
            generation_id = aggregate["effective_generation_id"]
            if generation_id is None:
                raise ValueError("official_date_effective_generation_required")
            cursor.execute(
                "SELECT id,generation_number FROM scheduling_generations "
                "WHERE id=%s AND case_no=%s AND status='effective' AND effective_marker=1" + suffix,
                (generation_id, case_no),
            )
            generation = cursor.fetchone()
            if generation is None:
                raise ValueError("official_date_effective_generation_conflict")
            cursor.execute(
                "SELECT a.id,a.staff_id,a.assignment_sequence,a.status,a.floor_fee_allocated,"
                "s.name AS staff_name FROM case_staff_assignments a "
                "JOIN staff s ON s.id=a.staff_id WHERE a.generation_id=%s "
                "AND a.status NOT IN ('cancelled','replaced') ORDER BY a.id" + suffix,
                (generation_id,),
            )
            rows = tuple(cursor.fetchall())
            if not rows:
                raise ValueError("official_date_completed_assignment_required")
            cursor.execute(
                "SELECT assignment_id,staff_id,work_date,is_work_day,is_double_pay "
                "FROM staff_schedule WHERE generation_id=%s AND effective_marker=1 "
                "ORDER BY work_date,assignment_id" + suffix,
                (generation_id,),
            )
            schedule = tuple(cursor.fetchall())
            by_assignment = {int(row["id"]): [] for row in rows}
            for day in schedule:
                assignment_id = int(day["assignment_id"])
                if assignment_id not in by_assignment or not bool(day["is_work_day"]):
                    raise ValueError("official_date_schedule_ownership_invalid")
                by_assignment[assignment_id].append(day["work_date"])
            if any(not dates for dates in by_assignment.values()):
                raise ValueError("official_date_schedule_incomplete")
            assignments = tuple(OfficialAssignmentDates(
                int(row["id"]), int(row["staff_id"]), int(row["assignment_sequence"]),
                str(row["status"]), tuple(by_assignment[int(row["id"])]), str(row["staff_name"]),
            ) for row in rows)
            cursor.execute("SELECT actual_end_date FROM orders WHERE case_no=%s" + suffix, (case_no,))
            actual_end_date = cursor.fetchone()["actual_end_date"]
            cursor.execute(
                "SELECT COUNT(*) AS total FROM scheduling_buffer_days "
                "WHERE generation_id=%s AND active_marker=1" + suffix,
                (generation_id,),
            )
            active_buffers = int(cursor.fetchone()["total"])
            ids = tuple(by_assignment)
            placeholders = ",".join("%s" for _ in ids)
            cursor.execute(
                "SELECT COUNT(*) AS total FROM payroll_special_pay_events "
                f"WHERE assignment_id IN ({placeholders})" + suffix, ids,
            )
            special_pay = int(cursor.fetchone()["total"])
            cursor.execute(
                "SELECT COUNT(*) AS total FROM assignment_payroll_rate_snapshots "
                f"WHERE assignment_id IN ({placeholders})" + suffix, ids,
            )
            complete_source_rates = int(cursor.fetchone()["total"]) == len(ids)
            cursor.execute(
                "SELECT COUNT(*) AS total FROM payroll_adjustment_allocations "
                f"WHERE assignment_id IN ({placeholders})" + suffix, ids,
            )
            adjustments = int(cursor.fetchone()["total"])
            cursor.execute(
                "SELECT COUNT(*) AS total FROM client_obligations "
                "WHERE case_no=%s AND obligation_type='subsidy_return'" + suffix,
                (case_no,),
            )
            subsidy_returns = int(cursor.fetchone()["total"])
            cursor.execute(
                "SELECT aggregate_version FROM client_finance_accounts WHERE case_no=%s" + suffix,
                (case_no,),
            )
            finance = cursor.fetchone()
            cursor.execute(
                "SELECT aggregate_version FROM payroll_case_accounts WHERE case_no=%s" + suffix,
                (case_no,),
            )
            payroll = cursor.fetchone()
        return OfficialDateFacts(
            case_no=case_no,
            order_version=int(order["lifecycle_version"]),
            order_status=str(order["status"]),
            actual_start_date=order["actual_start_date"],
            actual_end_date=actual_end_date,
            service_data_locked=bool(order["service_data_locked"]),
            service_days=int(order["service_days"]),
            hours_per_day=float(order["service_hours_per_day"]),
            scheduling_version=int(aggregate["aggregate_version"]),
            generation_id=int(generation_id),
            generation_number=int(generation["generation_number"]),
            assignments=assignments,
            monetary_change_blocker=bool(
                active_buffers or special_pay or adjustments or subsidy_returns
                or not complete_source_rates
                or any(bool(day["is_double_pay"]) for day in schedule)
                or any(int(row["floor_fee_allocated"] or 0) for row in rows)
            ),
            client_finance_version=int(finance["aggregate_version"]) if finance else None,
            payroll_version=int(payroll["aggregate_version"]) if payroll else None,
        )

    def validate_availability(self, candidate, *, lock: bool) -> None:
        staff_ids = tuple(sorted({assignment.staff_id for assignment in candidate.assignments}))
        with self._connection.cursor() as cursor:
            occupied, _ = load_occupancy_snapshot(
                cursor, staff_ids, candidate.case_no, lock=lock,
            )
        proposed = {
            (assignment.staff_id, assignment.assigned_start_date + timedelta(days=offset))
            for assignment in candidate.assignments
            for offset in range(
                (assignment.assigned_end_date - assignment.assigned_start_date).days + 1
            )
        }
        if any(
            (fact.staff_id, fact.occupancy_date) in proposed
            and fact.source_case_no != candidate.case_no
            for fact in occupied
        ):
            raise ValueError("official_date_occupancy_conflict")

    def replay(self, key: str, command_fingerprint: str, *, lock: bool = False) -> OfficialDateReceipt | None:
        suffix = " FOR UPDATE" if lock else ""
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT command_family,command_fingerprint,preview_fingerprint,case_no,"
                "resulting_scheduling_version,resulting_generation_id FROM scheduling_command_receipts "
                "WHERE idempotency_key=%s" + suffix, (key,),
            )
            row = cursor.fetchone()
            if row is None:
                return None
            if row["command_family"] != _FAMILY or row["command_fingerprint"] != command_fingerprint:
                raise ValueError("official_date_idempotency_mismatch")
            cursor.execute(
                "SELECT expected_version FROM order_lifecycle_state_events "
                "WHERE case_no=%s AND idempotency_key=%s" + suffix,
                (row["case_no"], key),
            )
            event = cursor.fetchone()
            if event is None:
                raise RuntimeError("official_date_receipt_incomplete")
            cursor.execute(
                "SELECT assignment_id,work_date FROM staff_schedule "
                "WHERE generation_id=%s AND is_work_day=1 ORDER BY assignment_id,work_date" + suffix,
                (row["resulting_generation_id"],),
            )
            dates = {}
            for item in cursor.fetchall():
                dates.setdefault(int(item["assignment_id"]), []).append(item["work_date"])
        return OfficialDateReceipt(
            str(row["case_no"]), int(event["expected_version"]) + 1,
            int(row["resulting_scheduling_version"]), int(row["resulting_generation_id"]),
            tuple(OfficialDateSelection(identity, tuple(values)) for identity, values in dates.items()),
            PreviewFingerprint(str(row["preview_fingerprint"])),
        )

    def replace_and_record(self, command, preview) -> OfficialDateReceipt:
        with self._connection.cursor() as cursor:
            result = persist_scheduling_replacement(cursor, command)
            persist_actual_start_rate_snapshot_carry(cursor, command, result)
            effective_dates = tuple(OfficialDateSelection(
                result.assignment_resolution.assignment_id_by_candidate_key[assignment.candidate_key],
                assignment.service_dates,
            ) for assignment in command.candidate.assignments)
            new_end = max(day for item in effective_dates for day in item.service_dates)
            cursor.execute(
                "INSERT INTO order_lifecycle_state_events "
                "(case_no,trigger_event,before_status,after_status,actor,business_date,"
                "expected_version,idempotency_key,facts_snapshot) "
                "VALUES (%s,'official_service_date_corrected',%s,%s,%s,%s,%s,%s,%s)",
                (
                    command.candidate.case_no, preview.facts.order_status,
                    preview.facts.order_status, command.actor.actor_id,
                    datetime.now(ZoneInfo("Asia/Taipei")).date(),
                    preview.facts.order_version, command.idempotency_key.value,
                    json.dumps({
                        "previous_generation_id": preview.facts.generation_id,
                        "successor_generation_id": result.generation_id,
                        "scheduling_receipt_id": result.scheduling_receipt_id,
                        "before": {str(a.assignment_id): [d.isoformat() for d in a.service_dates] for a in preview.facts.assignments},
                        "after": {str(a.assignment_id): [d.isoformat() for d in a.service_dates] for a in preview.selections},
                        "reason": command.reason,
                        "finance_impact": "no_op",
                        "payroll_impact": "no_op",
                    }, ensure_ascii=False, sort_keys=True),
                ),
            )
            cursor.execute(
                "UPDATE orders SET actual_end_date=%s,lifecycle_version=%s "
                "WHERE case_no=%s AND lifecycle_version=%s AND status='訂單完成'",
                (
                    new_end, preview.facts.order_version + 1,
                    command.candidate.case_no, preview.facts.order_version,
                ),
            )
            if cursor.rowcount != 1:
                raise ValueError("official_date_version_conflict")
        return OfficialDateReceipt(
            command.candidate.case_no, preview.facts.order_version + 1,
            result.scheduling_version, result.generation_id, effective_dates,
            preview.fingerprint,
        )
