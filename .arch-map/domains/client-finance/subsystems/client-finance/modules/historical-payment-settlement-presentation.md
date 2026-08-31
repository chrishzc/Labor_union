# Module: historical-payment-settlement-presentation

## Parent
- domain: `client-finance`
- subsystem: `client-finance`

## Responsibility
在既有 Finance owner page 以 Client Finance strict client 呈現 pre-system historical Query／Preview／Confirm／Apply／fresh readback。只允許 exact direction 與 obligation selection；正常銀行候選、stale、identity mismatch 或 outcome unknown 時 fail closed，不透過 Anomalies 或 generic settlement writer。

## Implementation
- primary: `ui_react/src/components/HistoricalClientPaymentWorkbench.tsx`
- client: `ui_react/src/api/client_finance/historical_client_payment_client.ts`
- composition: `ui_react/src/pages/FinancePage.tsx`

## Contracts
- `modules/historical-payment-settlement.md` — owner application/public contract。
- `document/架構重整/01_規格基線/06_Anomalies_Domain.md` — owner work item 顯示於 owner page，`#anomalies` 只保留 15 個 current issue。

## Verification
- layout_status: `custom_current`
- test_root: `ui_react/src/tests/historical_client_payment_workbench.test.tsx`

## Change triggers
Reconcile when owner-page placement、strict client endpoint、direction／selection、confirmation、fresh readback或test root changes。
