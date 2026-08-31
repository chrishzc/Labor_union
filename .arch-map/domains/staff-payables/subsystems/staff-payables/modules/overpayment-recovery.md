# Module: overpayment-recovery

## Parent
- domain: `staff-payables`
- subsystem: `staff-payables`

## Responsibility
Staff Payables 擁有既有超額付款追償的 owner root、collection／adjustment 與 fresh readback；不由
Payroll 或 historical settlement adapter 推定或建立 recovery。

## Implementation
- `domains/staff_payables/overpayment_recovery.py`
- `subsystems/staff_payables/overpayment_recovery.py`
- `infrastructure/mysql/staff_overpayment_recovery_repository.py`

## Verification
- tests由Staff Payables Subsystem current integration root持有。
