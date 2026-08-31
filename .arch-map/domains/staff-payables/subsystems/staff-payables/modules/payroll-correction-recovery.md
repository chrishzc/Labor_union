# Module: payroll-correction-recovery

## Parent
- domain: `staff-payables`
- subsystem: `staff-payables`

## Responsibility
只在Payroll negative paid correction產生合法超付時，以exact `payroll_correction_identity`建立既有Staff
Payables recovery root；不重算Payroll obligation。

## Implementation
- `domains/staff_payables/overpayment_recovery.py`
- `subsystems/staff_payables/overpayment_recovery.py`
- `infrastructure/mysql/staff_overpayment_recovery_repository.py`
- `infrastructure/mysql/staff_overpayment_recovery_from_payroll_adapter.py`

## Verification
- tests由Staff Payables Subsystem current integration root持有。
