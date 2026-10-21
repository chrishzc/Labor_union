# Module: overpayment-recovery

## Parent
- domain: `staff-payables`
- subsystem: `staff-payables`

## Responsibility
Staff Payables 擁有既有超額付款追償的 owner root、collection／adjustment 與 fresh readback；不由
Payroll 或 historical settlement adapter 直接寫 recovery。合法 Payroll correction 只提供 exact-source typed request，由 Staff Payables creation application 建立追償。

## Implementation
- `domains/staff_payables/overpayment_recovery.py`
- `subsystems/staff_payables/overpayment_recovery.py`
- `infrastructure/mysql/staff_overpayment_recovery_repository.py`
- `subsystems/staff_payables/payroll_correction.py` — 由合法 Payroll correction 協調 projection 與新增超付追償，借用 caller outer transaction。
- `infrastructure/mysql/staff_payable_payroll_correction.py`
- `infrastructure/mysql/staff_payable_correction_sql.py` — 原義務與來源相同換人差額的有效金額；差額不可獨立選取付款。

## Verification
- tests由Staff Payables Subsystem current integration root持有。
- `tests/domains/staff-payables/subsystems/staff-payables/integration/test_payroll_handover_correction.py`
