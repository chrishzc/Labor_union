"""
File: service_date_confirmation_repository.py
Description: 實作 confirmed service dates persistence 與 typed borrowed owner read。
"""

from __future__ import annotations

from datetime import timedelta

from shared_kernel.fingerprints import PreviewFingerprint
from subsystems.orders.service_date_confirmation_workflow import (
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
                "SELECT o.case_no,o.lifecycle_version,o.start_date,o.service_days,"
                "COALESCE(g.aggregate_version,0) AS scheduling_version "
                "FROM orders o LEFT JOIN scheduling_aggregates g ON g.case_no=o.case_no "
                "WHERE o.case_no=%s" + lock_clause,
                (case_no,),
            )
            order = cursor.fetchone()
            if not order:
                raise ValueError("service_date_confirmation_case_not_found")
            cursor.execute(
                "SELECT id,version FROM confirmed_service_date_versions "
                "WHERE case_no=%s AND is_current=1" + lock_clause,
                (case_no,),
            )
            current = cursor.fetchone()
            current_dates = self._dates(cursor, current["id"], lock=lock) if current else ()
            suggested = self._suggested_dates(cursor, case_no, order, lock=lock)
        return ServiceDateConfirmationFacts(
            str(order["case_no"]),
            int(order["lifecycle_version"] or 0),
            int(order["scheduling_version"] or 0),
            int(order["service_days"]),
            suggested,
            self._selectable_dates(order),
            int(current["version"]) if current else None,
            current_dates,
        )

    def load_service_dates(
        self, case_no: str, *, for_update: bool = False
    ) -> ServiceDateConfirmationFacts:
        """Expose the owner root through the shared typed M3 read port."""

        return self.load(case_no, lock=for_update)

    def replay(self, idempotency_key, command_fingerprint):
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT r.command_fingerprint,v.* FROM confirmed_service_date_receipts r "
                "JOIN confirmed_service_date_versions v ON v.id=r.confirmed_version_id "
                "WHERE r.idempotency_key=%s",
                (idempotency_key,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            if row["command_fingerprint"] != command_fingerprint:
                raise ValueError("service_date_confirmation_idempotency_conflict")
            dates = self._dates(cursor, row["id"])
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
                "UPDATE matching_schedule_snapshots SET current_marker=NULL,status='invalidated',"
                "invalidated_at_utc=UTC_TIMESTAMP(6) WHERE case_no=%s AND current_marker=1",
                (candidate.case_no,),
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
        return tuple(
            order["start_date"] + timedelta(days=offset)
            for offset in range(int(order["service_days"]) + 45)
        )


def _receipt(row, dates):
    return ServiceDateConfirmationReceipt(
        str(row["case_no"]),
        int(row["version"]),
        int(row["order_version"]),
        int(row["scheduling_version"]),
        dates,
        PreviewFingerprint(str(row["service_date_fingerprint"])),
    )
