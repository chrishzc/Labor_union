---
doc_type: work-package
declared_status: blocked
identity: PROV-20260816-react-admin-phase2b-orders-safe-mutations
owner: Integration Owner
date: 2026-08-16
base_ref: ad79f5b4fb35f1ef442f889702aaa4ccb2c5d922
specification: PROV-20260816-react-admin-phase2b-orders-safe-mutations-specification
approval_required: human-must-reply-核准此exact-Phase2B-Work-Package
---

# React 管理端 Phase 2B：Orders 安全 Mutation 工作包（防偷懶版）

## 0. Activation gate & Dirty Worktree Protection

本包已獲人工核准並完成 G1–G5 修復後驗證；目前因 G6 的真瀏覽器與合法測試案件證據不足而維持
`blocked`。任何後續 production/backend/tests 修改仍須在本包 exact write set 或新核准工作包內進行。

### 0.1 Worktree Baseline & Dirty Protection
Coordinator 開始前必須保存：
1. 完整 `git status --short` 輸出作為基線。
2. exact write-set 每個檔案的 path / size / SHA256 baseline。
3. dirty / untracked collision inventory，確保非本包之既有產出不被覆蓋。
4. 每次 lane handoff 進行 base-drift 比對；禁止以指定 commit 覆蓋未追蹤檔案。

### 0.2 Phase 2A Baseline
Phase 2A G1–G4 必須在 Phase 2B 開工基準重跑。Phase 2A 的 `BLOCKED_REAL_BROWSER_EVIDENCE` 只可阻擋
browser/completion，不得被代理拿來省略 Phase 2B contract/client/component tests。

## 1. Exact scope

### 1.1 In scope

- Confirmed Service Dates：Query／Preview／Apply／receipt／re-query。
- Controlled Reopen：Preview／Apply／receipt／re-query。
- 將 service-date route error 收斂成 Global typed error envelope（FastAPI request validation 列為 BACKEND_GAP）；Apply reason 改為必填且非空（1–500 字）。
- 將 order_reopen route 的 reason 補上 trim 後非空校驗（1–500 字）。
- 在既有 `OrdersPage` 原位置啟用上述操作；不重畫、不新增競爭入口。
- Strict Zod、typed clients、state-machine view adapters、component tests、route/workflow regression、browser receipt。

### 1.2 Out of scope

- Terms、Actual Start、Cancellation、Assignment Plan、Contract Completion mutation UI。
- candidate pool、matching、formal recommendation、LINE、7-stage、SOP、三結清、emergency warning contract。
- DDL/schema/migration/seed/backfill、Streamlit retirement、launcher/deployment、其他 10 頁、package/lockfile。
- 任何 optimistic business success、前端日期/coverage/lifecycle/finance 公式。

## 2. Exact write set

### Backend lane (Lane B)

- `api/routes/service_date_confirmation.py`
- `api/schemas/service_date_confirmation.py`（只有 typed error view 確有必要時）
- `api/routes/order_reopen.py`
- `tests/test_service_date_confirmation.py`
- `tests/test_service_date_confirmation_router.py`
- `tests/test_order_reopen_router.py`

不得修改 Domain candidate、workflow、repository、DB adapter；若現行 workflow 無法滿足規格，停止並回
`PUBLIC_CONTRACT_CHANGE_REQUIRED`，不得順手擴張。

### Frontend client lane (Lane C)

- `ui_react/src/api/orders/order_mutation_schemas.ts`
- `ui_react/src/api/orders/order_mutation_client.ts`
- `ui_react/src/api/orders/order_mutation_errors.ts`
- `ui_react/src/tests/orders_mutation_client.test.ts`
- `ui_react/src/tests/fixtures/orders/order_mutation_contract_fixtures.ts`

### Frontend presentation lane (Lane D)

- `ui_react/src/adapters/orders/order_mutation_adapter.ts`
- `ui_react/src/adapters/orders/order_mutation_flow_store.ts`
- `ui_react/src/pages/OrdersPage.tsx`
- `ui_react/src/pages/OrdersPage.css`
- `ui_react/src/tests/orders_mutation_adapter.test.ts`
- `ui_react/src/tests/orders_mutation_flow_store.test.ts`
- `ui_react/src/tests/orders_service_dates_flow.test.tsx`
- `ui_react/src/tests/orders_reopen_flow.test.tsx`
- `ui_react/src/tests/orders_no_fake_mutation.test.ts`

