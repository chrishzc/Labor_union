# Module: payment-destination-configuration

## Parent
- domain: `client-finance`
- subsystem: `client-finance`

## Responsibility
擁有客戶付款給工會／代收付的 current account configuration、revision、event 與 receipt；提供財務管理 UI 的 Query／Preview／Apply，並向 Contract Signing 提供唯一 typed payment-destination projection。不得讀取或覆寫服務人員個人帳戶。

## Implementation
- `domains/client_finance/payment_destination.py`
- `subsystems/client_finance/payment_destination_configuration.py`
- `infrastructure/mysql/client_payment_destination_repository.py`
- `api/routes/client_payment_destination.py`
- `ui_react/src/components/PaymentDestinationConfigurationPanel.tsx`
- `db/schema_parts/1029_client_payment_destination_configuration.sql`

## Contracts
- `document/架構重整/01_規格基線/04_Client_Finance_Domain.md`
- `document/架構重整/01_規格基線/21_Contract_Signing_Commitment與正常驗收資料鏈正式規格.md`

## Verification
- layout_status: `custom_current`
- test_root: `tests/domains/client-finance/subsystems/client-finance/modules/payment-destination-configuration/`
- test_root: `ui_react/src/tests/payment_destination_configuration.test.tsx`

## Change triggers
Reconcile when payment destination owner、Q/P/A public contract、schema、contract projection or Finance UI entry changes.
