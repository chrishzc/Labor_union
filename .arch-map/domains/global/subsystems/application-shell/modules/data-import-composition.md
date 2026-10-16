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
- 匯入頁只顯示來源筆數、成功匯入、重複略過、未匯入；不再組合 review 明細或單列更正工作台。
- outbound: `case-import` owners — HCM／Client BeClass typed workbook clients。
- inbound: authenticated React application navigation。

## Contracts
- `document/架構重整/01_規格基線/17_External_Integration_LINE_Access正式規格.md` §5.2 — four exclusive counters and no issue details in the import page。
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