### Integration-only docs/evidence (Integration Owner)

- 本 spec 與 Work Package、`02_決策與退役執行記錄/README.md`
- `03_追蹤清單與證據/evidence/PROV-20260816-react-admin-phase2b-orders-safe-mutations/`
  - `contract-matrix.md`
  - `contract-matrix-freeze-receipt.md`
  - `candidate-change-inventory.md`
  - `verification-receipt.md`
  - `browser-smoke-receipt.md`
  - `open-findings.md`

共享 `transport.ts`、`runtime_decoder.ts`、Auth、App、Drawer、package/lockfile 是 hot spots，禁止修改。

## 3. Contract-first Gate G1

Contract Scout 唯讀交付每個 request/response field：endpoint、method、Pydantic model、source line、required/
nullable/range/literal、HTTP status/error、UI field、sensitive policy、positive/negative test。至少證明：

- service dates query/preview/receipt 所有日期、versions、fingerprint、weeks。
- service-date error hardening before/after，不改 success payload。
- reopen preview/receipt、reason (1–500 字非空)、three expected versions、correlation/idempotency headers。
- Header 映射：
  - Service Query: `Authorization`
  - Service Preview: `Authorization`, `X-Correlation-ID`
  - Service Apply: `Authorization`, `X-Correlation-ID`, `Idempotency-Key`
  - Reopen Preview: `Authorization`, `X-Correlation-ID`
  - Reopen Apply: `Authorization`, `X-Correlation-ID`, `Idempotency-Key`
- raw dict 不存在於兩條核准 success data closure。
- route/application/workflow tests 實際存在，不能只以 route 存在判 ready。

Integration Owner 產出 `contract-matrix.md` 與 `contract-matrix-freeze-receipt.md`（含 SHA256 凍結碼）前，production writer 不得施工。

## 4. 多代理拓撲與嚴格交付順序

```text
1. Lane A: Contract Scout (唯讀)
   → 交付 Pydantic 逐欄清單與差距分析
2. Integration Owner 驗收並凍結 G1
   → 產出 contract-matrix.md 與 contract-matrix-freeze-receipt.md
3. Lane B: Backend Writer / Lane C: Frontend Client Writer (平行施工)
   → 交付後端 route tests 與前端 strict decoder/client tests
4. Integration Owner 驗收並確認 G2 / G3 交付
5. Lane D: Presentation Writer
   → 交付狀態機 adapter、OrdersPage UI 接線與 flow 測試
6. Lane E: Fresh Verification Auditor (唯讀)
   → 執行全量測試 (build, lint, vitest, pytest, diff, scans)，產出客觀數據
   → 禁止 Auditor 自修程式碼自證完成
7. Integration Owner
   → 執行真瀏覽器 G6 驗收、撰寫 6 份 evidence、更新 README 與判定最終狀態
```

| Lane | May write | Must not write | Required handoff |
|---|---|---|---|
| A Contract Scout | none | all files | source matrix、drift、test gaps |
| B Backend Writer | backend exact set | frontend/domain/DB/docs index | diff、route tests、no DDL/schema |
| C Client Writer | client exact set | pages/backend/shared/package | strict decoder/adversarial tests |
| D UI Writer | adapter/page exact set | backend/client shared/other pages | surface/control inventory、flow tests |
| E Fresh Auditor | none | all files | fresh raw commands/findings only |
| Integration Owner | docs/evidence/index | unapproved production | freeze/handoff/evidence/status decision |

## 5. Required frontend state machines

### 5.1 Service-date UI state

```text
idle → query_loading → query_ready
query_ready → draft_changed → preview_loading → preview_ready
preview_ready → draft_changed (invalidate preview)
preview_ready → apply_pending → receipt_received → requery_loading → observed
receipt_received → requery_loading → observation_failed → requery_loading → observed
apply_pending → outcome_unknown (timeout / 503 retryable)
outcome_unknown → apply_pending (僅限相同 payload + 相同 Idempotency-Key)
任何 query/preview failure → typed_error
409 → stale (clear preview, require query+preview)
```

