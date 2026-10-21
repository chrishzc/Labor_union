"""Refresh the Staff Payables projection without changing paid Payroll roots."""

from infrastructure.mysql.staff_payout_repository import _projection_rows, _upsert_projection
from infrastructure.mysql.staff_overpayment_recovery_repository import MySqlStaffOverpaymentRecoveryRepository
from subsystems.staff_payables.overpayment_recovery import StaffOverpaymentRecoveryCreationApplication
from subsystems.staff_payables.payroll_correction import PayrollCorrectionSettlement, StaffPayablesPayrollCorrectionApplication


def persist_staff_payable_payroll_corrections(connection, command):
    """Borrow the caller's connection; never open or commit another transaction."""
    owner = StaffPayablesPayrollCorrectionApplication(
        MySqlStaffPayablePayrollCorrectionRepository(connection),
        StaffOverpaymentRecoveryCreationApplication(MySqlStaffOverpaymentRecoveryRepository(connection)),
    )
    for item in command.candidate.frozen_settlements:
        owner.apply(PayrollCorrectionSettlement(command.candidate.case_no, item.obligation_identity,
            item.correction_identity, item.staff_id, item.revised_entitlement,
            item.paid_net_amount, item.recovery_increase), command)


class MySqlStaffPayablePayrollCorrectionRepository:
    def __init__(self, connection):
        self._connection = connection

    def refresh_payroll_correction(self, settlement):
        with self._connection.cursor() as cursor:
            cursor.execute("SELECT aggregate_version FROM staff_payable_accounts WHERE staff_id=%s FOR UPDATE",
                           (settlement.staff_id,))
            account = cursor.fetchone()
            if account is None:
                raise ValueError("staff_payables_account_missing")
            rows = _projection_rows(cursor, (settlement.obligation_identity,))
            if len(rows) != 1:
                raise ValueError("staff_payables_correction_source_missing")
            row = rows[0]
            if (int(row["obligation_amount_ntd"]) != settlement.revised_entitlement.amount
                    or int(row["net_paid_ntd"]) != settlement.paid_net_amount.amount
                    or int(row["staff_id"]) != settlement.staff_id):
                raise ValueError("staff_payables_correction_stale")
            version = int(account["aggregate_version"]) + 1
            _upsert_projection(cursor, row, version)
            cursor.execute("UPDATE staff_payable_accounts SET aggregate_version=%s WHERE staff_id=%s AND aggregate_version=%s",
                           (version, settlement.staff_id, version - 1))
            if cursor.rowcount != 1:
                raise ValueError("staff_payables_correction_stale")
