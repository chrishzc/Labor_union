---
doc_type: work-package
declared_status: completed
identity: PROV-20260816-react-admin-phase2c-two-step-auth
date: 2026-08-16
owner: Integration Owner
domain: Internal Access
subsystem: Authentication / Session / React presentation
specification: PROV-20260816-react-admin-phase2c-two-step-auth-specification
approval_required: human-must-reply-核准此exact-Phase2C-Work-Package
approval_evidence: user-replied-採用-2026-08-16
blockers: []
---

# React 管理端 Phase 2C：兩段式 TOTP Auth 真實接線工作包（防偷懶版）

## 0. Activation gate

使用者已於 2026-08-16 明確回覆「採用」，production/tests 的核准條件已滿足。G1–G5 已在最新
工作樹完成；使用者其後於真 Chrome 手動輸入合法帳密與即時 TOTP，後端 challenge 與 verify
皆回 200，React 解鎖 Shell 並載入 50 筆真實訂單。因此 G6 已通過，本工作包狀態為 `completed`。

開工前 Integration Owner 必須保存 current branch、HEAD、`git status --short`、exact write-set path／size，
以及所有 dirty/untracked collision。禁止 checkout/reset/clean/stash、禁止以歷史 base 覆蓋 current candidate。

## 1. Goal 與成功邊界

把已設計完成的 Login UI 接上現有兩個 backend endpoints，不重畫：

1. Stage 1 真正呼叫 password challenge endpoint。
2. Stage 2 使用該 challenge 驗 TOTP，成功才建立 memory Session。
3. 用真 FastAPI+Vite browser flow 對 Phase 2A/2B auth prerequisite 提供新 evidence。

Phase 2C 不保證 Phase 2A/2B 自動完成；Orders 合法 mutation test data 仍是獨立 blocker。

## 2. Contract-first gate (G1)

任何 Writer 開工前，Contract Scout 唯讀產出並由 Integration Owner 凍結：

| surface_field_id | endpoint | method | request JSON path | response JSON path | Pydantic source | required/nullable | secret handling | disposition |
|---|---|---|---|---|---|---|---|---|

至少涵蓋 username、password、challenge_id、challenge_token、expires_at、factor_code、access_token、
token_type、session expires_at、AdminPublic 全欄與 error code。每欄只能是
`READY_TYPED | BACKEND_GAP | INTERNAL_SECRET | DISPLAY`。

凍結前 Writer 不得自行挑 endpoint、複製測試 fixture 當 contract 或沿用 combined `/login`。

## 3. Exact write set

### Lane B — Auth Client Writer

- `ui_react/src/api/auth/session_client.ts`
- `ui_react/src/api/auth/two_step_auth_schemas.ts`（new）
- `ui_react/src/api/auth/two_step_auth_errors.ts`（new；只有證據證明需要時）
- `ui_react/src/tests/session_client_two_step_auth.test.ts`（new）
- `ui_react/src/tests/fixtures/auth/two_step_auth_contract_fixtures.ts`（new）

不得修改 `transport.ts`、`runtime_decoder.ts`、package/lockfile 或 backend。

### Lane C — Login Presentation Writer

- `ui_react/src/pages/LoginPage.tsx`
- `ui_react/src/pages/LoginPage.css`
- `ui_react/src/tests/LoginPage.test.tsx`

不得修改 Auth client、App、MasterLayout 或其他頁面。

### Lane D — Shell Integration Writer（在 B/C freeze 後）

- `ui_react/src/App.tsx`（僅若 Session handoff/guard 必要）
- `ui_react/src/tests/route_guard.test.tsx`
- `ui_react/src/tests/challenger_auth_navigation.test.tsx`

若 App 不需修改，必須明記 `NO_CHANGE_REQUIRED`，不得為了顯示有工作而重構。

### Integration Owner only — shared docs/evidence

- 本 specification、work package 與 `02_決策與退役執行記錄/README.md`
- `03_追蹤清單與證據/evidence/PROV-20260816-react-admin-phase2c-two-step-auth/`
- Phase 2A/2B browser receipts：只有真 browser evidence 通過後才能更新。

### Prohibited

- `api/**`、`subsystems/**`、`domains/**`、`db/**`、`scripts/**`
- AccountManagementPage、Orders pages、其餘頁面
- package.json、package-lock.json、shared transport/decoder
- localStorage/sessionStorage/cookie/URL persistence

任何需要 prohibited path 才能完成的情況，停止並回報 `SHARED_OR_BACKEND_SCOPE_REQUIRED`，不得越界。

## 4. Multi-agent topology 與順序

