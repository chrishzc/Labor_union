---
doc_type: work-package
declared_status: blocked
identity: PROV-20260816-react-admin-phase3a-line-customer-service-identity
date: 2026-08-16
owner: Integration Owner
domain: Customer Service / LINE Identity Management
subsystem: Ticket Handling / Identity Revocation / React Presentation
specification: PROV-20260816-react-admin-phase3a-line-customer-service-identity-specification
approval_required: human-must-reply-核准此-exact-Phase-3A-Work-Package
approval_evidence: user-replied-exact-text-2026-08-16
base_branch: main
base_head: 8615225481c8f72a9629289285516189b270cb36
---

# React 管理端 Phase 3A：LINE 客服結案與身分解除工作包（防偷懶版）

## 0. Activation gate

本文件已於2026-08-16取得使用者 exact 核准。核准文字：

> 核准此 exact Phase 3A Work Package

本次只可執行本文件 exact write set；核准不擴張至Phase 4、DB、deployment或其他頁面。

核准後 Integration Owner 必須先記錄 current branch、HEAD、`git status --short`，保存每個 write-set path
的存在性、size、mtime及 SHA256 collision inventory，並把本文件改為 `approved`／`in-progress`。
base SHA只作歷史來源，不得 checkout覆蓋 current dirty files。禁止 reset、clean、stash、切分支、建立
worktree、stage、commit、push。

## 1. Goal 與合法完成狀態

在現有 LINE 管理頁原位接線 ticket/binding Query、客服結案與 identity revocation。不得順手實作
Phase 4。最高合法狀態：G0–G8 全 PASS後 `completed-local-validated`；缺 controlled data或真 browser時
固定 `blocked`。

## 2. Contract freeze before code

Integration Owner 建立唯一 artifact：

`document/架構重整/03_追蹤清單與證據/evidence/PROV-20260816-react-admin-phase3a-line-customer-service-identity/contract-field-matrix.md`

每列必須包含：

`surface/control id | business owner | method/path | request/JSON path | Pydantic file:line | required | nullable | enum/range | privacy | error/status | disposition | UI slot`

Disposition只允許 `READY_TYPED_DISPLAY | READY_TYPED_INTERNAL_ONLY | PRESENTATION_CONSTANT | BACKEND_GAP | OUT_OF_SCOPE`。

Contract Scout 另交：

- action → allowed endpoint → max-call request budget；
- 客服 update Preview缺口與 Apply fingerprint/version closure；
- identity revocation request/saga completion的分離；
- locked-control inventory；
- current worktree collision/base drift；
- endpoint×allowed status/error matrix。

只有 Integration Owner fresh-read route/schema/application/tests 後可宣告 `CONTRACT_MATRIX_FROZEN`。Writer
提供的 fixture或 chat摘要不能取代 matrix。

## 3. Mutually exclusive lanes

### Lane A — Contract Scout（Luna，可平行，strict read-only）

Write set：無。只讀 specs、routes、schemas、application、tests與React page，回傳 evidence，不修改文件。

### Lane B — Customer Service Backend Contract Writer

G1 freeze後才能開始。Exact write set：

- `api/schemas/customer_service.py`
- `api/routes/customer_service.py`
- `subsystems/customer_service/contracts.py`
- `subsystems/customer_service/application.py`
- `tests/test_line_customer_service_first_release.py`
- `tests/test_customer_service_preview_contract.py`（新增）

只新增 purpose-specific update Preview／Apply pair，不改或退役既有 PATCH，不改 Domain transition、DB
schema、repository、delivery worker。
Preview測試必須證明零寫入；Apply測 fresh version/fingerprint、replay、payload mismatch、rollback、audit，
並證明純狀態更新不建立LINE delivery task。
若閉合需要 shared exception handler或DB變更，停止並回 `SCOPE_EXPANSION_REQUIRED`。

### Lane C — Frontend Customer Service Client Writer

G1 freeze後可與 Lane B 平行，但只能依 frozen candidate contract。Exact write set：

- `ui_react/src/api/customer_service/customer_service_schemas.ts`
- `ui_react/src/api/customer_service/customer_service_errors.ts`
- `ui_react/src/api/customer_service/customer_service_client.ts`
- `ui_react/src/adapters/customer_service/customer_service_adapter.ts`
- `ui_react/src/tests/fixtures/customer_service/customer_service_contract_fixtures.ts`
- `ui_react/src/tests/customer_service_client.test.ts`
- `ui_react/src/tests/customer_service_adapter.test.ts`

不得直接fetch繞過 shared transport，不得把 raw payload傳 page。

### Lane D — Frontend LINE Identity Client Writer

G1 freeze後可與 B/C平行。Exact write set：

- `ui_react/src/api/line_identity/line_identity_schemas.ts`
- `ui_react/src/api/line_identity/line_identity_errors.ts`
- `ui_react/src/api/line_identity/line_identity_client.ts`
- `ui_react/src/adapters/line_identity/line_identity_adapter.ts`
- `ui_react/src/tests/fixtures/line_identity/line_identity_contract_fixtures.ts`
- `ui_react/src/tests/line_identity_client.test.ts`
- `ui_react/src/tests/line_identity_adapter.test.ts`

只實作 list/detail/revocation preview/apply；其他 route即使存在也禁止加入 client。

### Lane E — Presentation Writer

Lane B/C/D freeze且focused tests PASS後才開始。Exact write set：

- `ui_react/src/pages/LineManagementPage.tsx`
- `ui_react/src/pages/LineManagementPage.css`
- `ui_react/src/tests/line_management_page_real_data.test.tsx`
- `ui_react/src/tests/line_customer_service_resolve_flow.test.tsx`
- `ui_react/src/tests/line_identity_revocation_flow.test.tsx`
- `ui_react/src/tests/line_management_no_fake_mutation.test.tsx`

