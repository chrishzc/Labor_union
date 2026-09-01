# Module: historical-service-accounting

## Parent
- domain: `client-finance`
- subsystem: `client-finance`

## Responsibility
由歷史逐月嫂服務天數總量、案件 `client_payment_terms` 費率快照與正式補助政策推導客戶單薪應收及比例樓層費；差額以新的 direction-owned obligation 表達，不覆寫既有核銷或付款證據。

## Implementation
- `domains/client_finance/historical_obligation_calculation.py`
- `infrastructure/mysql/historical_service_accounting_repository.py` — shared outer-UoW adapter.

## Contracts
- `document/架構重整/01_規格基線/27_歷史訂單生命週期與服務天數帳務正式規格.md`

## Verification
- test_root: `tests/domains/client-finance/subsystems/client-finance/modules/historical-service-accounting/`

## Change triggers
Reconcile when historical service-volume pricing, subsidy/self-pay split, correction direction or owner-version contract changes.
