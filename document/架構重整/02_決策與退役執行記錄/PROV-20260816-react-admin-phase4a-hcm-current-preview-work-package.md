---
doc_type: work-package
declared_status: completed
identity: PROV-20260816-react-admin-phase4a-hcm-current-preview
date: 2026-08-16
owner: Integration Owner
domain: Case Import
subsystem: HCM Current Workbook Preview / React Presentation
specification: PROV-20260816-react-admin-phase4a-hcm-current-preview-specification
authority: user-approved-autonomous-phase-progression-2026-08-16
base_branch: main
base_head: 8615225481c8f72a9629289285516189b270cb36
---

# React 管理端 Phase 4A-P：HCM Current Workbook 真檔 Preview 工作包（防偷懶版）

## 0. Activation 與 scope

使用者已採用自動推進 Phase 3→6、以子代理分工並要求主代理持續產生 Work Package 與執行；本包只
執行已存在 typed success contract 的 Preview-only slice。任何 backend public contract、Apply、DB 或
entry cutover 均未被本包授權。

base SHA 只作歷史來源。既有 dirty/untracked 全部保留；禁止 reset/clean/stash/checkout/worktree/stage/
commit/push。Integration Owner 是文件/index與 `DataImportPage` 唯一 writer。

## 1. Contract freeze artifact

開工前凍結：

`document/架構重整/03_追蹤清單與證據/evidence/PROV-20260816-react-admin-phase4a-hcm-current-preview/contract-field-matrix.md`

每列含 `surface/control | method/path | multipart/header | Pydantic path | required/nullability/range | privacy |
disposition | UI slot`。只有 matrix 中 `READY_TYPED_PREVIEW` 可進 production。

## 2. Mutually exclusive lanes

### Lane A — Contract Scout（Luna，read-only）

讀 route/schema/service/repository/tests/Streamlit/React，交 request budget、field matrix、locked controls 與
backend gaps。不得寫檔。

### Lane B — Frontend Client／Adapter Writer（Terra）

Exact write set：

- `ui_react/src/api/case_import/hcm_workbook_schemas.ts`
- `ui_react/src/api/case_import/hcm_workbook_errors.ts`
- `ui_react/src/api/case_import/hcm_workbook_client.ts`
- `ui_react/src/adapters/case_import/hcm_workbook_adapter.ts`
- `ui_react/src/tests/fixtures/hcm_workbook_contract_fixtures.ts`
- `ui_react/src/tests/hcm_workbook_client.test.ts`
- `ui_react/src/tests/hcm_workbook_adapter.test.ts`

只能實作 file snapshot/validation/hash、strict decoder 與 Preview request；不得加入 Apply method。

### Lane C — Integration／Presentation Writer（Primary）

Exact write set：

- `ui_react/src/pages/DataImportPage.tsx`
- `ui_react/src/pages/DataImportPage.css`
- `ui_react/src/tests/data_import_hcm_preview_flow.test.tsx`
- `ui_react/src/tests/data_import_no_fake_mutation.test.tsx`

語意 merge current dirty baseline；不得整檔從 Desktop 覆蓋。

### Lane D — Fresh Auditor（Luna，read-only）

候選 freeze 後執行 commands、讀完整 diff、回傳 raw counts/findings；不得修 code 或寫 receipt。

## 3. Shared hotspots／forbidden writes

禁止修改 backend、DB、`api/shared`、`ui_react/src/api/shared/*`、Auth/session/App/MasterLayout/Drawer、package/
lock/config、其他頁面、Streamlit、entry queue。若完成 Preview 需要 hotspot，記錄 blocker，不複製第二套
transport或自創 backend schema。

## 4. Anti-laziness rules

1. 不得以 build/lint 或截圖取代 contract／negative／DOM tests。
2. 不得複製 fake sample、fixture、filename 或 counts 到 production。
3. component tests 任何 unexpected fetch 立即失敗；只有一個 allowlisted POST。
4. Apply 及其他 10 controls 必須 native disabled、無 handler、click 後 non-GET=0。
5. 禁止 `.skip/.todo/.only`、snapshot-only、零 assertion、`expect(true)`。
6. 必須用兩份同名不同 bytes sentinel 證明 DOM digest/count 由 server response 改變。
7. 必須驗證 multipart key、session token freshness、Abort、30s timeout、新檔清舊 preview、digest mismatch。
8. 不得將 raw `detail`、bytes、完整檔名路徑、token或客戶資料放入 DOM/log/receipt。
9. 不得把 row-detail unavailable、Apply locked 或 historical retired 算成 real-data completion。
10. Auditor 必須在最後修改後 fresh-run，不採信 writer 自報數字。

## 5. G0–G6 gates

| Gate | PASS condition |
|---|---|
| G0 Scope | authority/baseline/collision inventory；exact write set；0 backend/DB/hotspot |
| G1 Contract | matrix freeze；唯一 endpoint、fields、request budget、locked inventory閉合 |
| G2 Client | strict decoder負向測試；真FormData `workbook`；fresh memory token；digest lineage |
| G3 Presentation | 六卡/Drawer槽位保留；HCM真file Preview；row detail unavailable；Apply/其餘controls disabled |
| G4 Negative safety | mock/Math.random/alert/confirm/fake sample/Apply request/unexpected network皆0 |
| G5 Static suites | focused→full Vitest、lint、build、focused pytest、UTF-8/header/secret/diff/skip掃描 |
| G6 Fresh evidence | Integration讀diff/raw output；evidence/index/status與實際結果一致 |

任一必要 gate BLOCKED/NOT_RUN 不得標 completed。

## 6. Required commands

```powershell
cd D:\project\Labor_union\ui_react
npm test -- src/tests/hcm_workbook_client.test.ts src/tests/hcm_workbook_adapter.test.ts
npm test -- src/tests/data_import_hcm_preview_flow.test.tsx src/tests/data_import_no_fake_mutation.test.tsx
npm test
npm run lint
npm run build
```

```powershell
cd D:\project\Labor_union
.venv\Scripts\python.exe -m pytest -p no:cacheprovider --basetemp .pytest_tmp/phase4a-hcm-preview -q tests/test_hcm_import_router.py tests/test_hcm_workbook_import.py tests/test_hcm_import_api_client.py tests/test_data_import_command_key.py
git diff --check
```

命令不存在、0 tests collected、unexpected network、後續相關修改使證據過期，固定 fail。

## 7. Evidence set

Integration Owner 唯一寫入：`contract-field-matrix.md`、`candidate-change-inventory.md`、
`verification-receipt.md`、`open-findings.md`、`evidence-summary.md`。本波沒有 Apply/runtime mutation，
不以空白 browser mutation receipt 冒充 gate。

## 8. Current result（2026-08-16）

Phase 4A-P 為 `completed-local-validated-preview-only`：focused 4 files／14 tests、full React 39 files／
496 tests、build、lint exit 0與backend HCM 22 tests通過。Apply、warning disposition、outer UoW、receipt
observation、browser upload與entry cutover沒有完成，詳見同identity evidence及Phase4A-H gap。
