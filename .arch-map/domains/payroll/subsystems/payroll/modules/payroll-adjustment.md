# Module: payroll-adjustment

## Parent
- domain: `payroll`
- subsystem: `payroll`

## Responsibility
既有 Payroll 調整 Query／Preview／Apply 與案件、月嫂薪資查詢。Query 保留已取消及已結清的合法 0 元紀錄，不改寫金額、狀態或付款；新增調整仍依 owner 非零規則。

## Implementation
- amount modes: `domains/payroll/amount_correction.py`, `subsystems/payroll/amount_correction.py`, `infrastructure/mysql/payroll_amount_correction_repository.py`; original Payroll rebuild borrows amount controls, paid differences delegate recovery to Staff Payables without changing cash.
- entrypoint: `api/routes/accounting_differences.py`; presentation via `ui_react/src/components/AccountingDifferencePanel.tsx`.
- 歷史未付款承接與更正沿同一 Payroll application／repository，使用原帳務依據與原應付版本，保存取代關聯，不改實際付款紀錄。
- primary:
  - `domains/payroll/adjustment.py`
  - `subsystems/payroll/adjustment_workflow.py`
  - `infrastructure/mysql/payroll_adjustment_repository.py`
  - `api/dependencies/payroll.py`
  - `api/routes/payroll.py`
  - `api/schemas/payroll.py`

## Contracts
- `document/架構重整/01_規格基線/03_Payroll_Domain.md`

## Verification
- integration_root: `tests/domains/payroll/subsystems/payroll/integration/test_payroll_amount_correction_mysql.py`
- test_root: `tests/domains/payroll/subsystems/payroll/modules/payroll-adjustment/`
- integration_root: `tests/domains/payroll/subsystems/payroll/integration/test_payroll_adjustment_workflow.py`

## Provenance
- Existing implementation and read response contract — `source_observed` — current repository.
