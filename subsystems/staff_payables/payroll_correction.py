"""Staff Payables owner coordination under the caller's outer transaction."""

from dataclasses import dataclass
from typing import Protocol

from domains.staff_payables.overpayment_recovery import PayrollCorrectionRecoverySource
from shared_kernel.fingerprints import fingerprint_payload
from shared_kernel.identities import IdempotencyKey
from shared_kernel.money import MoneyNTD
from subsystems.staff_payables.overpayment_recovery import (
    StaffOverpaymentRecoveryCreationApplication, StaffOverpaymentRecoveryCreationRequest,
)


@dataclass(frozen=True, slots=True)
class PayrollCorrectionSettlement:
    case_no: str
    obligation_identity: str
    correction_identity: str | None
    staff_id: int
    revised_entitlement: MoneyNTD
    paid_net_amount: MoneyNTD
    recovery_increase: MoneyNTD


class PayrollCorrectionProjectionPort(Protocol):
    def refresh_payroll_correction(self, settlement: PayrollCorrectionSettlement) -> None: ...


class StaffPayablesPayrollCorrectionApplication:
    def __init__(self, projection: PayrollCorrectionProjectionPort,
                 recoveries: StaffOverpaymentRecoveryCreationApplication):
        self._projection = projection
        self._recoveries = recoveries

    def apply(self, settlement, context):
        self._projection.refresh_payroll_correction(settlement)
        if settlement.recovery_increase.is_zero:
            return
        if settlement.correction_identity is None:
            raise ValueError("payroll_recovery_correction_missing")
        key = "handover-recovery:" + fingerprint_payload({
            "batch": context.idempotency_key.value, "correction": settlement.correction_identity,
        }).value
        self._recoveries.create_from_payroll_correction(StaffOverpaymentRecoveryCreationRequest(
            PayrollCorrectionRecoverySource(settlement.correction_identity, settlement.case_no,
                settlement.obligation_identity, settlement.staff_id, settlement.recovery_increase),
            IdempotencyKey(key), context.actor, context.reason, context.correlation_id,
        ))
