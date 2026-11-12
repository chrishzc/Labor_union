# Module: historical-service-accounting

## Parent
- domain: `payroll`
- subsystem: `payroll`

## Responsibility
以每位歷史 assignment 的服務天數、每日時數、`assignment_payroll_rate_snapshots` 費率快照與既有 Payroll adjustments 計算服務薪資應付，樓層費按最大餘數法分配。天數更正只保存比較金額；需入帳的差異由 Payroll／Staff Payables 正式更正處理，保留既有應付及付款證據。
歷史服務完成的基準應付讀取 HCM 登記天數／每日時數、已採納唯一指派、歷史結束日、正式費率及付款來源，借用既有 Payroll rebuild 事件、投影與收據 writer。採納、到期推進和既有同步入口共用同一流程。

## Implementation
- `domains/payroll/historical_calculation.py`
- `subsystems/payroll/historical_baseline_obligation_sync.py` — historical source synchronization in the caller's transaction.
- `api/routes/accounting_differences.py`、`scripts/sync_historical_staff_obligations.py` — existing historical synchronization entry points.
- `infrastructure/mysql/historical_service_accounting_repository.py` — reads calculation inputs and persists the Orders comparison snapshot.

## Contracts
- `document/架構重整/01_規格基線/27_歷史訂單生命週期與服務天數帳務正式規格.md`
- `document/架構重整/01_規格基線/03_Payroll_Domain.md` §2.2、§3.2

## Verification
- test_root: `tests/domains/payroll/subsystems/payroll/modules/historical-service-accounting/`

## Change triggers
Reconcile when the single-pay rule, rate snapshot, floor-fee allocation or comparison inputs change.