### 5.2 Reopen UI state

```text
closed → preview_loading → preview_ready
preview_ready + nonblank reason → apply_pending
apply_pending → receipt_received → requery_loading → observed
receipt_received → requery_loading → observation_failed → requery_loading → observed
apply_pending → outcome_unknown (timeout / 503 retryable)
outcome_unknown → apply_pending (僅限相同 payload + 相同 Idempotency-Key)
preview blocker → typed_error (no Apply)
409 stale → preview invalidated
```

用 discriminated union；禁止多個互相矛盾 boolean、`as` assertion、catch 後顯示 unavailable 吞錯。
Drawer 關閉、切頁或重新 mount 不得遺失進行中 draft 的 Idempotency-Key。Lane D 必須使用
`order_mutation_flow_store.ts` 建立 task-owned、memory-only store；不得使用 Drawer local state、
`localStorage`、`sessionStorage`、URL、cookie 或 Client module cache 冒充持久化。

`outcome_unknown` 必須凍結 payload 與正常 Apply 控制，只允許專用 same-key replay；收到 receipt 後的
re-query 失敗必須保留 receipt 並進入 `observation_failed`，只可重試 Query，禁止再次 Apply。

## 6. Idempotency implementation rules

- key 在首次形成可 Apply draft 時產生並保存在 memory-only Orders flow store；不得使用 Math.random、時間戳單獨作 key。
- 使用 Web Crypto UUID 或既有安全 identity helper；不得新增套件。
- same draft retry 使用同一 key；任何 request payload 改變使舊 preview/key 失效。
- Apply pending 時所有同 flow 提交控制 native disabled；不得只改 CSS。
- correlation id 與 idempotency key 只送 header，不顯示完整值、不寫 log/snapshot/evidence。
- server receipt fingerprint 必與 preview 一致；不一致 fail closed。

## 7. Strict decoder anti-cheat

禁止：`z.any`、`z.unknown`、`z.record`、`.passthrough`、`.catch`、`.default`、`.coerce`、`.preprocess`、
`.transform` 吞錯、`unknown as`、只驗 outer envelope。後端 required 欄位前端 required；nullable 不等於 optional。

每個 success schema 至少測：missing required、wrong primitive、extra envelope、extra nested、null non-null、
invalid ISO date、invalid hex fingerprint、negative/zero range、invalid literal。每個 command 另測 headers/body 完全匹配。

## 8. UI preservation / control inventory

Existing surface 必須保留且可見：

```text
orders.page, orders.filters, orders.cards
orders.drawer.date, orders.drawer.matching, orders.drawer.contract, orders.drawer.cancellation
tracker.page, tracker.stepper, tracker.stage-sections, tracker.drawer
tracker.tab.sop, tracker.tab.notifications
```

Phase 2B 只允許下列 controls 從 locked 轉為 flow control：

```text
orders.date.service-date-select
orders.date.service-date-preview
orders.date.service-date-apply
orders.card.reopen
orders.reopen.reason
orders.reopen.apply
```

原有 `orders.date.actual-start/update/send/customer-confirm/staff-confirm/convert`、matching 全部、cancellation
apply、notification replay 仍 native disabled。測試逐 stable ID 點擊，斷言只有核准 endpoint 可發 request。

## 9. Request budget

| User action | Allowed requests | Max normal calls |
|---|---|---:|
| Open date drawer | existing Phase2A reads + service-dates Query | each 1 |
| Change date draft | none | 0 |
| Preview dates | service-dates Preview | 1 |
| Apply dates | service-dates Apply | 1 |
| receipt re-observe | service-dates Query + summary refresh | each 1 |
| Click reopen | reopen Preview | 1 |
| Apply reopen | reopen Apply | 1 |
| receipt re-observe | summary + selected detail | each 1 |

任何 POST 不得在 render/effect 自動發送；只有明確 user action。

## 10. Acceptance tests

### Backend

