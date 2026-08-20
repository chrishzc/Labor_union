---
doc_type: work-package
declared_status: completed
identity: PROV-20260816-react-admin-phase4c-line-rules-rich-menu-query
date: 2026-08-16
owner: Integration Owner
domain: LINE Configuration
subsystem: Notification Rules Catalog / Rich Menu Snapshot / Publication History
specification: PROV-20260816-react-admin-phase4c-line-rules-rich-menu-query-specification
authority: user-approved-autonomous-phase-progression-2026-08-16
base_branch: main
base_head: 8615225481c8f72a9629289285516189b270cb36
---

# React 管理端 Phase 4C-Q：LINE Rules／Rich Menu Query-only 工作包（防偷懶版）

## 0. Activation／scope

只執行四個 authenticated GET 的 runtime-validated presentation adapter。base SHA 只作歷史來源；保留所有
dirty/untracked，禁止 reset/clean/stash/checkout/worktree/stage/commit/push。

## 1. Lanes 與 exact write set

### Lane A — Contract Scout（Luna，read-only）

凍結 endpoint、field/enum/nullability、request budget、sensitive render allowlist及 locked controls；不得寫檔。

### Lane B — Client／Adapter Writer（Terra）

- `ui_react/src/api/line_configuration/line_configuration_query_schemas.ts`
- `ui_react/src/api/line_configuration/line_configuration_query_errors.ts`
- `ui_react/src/api/line_configuration/line_configuration_query_client.ts`
- `ui_react/src/adapters/line_configuration/line_configuration_query_adapter.ts`
- `ui_react/src/tests/fixtures/line_configuration_query_fixtures.ts`
- `ui_react/src/tests/line_configuration_query_client.test.ts`
- `ui_react/src/tests/line_configuration_query_adapter.test.ts`

### Lane C — Presentation／Integration Writer（Primary）

- `ui_react/src/pages/LineManagementPage.tsx`
- `ui_react/src/pages/LineManagementPage.css`
- `ui_react/src/tests/line_rules_query_flow.test.tsx`
- `ui_react/src/tests/line_rich_menu_query_flow.test.tsx`
- `ui_react/src/tests/line_management_no_fake_mutation.test.tsx`

### Lane D — Fresh Auditor（Luna，read-only）

在最後修改後跑 raw commands、讀 diff、檢查 unexpected network與 stable IDs；不得修 code／寫 receipt。

Integration Owner 唯一修改本工作包、spec、README、主計畫與 evidence。

## 2. Forbidden writes／anti-laziness

禁止 backend/DB/shared/Auth/App/package/其他頁面。禁止 `z.any/z.unknown/z.record/.passthrough/.catch/.default/
.coerce/.preprocess/.transform`、`as any/unknown as`。禁止 fixture 成為 production fallback、snapshot-only、
`.skip/.todo/.only`、alert/confirm。任何 unexpected fetch 或 non-GET 立即 fail。

空 catalog 必須顯示 empty；schema drift才顯示 unavailable。不得將兩者混成「沒有資料」。不得 render
action URI/postback data/image path/provider/correlation/raw error。其餘客服/identity flows必須回歸全綠。

## 3. Gates

| Gate | PASS condition |
|---|---|
| G0 Scope | exact write set；0 backend/DB/shared/hotspot collision |
| G1 Contract | 四GET、全欄位/enum、display allowlist、request budget凍結 |
| G2 Client | strict decoder負向測試、fresh bearer、abort、401/403/404/schema mismatch |
| G3 Presentation | 真 rules/menu/publications；empty/error/retry；既有六tabs與Phase3A flows保留 |
| G4 Safety | non-GET=0；publish-preview/save/delete/retry/upload全鎖；mock RULES/menu literals=0 |
| G5 Static | focused/full Vitest、lint、build、UTF-8/header/secret/diff/skip scans |
| G6 Evidence | fresh outputs、candidate inventory、open findings與實際狀態一致 |

## 4. Required commands

```powershell
cd D:\project\Labor_union\ui_react
npm test -- src/tests/line_configuration_query_client.test.ts src/tests/line_configuration_query_adapter.test.ts
npm test -- src/tests/line_rules_query_flow.test.tsx src/tests/line_rich_menu_query_flow.test.tsx src/tests/line_management_no_fake_mutation.test.tsx
npm test
npm run lint
npm run build
```

```powershell
cd D:\project\Labor_union
git diff --check
```

## 5. Evidence

`document/架構重整/03_追蹤清單與證據/evidence/PROV-20260816-react-admin-phase4c-line-rules-rich-menu-query/`
由 Integration Owner 寫入 contract matrix、candidate inventory、verification、open findings、summary。

## 6. Completion result（2026-08-17）

本工作包完成狀態為 `completed-local-validated-query-only`：focused 5 files／12 tests與完整 React
43 files／507 tests均通過，build／lint／UTF-8／scoped diff check通過。真 browser controlled-data
Network↔DOM證據尚未執行，因此不構成 entrypoint cutover ready；backend raw-dict、delivery、Knowledge及
既有測試 warnings仍依 evidence/open findings追蹤。
