"""Fixed, case-scoped SQL projections for the registry inspection export."""

from __future__ import annotations

from infrastructure.mysql.client_registry_query_repository import MySqlClientRegistryQueryRepository
from subsystems.client_profile.case_inspection_export import (
    AllocationRecord, AssignmentRecord, CaseInspectionData, CaseRecord,
    ClientObligationRecord, LedgerRecord, ScheduleRecord, StaffObligationRecord, StaffTransferRecord,
)
from subsystems.client_profile.order_accounting_export import OrderAccountingExportQuery


class MySqlClientCaseInspectionRepository:
    def __init__(self, connection) -> None:
        self._connection = connection

    def query_case_inspection(self, selection: OrderAccountingExportQuery) -> CaseInspectionData:
        overview = MySqlClientRegistryQueryRepository(self._connection).query_order_accounting_rows(selection)
        case_nos = tuple(row.case_no for row in overview)
        if not case_nos:
            return CaseInspectionData(overview=())
        placeholders = ",".join("%s" for _ in case_nos)
        common = " JOIN orders o ON o.case_no=t.case_no JOIN clients c ON c.id=o.client_id "
        customer = "t.case_no,c.name AS customer_name,"
        specs = (
            ("cases", CaseRecord,
             "SELECT o.case_no,c.name AS customer_name,o.client_id,o.staff_id,s.name AS staff_name,o.status,"
             "o.lifecycle_version,c.client_profile_version,f.aggregate_version AS finance_version,p.policy_version AS terms_version,"
             "c.service_type,o.start_date,o.end_date,o.actual_start_date,o.actual_end_date,"
             "CAST(o.service_start_time AS CHAR) AS service_start_time,CAST(o.service_end_time AS CHAR) AS service_end_time,"
             "o.service_end_day_offset,CAST(o.custom_rest_dates AS CHAR) AS custom_rest_dates,"
             "o.service_days,o.service_hours_per_day,o.requires_cooking,o.floor_fee,p.client_hourly_rate_ntd,o.created_at,o.updated_at "
             "FROM orders o JOIN clients c ON c.id=o.client_id LEFT JOIN staff s ON s.id=o.staff_id "
             "LEFT JOIN client_finance_accounts f ON f.case_no=o.case_no LEFT JOIN client_payment_terms p ON p.case_no=o.case_no "
             f"WHERE o.case_no IN ({placeholders}) ORDER BY o.case_no"),
            ("assignments", AssignmentRecord,
             "SELECT " + customer + "t.id AS assignment_id,t.staff_id,s.name AS staff_name,t.generation_id,t.assignment_sequence,"
             "t.assigned_start_date,t.assigned_end_date,t.original_assigned_start_date,t.original_assigned_end_date,"
             "t.planned_hours,t.actual_hours,t.hourly_rate,t.floor_fee_allocated,t.status,t.replaced_assignment_id "
             "FROM case_staff_assignments t" + common + "LEFT JOIN staff s ON s.id=t.staff_id "
             f"WHERE t.case_no IN ({placeholders}) ORDER BY t.case_no,t.assignment_sequence,t.id"),
            ("schedules", ScheduleRecord,
             "SELECT " + customer + "t.id AS schedule_id,t.assignment_id,t.staff_id,s.name AS staff_name,t.generation_id,"
             "t.work_date,t.is_work_day,t.is_double_pay,t.effective_marker FROM staff_schedule t" + common
             + "LEFT JOIN staff s ON s.id=t.staff_id "
             f"WHERE t.case_no IN ({placeholders}) ORDER BY t.case_no,t.work_date,t.staff_id,t.id"),
            ("client_obligations", ClientObligationRecord,
             "SELECT " + customer + "t.obligation_identity,t.obligation_type,t.direction,t.source_obligation_identity,"
             "t.amount_due_ntd,t.due_date,t.status,t.current_event_id,t.projection_version FROM client_obligations t" + common
             + f"WHERE t.case_no IN ({placeholders}) ORDER BY t.case_no,t.obligation_identity"),
            ("ledger", LedgerRecord,
             "SELECT " + customer + "t.id AS ledger_entry_id,t.finance_import_row_id,t.entry_type,t.amount_ntd,t.occurred_on,"
             "t.reconciliation_reference,t.reversal_of_entry_id FROM client_ledger_entries t" + common
             + f"WHERE t.case_no IN ({placeholders}) ORDER BY t.case_no,t.occurred_on,t.id"),
            ("allocations", AllocationRecord,
             "SELECT " + customer + "a.id AS allocation_id,t.id AS ledger_entry_id,a.obligation_identity,b.obligation_type,b.direction,"
             "a.amount_ntd,a.allocation_ordinal,t.occurred_on FROM client_ledger_obligation_allocations a "
             "JOIN client_ledger_entries t ON t.id=a.ledger_entry_id" + common
             + "LEFT JOIN client_obligations b ON b.obligation_identity=a.obligation_identity "
             f"WHERE t.case_no IN ({placeholders}) ORDER BY t.case_no,t.id,a.allocation_ordinal,a.id"),
            ("staff_obligations", StaffObligationRecord,
             "SELECT " + customer + "t.obligation_identity,t.assignment_id,t.staff_id,s.name AS staff_name,t.obligation_kind,"
             "t.direction,t.source_obligation_identity,t.amount_due_ntd,t.due_date,t.status,t.current_event_id,t.payroll_version,"
             "t.payout_history_exists FROM staff_obligations t" + common + "LEFT JOIN staff s ON s.id=t.staff_id "
             f"WHERE t.case_no IN ({placeholders}) ORDER BY t.case_no,t.staff_id,t.obligation_identity"),
            ("staff_transfers", StaffTransferRecord,
             "SELECT " + customer + "t.staff_id,s.name AS staff_name,t.assignment_id,t.id AS settlement_detail_id,"
             "p.id AS transfer_id,a.id AS allocation_id,a.allocated_amount,a.component_type,a.review_status AS allocation_review_status,"
             "p.transaction_type,p.transaction_status,p.occurred_at,p.external_reference,p.reversal_of_transfer_id,a.reversal_of_allocation_id "
             "FROM staff_transfer_allocations a JOIN staff_monthly_settlement_details t ON t.id=a.settlement_detail_id "
             "JOIN staff_actual_transfers p ON p.id=a.transfer_id" + common + "LEFT JOIN staff s ON s.id=t.staff_id "
             f"WHERE t.case_no IN ({placeholders}) ORDER BY t.case_no,p.occurred_at,p.id,a.id"),
        )
        details = {}
        with self._connection.cursor() as cursor:
            for field, row_type, sql in specs:
                cursor.execute(sql, case_nos)
                details[field] = tuple(row_type(**row) for row in cursor.fetchall())
        return CaseInspectionData(overview=overview, **details)