```text
Contract Scout (read-only)
  → Integration freeze matrix
  → Lane B Client Writer || Lane C Presentation Writer
  → Integration interface review
  → Lane D Shell Integration
  → Fresh Verification Auditor (read-only)
  → Integration Owner writes receipts/status
```

Lane B/C 可在 matrix freeze 後平行，但不得互改。Lane D 必須等 B/C API freeze。Auditor 不寫任何檔案，
只回傳 exact commands、exit code、raw counts、warnings 與 findings。所有 receipts 由 Integration Owner
親自重跑／讀 diff 後撰寫。

## 5. Required implementation contract

### 5.1 Client API

必須提供語意明確的方法（名稱可依既有風格，但不得合併）：

- `issuePasswordChallenge({username,password})`
- `verifyPasswordChallenge({challengeId,challengeToken,factorCode})`
- `getToken/getCurrentUser/setSession/clearSession`
- 既有 `fetchCurrentUser/refreshToken/logout`

禁止 production 呼叫：

- `/api/v1/admin/auth/login`
- `/api/v1/admin/auth/development-session`

Client 每次 verify success 才設定 token/user。Stage 1、Stage 2 error、schema mismatch、timeout 都不得留下
半套 Session。

### 5.2 Strict Zod

- `.strict()` 驗 envelope data 與 nested objects。
- Server required key 必須 required；nullable 不等於 optional。
- 禁止 `.default()`、`.catch()`、`.passthrough()`、`z.any`、`z.unknown`、`z.record`、`.coerce`、
  `.preprocess`、`.transform`、`as any`、`unknown as`。
- date-time 至少驗證合法 ISO datetime；factor code UI 驗 6 位 ASCII digits。
- 每個 DTO 必測 missing required、wrong type、extra nested/envelope、null violation、invalid datetime。

### 5.3 Secret hygiene

- password 只存在 Stage 1 request 所需時間；challenge success 後清除。
- challenge token memory-only；返回/過期/成功/unmount 清除。
- TOTP verify 完成或錯誤後清除輸入；不得進 error text。
- bearer 只進 Authorization header 與 memory session。
- 測試 fixture 使用明顯假值，不使用真 credential/TOTP/secret。

### 5.4 Login state machine

Stage 1 submit 必須等 API success 才進 TOTP；不得再用 local non-empty validation直接換頁。Stage 2 只送
challenge + factor code，不重送 username/password。pending 時原生 disabled；back action 清 challenge與輸入，
再次前進必須重新 issue challenge。

## 6. Required tests (不得少做)

### Client contract tests

1. Stage 1 exact URL/method/body，且不帶 Authorization。
2. Stage 1 success不建立 Session。
3. Stage 2 path 使用 `encodeURIComponent(challenge_id)`，body只有 token+factor code。
4. Stage 2 success strict decode後才建立 Session。
5. 401/403/429/503、network、timeout、schema mismatch均不建立 Session。
6. `mfa_enrollment_required` raw payload 不進 DOM/log/client public error fields。
7. 靜態/spy 證明 0 combined-login、0 dev-session、0 Web Storage/cookie/URL。
8. token切換/clear後所有 protected request即時使用最新記憶體 token，不快取舊 token。

### Login component tests

1. Stage 1 local validation後發 request；request pending不切頁且 inputs/submit disabled。
2. Challenge success才呈現既有六格TOTP。
3. Stage 1 failure停留Stage 1，password清除，不洩漏帳號/MFA狀態。
4. Stage 2不足六位不發 request；六位才 verify。
5. verify pending 防 double-submit。
6. verify success才呼叫 `onLoginSuccess` 一次。
7. invalid factor清TOTP但不建立session；expired challenge退回Stage1並清challenge。
8. back清除challenge/password/TOTP；舊response不得覆蓋新attempt。
9. enrollment-required只顯示去敏阻擋訊息，不 render URI/token/secret。

### Shell tests

1. Stage 1 success仍不可見 MasterLayout。
2. Stage 2 success才解鎖 Shell。
3. logout清 memory並回 Login。
4. Hash/deep-link在未認證狀態仍被 guard。

禁止 `.skip/.todo/.only`、snapshot-only、`expect(true)`、零 assertion、以自創 client response欄位冒充
Pydantic contract。

## 7. Browser G6

必須使用真 FastAPI + Vite + 已 enrollment 的合法本機帳號：