語意 merge current dirty baseline，不從 Desktop整檔覆蓋。不得刪除六 tabs或更改整體設計。

### Lane F — Fresh Verification Auditor（Luna，strict read-only）

不得寫 receipt或修code。只在最新整合內容執行命令、記錄 raw output／exit code／counts，逐檔讀diff並
找出假測試、skip、unexpected network、write-set violation。Integration Owner唯一落盤 evidence。

## 4. Shared hotspots（禁止競寫）

本批次不得修改：

- `ui_react/src/api/shared/transport.ts`
- `ui_react/src/api/shared/runtime_decoder.ts`
- Auth/session/App/MasterLayout/Drawer
- `package.json`、lockfile、Vite/TS config
- `api/main.py`、shared exception handler
- DB schema、migration、release catalog
- 其他頁面與 Phase 2 artifacts

如必要能力缺在 hotspot，停止，不複製第二套 transport/router/error handler。

## 5. Anti-laziness rules

1. 禁止只跑 build/lint就宣稱完成。
2. 禁止複製 prototype literals、把 fixtures搬入production、fallback到mockData/local arrays。
3. 禁止把所有區塊顯示 unavailable後宣稱接線完成；每個 READY field至少一個decoder＋adapter＋DOM sentinel assertion。
4. 禁止 snapshot-only、`expect(true)`、`.skip/.todo/.only`、零 assertion tests。
5. component tests不准真連localhost；unexpected fetch立即fail。真API只在G7。
6. 所有 non-GET依 exact allowlist；locked control click後 non-GET總數為0。
7. Apply pending按鈕 native disabled；CSS灰色或handler early-return不算。
8. 不得把 revocation request accepted顯示成 revoked／owner projection cleared。
9. Phase3A React不得呼叫legacy customer PATCH，也不得把它包成前端假Preview。
10. 不得引用其他代理「passed」或舊測試數；Auditor在最新tree重跑。

## 6. G0–G8 acceptance gates

| Gate | PASS condition |
|---|---|
| G0 Scope | exact approval、baseline/collision inventory、0 write-set violation、0 DB |
| G1 Contract | matrix逐欄freeze，route/schema/application/tests與privacy/error閉合 |
| G2 Backend | Customer Preview zero-write；Apply stale/replay/conflict/UoW/audit且0 delivery通過；Identity saga/outbox focused regression通過 |
| G3 Clients | strict decoder負向tests；即時memory token注入；method/path/header/request budget exact |
| G4 Presentation | 六tab與stable surfaces存在可見；兩flow exhaustive state；其餘controls native disabled |
| G5 Negative safety | sentinel divergence、unexpected network=0、fake mutation=0、mock dependency closure=0 |
| G6 Static suites | focused→full Vitest、lint、build、focused pytest、UTF-8/header/secret/PII/diff/skip scans全PASS |
| G7 Runtime | 真FastAPI＋Vite＋帳密→TOTP；controlled ticket/binding；Network request/header/body→typed DOM→re-query evidence |
| G8 Fresh audit | Integration Owner讀完整diff與raw output；receipt/current counts/open findings/index一致 |

任何必要 gate `BLOCKED`／`NOT_RUN`，整包不得標 completed。

## 7. Required commands

```powershell
cd D:\project\Labor_union\ui_react
npm test -- src/tests/customer_service_client.test.ts src/tests/customer_service_adapter.test.ts
npm test -- src/tests/line_identity_client.test.ts src/tests/line_identity_adapter.test.ts
npm test -- src/tests/line_management_page_real_data.test.tsx src/tests/line_customer_service_resolve_flow.test.tsx src/tests/line_identity_revocation_flow.test.tsx src/tests/line_management_no_fake_mutation.test.tsx
npm test
npm run lint
npm run build
```

```powershell
cd D:\project\Labor_union
.venv\Scripts\python.exe -m pytest -p no:cacheprovider --basetemp .pytest_tmp/phase3a-line -q tests/test_line_customer_service_first_release.py tests/test_customer_service_preview_contract.py tests/test_line_identity_management_first_release.py
git diff --check
```

測試暫存不得共用。命令實際不存在或0 tests collected固定fail，不得記為PASS。

## 8. Evidence set

Integration Owner唯一可寫：`contract-field-matrix.md`、`contract-matrix-freeze-receipt.md`、
`candidate-change-inventory.md`、`verification-receipt.md`、`browser-smoke-receipt.md`、`open-findings.md`、
`evidence-summary.md`。Receipt不得含token、完整LINE ID、電話、internal note或provider secret。

## 9. Current result（2026-08-17 fresh audit）

Phase 3A production scope 已完成本機 focused validation，但整包維持 `blocked`：

- `BLOCKED_REAL_BROWSER_EVIDENCE`：Vite 頁面可開啟，但目前瀏覽器沒有 volatile Session，且沒有
  controlled ticket／binding 可安全執行 mutation。

後續 integration repair 已恢復被覆蓋的 Phase 2B Orders presentation，並修正 Phase 2D／Phase 2A
測試的 Session／mock drift。fresh audit 另移除 LINE identity Apply 的完成狀態推論，並將 Customer
Service datetime 收緊為 strict ISO decoder；最新全量 Vitest 為 43 files、510 tests 全數通過。這只關閉
static regression blocker，不替代真實 browser mutation evidence。

不得把 focused PASS 升格為 `completed-local-validated`。關閉條件與實測數字以同 identity evidence 目錄
的 `verification-receipt.md`、`browser-smoke-receipt.md` 與 `open-findings.md` 為準。
