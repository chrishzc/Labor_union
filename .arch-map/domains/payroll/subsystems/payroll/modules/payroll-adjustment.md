# Module: payroll-adjustment

## Parent
- domain: `payroll`
- subsystem: `payroll`

## Responsibility
既有 Payroll 調整 Query／Preview／Apply 與案件、月嫂薪資查詢。Query 保留已取消及已結清的合法 0 元紀錄，不改寫金額、狀態或付款；新增調整仍依 owner 非零規則。

## Implementation
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
- test_root: `tests/domains/payroll/subsystems/payroll/modules/payroll-adjustment/`
- integration_root: `tests/domains/payroll/subsystems/payroll/integration/test_payroll_adjustment_workflow.py`

## Provenance
- Existing implementation and read response contract — `source_observed` — current repository.