1. Network證明先 `/login/challenges`，再 `/login/challenges/{id}/verify`。
2. Stage 1 response 沒有 access token；DOM仍停在登入流程。
3. Stage 2成功才出現 Session與Shell；Network Authorization只在後續 protected request。
4. wrong TOTP不建立 Session；rate-limit/expired challenge依typed UI顯示。
5. 跨 Orders/System Status 頁面使用同一 bearer；logout後 protected request不可再用舊token。
6. 截圖/receipt全面去敏，不保存 password、TOTP、challenge token、bearer、provisioning URI。

沒有人工提供合法 credential/TOTP 時，G6 標 `BLOCKED_AUTH_TEST_CREDENTIAL`，但 G1–G5 必須完成。
不可用 dev endpoint、固定TOTP、直接setSession或測試注入token充數。

## 8. G0–G7 gates

| Gate | Pass condition | Lazy-model failure |
|---|---|---|
| G0 Authority | exact approval、dirty baseline、write set freeze | 未核准/越界即 fail |
| G1 Contract | field/error/secret matrix與freeze receipt | chat摘要或writer fixture不算 |
| G2 Client | 兩個分離client、strict decode、secret hygiene | combined login即 fail |
| G3 UI | Stage1真request、Stage2 verify、UI preserved | local stage switch即 fail |
| G4 Integration | Session/guard/logout與stale response tests | 直接setSession假整合即 fail |
| G5 Static | lint/build/full Vitest/focused backend/UTF-8/diff/scans | warnings/skips必揭露 |
| G6 Runtime | 真FastAPI+Vite+TOTP Network↔DOM | mock/dev token不算 |
| G7 Evidence | current candidate receipts、open findings、status/index | 舊數字/他代理宣稱不算 |

G6 blocker 不得成為 G1–G5 不施工的理由。只有 G0–G7 全 PASS 才可 completed；否則最高狀態是
`implemented-local-validated` 或帶明確 blocker 的 `blocked`，禁止 `VICTORY_CONFIRMED`。

## 9. Required commands

```powershell
cd D:\project\Labor_union\ui_react
npm run lint
npm run build
npm test
```

```powershell
cd D:\project\Labor_union
.\.venv\Scripts\python.exe -m pytest -p no:cacheprovider `
  tests/test_admin_auth_runtime.py tests/test_admin_auth_security.py `
  tests/test_access_totp.py --basetemp .pytest_tmp/react-phase2c-auth -q
git diff --check
```

另做 strict UTF-8、secret、forbidden endpoint/storage、test skip與write-set closure掃描。命令必由 Auditor 在
current candidate重跑，不可複製舊報告數字。

## 10. Required evidence

落點：
`document/架構重整/03_追蹤清單與證據/evidence/PROV-20260816-react-admin-phase2c-two-step-auth/`

1. `contract-matrix.md`
2. `contract-matrix-freeze-receipt.md`
3. `candidate-change-inventory.md`
4. `verification-receipt.md`
5. `browser-smoke-receipt.md`
6. `open-findings.md`

## 11. Teamwork Project Prompt（取得核准後原文交付）

```text
你是 Phase 2C Integration Owner。先完整讀 AGENTS.md、Phase 2C specification/work-package、
Global contract 與 Access 正式規格。禁止 DDH。先唯讀建立 current dirty baseline，再由 Contract Scout
凍結 password challenge→TOTP verify→Session 逐欄矩陣；矩陣未freeze前不得寫production。

依 Work Package exact lanes 分工。不得重畫 Login UI、不得修改backend/DB/shared transport/package、
不得呼叫combined /login或development-session、不得用storage/dev token/direct setSession繞過。
Stage1成功只取得memory challenge且清password；Stage2成功strict decode後才建立memory bearer session。
所有secret不得進URL/DOM/log/receipt。缺browser credential只能阻擋G6，不能省略G1–G5。

每個writer只改自己的exact write set，不commit。Verifier唯讀回傳raw commands/counts/warnings；
Integration Owner親自核對diff後才寫6份evidence與status。任何schema mismatch、scope need、base drift或
shared hotspot需求立即fail closed，不得自行擴張。禁止自報VICTORY；只有G0–G7全PASS才completed。
```

## 12. DB gate

| Gate | Status | Evidence |
|---|---|---|
| Scope gate | PASS | exact write set排除所有DB/schema path |
| Change inventory | NOT_RUN | 無DB change |
| Static release gate | NOT_RUN | 無migration |
| Descriptor gate | NOT_RUN | 無DB object |
| Read-only plan gate | NOT_RUN | 非migration |
| Engine verification gate | NOT_RUN | 不操作DB |
| Developer acceptance gate | NOT_RUN | 不操作既有資料 |

總結：`DB_CHANGE_NOT_READY`。
