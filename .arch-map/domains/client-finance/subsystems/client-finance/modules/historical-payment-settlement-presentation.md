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
- payable export adapter: `ui_react/src/api/accounts_payable/accounts_payable_export_client.ts` — FinancePage 既有應付帳款下載入口；呼叫既有 Staff Payables 匯出端點，保留登入檢查與 XLSX 回應驗證，不計算帳務事實。
- cross-order presentation: `ui_react/src/components/OrderGovernmentSubsidyLane.tsx` — FinancePage 內嵌的補助唯讀摘要；只呈現業務狀態、金額與報表入口，不展示來源識別。補助規則仍由 Government Subsidy 擁有。

## Contracts
- `modules/historical-payment-settlement.md` — owner application/public contract。
- `document/架構重整/01_規格基線/06_Anomalies_Domain.md` — owner work item 顯示於 owner page，`#anomalies` 只保留 15 個 current issue。

## Verification
- layout_status: `custom_current`
- test_root: `ui_react/src/tests/historical_client_payment_workbench.test.tsx`
- test_root: `ui_react/src/tests/finance_query_transport_identity.test.ts`
- integration_root: `ui_react/src/tests/domains/client-finance/subsystems/client-finance/modules/historical-payment-settlement-presentation/`

## Change triggers
Reconcile when owner-page placement、strict client endpoint、direction／selection、confirmation、fresh readback或test root changes。
