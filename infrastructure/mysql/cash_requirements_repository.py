"""Bounded read-only cash-planning adapter; never creates accounting facts."""

from datetime import date
from decimal import Decimal

from infrastructure.mysql.accounts_payable_export_sources import MySqlStaffPayableExportSource
from subsystems.staff_payables.accounts_payable_export import CaseStaffPayableAuditItem
from subsystems.staff_payables.cash_requirements_query import CashRefundFact, CashRequirementCase


class MySqlCashRequirementsRepository:
    def __init__(self, connection):
        self._connection = connection
        self._staff = MySqlStaffPayableExportSource(connection)

    def query_cases(self, after_case_no, limit):
        with self._connection.cursor() as cursor:
            cursor.execute(_CASES_SQL, (after_case_no, after_case_no, limit))
            cases = tuple(cursor.fetchall())
        return tuple(self._case(row) for row in cases)

    def _case(self, row):
        case_no = row["case_no"]
        with self._connection.cursor() as cursor:
            cursor.execute(_REFUNDS_SQL, (case_no,))
            refunds = tuple(CashRefundFact(
                str(r["obligation_identity"]),
                "client_subsidy_return" if r["obligation_type"] == "subsidy_return" else "client_refund",
                int(r["amount_due_ntd"]), r["due_date"], str(row["client_name"]), bool(r["recipient_ready"]),
            ) for r in cursor.fetchall())
        staff_items = self._staff.load_case(case_no, date.min)
        if row["has_arrangement"]:
            with self._connection.cursor() as cursor:
                cursor.execute(_ARRANGED_STAFF_SQL, (case_no,))
                arranged_staff = tuple(cursor.fetchall())
            if arranged_staff:
                # A successor date assignment may retain the prior payable for
                # the same staff. Keep that owner fact, including paid evidence.
                staff_items = tuple(item for item in staff_items if item.source != "order_facts")
                covered_staff = {item.staff_id for item in staff_items}
                staff_items += tuple(CaseStaffPayableAuditItem(
                    str(case_no), int(staff["staff_id"]), staff["recipient_name"], None, None, None,
                    None, None, "order_facts", "missing_calculation_basis", "月嫂應付金額待確認",
                ) for staff in arranged_staff if staff["staff_id"] not in covered_staff)
        hours = row["historical_hours"]
        if hours is None and row["work_day_count"] and row["service_hours_per_day"] is not None:
            hours = Decimal(str(row["work_day_count"])) * Decimal(str(row["service_hours_per_day"]))
        return CashRequirementCase(
            str(case_no), str(row["client_name"]), str(row["order_status"]), bool(row["has_arrangement"]),
            row["planned_end_date"], str(row["identity_status"]),
            None if hours is None else Decimal(str(hours)),
            None if row["floor_fee"] is None else Decimal(str(row["floor_fee"])),
            row["client_hourly_rate_ntd"],
            None if not row["receivable_count"] else not bool(row["open_receivable_count"]),
            bool(row["return_count"]), staff_items, refunds,
        )


