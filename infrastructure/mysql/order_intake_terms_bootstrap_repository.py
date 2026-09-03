"""MySQL adapter for Orders intake terms bootstrap."""

from __future__ import annotations

from datetime import date

from domains.orders.lifecycle import OrderLifecycleStatus
from infrastructure.mysql.admin_command_repository import AdminCommandRepository
from subsystems.orders.order_intake_terms_bootstrap import (
    OrderIntakeTermsBootstrapFacts,
)


class MySqlOrderIntakeTermsBootstrapRepository:
    def __init__(self, connection) -> None:
        self._connection = connection
        self._receipts = AdminCommandRepository(connection)

    def load_case(self, case_no: str, *, for_update: bool):
        suffix = " FOR UPDATE" if for_update else ""
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT o.case_no,o.status,o.lifecycle_version,o.start_date,"
                "o.service_days,o.actual_start_date,"
                "EXISTS(SELECT 1 FROM order_service_data_locks l "
                "WHERE l.case_no=o.case_no) AS service_data_locked,"
                "(EXISTS(SELECT 1 FROM client_finance_accounts f "
                "WHERE f.case_no=o.case_no) OR "
                "EXISTS(SELECT 1 FROM client_payment_terms t "
                "WHERE t.case_no=o.case_no)) AS client_finance_present,"
                "(EXISTS(SELECT 1 FROM payroll_case_accounts p "
                "WHERE p.case_no=o.case_no) OR "
                "EXISTS(SELECT 1 FROM case_payroll_rate_policy_snapshots r "
                "WHERE r.case_no=o.case_no)) AS payroll_present,"
                "s.case_no AS scheduling_case_no,s.aggregate_version,"
                "s.generation_counter,s.effective_generation_id,"
                "EXISTS(SELECT 1 FROM case_staff_assignments a "
                "WHERE a.case_no=o.case_no) AS assignment_exists "
                "FROM orders o LEFT JOIN scheduling_aggregates s "
                "ON s.case_no=o.case_no WHERE o.case_no=%s" + suffix,
                (case_no,),
            )
            row = cursor.fetchone()
        if row is None:
            return None
        scheduling_present = row["scheduling_case_no"] is not None
        scheduling_pristine = (
            not scheduling_present
            or (
                int(row["aggregate_version"] or 0) == 0
                and int(row["generation_counter"] or 0) == 0
                and row["effective_generation_id"] is None
                and not bool(row["assignment_exists"])
            )
        )
        service_days = row["service_days"]
        return OrderIntakeTermsBootstrapFacts(
            case_no=str(row["case_no"]),
            status=OrderLifecycleStatus(str(row["status"])),
            lifecycle_version=int(row["lifecycle_version"]),
            start_date=row["start_date"],
            service_days=None if service_days is None else int(service_days),
            actual_start_date=row["actual_start_date"],
            service_data_locked=bool(row["service_data_locked"]),
            client_finance_present=bool(row["client_finance_present"]),
            payroll_present=bool(row["payroll_present"]),
            scheduling_present=scheduling_present,
            scheduling_pristine=scheduling_pristine,
        )

    def update_missing_terms(
        self,
        case_no: str,
        expected_lifecycle_version: int,
        start_date: date,
        service_days: int,
        *,
        fill_start_date: bool,
        fill_service_days: bool,
    ) -> int:
        assignments: list[str] = []
        parameters: list[object] = []
        if fill_start_date:
            assignments.append("start_date=%s")
            parameters.append(start_date)
        if fill_service_days:
            assignments.append("service_days=%s")
            parameters.append(service_days)
        if not assignments:
            raise RuntimeError("order_intake_terms_bootstrap_nothing_to_write")
        assignments.append("lifecycle_version=lifecycle_version+1")
        parameters.extend((case_no, expected_lifecycle_version))
        with self._connection.cursor() as cursor:
            cursor.execute(
                "UPDATE orders SET "
                + ",".join(assignments)
                + " WHERE case_no=%s AND lifecycle_version=%s",
                tuple(parameters),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("order_intake_terms_bootstrap_write_conflict")
        return expected_lifecycle_version + 1

    def load_receipt(self, family: str, key: str):
        return self._receipts.load_receipt(family, key)

    def save_receipt(
        self,
        family: str,
        key: str,
        request_fingerprint: str,
        preview_fingerprint: str,
        actor: str,
        reason: str,
        result: dict[str, object],
    ) -> None:
        self._receipts.save_receipt(
            family,
            key,
            request_fingerprint,
            preview_fingerprint,
            actor,
            reason,
            result,
        )


__all__ = ["MySqlOrderIntakeTermsBootstrapRepository"]
