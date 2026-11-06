# Module: historical-service-accounting

## Parent
- domain: `payroll`
- subsystem: `payroll`

## Responsibility
以每位歷史 assignment 的服務天數、每日時數、`assignment_payroll_rate_snapshots` 費率快照與既有 Payroll adjustments 計算固定單薪應付，雙薪為零，樓層費按最大餘數法分配。天數更正只保存比較金額；需入帳的差異由 Payroll／Staff Payables 正式更正處理，保留既有應付及付款證據。

## Implementation
- `domains/payroll/historical_calculation.py`
- `infrastructure/mysql/historical_service_accounting_repository.py` — reads calculation inputs and persists the Orders comparison snapshot.

## Contracts
- `document/架構重整/01_規格基線/27_歷史訂單生命週期與服務天數帳務正式規格.md`

## Verification
- test_root: `tests/domains/payroll/subsystems/payroll/modules/historical-service-accounting/`

## Change triggers
Reconcile when the single-pay rule, rate snapshot, floor-fee allocation or comparison inputs change.