_CASES_SQL = """
SELECT o.case_no,c.name AS client_name,o.status AS order_status,c.identity_status,
       o.service_hours_per_day,
       CASE WHEN o.status IN ('歷史訂單－服務完成','歷史訂單－帳務完成')
            THEN COALESCE(day_event.historical_floor_fee_ntd,o.floor_fee) ELSE o.floor_fee END AS floor_fee,
       CASE WHEN o.status IN ('歷史訂單－服務完成','歷史訂單－帳務完成')
            THEN day_projection.total_actual_service_hours ELSE NULL END AS historical_hours,
       terms.client_hourly_rate_ntd,
       EXISTS(SELECT 1 FROM case_staff_assignments a
              WHERE a.case_no=o.case_no AND a.status IN ('planned','active','completed')
                AND (a.generation_id=aggregate.effective_generation_id OR a.generation_id IS NULL)) AS has_arrangement,
       (SELECT MAX(a.assigned_end_date) FROM case_staff_assignments a
         WHERE a.case_no=o.case_no AND a.status IN ('planned','active','completed')
           AND (a.generation_id=aggregate.effective_generation_id OR a.generation_id IS NULL)) AS planned_end_date,
       (SELECT COUNT(*) FROM staff_schedule s JOIN case_staff_assignments a ON a.id=s.assignment_id
         WHERE s.case_no=o.case_no AND s.effective_marker=1 AND s.is_work_day=1
           AND a.status IN ('planned','active','completed')
           AND (a.generation_id=aggregate.effective_generation_id OR a.generation_id IS NULL)) AS work_day_count,
       (SELECT COUNT(*) FROM client_obligations b WHERE b.case_no=o.case_no
         AND b.direction='receivable_from_client' AND b.obligation_type IN ('deposit','first','second')
         AND b.status<>'cancelled') AS receivable_count,
       (SELECT COUNT(*) FROM client_obligations b WHERE b.case_no=o.case_no
         AND b.direction='receivable_from_client' AND b.obligation_type IN ('deposit','first','second')
         AND b.status='open' AND b.amount_due_ntd>0) AS open_receivable_count,
       (SELECT COUNT(*) FROM client_obligations b WHERE b.case_no=o.case_no
         AND b.direction='payable_to_client' AND b.obligation_type='subsidy_return'
         AND b.status<>'cancelled') AS return_count
FROM orders o JOIN clients c ON c.id=o.client_id
LEFT JOIN scheduling_aggregates aggregate ON aggregate.case_no=o.case_no
LEFT JOIN client_payment_terms terms ON terms.case_no=o.case_no
LEFT JOIN historical_service_day_projections day_projection ON day_projection.case_no=o.case_no
LEFT JOIN historical_service_day_events day_event ON day_event.id=day_projection.current_event_id
WHERE (%s IS NULL OR o.case_no>%s)
  AND (EXISTS(SELECT 1 FROM case_staff_assignments a WHERE a.case_no=o.case_no
               AND a.status IN ('planned','active','completed')
               AND (a.generation_id=aggregate.effective_generation_id OR a.generation_id IS NULL))
       OR EXISTS(SELECT 1 FROM staff_obligations b WHERE b.case_no=o.case_no
                  AND b.direction='payable_to_staff' AND b.status<>'cancelled' AND b.amount_due_ntd>0)
       OR EXISTS(SELECT 1 FROM client_obligations b WHERE b.case_no=o.case_no
                  AND b.direction='payable_to_client' AND b.status='open' AND b.amount_due_ntd>0))
ORDER BY o.case_no LIMIT %s
"""

_REFUNDS_SQL = """
SELECT b.obligation_identity,b.obligation_type,b.amount_due_ntd,b.due_date,
       (snapshot.bank_code IS NOT NULL AND snapshot.bank_code<>''
        AND snapshot.bank_account IS NOT NULL AND snapshot.bank_account<>'') AS recipient_ready
FROM client_obligations b
LEFT JOIN client_refund_recipient_snapshots snapshot ON snapshot.refund_obligation_identity=b.obligation_identity
WHERE b.case_no=%s AND b.direction='payable_to_client' AND b.status='open'
  AND b.obligation_type IN ('refund','subsidy_return') AND b.amount_due_ntd>0
ORDER BY b.obligation_identity
"""

_ARRANGED_STAFF_SQL = """
SELECT DISTINCT a.staff_id,staff.name AS recipient_name
FROM case_staff_assignments a
JOIN staff ON staff.id=a.staff_id
LEFT JOIN scheduling_aggregates scheduling ON scheduling.case_no=a.case_no
WHERE a.case_no=%s AND a.status IN ('planned','active','completed')
  AND (a.generation_id=scheduling.effective_generation_id OR a.generation_id IS NULL)
ORDER BY a.staff_id
"""