- service-date Query/Preview/Apply success typed envelope。
- Preview DB snapshot/fake repository state 完全不變。
- invalid date count/out-of-range/duplicate、blank reason、stale versions/fingerprint typed error。
- same-key same-payload replay 同 receipt；same-key changed-payload conflict。
- order_reopen reason 空字串、純空白、1–500 字、>500 字校驗。
- workflow/route 產生的 validation/conflict/unavailable/internal errors 使用 Global typed error欄位；
  FastAPI pre-route 401/403/422 保留為已凍結的 `BACKEND_GAP`，Client 必須正規化但不得宣稱後端已全域收斂。
- reopen 既有 workflow replay/stale/blocker/rollback regression。

### Frontend client

- exact URL/method/body/headers，case_no 安全 encode。
- token 每次 request 即時讀取；logout/replace token 不重用舊 token。
- strict success/error decode、timeout/network/abort。
- Apply timeout 保留 same idempotency identity；stale 清 preview。

### Components

- 兩組不同 server sentinel 使 DOM 跟著變，證明非 hard-code。
- Preview 前不可 Apply；draft 變更後舊 preview 失效；double-click 只有一 POST。
- Apply receipt 前不顯示成功；receipt 後 re-query 才更新 server-derived facts。
- fast A→B、close/unmount 時舊 Preview 不覆蓋；Apply outcome unknown 不被當取消且可同 key 重試。
- reopen restored assignment/schedule/lock lists 若非空，client fail closed 並標 contract drift。
- 其餘 mutation controls 全 disabled 且 non-GET 總數為 0。

## 11. Browser G6

1. 啟動真 FastAPI 與 Vite，保存本次 PID 並只清理本次 process。
2. 真 `password challenge → TOTP → Session`；禁止 dev token/storage bypass。
3. 使用去敏 disposable/local test case；不得讀 production PII。
4. Service dates：Network Query→Preview→Apply→Query 與 DOM 逐欄比對。
5. Reopen：使用可重開 test case，Network Preview→Apply→summary/detail；若沒有合法 case 標 `BLOCKED_TEST_DATA`，不得修改正式資料造 case。
6. 抽驗四 Drawer/雙 Tab 可見、computed style 與 bounding rect 非 hidden。
7. Network 確認只有核准 GET/POST，無其他 PUT/PATCH/DELETE。
8. 截圖/receipt 去敏，不保存 token/TOTP/完整個資。

若無真登入環境標記為 `BLOCKED_REAL_BROWSER_EVIDENCE`；若無合法測試資料標記為 `BLOCKED_TEST_DATA`。

## 12. Verification commands

```powershell
cd D:\project\Labor_union\ui_react
npm test -- src/tests/orders_mutation_client.test.ts
npm test -- src/tests/orders_mutation_adapter.test.ts
npm test -- src/tests/orders_mutation_flow_store.test.ts
npm test -- src/tests/orders_service_dates_flow.test.tsx
npm test -- src/tests/orders_reopen_flow.test.tsx
npm test -- src/tests/orders_no_fake_mutation.test.ts
npm run lint
npm run build
npm test

cd D:\project\Labor_union
.venv\Scripts\python.exe -m pytest -p no:cacheprovider `
  tests/test_service_date_confirmation.py `
  tests/test_service_date_confirmation_router.py `
  tests/test_order_reopen_workflow.py `
  tests/test_order_reopen_router.py `
  --basetemp .pytest_tmp/react-phase2b-orders -q

rg -n "z\.any|z\.unknown|z\.record|\.passthrough|\.default\(|unknown as|alert\(|confirm\(" `
  ui_react/src/api/orders ui_react/src/adapters/orders ui_react/src/pages/OrdersPage.tsx `
  ui_react/src/tests/orders_*mutation* ui_react/src/tests/orders_*flow*
