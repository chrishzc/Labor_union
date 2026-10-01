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
- customer subsidy payable presentation: `ui_react/src/components/ClientSubsidyReturnQueryPanel.tsx` — FinancePage 的客戶補助退款案件清單，支援姓名／案件搜尋與選用應退款月份，一次呈現全部符合條件案件與合計，不提供分頁操作；明示後端的預估金額、未知日期，不計算退款資格或金額。
- customer subsidy payable client: `ui_react/src/api/client_finance/client_subsidy_return_query_client.ts` — strict 解碼 `/api/v1/finance-reports/client-subsidy-returns` typed projection，`queryAll` 自動循游標取完所有符合結果，核對案件唯一性與游標；只做 GET，條件改變或 unmount 取消整次查詢，失敗不交付部分結果。

## Contracts
- `modules/client-subsidy-return-query.md` — 補助退款案件查詢 owner。
- `modules/historical-payment-settlement.md` — owner application/public contract。
- `document/架構重整/01_規格基線/06_Anomalies_Domain.md` — owner work item 顯示於 owner page，`#anomalies` 只保留 15 個 current issue。
- `document/架構重整/01_規格基線/04_Client_Finance_Domain.md` 與 `16_Staff_Payables與Client_Refund正式規格.md` — 客戶補助退還義務與月期應付清單；不重定義退款資格、金額、日期或核銷。

## Verification
- layout_status: `custom_current`
- test_root: `ui_react/src/tests/historical_client_payment_workbench.test.tsx`
- test_root: `ui_react/src/tests/finance_query_transport_identity.test.ts`
- test_root: `ui_react/src/tests/finance_query_clients.test.ts`
- test_root: `ui_react/src/tests/finance_request_lifecycle.test.tsx`
- integration_root: `ui_react/src/tests/domains/client-finance/subsystems/client-finance/modules/historical-payment-settlement-presentation/`

## Change triggers
Reconcile when owner-page placement、strict client endpoint、direction／selection、confirmation、fresh readback或test root changes。
