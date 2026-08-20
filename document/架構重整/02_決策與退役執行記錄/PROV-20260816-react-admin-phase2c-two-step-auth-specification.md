---
doc_type: implementation-specification
declared_status: approved
identity: PROV-20260816-react-admin-phase2c-two-step-auth
date: 2026-08-16
owner: Access Control / React Integration
domain: Internal Access
subsystem: Authentication / Session
authority: user-approved-採用-2026-08-16
---

# React 管理端 Phase 2C：帳密 Challenge → TOTP → Session 真實接線規格

## 0. 狀態與目的

本規格已由使用者於 2026-08-16 明確回覆「採用」核准。G1–G5 已依最新工作樹完成；G6 已由
使用者在真 Chrome 手動輸入已 enrollment 的帳密與 TOTP 驗證通過。Orders mutation 的本機
測試案件仍屬 Phase 2B 獨立 runtime gate，不影響本 Auth 規格完成狀態。

Phase 2C 不重畫既有 Login UI。唯一目的，是把目前「Stage 1 本機切畫面、Stage 2 呼叫 combined
login」改為後端已存在的真正兩段式流程：

```text
username + password
  → POST /api/v1/admin/auth/login/challenges
  → short-lived single-use challenge (no Session)
  → TOTP six digits
  → POST /api/v1/admin/auth/login/challenges/{challenge_id}/verify
  → bearer Session
```

## 1. 權威與現況證據

- 正式語意：`01_規格基線/17_External_Integration_LINE_Access正式規格.md` 4.2–4.3。
- Backend routes：`api/routes/admin_auth.py` 的 `issue_login_challenge`、
  `verify_login_challenge`。
- Pydantic：`api/schemas/admin_auth.py` 的 `AdminPasswordChallenge*`、
  `AdminFactorVerificationRequest`、`AdminSessionResponse`。
- Domain/subsystem：`subsystems/access/authentication_session.py` 的
  `issue_password_login_challenge`、`complete_password_login_challenge`。
- React live-drift：`ui_react/src/pages/LoginPage.tsx` 的 Stage 1 沒有 API；
  `ui_react/src/api/auth/session_client.ts` 仍呼叫 `/api/v1/admin/auth/login`。

既有 backend 能力不代表 React 已完成。Phase 2C 只接線上述 active typed endpoints，不重新定義
Access 根事實、TOTP 演算法、challenge expiry、rate limit 或 Session 規則。

## 2. Business scenario 與不變量

操作者輸入正確帳密後只能取得短效 challenge，不能取得 Session。只有同一 challenge 搭配有效 TOTP
驗證成功後，React 才可把 bearer token 與 principal 放入既有 memory-only session client，解鎖 Shell。

不變量：

1. Stage 1 success 不得呼叫 `onLoginSuccess`、不得建立 token、不得顯示「登入成功」。
2. Stage 2 request 必須使用 Stage 1 回傳的 `challenge_id` path 與 `challenge_token` body。
3. password、TOTP、challenge token、bearer token 不得進 URL、DOM、console、snapshot、receipt、
   localStorage、sessionStorage 或 cookie。
4. challenge 只存在 task-owned memory；返回 Stage 1、challenge expiry、驗證成功或 component unmount
   時清除。Stage 1 成功後立即從 React state 清除 password。
5. 只有 strict-decoded `AdminSessionResponse` 可建立 session；任何 transport/schema/error 均 fail closed。
6. `mfa_enrollment_required` 只顯示去敏阻擋訊息；不得把 error payload 內 provisioning URI、secret 或
   challenge token render／log。首次 enrollment 另立工作包。
7. 不使用 `/development-session`、舊 combined `/login`、dev token 或 storage shortcut 作驗收。
8. enabled 內部帳號業務功能同權；此波不建立 role/capability 差異 UI。

## 3. Exact HTTP contract

### 3.1 Stage 1 — password challenge

- `POST /api/v1/admin/auth/login/challenges`
- body：`{ username: string[1..100], password: string[1..256] }`
- success：`BaseResponse[AdminPasswordChallengeResponse]`
- data required fields：
  - `challenge_id: string`
  - `challenge_token: string`
  - `expires_at: ISO datetime`
- success 後 Session 必須仍為空。

### 3.2 Stage 2 — TOTP verification

- `POST /api/v1/admin/auth/login/challenges/{encoded challenge_id}/verify`
- body：`{ challenge_token: string[32..256], factor_code: string[6..32] }`
- 本 UI 只送 6 位 ASCII digit TOTP；recovery code UI 不在本波。
- success：`BaseResponse[AdminSessionResponse]`
- required：`access_token`、`token_type`、`expires_at`、strict `admin` view。

