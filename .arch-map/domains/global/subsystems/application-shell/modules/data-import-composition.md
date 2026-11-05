# Module: data-import-composition

## Parent
- domain: `global`
- subsystem: `application-shell`

## Responsibility
組成 Case Import 與 Orders 等既有 owner 的 typed workbook Preview／Apply UI；只協調頁面狀態與顯示，不重算 Domain facts 或取得 mutation authority。

## Implementation
- primary: `ui_react/src/pages/DataImportPage.tsx`
- `ui_react/src/pages/DataImportPage.css` — four-metric import presentation。
- `ui_react/src/adapters/workbook_import_result_adapter.ts` — project typed owner receipts into source／imported／duplicate／not-imported counts without counting review overlays twice。

## Dependencies
- outbound: `orders/orders/module:historical-adoption-presentation` — Historical Orders typed preview／receipt。
- 匯入頁顯示四種統計及 terminal receipt 的未匯入列明細；成功警示與單列更正工作台由其他 owner 頁承接。
- outbound: `case-import` owners — HCM／Client BeClass typed workbook clients。
- inbound: authenticated React application navigation。

## Contracts
- 匯入頁維持只顯示四種互斥筆數與問題／未匯入列明細（含跨案件月嫂排程重疊的對造 Excel 列號與案件期間說明，以及 Preview／Apply 驗證失敗時的 `衝突與錯誤明細` 列號與案件表格），不顯示應收、應付、樓層費、單雙薪等正常帳務明細。
- 匯入等待與結果未確認時維持換檔／重複送出鎖，允許側邊導覽與匯入類型切換；不提供「停止等待」。離開匯入頁停止後續確認，不取消已送出的 Apply。未知結果仍顯示實際去敏錯誤原因及穩定代碼。
- `document/架構重整/01_規格基線/17_External_Integration_LINE_Access正式規格.md` §5.2 — four exclusive counters、未匯入明細及 bounded same-key 結果確認。
- `document/架構重整/01_規格基線/01_Orders_Domain.md` §3.7 — Historical Order Adoption presentation boundary。

## Verification
- layout_status: `custom_current`
- integration_root: `ui_react/src/tests/case_workbook_adapters.test.ts`
- integration_root: `ui_react/src/tests/data_import_case_workbooks_preview_flow.test.tsx`
- integration_root: `ui_react/src/tests/data_import_entry_cutover.test.tsx`
- integration_root: `ui_react/src/tests/data_import_hcm_result_page.test.tsx`
- integration_root: `ui_react/src/tests/data_import_no_fake_mutation.test.tsx`
- integration_root: `ui_react/src/tests/data_import_hcm_preview_flow.test.tsx`
- integration_root: `ui_react/src/tests/hcm_workbook_client.test.ts`
- integration_root: `ui_react/src/tests/fixtures/hcm_import_result_fixtures.ts`
- integration_root: `ui_react/src/tests/historical_service_accounting_entry.test.tsx`

## Provenance
- Data Import page is cross-owner presentation composition, not a new Domain owner — `architecture_declared` — root workspace architecture boundary。
- Page and integration test paths — `source_observed` — current repository。

## Change triggers
Reconcile when Data Import page composition、typed workbook adapters、preview/apply flow or integration test paths change。
