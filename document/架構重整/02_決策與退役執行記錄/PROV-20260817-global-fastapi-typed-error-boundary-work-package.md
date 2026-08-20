---
doc_type: work-package
declared_status: completed
identity: PROV-20260817-global-fastapi-typed-error-boundary
date: 2026-08-17
owner: Global / API Boundary Integration Owner
domain: Global
source_gap: PROV-20260817-global-fastapi-typed-error-boundary-gap
prerequisites: PROV-20260817-react-admin-phase3-scenario-lineage-governance completed with PHASE3_SCENARIO_LINEAGE_METADATA_READY
activation_blocker: none; PROV-20260817-global-fastapi-typed-error-boundary-correlation-precedence-amendment completed
approval_required: 核准此 exact Global FastAPI Typed Error Boundary Work Package
scenario_governance: Part_00_全域測試資料治理與Scenario契約.md
ui_execution_mode: not-applicable
base_branch: main
base_head: 8615225481c8f72a9629289285516189b270cb36
dirty_baseline: integration-owner-must-capture-before-writer
base_drift_rule: any relevant path drift requires fresh read and re-freeze before edits
---

# Global FastAPI typed error boundary 工作包

## 0. Scope

Controlled contract input固定來自`validation/scenarios/global_fastapi_typed_error_boundary.json`與其
expected lineage；缺少時固定`PHASE3_SCENARIO_LINEAGE_NOT_READY`。

建立單一 FastAPI transport boundary，把 request validation、auth/authz、route 已知錯誤與未預期
錯誤統一為正式 Global typed error envelope，並收斂既有 React shared transport 對 nested
`detail.error` 的解碼。本包不改 Domain 規則、狀態機、DB 或 provider side effect；React 只允許
修改 shared transport 的錯誤解碼與既有兩段式登入相容測試，不改 Auth state machine、Session 儲存政策或頁面設計。

本包只統一管理端 JSON namespaces：`/api/v1/**`與`/internal/v1/**`。LINE provider webhook、LIFF／
gateway 與 legacy public surfaces（含`/webhook*`、`/liff-page`、`/gateway`、`/bind-page`、
`/register-page`、`/api/line/**`、`/api/config/**`及root landing）維持原 transport/protocol，
不得被此 boundary 改寫；若其契約也需統一，必須另立 provider/public-interface Work Package。

## 1. Exact production write set

- `api/main.py`
- `api/exception_handlers/__init__.py`
- `api/exception_handlers/typed_errors.py`（new）
- `api/schemas/errors.py`（new）
- `api/schemas/admin_auth.py`（只把`AdminPasswordChallengeRequest`收緊為`extra="forbid"`；不得改其他Auth payload）
- `ui_react/src/api/shared/transport.ts`（shared hot spot；只加入strict `detail.error` decode與header相容）

相容性只讀來源：`shared_kernel/errors.py`、`api/error_contracts.py`、
`api/dependencies/admin_auth.py`、`api/dependencies/internal_service_auth.py`、
`ui_react/src/api/shared/typed_errors.ts`。不得為方便而修改
這些模組；若 handler 無法在不改它們的情況下完成，回 `SCOPE_EXPANSION_REQUIRED`。

`shared_kernel/errors.py` 為既有 Domain-neutral contract，本包預設只讀；若必須修改，固定停工並回
`GLOBAL_ERROR_CONTRACT_EXPANSION_REQUIRED`。

## 2. Exact test / integration write set

- `tests/test_global_typed_error_boundary.py`（new）
- `tests/test_admin_auth_security.py`
- `tests/test_admin_auth_runtime.py`
- `ui_react/src/tests/transport.test.ts`
- `ui_react/src/tests/LoginPage.test.tsx`
- `ui_react/src/tests/session_client_two_step_auth.test.ts`
- `document/架構重整/01_規格基線/00_Global_共同契約.md`（Integration Owner only）
- `document/架構重整/01_規格基線/15_正式規格索引與裁決總表.md`（Integration Owner only）
- `document/架構重整/03_追蹤清單與證據/evidence/PROV-20260817-global-fastapi-typed-error-boundary/`（new）

## 3. Frozen public contract

