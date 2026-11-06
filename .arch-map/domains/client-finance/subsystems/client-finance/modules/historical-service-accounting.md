# Module: historical-service-accounting

## Parent
- domain: `client-finance`
- subsystem: `client-finance`

## Responsibility
由歷史逐月嫂服務天數總量、案件 `client_payment_terms` 費率快照與正式補助政策推導客戶單薪應收及比例樓層費。天數更正只保存比較金額；需入帳的差異由 Client Finance 正式更正處理，保留原期款與核銷。

## Implementation
- `domains/client_finance/historical_obligation_calculation.py`
- `infrastructure/mysql/historical_service_accounting_repository.py` — reads calculation inputs and persists the Orders comparison snapshot.

## Contracts
- `document/架構重整/01_規格基線/27_歷史訂單生命週期與服務天數帳務正式規格.md`

## Verification
- test_root: `tests/domains/client-finance/subsystems/client-finance/modules/historical-service-accounting/`

## Change triggers
Reconcile when historical service-volume pricing, subsidy/self-pay split, correction direction or owner-version contract changes.
