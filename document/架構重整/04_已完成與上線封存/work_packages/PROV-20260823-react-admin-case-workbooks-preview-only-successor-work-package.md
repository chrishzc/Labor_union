---
doc_type: work-package
declared_status: completed
identity: PROV-20260823-react-admin-case-workbooks-preview-only-successor
date: 2026-08-23
owner: Case Import / Orders Historical Adoption / React Integration
domain: Case Import / Staff / Orders
approval_required: 核准此 exact Phase 4A-CW Preview-only React successor Work Package
authority: exact-human-approved-2026-08-23
db_change: none
delivery_ceiling: local-preview-candidate-only
---

# Phase 4A-CW Preview-only React successor工作包

## 人工核准與優先序補充（2026-08-23）

人工已核准建立並執行本 exact successor：接入 Client BeClass、Staff Historical、Historical Orders
三個 typed Preview；本包內 Apply 全部維持 disabled，且不授權 DB、production host、entry switch 或
public-contract 擴張。

人工同時裁決 Preview-only 不是營運匯入完成狀態。完成本包後必須緊接三 family 的假資料匯入／Apply
功能測試，驗證實際寫入結果、錯誤、stale、replay 與 idempotency，再由後續已核准工作包裁決 UI Apply
解鎖與 `lu_test_*` 真 MySQL／API／browser 驗收；不得以本包 PASS 宣稱真實資料已可匯入。

## Business scenario

為了先完成營運作業前端，管理員需要在Data Import頁分別選取Client BeClass、Staff Historical與
Historical Orders工作簿，取得server whole-workbook Preview aggregate。這一階段只證明檔案快照、strict typed
Preview、錯誤與UI呈現；不Apply、不建立production readiness或entry switch。

本包是2026-08-22營運前端優先序的最小解鎖候選。它不把既有live route升格為完成的CW-H public contract；
人工核准本包即只確認React可在`local-preview-candidate-only` ceiling下消費目前三個candidate Preview response。

## Exact write set

- `ui_react/src/api/case_import/client_beclass_workbook/`（schemas／errors／client）
- `ui_react/src/api/case_import/staff_historical_workbook/`（schemas／errors／client）
- `ui_react/src/api/orders/historical_order_workbook/`（schemas／errors／client）
- `ui_react/src/adapters/case_import/client_beclass_workbook_adapter.ts`
- `ui_react/src/adapters/case_import/staff_historical_workbook_adapter.ts`
- `ui_react/src/adapters/orders/historical_order_workbook_adapter.ts`
- `ui_react/src/pages/DataImportPage.tsx`
- `ui_react/src/pages/DataImportPage.css`
- 三個bounded client tests、`case_workbook_adapters.test.ts`、`data_import_case_workbooks_preview_flow.test.tsx`
- 本工作包與專屬evidence receipt。

DataImportPage是shared hot spot，只能由Integration Writer修改。Backend、Domain、Subsystem、repository、schema、
migration、shared transport、App、entry registry與Finance Import均不在write set。

## Contract與UI不變量

1. 三family各有獨立client／schema／error／adapter；禁止generic import client。
2. file bytes只讀一次形成immutable snapshot與SHA-256；同檔名不同bytes必須清除舊Preview並產生不同digest。
3. multipart只送`workbook`及route已定義的optional source identity；bearer每次從memory session取得，無token零fetch。
4. success envelope與data使用strict Zod；unknown extra、缺欄、null required、錯誤enum、非小寫64-hex全部fail closed。
5. Preview只顯示server aggregate、source digest與preview fingerprint；不得合成row success、warning或business facts。
6. 選檔、重選、tab切換、unmount、retry具Abort／generation guard；late response不得覆蓋新檔。
7. 三family Apply controls固定native disabled，且沒有handler、idempotency key或成功訊息。
8. HCM Historical維持410 retired；HCM Current既有Preview/result不受本包改變。
9. Finance／Bank卡保持disabled，直到FI-H證明真正Preview語意與FI-R另行核准。

## Acceptance

- 每family：positive aggregate、same-name/different-bytes、extra/missing/null/invalid digest、401/403/409/422/503、
  timeout/abort/schema mismatch focused tests。
- DataImportPage UI tests驗證三張卡可選檔與Preview，所有Apply及Finance控制仍native disabled，0 fake success。
- production build、strict UTF-8/no BOM、file headers、scoped `git diff --check` PASS。
- fixture gate PASS後才可進`lu_test_*`真API/browser Preview；未取得工會主機授權前不連線。

## Non-goals與後續門

本包不裁決whole-workbook／row-atomic、raw source archive、retention、recovery、receipt或Apply transaction；上述仍由
CW-H正式關閉。不得以本包PASS宣稱三family production-ready、資料已匯入或Phase 5 entry完成。

DB gate：Scope／Change inventory `PASS`（0 DB）；Static release、Descriptor、Read-only plan、Engine migration與
Developer migration acceptance均`NOT_RUN`，固定結論`DB_CHANGE_NOT_READY`。

## 完成證據（2026-08-23）

- React三個bounded client／schema／error／adapter與DataImportPage接線完成；三個Apply及Finance控制維持
  native disabled，entry target仍為Streamlit。
- focused Vitest：8 files／22 tests `PASS`；既有`data_import_no_fake_mutation`仍有React `act(...)` warning，
  無failed assertion。
- production build：TypeScript與Vite `PASS`，202 modules；僅既有large-chunk warning。
- 假資料匯入／Apply business tests：20 pytest `PASS`；Python API client contract：4 pytest `PASS`；
  Data Import entry governance：3 pytest `PASS`。
- strict UTF-8／no BOM／source-test file header／trailing whitespace：20 files `PASS`；scoped
  `git diff --check` `PASS`，只有line-ending提示。
- Final receipt：`../03_追蹤清單與證據/evidence/PROV-20260823-react-admin-case-workbooks-preview-only-successor/verification-receipt.md`。

本包完成只代表local fixture Preview candidate與既有假資料Apply核心通過，不代表React Apply、`lu_test_*`
真MySQL／API／browser、工會主機真實資料或production readiness完成。
