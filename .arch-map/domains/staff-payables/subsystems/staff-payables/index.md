# Subsystem: staff-payables

## Parent
- domain: `staff-payables`

## Responsibility
編排 staff payable owner Query／Preview／Apply、export/read models 與 settlement transitions；不從 imported bank row 重建 owner state。

## Dependencies
- inbound: `finance-import` — typed bank classification/delegation only。

## Contracts
- `domains/staff_payables/` — Staff Payables rules
- `subsystems/staff_payables/` — Staff Payables workflows
- `document/架構重整/01_規格基線/00_Global_共同契約.md` — transaction/replay contract

## Modules
- `historical-payment-settlement` — adopted pre-system historical Staff payout evidence and exact obligation settlement overlay; path: `modules/historical-payment-settlement.md`
- `historical-payment-settlement-presentation` — owner-page exact staff/case historical payout Q/P/A and fresh readback; path: `modules/historical-payment-settlement-presentation.md`
- `payout-remediation-presentation` — 逾期應付款核銷的既有安全 workflow 與 business-first React projection; path: `modules/payout-remediation-presentation.md`
- `overpayment-recovery-presentation` — 月嫂超額付款追償的既有安全 workflow 與 business-first React projection; path: `modules/overpayment-recovery-presentation.md`
- `payroll-correction-recovery` — negative paid Payroll correction的exact Staff recovery linkage；path: `modules/payroll-correction-recovery.md`

## Verification routing
- default_boundary: Subsystem
- test_root: `tests/domains/staff-payables/subsystems/staff-payables/`
- integration_root: `tests/domains/staff-payables/subsystems/staff-payables/integration/`
- legacy_ui_boundary: `tests/test_accounts_payable_export_api_client.py`
- routing: `.arch-map/tests/domains/staff-payables/subsystems/staff-payables/index.md`.
