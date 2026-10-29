# Module: historical-payment-settlement-presentation

## Parent
- domain: `client-finance`
- subsystem: `client-finance`

## Responsibility
在既有 Finance owner page 以 Client Finance strict client 呈現 pre-system historical Query／Preview／Confirm／Apply／fresh readback。只允許 exact direction 與 obligation selection；正常銀行候選、stale、identity mismatch 或 outcome unknown 時 fail closed，不透過 Anomalies 或 generic settlement writer。

## Implementation
- classification query: `subsystems/client_finance/client_payments_query.py`、`infrastructure/mysql/case_category_query.py`、`api/routes/client_payments.py` — authenticated `/api/v1/client-payments/case-categories` 只回 case_no／category，依綁定費率規則及舊身分分類，不依 A 前綴，不寫入帳務。
- category client: `ui_react/src/api/client_finance/case_categories_client.ts` — strict 分類投影供收款／付款的補助（預設）、非市民、全部篩選；同一集合產生明細、件數及金額合計；來源不完整明示查詢失敗。
- primary: `ui_react/src/components/HistoricalClientPaymentWorkbench.tsx`
- client: `ui_react/src/api/client_finance/historical_client_payment_client.ts`
- composition: `ui_react/src/pages/FinancePage.tsx` — 唯一三個主工作區：收款、付款、銀行對帳；舊深連結解析至對應工作區／同案明細，帳務設定獨立。
- workbench referral: Finance 客戶收款以 `case_no` 定位原案件，`from=workbench` 提供返回同案入口；所選案件已歷史服務完成時承接 Orders-owned `HistoricalCompletionPanel`，沿用既有 Query／Preview／Apply 與重新讀取，不改寫結清規則。
- payable export adapter: `ui_react/src/api/accounts_payable/accounts_payable_export_client.ts` — FinancePage 既有應付帳款下載入口；呼叫既有 Staff Payables 匯出端點，保留登入檢查與 XLSX 回應驗證，不計算帳務事實。
- shared collections: `ui_react/src/components/FinanceReceiptsWorkspace.tsx`、`ui_react/src/components/FinancePaymentsWorkspace.tsx` — 收款／付款清單，沿用既有 owner 摘要、government projection、cash planning；正式與預估分開加總，原 XLSX 匯出條件不受列表篩選改寫。
- overdue reminder composition: `FinanceReceiptsWorkspace.tsx` 承接既有 LINE-owned `PaymentOverdueReminderWorkbench.tsx`；只移動入口，不改逾期資格、金額或寄送 writer。
- government receipt grouping: `ui_react/src/components/SubsidyPeriodWorkbench.tsx` — 月／季／年整期入款、同單位總額、季度涵蓋月份及防重，歸 Government Subsidy owner。
- shared case subsidy detail: `ui_react/src/components/CaseSubsidyDetailDrawer.tsx` — exact-case 補助金額、整期涵蓋與目前應退／實付；不提供逐案銷帳。
- immutable history: `ui_react/src/components/FinanceCaseHistory.tsx`、`ui_react/src/api/client_finance/client_finance_history_client.ts` — strict 解碼既有 `/api/v1/client-payments` 摘要／同案根事實與 immutable ledger，拒絕重複及跨案回應。
- history adapter: `infrastructure/mysql/client_payments_query_repository.py`、`api/schemas/client_payments.py` — 既有 read model 接受已存在的 subsidy_return／subsidy_advance 類型，不改 writer 或歷史資料。
  - 摘要 `receipt_status` 組合 canonical receipt／reversal 淨額及 exact current historical payment overlay，分開呈現待收、部分收款、已收款、已結清；有效歷史 overlay 從未收／未付餘額扣除，不改 canonical receipt 計數。
- receipt filter contract: `subsystems/client_finance/client_payments_query.py` → `api/routes/client_payments.py` → strict history client；摘要 `receipt_entry_count` 只計 canonical receipt，收款頁「已收款」依 `receipt_status` 包含已收／部分收款，其他 ledger 類型不作收款證據。跨層驗證：`tests/domains/client-finance/subsystems/client-finance/integration/test_client_receipt_summary_query.py`。
- government read client: `ui_react/src/api/government_subsidy/period_reconciliation_client.ts` — current period query／receipt／case coverage；舊 Orders batch projection 僅歷史能力。
- retained source clients: `ui_react/src/api/accounts_payable/cash_requirements_query_client.ts`、`ui_react/src/api/client_finance/client_subsidy_return_query_client.ts` — 預估與正式未退款仍由原 owner 投影。`ClientSubsidyReturnQueryPanel.tsx`、`CashRequirementsPanel.tsx` 不再是 Finance 主入口；不刪除其仍有效的來源測試。

## Contracts
- `modules/client-subsidy-return-query.md` — 補助退款案件查詢 owner。
- `staff-payables/staff-payables/module:accounts-payable-export` — 預估資金需求與已確定款項清冊的 reporting owner；presentation 不計算薪資或退款資格。
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
- cross-workspace verification: parent subsystem integration_root `ui_react/src/tests/domains/client-finance/subsystems/client-finance/integration/finance_workspaces.test.tsx`

- integration_root: `ui_react/src/tests/fixtures/finance/finance_query_contract_fixtures.ts` — 同一 FinancePage composition 的 query client／adapter／transport／page／cutover tests 共用 typed fixture；僅此既有檔案，不宣告整個 fixtures 目錄。

## Change triggers
Reconcile when owner-page placement、strict client endpoint、direction／selection、confirmation、fresh readback或test root changes。
