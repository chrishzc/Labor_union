"""Bounded read-only cash-planning adapter; never creates accounting facts."""

from datetime import date
from decimal import Decimal

from infrastructure.mysql.accounts_payable_export_sources import MySqlStaffPayableExportSource
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
            cursor.execute(_REFUNDS_SQL, (case_no, case_no))
            refunds = tuple(CashRefundFact(
                str(r["obligation_identity"]),
                "client_subsidy_return" if r["obligation_type"] == "subsidy_return" else "client_refund",
                0 if r["confirmation_kind"] else int(r["amount_due_ntd"]), r["due_date"], str(row["client_name"]), bool(r["recipient_ready"]),
                r["confirmation_kind"] or ("paid" if int(r["amount_due_ntd"]) == 0 and int(r["net_paid_ntd"]) > 0 else
                                           "settled" if int(r["amount_due_ntd"]) == 0 else
                                           "partially_paid" if int(r["net_paid_ntd"]) > 0 else "pending"),
                int(r["amount_snapshot_ntd"]) if r["confirmation_kind"] else max(0, int(r["net_paid_ntd"])),
            ) for r in cursor.fetchall())
        staff_items = self._staff.load_case(case_no, date.min)
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
         AND b.status='open' AND b.amount_due_ntd>0
         AND NOT EXISTS (SELECT 1 FROM historical_client_payment_projections historical
                          WHERE historical.obligation_identity=b.obligation_identity
                            AND historical.amount_snapshot_ntd=b.amount_due_ntd
                            AND historical.obligation_projection_version=b.projection_version)) AS open_receivable_count,
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
                  AND b.direction='payable_to_client' AND b.status<>'cancelled'))
ORDER BY o.case_no LIMIT %s
"""

_REFUNDS_SQL = """
SELECT b.obligation_identity,b.obligation_type,b.amount_due_ntd,b.due_date,
       historical.confirmation_kind,historical.amount_snapshot_ntd,
       COALESCE(paid.net_paid_ntd,0) AS net_paid_ntd,
       (snapshot.bank_code IS NOT NULL AND snapshot.bank_code<>''
        AND snapshot.bank_account IS NOT NULL AND snapshot.bank_account<>'') AS recipient_ready
FROM client_obligations b
LEFT JOIN client_refund_recipient_snapshots snapshot ON snapshot.refund_obligation_identity=b.obligation_identity
LEFT JOIN historical_client_payment_projections historical
  ON historical.obligation_identity=b.obligation_identity
 AND historical.amount_snapshot_ntd=b.amount_due_ntd
 AND historical.obligation_projection_version=b.projection_version
LEFT JOIN (
    SELECT allocation.obligation_identity,
           SUM(CASE WHEN ledger.entry_type IN ('refund','subsidy_return') THEN allocation.amount_ntd
                    WHEN ledger.entry_type='reversal' AND target.entry_type IN ('refund','subsidy_return') THEN -allocation.amount_ntd
                    ELSE 0 END) AS net_paid_ntd
    FROM client_ledger_obligation_allocations allocation
    JOIN client_ledger_entries ledger ON ledger.id=allocation.ledger_entry_id
    LEFT JOIN client_ledger_entries target ON target.id=ledger.reversal_of_entry_id AND target.case_no=ledger.case_no
    WHERE ledger.case_no=%s
    GROUP BY allocation.obligation_identity
) paid ON paid.obligation_identity=b.obligation_identity
WHERE b.case_no=%s AND b.direction='payable_to_client' AND b.status<>'cancelled'
  AND b.obligation_type IN ('refund','subsidy_return')
ORDER BY b.obligation_identity
"""
