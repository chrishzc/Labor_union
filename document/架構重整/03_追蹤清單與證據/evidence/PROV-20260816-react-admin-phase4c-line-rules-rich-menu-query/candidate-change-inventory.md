# Phase 4C-Q candidate change inventory

## Production／adapter

- `ui_react/src/api/line_configuration/line_configuration_query_schemas.ts`
- `ui_react/src/api/line_configuration/line_configuration_query_errors.ts`
- `ui_react/src/api/line_configuration/line_configuration_query_client.ts`
- `ui_react/src/adapters/line_configuration/line_configuration_query_adapter.ts`
- `ui_react/src/pages/LineManagementPage.tsx`

`LineManagementPage.css` 經 fresh-read 後不需修改。沒有 backend、DB、shared transport、Auth、package 或其他頁面變更。

## Tests／fixtures

- `ui_react/src/tests/fixtures/line_configuration_query_fixtures.ts`
- `ui_react/src/tests/line_configuration_query_client.test.ts`
- `ui_react/src/tests/line_configuration_query_adapter.test.ts`
- `ui_react/src/tests/line_rules_query_flow.test.tsx`
- `ui_react/src/tests/line_rich_menu_query_flow.test.tsx`
- `ui_react/src/tests/line_management_no_fake_mutation.test.tsx`

## Adjacent test-harness correction

- `ui_react/src/tests/route_guard.test.tsx`：兩個 challenge fixture 原固定於
  `2026-08-16T16:00:00Z`，於 2026-08-17 起必然失效；只將其改為明確的未來測試時間，沒有修改 Auth production 行為。

## Integration-owned documents

- Phase 4C-Q specification／Work Package／active index／主 React 計畫。
- 本 evidence 目錄內的 contract matrix、inventory、verification、open findings 與 summary。

## Boundary result

- DB/schema/migration/seed/backfill：0。
- Backend route／application／repository：0。
- LINE provider、worker、outbox、job side effect：0。
- Notification rule／Rich Menu mutation：0；相關控制維持原生鎖定。