1. HTTP JSON wrapper 固定保留現行 `{"detail":{"error":{...}}}`；本包不得改成
   top-level `error`、`BaseResponse.error` 或其他形狀。Envelope exact fields：`category`, `code`,
   `message`, `field_errors`, `domain_blockers`,
   `retryable`, `correlation_id`, `current_version`；response 與 nested fields 禁止 extra keys。
2. `RequestValidationError` 產生 deterministic field paths/codes；不回傳 Python exception、request body、
   secret、token 或 PII。
3. Stable status mapping：400/405/422 → `validation`；401/403 → `forbidden`；404/410 →
   `not_found`；409 →保留已 typed category，否則 `conflict`；429/502/503/504 →
   `unavailable` 且依明確 server hint 裁決 retryable；500 → `internal`。不以文字片段
   猜測 Domain semantics。
4. 已是 Global typed error 的 `detail.error` payload 必須無損保留；legacy `detail.code` /
   `detail.error` /
   string 只能由明確 allowlist adapter 統一。
5. unexpected exception 固定為 redacted internal error，log 也不得包含 request body/secret/PII。
6. canonical request/response header固定為`X-Correlation-ID`。合法值必須完整符合
   `^[A-Za-z0-9][A-Za-z0-9._:-]{0,190}$`；leading/trailing whitespace直接視為非法，不得trim後接受。
   合法值原樣回傳；缺少時server產生`uuid4().hex`。blank、超長或非法字元不得回顯，server改產生
   安全ID並回422 validation error；response header與envelope correlation id必須一致。
7. boundary 不 commit、不建 outbox/job、不執行 provider call。
8. 保留原 HTTP status 與 `Retry-After`、`WWW-Authenticate` 等 headers；已 typed payload 只能
   unwrap/rewrap 一次，禁止 `detail.error.error` 或 `detail.detail`。
9. Legacy allowlist 必須是 handler 擁有的明確 constant/table，列出可接受的 shape/code。
   未登錄 dict/string 只能根據 status 轉成固定去敏 transport code/message，不得
   `str(exc)` 穿透。
10. Validation field path 固定為 `body.<field>` / `query.<field>` / `path.<field>` /
    `header.<lowercase-name>`；code 來自正規化 Pydantic error type，禁止收錄 `input`、`ctx`、
    body value 或 credential。
11. handler 必須明確註冊並分流 Starlette `HTTPException`、FastAPI `HTTPException`、
    `RequestValidationError`、`ResponseValidationError`與未預期`Exception`；response validation固定為
    500/internal。FastAPI dependency本身的exception shape不修改，由boundary在runtime轉換。
12. `api/schemas/errors.py`使用strict Pydantic model（`extra="forbid"`及適用的Strict primitive）；
    `field_errors`、`domain_blockers`必須存在，只有`current_version`可nullable。
13. React `transport.ts`使用strict Zod object解碼完整`raw.detail.error`。只有完整fixed envelope通過時，
    才以其`code`、`message`、`retryable`建立`ApiHttpError`；schema mismatch保留`ApiHttpError.raw`並退回
    HTTP status fallback。禁止`z.any()`、`z.unknown()`、`z.record()`、`.passthrough()`或unsafe cast吞掉drift。
14. CORS只對核准管理端origins expose `X-Correlation-ID`、`Retry-After`、`WWW-Authenticate`；不得新增
    wildcard origin/method/header policy。React若不需要讀某header，仍不得從body杜撰其值。

## 4. Acceptance / anti-lazy gates

- TestClient 真實觸發 body/path/query/header validation，不只直接呼叫 handler。
- 每類錯誤都測 missing/wrong/extra/null/redaction/correlation；extra 必須使用已經
  `extra="forbid"` 的真`AdminPasswordChallengeRequest` route，不得偽造一個只有 test 看得到的 endpoint。
- 另有 regression 證明已 typed route error 不被 double-wrap。
- React transport regression 必須證明 canonical `ApiHttpError.raw`中的`detail.error`原樣保留，
  nested strict envelope的code/message/retryable會傳到`ApiHttpError`，Login/TOTP可分辨
  `challenge_expired`、`login_rate_limited`等server code；malformed nested envelope必須退回HTTP status，
  不得因transport只產生人類訊息就宣稱相容。