git diff --check
```

## 13. Anti-fake completion scans

- Production dependency closure 不得 import `mockData.ts`。
- 禁止將舊 mock literals 改名搬到 adapter/fixture 後稱 real data。
- 禁止 `.skip/.todo/.only`、`expect(true)`、snapshot-only、unconditional pass。
- 禁止刪除/隱藏 UI、把所有欄位 unavailable、用 fixture 自創 server 欄位。
- 禁止由 order status 啟用 reopen、由日期 range 計算 service days、由 assignment 推 formal recommendation。
- 禁止測試只 mock client 而不驗 exact transport request 與 live Pydantic provenance。
- 「build 綠」「POST 200」「畫面截圖」「其他 agent 說 passed」均不是完成證據。

## 14. Gate table

| Gate | Pass condition | Failure disposition |
|---|---|---|
| G0 Authority | exact WP 人工核准、dirty baseline 建立、write set 鎖定 | 未核准不得寫 production |
| G1 Contract | 矩陣逐欄比對＋SHA256 freeze receipt | 回 Contract Scout |
| G2 Backend | typed errors (route/workflow)＋reason 非空＋route/workflow tests | 回 Backend writer |
| G3 Client | strict schemas＋exact headers＋idempotency/negative tests | 回 Client writer |
| G4 UI | two flows 狀態機＋outcome_unknown 恢復＋UI preservation＋zero fake controls | 回 UI writer |
| G5 Static | lint/build/full tests/backend regression/scans；記錄開工前與結案即時數字且不得少於基線 | 修正後全部受影響證據重跑 |
| G6 Runtime | 真 Auth/API/DOM/controlled test data | blocked with `BLOCKED_REAL_BROWSER_EVIDENCE` or `BLOCKED_TEST_DATA` |
| G7 Evidence | 6 份 fresh receipts/current counts/write-set audit (Integration Owner) | 不得 completed |

合法共享 status 只有 `proposed | approved | in-progress | blocked | completed | superseded`。

## 15. Blocker codes

`BASE_DRIFT`、`WRITE_SET_VIOLATION`、`PUBLIC_CONTRACT_CHANGE_REQUIRED`、`SHARED_HOTSPOT_REQUIRED`、
`BACKEND_CONTRACT_GAP`、`BLOCKED_AUTH_TWO_STEP_CONTRACT`、`BLOCKED_TEST_DATA`、
`BLOCKED_REAL_BROWSER_EVIDENCE`、`PII_OR_SECRET_EXPOSURE`、`OUTCOME_UNKNOWN_REQUIRES_REPLAY`。

Blocker 只阻擋對應 gate；G6 blocker 不得使 G1–G5 變成 `NOT_RUN`。任何修正 production/test 後，
先前 G5–G7 receipt 立即 stale，必須在 current candidate 重跑。

## 16. DB gate

| Gate | Status | Evidence/reason |
|---|---|---|
| Scope gate | PASS | exact write set 禁止 DDL/schema/migration/seed/backfill |
| Change inventory | NOT_RUN | 無 DB 結構或資料遷移 artifact |
| Static release gate | NOT_RUN | 無 migration release |
| Descriptor gate | NOT_RUN | 無 DB object 變更 |
| Read-only plan gate | NOT_RUN | 非 migration 任務 |
| Engine verification gate | NOT_RUN | 不以 backend tests 冒充 DB gate |
| Developer acceptance gate | NOT_RUN | 不操作既有營運資料；G6 只可使用獲准 disposable/local case |

總結固定為 `DB_CHANGE_NOT_READY`。這表示沒有 DB 結構／migration 授權，不表示兩條 Apply 沒有業務資料寫入。

## 17. Canonical Teamwork launch prompt

```text
你是 D:\project\Labor_union 的 Phase 2B Integration Owner。任務是依：

- document/架構重整/02_決策與退役執行記錄/
  PROV-20260816-react-admin-phase2b-orders-safe-mutations-specification.md
- document/架構重整/02_決策與退役執行記錄/
  PROV-20260816-react-admin-phase2b-orders-safe-mutations-work-package.md

實作 Orders 的兩條安全 mutation：Confirmed Service Dates 與 Controlled Reopen。

【G0 授權門】
1. 未收到使用者逐字核准「核准此 exact Phase 2B Work Package」前，不得修改 production/backend/tests。
2. 收到核准後，由 Integration Owner 唯一更新 spec/WP/README 狀態為 approved/in-progress，再派 writer。
3. 先保存 branch、HEAD、完整 git status --short，以及 exact write-set 的 path/size/SHA256 baseline；
   SHA256 只作檔案完整性證據，不作 task identity 或 owner。
