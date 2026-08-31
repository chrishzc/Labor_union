"""Staff Payables owner composition for Payroll overpayment recovery."""

from __future__ import annotations

from domains.staff_payables.overpayment_recovery import PayrollCorrectionRecoverySource
from infrastructure.mysql.staff_overpayment_recovery_repository import (
    MySqlStaffOverpaymentRecoveryRepository,
)
from subsystems.staff_payables.overpayment_recovery import (
    StaffOverpaymentRecoveryCreationApplication,
    StaffOverpaymentRecoveryCreationRequest,
)

class StaffOverpaymentRecoveryCreationBoundary(RuntimeError):
    """Reserved for a missing Staff Payables successor contract."""


class MySqlStaffOverpaymentRecoveryFromPayrollAdapter:
    """Adapt Payroll's candidate to the Staff Payables owner command.

    Payroll owns the outer transaction. This adapter only calls the Staff
    owner application and never begins, commits, or rolls back.
    """

    def __init__(self, connection, *, application=None) -> None:
        self._application = application or StaffOverpaymentRecoveryCreationApplication(
            MySqlStaffOverpaymentRecoveryRepository(connection)
        )

    def create_from_payroll_correction(self, *, candidate, request) -> None:
        source = PayrollCorrectionRecoverySource(
            correction_identity=candidate.correction_identity,
            case_no=candidate.case_no,
            obligation_identity=candidate.obligation_identity,
            staff_id=candidate.staff_id,
            amount=candidate.recovery_amount,
        )
        owner_request = StaffOverpaymentRecoveryCreationRequest(
            source=source,
            idempotency_key=request.idempotency_key,
            actor=request.actor,
            reason=request.reason,
            correlation_id=request.correlation_id,
        )
        try:
            self._application.create_from_payroll_correction(owner_request)
        except RuntimeError as error:
            if str(error).startswith("BOUNDARY_REQUIRED_"):
                raise StaffOverpaymentRecoveryCreationBoundary(str(error)) from error
            raise


PayrollStaffOverpaymentRecoveryAdapter = MySqlStaffOverpaymentRecoveryFromPayrollAdapter
MySqlStaffOverpaymentRecoveryPort = MySqlStaffOverpaymentRecoveryFromPayrollAdapter


__all__ = [
    "MySqlStaffOverpaymentRecoveryFromPayrollAdapter",
    "PayrollStaffOverpaymentRecoveryAdapter",
    "MySqlStaffOverpaymentRecoveryPort",
    "StaffOverpaymentRecoveryCreationBoundary",
]