### 3.3 Error matrix

| Operation | Status/code | UI disposition |
|---|---|---|
| Stage 1 | 401 `invalid_credentials_or_factor` | 泛化錯誤，不透露帳號/MFA狀態 |
| Stage 1/2 | 429 `login_rate_limited` | 顯示稍後重試；保留非敏感 username，清 password/TOTP |
| Stage 1 | 403 `mfa_enrollment_required` | fail closed；不顯示 raw challenge/provisioning URI |
| Stage 2 | 401 `invalid_credentials_or_factor` | 清 TOTP；challenge仍未過期時可重新輸入 |
| Stage 1/2 | 503 `admin_auth_unavailable` | 顯示暫時不可用；不建立 session |
| any | schema mismatch/network/timeout | typed error；不建立 session、不宣稱完成 |

FastAPI pre-route error envelope 仍可能是 raw `detail`; Client 必須 bounded decode，不能修改 shared
transport 或以 message substring 推狀態。

## 4. Frontend state machine

```text
password_entry
  → challenge_pending
  → totp_entry
  → verify_pending
  → authenticated

challenge_pending → password_error | enrollment_required | unavailable
totp_entry → password_entry (explicit back; clear challenge/password/TOTP)
verify_pending → totp_error | rate_limited | challenge_expired | unavailable
challenge_expired → password_entry (must obtain a new challenge)
```

使用 discriminated union 或單一 stage + typed context，不使用互相矛盾 boolean。Stage 1／2 pending 時
所有相應 submit/input 原生 disabled，double-click 只能送一次。Stale response 必須以 generation guard
丟棄，上一個 challenge 的 response 不得覆蓋新的登入嘗試。

## 5. UI preservation

- 保留既有 Login card、帳號／密碼欄、顯示密碼、忘記密碼訊息、六格 TOTP 與返回按鈕。
- Stage 1 submit 文案可顯示「驗證帳密中」；Stage 1 API success 才切換 TOTP 畫面。
- Stage 2 成功才進 Shell；錯誤留在對應 stage。
- 不新增 Badge、Dashboard 或重新設計；只加入 loading、typed error、challenge expiry 與安全提示。

## 6. Session 與 restore 邊界

- 本波沿用 memory-only bearer session；每次 API request 即時取得 current token。
- F5/new-tab 仍會失去 memory session，屬獨立 restore/cookie 決策，不得以 localStorage 修補。
- `/me`、refresh、logout 保留現行行為；本波只在契約對齊需要時修改其 strict decoder/tests。
- Phase 2C 通過後，只能解除 `BLOCKED_AUTH_TWO_STEP_CONTRACT`；Phase 2A/2B 的 runtime gate 仍須
  以真瀏覽器與合法測試資料重跑，不能引用 component test 自動改成 completed。

## 7. Out of scope

- Backend、DB/schema/migration/seed/backfill。
- TOTP enrollment、QR、recovery codes 顯示與下載。
- Account Center 建立/停權/MFA reset/session revoke。
- HttpOnly cookie、CSRF、F5/new-tab restore。
- Production target/cutover、keyring、時鐘、雙人 enrollment、external security alert。
- Orders 或其他業務頁 mutation。

## 8. Completion definition

只有 strict client、真 Stage 1 request、真 Stage 2 verify、memory secret hygiene、negative tests、Shell
guard integration、lint/build/full frontend tests、focused backend tests、真 FastAPI+Vite browser
Network↔DOM 全部通過才可 completed。

缺已 enrollment 的合法本機帳號/TOTP 時標 `BLOCKED_AUTH_TEST_CREDENTIAL`；缺 browser evidence 時標
`BLOCKED_REAL_BROWSER_EVIDENCE`。兩者不得阻擋 contract/client/component gates，也不得使用 dev endpoint
繞過。

## 9. DB gate

| Gate | Status | Reason |
|---|---|---|
| Scope gate | PASS | 本規格明確 0 DB/schema write |
| Change inventory | NOT_RUN | 無 DB change |
| Static release gate | NOT_RUN | 無 migration release |
| Descriptor gate | NOT_RUN | 無 DB object |
| Read-only plan gate | NOT_RUN | 非 migration 任務 |
| Engine verification gate | NOT_RUN | 不把既有 TOTP DB evidence重跑成UI gate |
| Developer acceptance gate | NOT_RUN | 不操作既有營運資料 |

總結：`DB_CHANGE_NOT_READY`（本波不應有 DB 變更）。
