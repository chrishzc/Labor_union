# Module: data-import-composition

## Parent
- domain: `global`
- subsystem: `application-shell`

## Responsibility
組成 Case Import 與 Orders 等既有 owner 的 typed workbook Preview／Apply UI；只協調頁面狀態與顯示，不重算 Domain facts 或取得 mutation authority。

## Implementation
- primary: `ui_react/src/pages/DataImportPage.tsx`

## Dependencies
- outbound: `orders/orders/module:historical-adoption-presentation` — Historical Orders typed preview／receipt。
- outbound: `case-import` owners — HCM／Client BeClass typed workbook clients。
- inbound: authenticated React application navigation。

## Contracts
- `document/架構重整/01_規格基線/01_Orders_Domain.md` §3.7 — Historical Order Adoption presentation boundary。

## Verification
- layout_status: `custom_current`
- integration_root: `ui_react/src/tests/case_workbook_adapters.test.ts`
- integration_root: `ui_react/src/tests/data_import_case_workbooks_preview_flow.test.tsx`

## Provenance
- Data Import page is cross-owner presentation composition, not a new Domain owner — `architecture_declared` — root workspace architecture boundary。
- Page and integration test paths — `source_observed` — current repository。

## Change triggers
Reconcile when Data Import page composition、typed workbook adapters、preview/apply flow or integration test paths change。