- 禁止 catch-all 後回 HTTP 200；禁止在 tests 以自製 handler fixture 代替 FastAPI runtime。
- 任一 route 需要新 Domain error code 時，回原 Domain WP，不在 Global boundary 發明。

### 4.1 Exact TestClient matrix

- A Success：`/health` 的 `BaseResponse` bytes/fields 相容；2xx/304 不經 error handler。
- B Validation：真 body/query/path/header missing/wrong/null/extra/range；422 exact wrapper/fields/sort/redaction。
- C Correlation：valid preserved，missing generated，invalid not reflected，header=envelope。
- D Auth：missing/expired bearer 401，disabled/forbidden 403，session store/internal auth unavailable 503。
- E Rate limit：真 admin challenge 429 保留429、typed/retryable，不洩露 challenge/credential。
- F Typed regression：至少一個409與一個503+`Retry-After`，payload 無損且無double-wrap。
- G Legacy：allowlisted `detail.code` / `detail.error` / string；unknown dict/string 去敏，
  `table`/`replacement`/`attempt`/provisioning URI 不穿透。
- H Framework：unknown route 404、method 405，headers 保留。
- I Unexpected/response validation：TestClient `raise_server_exceptions=False`；500/internal，回應與
  captured logs 的 injected secret 均不存在。
- J Schema：missing/wrong/extra/null 建模失敗；category enum strict，arrays required，僅
  `current_version` nullable。
- K Compatibility：現有 assert `response.json()["detail"]["error"]` 的 focused routes、Auth、React
  transport/bounded decoder 一併回歸。

### 4.2 Contract-first freeze與互斥施工

Integration Owner在production writer啟動前，必須先在本包evidence目錄凍結
`contract-matrix.md`，列出：namespace applicability、exception class×status mapping、固定wrapper、
correlation grammar、可保留headers，以及handler-owned `LEGACY_ERROR_ALLOWLIST` 的exact shape/code。
writer不得自行從錯誤訊息猜allowlist；未知code固定走status-based redacted fallback。

`api/main.py`、`ui_react/src/api/shared/transport.ts`、`api/schemas/admin_auth.py`都是shared hot spots，
本包由唯一Primary／Integration Writer串行修改；執行期間不得與Auth、Phase5/6 runtime、其他shared
transport writer平行。任何base drift先停止、fresh-read並重新凍結matrix。

## 5. Required commands

```powershell
.\.venv\Scripts\python.exe -m pytest -p no:cacheprovider `
  --basetemp .pytest_tmp\global-fastapi-typed-error-boundary -q `
  tests\test_global_typed_error_boundary.py `
  tests\test_admin_auth_security.py `
  tests\test_admin_auth_runtime.py

Set-Location ui_react
npx vitest run src/tests/transport.test.ts src/tests/LoginPage.test.tsx `
  src/tests/session_client_two_step_auth.test.ts
npm test
npm run lint
npm run build
```

另須strict UTF-8/BOM、scoped `git diff --check`、secret/PII、forbidden Zod/unsafe-cast、exact write-set
及provider namespace相容掃描。測試綠燈不能取代對真FastAPI exception runtime與兩段式登入錯誤碼的驗證。

## 6. DB gate

Scope / Change inventory `PASS`（0 DB change）；其餘 `NOT_RUN`；結論 `DB_CHANGE_NOT_READY`。

## 7. Activation result（2026-08-17）

Phase 3 Scenario Lineage已達`PHASE3_SCENARIO_LINEAGE_METADATA_READY`；Correlation Precedence Amendment
亦於2026-08-17取得exact核准並採response-only rebase。Luna MAX backend/frontend lanes完成implementation，
Integration Owner fresh重跑backend 72 tests、frontend focused 69 tests、full React 43 files／517 tests、build
均PASS。Lint exit 0但保留MasterLayout既有2 warnings；Vite保留既有bundle-size advisory。Global boundary
本身標為`completed`；依逐頁精簡遷移裁決，它不再被解讀為所有既有typed GET頁面的總前置。
