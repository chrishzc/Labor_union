# Module: historical-service-accounting

## Parent
- domain: `payroll`
- subsystem: `payroll`

## Responsibility
以每位歷史 assignment 的服務天數、每日時數、`assignment_payroll_rate_snapshots` 費率快照與既有 Payroll adjustments 計算固定單薪應付，雙薪永遠為零，樓層費按最大餘數法守恆分配。尚無付款歷史的義務在原 identity 上重建；已有正式或歷史付款連結時，修正以 source-bound immutable adjustment／reversal 表達差額。所有變更沿用 `payroll_outbox.staff_obligation_changed` 通知既有下游 owner。

## Implementation
- `domains/payroll/historical_calculation.py`
- `infrastructure/mysql/historical_service_accounting_repository.py` — shared outer-UoW adapter.

## Contracts
- `document/架構重整/01_規格基線/27_歷史訂單生命週期與服務天數帳務正式規格.md`

## Verification
- test_root: `tests/domains/payroll/subsystems/payroll/modules/historical-service-accounting/`

## Change triggers
Reconcile when single-pay rule, rate snapshot, floor-fee allocation, unpaid rebuild eligibility, paid-history detection, immutable difference direction, Payroll outbox or version ownership changes.