4. 工作區已有大量 dirty/untracked 成果。不得 reset/clean/stash/checkout/整檔覆蓋，不得 stage/commit/push。
5. 本波為 0 DDL/schema/migration/seed/backfill，但兩條 Apply 會寫業務資料；G6 只能操作人工允許的
   disposable/local test case，禁止修改既有營運資料。

【強制拓撲】
Lane A Contract Scout（唯讀）
→ Integration Owner source-readback 並寫 contract-matrix.md、contract-matrix-freeze-receipt.md，輸出
  PHASE2B_CONTRACT_MATRIX_FROZEN
→ Lane B Backend Writer 與 Lane C Frontend Client Writer平行
→ Integration Owner逐檔驗收 G2/G3 handoff
→ Lane D Presentation Writer
→ Lane E Fresh Verification Auditor（唯讀，只回 raw commands/exit codes/counts/findings）
→ Integration Owner親自寫六份 evidence、更新 README/status並判定 G0–G7。

四個 slot 時先只跑 Lane A；G1 freeze 後才平行 B/C；B/C freeze 後才跑 D；最後才跑 E。
Contract Scout與Auditor不得寫檔。Auditor後若再改任何 production/test，所有相關驗收作廢並重跑。

【寫入邊界】
每個 Lane 只能修改本 Work Package 第2節列出的 exact paths。特別注意：
- Backend route test固定為 tests/test_order_reopen_router.py，不得自行創造 receipt欄位或重複測試入口。
- Client 必須包含 order_mutation_errors.ts，strict decode ApiHttpError.rawPayload.detail.error；不得以
  message substring 決定 business state。
- Presentation 必須使用 memory-only order_mutation_flow_store.ts 保存 outcome_unknown draft/key；不得
  使用 Web Storage、URL、cookie、Drawer local state或Client module cache。
- transport.ts、runtime_decoder.ts、Auth、App、Drawer、package/lockfile、Domain、workflow、repository、DB
  都是禁止熱點；確有必要立即回 blocker，不可擴張。

【契約不可猜測】
- Service Query: Authorization。
- Service Preview: Authorization + X-Correlation-ID。
- Service Apply: Authorization + X-Correlation-ID + Idempotency-Key。
- Reopen Preview: Authorization + X-Correlation-ID。
- Reopen Apply: Authorization + X-Correlation-ID + Idempotency-Key。
- Reopen Preview有 order/client_finance/payroll 三版本；Apply body傳三 expected versions；Receipt只有live
  schema現存欄位，禁止新增 client_finance_version、payroll_version、created_at。
- workflow/route錯誤收斂typed error；FastAPI pre-route 401/403/422仍為BACKEND_GAP。若要求全域收斂，
  回 SHARED_HOTSPOT_REQUIRED，不得修改 api/main.py。
- reason必須trim後1–500字，測空字串、純空白、邊界1/500、>500。

【狀態與安全】
只使用 Work Package 第5節 discriminated unions。Apply timeout/503進 outcome_unknown；只允許相同payload
+ 相同 Idempotency-Key重放。不得換key、清draft/preview、顯示成功/失敗或把abort當未提交。Receipt後必須
re-query觀察server facts才進observed。禁止 optimistic success、前端日期/eligibility/lifecycle/finance公式。

只允許 Work Package 第8節六個 stable IDs轉成flow controls；其餘以凍結的完整stable-ID inventory逐項
驗證native disabled、可見且無非核准request。不得用「其餘20個」等固定數字替代清冊，不得刪除、hidden、
zero-size或把整頁改成unavailable冒充合規。

【完成門】
逐門執行 G0–G7。G5測試數字必須由當次raw output取得，不得複製161、170或舊報告。G6必須是真
FastAPI+Vite+password→TOTP→Session+Network↔DOM；禁止dev token/storage bypass。缺登入或合法case時
狀態為blocked，但G1–G5仍須完成。只有G0–G7全部PASS才可completed，禁止VICTORY_CONFIRMED、自報完成、
空browser receipt或引用其他agent說passed。

最終交付必須列：actual changed paths、每條命令/exit code/即時test counts、六份evidence、open findings、
write-set外byte-drift audit、browser blocker或receipt，以及DB gate表。任何未執行項目明列NOT_RUN。
```
