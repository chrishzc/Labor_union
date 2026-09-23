"""
File: service_date_confirmation_repository.py
Description: 實作 confirmed service dates persistence 與 typed borrowed owner read。
"""

from __future__ import annotations

import json
from datetime import timedelta

from pymysql.err import IntegrityError

from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from subsystems.orders.historical_restart_arrangement import (
    HistoricalRestartArrangementReceipt,
)
from infrastructure.mysql.payroll_terms_writer import (
    load_historical_restart_arrangement_rates,
    persist_historical_restart_arrangement_rates,
)
from infrastructure.mysql.scheduling_replacement_writer import (
    persist_scheduling_replacement,
)
from subsystems.orders.service_date_confirmation_workflow import (
    RestartSchedulingAssignmentFacts,
    ServiceDateConfirmationFacts,
    ServiceDateConfirmationReceipt,
)


class MySqlServiceDateConfirmationRepository:
    def __init__(self, connection) -> None:
        self._connection = connection

    def load(self, case_no, *, lock=False):
        lock_clause = " FOR UPDATE" if lock else ""
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT o.case_no,o.lifecycle_version,o.start_date,o.actual_start_date,o.service_days,"
                "o.service_hours_per_day,"
                "COALESCE(g.aggregate_version,0) AS scheduling_version "
                "FROM orders o LEFT JOIN scheduling_aggregates g ON g.case_no=o.case_no "
                "WHERE o.case_no=%s" + lock_clause,
                (case_no,),
            )
            order = cursor.fetchone()
            if not order:
                raise ValueError("service_date_confirmation_case_not_found")
            cursor.execute(
                "SELECT id,version,order_version FROM confirmed_service_date_versions "
                "WHERE case_no=%s AND is_current=1" + lock_clause,
                (case_no,),
            )
            current = cursor.fetchone()
            current_dates = self._dates(cursor, current["id"], lock=lock) if current else ()
            suggested = self._suggested_dates(cursor, case_no, order, lock=lock)
            restart_generation, restart_assignments = self._restart_scheduling_source(
                cursor, case_no, int(order["service_days"]), lock=lock
            )
        return ServiceDateConfirmationFacts(
            str(order["case_no"]),
            int(order["lifecycle_version"] or 0),
            int(order["scheduling_version"] or 0),
            int(order["service_days"]),
            suggested,
            self._selectable_dates(order),
            int(current["version"]) if current else None,
            current_dates,
            restart_generation,
            restart_assignments,
            float(order["service_hours_per_day"]),
            int(current["order_version"]) if current else None,
        )

    def load_service_dates(
        self, case_no: str, *, for_update: bool = False
    ) -> ServiceDateConfirmationFacts:
        """Expose the owner root through the shared typed M3 read port."""

        return self.load(case_no, lock=for_update)

    def lock_arrangement_staff(self, staff_ids):
        if staff_ids != tuple(sorted(set(staff_ids))) or not staff_ids:
            raise ValueError("historical_arrangement_staff_set_invalid_blocked")
        placeholders = ",".join("%s" for _ in staff_ids)
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT s.id,s.status,COALESCE(l.lifecycle_state,'active') AS lifecycle_state "
                "FROM staff s LEFT JOIN staff_lifecycle_states l ON l.staff_id=s.id "
                f"WHERE s.id IN ({placeholders}) ORDER BY s.id FOR UPDATE",
                staff_ids,
            )
            rows = tuple(cursor.fetchall())
        if tuple(int(row["id"]) for row in rows) != staff_ids or any(
            row["status"] != "active" or row["lifecycle_state"] == "retired"
            for row in rows
        ):
            raise ValueError("historical_arrangement_staff_ineligible_blocked")

    def validate_arrangement_availability(self, candidate, *, lock):
        occupied = {
            (assignment.staff_id, assignment.assigned_start_date + timedelta(days=offset))
            for assignment in candidate.assignments
            for offset in range(
                (assignment.assigned_end_date - assignment.assigned_start_date).days + 1
            )
        }
        occupied.update(
            (buffer.staff_id, day)
            for buffer in candidate.buffers if buffer.active
            for day in buffer.dates
        )
        staff_ids = tuple(sorted({item.staff_id for item in candidate.assignments}))
        first = min(day for _, day in occupied)
        last = max(day for _, day in occupied)
        placeholders = ",".join("%s" for _ in staff_ids)
        suffix = " FOR UPDATE" if lock else ""
        queries = (
            (
                "SELECT o.staff_id,o.occupancy_date,g.case_no "
                "FROM scheduling_effective_occupancy o "
                "JOIN scheduling_generations g ON g.id=o.generation_id "
                f"WHERE o.staff_id IN ({placeholders}) "
                "AND o.occupancy_date BETWEEN %s AND %s" + suffix,
            ),
            (
                "SELECT d.staff_id,d.lock_date AS occupancy_date,p.case_no "
                "FROM caregiver_availability_lock_days d "
                "JOIN caregiver_availability_locks l ON l.id=d.lock_id "
                "JOIN caregiver_matching_plan_segments s ON s.id=d.segment_id "
                "JOIN caregiver_matching_plans p ON p.id=s.plan_id "
                f"WHERE d.staff_id IN ({placeholders}) "
                "AND d.lock_date BETWEEN %s AND %s "
                "AND d.active_marker=1 AND l.is_active=1" + suffix,
            ),
            (
                "SELECT d.staff_id,d.occupancy_date,b.case_no "
                "FROM scheduling_leave_occupancy_days d "
                "JOIN scheduling_leave_substitution_batches b ON b.batch_key=d.batch_key "
                f"WHERE d.staff_id IN ({placeholders}) "
                "AND d.occupancy_date BETWEEN %s AND %s AND d.active_marker=1" + suffix,
            ),
        )
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT s.id,s.status,COALESCE(l.lifecycle_state,'active') AS lifecycle_state "
                "FROM staff s LEFT JOIN staff_lifecycle_states l ON l.staff_id=s.id "
                f"WHERE s.id IN ({placeholders}) ORDER BY s.id" + suffix,
                staff_ids,
            )
            staff_rows = tuple(cursor.fetchall())
            if tuple(int(row["id"]) for row in staff_rows) != staff_ids or any(
                row["status"] != "active" or row["lifecycle_state"] == "retired"
                for row in staff_rows
            ):
                raise ValueError("historical_arrangement_staff_ineligible_blocked")
            for (sql,) in queries:
                cursor.execute(sql, (*staff_ids, first, last))
                for row in cursor.fetchall():
                    if (
                        int(row["staff_id"]), row["occupancy_date"]
                    ) in occupied and str(row["case_no"]) != candidate.case_no:
                        raise ValueError("historical_arrangement_occupancy_conflict")

    def arrangement_rate_fingerprint(self, candidate, *, lock):
        with self._connection.cursor() as cursor:
            policies = load_historical_restart_arrangement_rates(
                cursor, candidate.case_no, candidate.assignments, lock=lock,
            )
        return fingerprint_payload({"rates": policies})

    def replay_arrangement(self, key, command_fingerprint, *, lock):
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT command_family,command_fingerprint,preview_fingerprint,"
                "result_snapshot FROM scheduling_command_receipts "
                "WHERE idempotency_key=%s" + (" FOR UPDATE" if lock else ""),
                (key,),
            )
            row = cursor.fetchone()
        if row is None:
            return None
        if (
            row["command_family"] != "orders_historical_restart_arrangement"
            or row["command_fingerprint"] != command_fingerprint
        ):
            raise ValueError("historical_arrangement_idempotency_conflict")
        stored = row["result_snapshot"]
        payload = json.loads(stored) if isinstance(stored, str) else stored
        if (
            not isinstance(payload, dict)
            or not isinstance(payload.get("assignment_ids"), dict)
            or not isinstance(payload.get("case_no"), str)
            or not payload["case_no"]
            or not isinstance(payload.get("scheduling_version"), int)
            or not isinstance(payload.get("generation_number"), int)
            or not payload["assignment_ids"]
            or any(
                not isinstance(value, int) or value <= 0
                for value in payload["assignment_ids"].values()
            )
        ):
            raise ValueError("historical_arrangement_receipt_integrity_blocked")
        assignment_ids = payload["assignment_ids"]
        return HistoricalRestartArrangementReceipt(
            str(payload["case_no"]),
            int(payload["scheduling_version"]),
            int(payload["generation_number"]),
            tuple(int(value) for _, value in sorted(assignment_ids.items())),
            PreviewFingerprint(str(row["preview_fingerprint"])),
        )

    def persist_arrangement(self, command):
        with self._connection.cursor() as cursor:
            policies = load_historical_restart_arrangement_rates(
                cursor, command.candidate.case_no,
                command.candidate.assignments, lock=True,
            )
            try:
                result = persist_scheduling_replacement(cursor, command)
            except IntegrityError as error:
                if error.args and error.args[0] == 1062:
                    detail = str(error)
                    if (
                        "uq_staff_schedule_effective_date" in detail
                        or "scheduling_effective_occupancy.PRIMARY" in detail
                    ):
                        raise ValueError("historical_arrangement_occupancy_conflict") from error
                    if (
                        "uq_scheduling_command_receipt_key" in detail
                        or "uq_scheduling_rebuild_idempotency" in detail
                    ):
                        raise ValueError("historical_arrangement_idempotency_conflict") from error
                raise
            persist_historical_restart_arrangement_rates(cursor, policies, result)
        resolved = result.assignment_resolution.assignment_id_by_candidate_key
        return HistoricalRestartArrangementReceipt(
            command.candidate.case_no,
            result.scheduling_version,
            command.candidate.generation_number,
            tuple(resolved[item.candidate_key] for item in command.candidate.assignments),
            command.preview_fingerprint,
        )

    def replay(self, idempotency_key, command_fingerprint, *, actor, reason, for_update=False):
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT r.command_fingerprint,v.* FROM confirmed_service_date_receipts r "
                "JOIN confirmed_service_date_versions v ON v.id=r.confirmed_version_id "
                "WHERE r.idempotency_key=%s" + (" FOR UPDATE" if for_update else ""),
                (idempotency_key,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            if row["command_fingerprint"] != command_fingerprint:
                raise ValueError("service_date_confirmation_idempotency_conflict")
            if (
                row["confirmed_by_actor_id"] != actor
                or row["reason"] != reason
            ):
                raise ValueError("service_date_confirmation_idempotency_conflict")
            dates = self._dates(cursor, row["id"], lock=for_update)
        return _receipt(row, dates)

    def save(self, candidate, *, actor, reason, idempotency_key, command_fingerprint):
        with self._connection.cursor() as cursor:
            cursor.execute(
                "UPDATE confirmed_service_date_versions SET is_current=NULL,invalidated_at_utc=UTC_TIMESTAMP(6) "
                "WHERE case_no=%s AND is_current=1",
                (candidate.case_no,),
            )
            cursor.execute(
                "SELECT COALESCE(MAX(version),0)+1 AS next_version FROM confirmed_service_date_versions "
                "WHERE case_no=%s FOR UPDATE",
                (candidate.case_no,),
            )
            version = int(cursor.fetchone()["next_version"])
            cursor.execute(
                "INSERT INTO confirmed_service_date_versions "
                "(case_no,version,order_version,scheduling_version,service_day_count,service_date_fingerprint,"
                "is_current,confirmed_by_actor_id,reason) VALUES (%s,%s,%s,%s,%s,%s,1,%s,%s)",
                (candidate.case_no, version, candidate.order_version, candidate.scheduling_version,
                 candidate.contracted_service_days, candidate.fingerprint.value, actor, reason or None),
            )
            version_id = int(cursor.lastrowid)
            cursor.executemany(
                "INSERT INTO confirmed_service_date_days (confirmed_version_id,ordinal,service_date) VALUES (%s,%s,%s)",
                [(version_id, index, value) for index, value in enumerate(candidate.service_dates, start=1)],
            )
            cursor.execute(
                "INSERT INTO confirmed_service_date_receipts "
                "(idempotency_key,command_fingerprint,confirmed_version_id,actor_id) VALUES (%s,%s,%s,%s)",
                (idempotency_key, command_fingerprint, version_id, actor),
            )
        return ServiceDateConfirmationReceipt(
            candidate.case_no,
            version,
            candidate.order_version,
            candidate.scheduling_version,
            candidate.service_dates,
            candidate.fingerprint,
        )

    @staticmethod
    def _dates(cursor, version_id, *, lock=False):
        cursor.execute(
            "SELECT service_date FROM confirmed_service_date_days WHERE confirmed_version_id=%s "
            "ORDER BY ordinal" + (" FOR UPDATE" if lock else ""),
            (version_id,),
        )
        return tuple(row["service_date"] for row in cursor.fetchall())

    @staticmethod
    def _suggested_dates(cursor, case_no, order, *, lock=False):
        cursor.execute(
            "SELECT s.work_date FROM staff_schedule s JOIN scheduling_aggregates g "
            "ON g.effective_generation_id=s.generation_id WHERE g.case_no=%s "
            "AND s.effective_marker=1 AND s.is_work_day=1 ORDER BY s.work_date"
            + (" FOR UPDATE" if lock else ""),
            (case_no,),
        )
        dates = tuple(dict.fromkeys(row["work_date"] for row in cursor.fetchall()))
        if len(dates) == int(order["service_days"]):
            return dates
        return ()

    @staticmethod
    def _selectable_dates(order):
        start_date = order["actual_start_date"] or order["start_date"]
        return tuple(
            start_date + timedelta(days=offset)
            for offset in range(int(order["service_days"]) + 30)
        )

    @staticmethod
    def _restart_scheduling_source(cursor, case_no, contracted_days, *, lock=False):
        lock_clause = " FOR UPDATE" if lock else ""
        cursor.execute(
            "SELECT generation.generation_number FROM scheduling_aggregates aggregate "
            "JOIN scheduling_generations generation ON generation.id=aggregate.effective_generation_id "
            "JOIN scheduling_command_receipts restart_receipt "
            "ON restart_receipt.resulting_generation_id=generation.id "
            "AND restart_receipt.case_no=aggregate.case_no "
            "AND restart_receipt.command_family='orders_historical_precision_restart' "
            "WHERE aggregate.case_no=%s AND generation.status='effective' "
            "AND generation.effective_marker=1 "
            "AND NOT EXISTS (SELECT 1 FROM case_staff_assignments current_assignment "
            "WHERE current_assignment.generation_id=generation.id)" + lock_clause,
            (case_no,),
        )
        generation = cursor.fetchone()
        if generation is None:
            return None, ()
        cursor.execute(
            "SELECT evidence.assignment_id,evidence.staff_id,evidence.caregiver_ordinal,"
            "staff.name AS staff_name,"
            "COUNT(schedule.id) AS service_day_count "
            "FROM historical_order_adoption_receipts receipt "
            "JOIN historical_order_pairing_evidence evidence ON evidence.receipt_id=receipt.id "
            "JOIN staff ON staff.id=evidence.staff_id "
            "LEFT JOIN staff_schedule schedule ON schedule.assignment_id=evidence.assignment_id "
            "AND schedule.is_work_day=1 "
            "WHERE receipt.id=(SELECT MAX(candidate.id) FROM historical_order_adoption_receipts candidate "
            "WHERE candidate.case_no=%s AND candidate.outcome='adopted') "
            "AND evidence.staff_id IS NOT NULL "
            "GROUP BY evidence.assignment_id,evidence.staff_id,evidence.caregiver_ordinal,staff.name "
            "ORDER BY evidence.caregiver_ordinal" + lock_clause,
            (case_no,),
        )
        rows = tuple(cursor.fetchall())
        assignments = tuple(
            RestartSchedulingAssignmentFacts(
                None if row["assignment_id"] is None else int(row["assignment_id"]),
                int(row["staff_id"]),
                index,
                contracted_days if len(rows) == 1 else int(row["service_day_count"]),
                str(row["staff_name"]),
            )
            for index, row in enumerate(rows, start=1)
        )
        return int(generation["generation_number"]), assignments


def _receipt(row, dates):
    return ServiceDateConfirmationReceipt(
        str(row["case_no"]),
        int(row["version"]),
        int(row["order_version"]),
        int(row["scheduling_version"]),
        dates,
        PreviewFingerprint(str(row["service_date_fingerprint"])),
    )
