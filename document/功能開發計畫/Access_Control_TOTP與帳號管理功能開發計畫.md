# Access Control：TOTP、帳號管理與內部金鑰退役功能開發計畫

> 狀態：`proposed-awaiting-human-confirmation`  
> 日期：2026-08-10  
> 本文件是後續改善計畫與待辦基線，不授權修改 production code、schema 或 pytest。  
> 必須先整體人工確認本文件的 `Global → Domain → Subsystem → Module` 架構，才可開始實作。

## 1. 目標與業務場景

管理後台目前主要以開發模式運行。正式上線前必須完成：

1. 完整退役 `INTERNAL_API_KEY` 與 `X-Internal-API-Key`；
2. 正式環境的管理員登入必須同時通過帳號、密碼與 Google Authenticator 相容的 TOTP；
3. 新增獨立的帳號管理頁，供授權管理員建立、停用、啟用、調整角色／能力、撤銷 Session、
   發起 TOTP 綁定或重設；
4. 修復並驗收本機「實際登入模式」，使開發者可明確選擇 bypass 或完整驗證帳密＋TOTP；
5. 保留所有安全決策的不可否認稽核、衝突保護與人工復原入口。

「Google Authenticator」在此是使用者端 App；伺服器實作的是 vendor-neutral RFC 6238 TOTP，
不得綁定 Google 帳號或依賴 Google API。相同 QR code 亦可由其他相容 TOTP App 使用。

## 2. 現況證據與已知問題

### 2.1 現況

| 項目 | 現況證據 | 判定 |
|---|---|---|
| 人員與服務認證混合 | `api/dependencies/admin_auth.py` 的 `require_admin` 先依賴 `require_internal_service` | 管理 API 同時要求共用 internal key 與 Bearer Session |
| 登入亦要求 internal key | `api/routes/admin_auth.py` 的 `/login` 依賴 `require_internal_service` | 尚未持有 Session 的登入也被共用 key 擋在外層 |
| UI 全域附加 key | `ui/pages/shared.py`、`ui/api_clients/line_api_client.py` | key 是 UI transport 的隱性必要條件 |
| 開發 bypass | `APP_ENV` 為開發環境且 `ENABLE_ADMIN_AUTH=false` 時跳過人員登入 | 可供本機快速開發，但無法驗證真實登入流程 |
| 帳密與 Session 已存在 | `admin_users`、`admin_sessions`、`authentication_session.py` | 已有 scrypt 密碼與 30 分鐘 idle／8 小時 absolute Session |
| 帳號管理未完成 | 正式規格已有 `admin.user.manage` 等能力，但 UI 只有 `scripts/create_admin.py` 建立入口 | 規格與實作漂移 |
| TOTP 尚不存在 | schema、request model、authentication flow 均無 TOTP seed／challenge／recovery facts | 正式 MFA 缺口 |

### 2.2 測試登入無法正常登入的現況根因

2026-08-10 的只讀檢查顯示：

- `.env` 含 UTF-8 BOM，第一個鍵實際被 `python-dotenv` 解析成 `\ufeffAPP_ENV`，程式讀不到
  正常的 `APP_ENV`；這也違反本專案 strict UTF-8 無 BOM 規範；
- `ENABLE_ADMIN_AUTH=false`，因此在預設 development 判定下，UI 直接進入 bypass，不顯示登入；
- 目前連線的 `union_db_candidate_20260803_v5` 中 `admin_users` 為 0 筆，因此開啟 auth 後任何
  帳密都只能失敗；
- live `admin_sessions` 缺少登入程式固定寫入／讀取的 `absolute_expires_at`，且 live DB 缺少
  `admin_capability_grants`；即使先建立帳號，成功驗密後仍會在建立 Session 或載入 principal 時
  發生 schema error。對應 additive migrations 已存在，但不得未經既定 preserved-data／cutover
  流程直接套用；
- UI transport 對所有 401 固定顯示「登入已失效」，會遮蔽 login route 的帳密錯誤語意；
- 目前登入表單散落於 LINE 管理中心與系統狀態頁，不是全域 Access Control 入口；
- 既有測試主要驗證 password hash、role/capability 與 bypass 環境限制，尚未形成「建立帳號 →
  綁定 TOTP → 登入 → Session → 跨頁」的真實登入閉環。

所以「bypass 可用」不能作為「測試登入可用」的證據。P0 必須先建立可重現的 authenticated
development profile，再分辨帳號資料、schema、API envelope、UI session 或服務連線問題。

## 3. Global → Domain → Subsystem → Module

### 3.1 Global

Global 責任是確保所有管理與業務 API 的 human actor 都來自有效 `AdminPrincipal`，且：

- 正式環境不得使用 auth bypass 或 `INTERNAL_API_KEY`；
- 未登入 public surface 只保留健康檢查、登入、TOTP enrollment challenge 所需的最小入口；
- 每個受保護操作仍由 owning Domain 的 operation capability 作最終授權；
- Streamlit 只保存短效 Session token、呼叫 typed API client、顯示 typed result；
- 所有帳號、MFA、授權變更都撤銷受影響 Session 並留下同交易 security audit；
- TLS、可信反向代理、Secure／HttpOnly／SameSite cookie 或等價的 server-side Session 傳輸方案，
  必須在 production cutover 前確認；TOTP 不可補償明文傳輸。

Global release invariant：正式 profile 中搜尋 runtime source、startup、文件與部署設定，
不得再存在 `INTERNAL_API_KEY`、`X-Internal-API-Key` 或以它作為 human authorization 的 fallback。

### 3.2 Domain：Access Control

#### 責任與 SSOT

Access Control 唯一擁有：

- admin identity、normalized username、display name、enabled state；
- password hash、credential version、credential changed time；
- TOTP factor identity、加密 seed、enrollment／activation／rotation／revocation facts；
- recovery code hash 與 consumed fact；
- role、dynamic capability grant、authorization version；
- hashed Session token、issued／idle expiry／absolute expiry／revoked time；
- login attempt、rate-limit decision與不可變 security decision audit。

衍生值包括 effective capabilities、MFA readiness、Session validity、account list view、最近登入與
風險摘要。UI session state、QR code、目前 TOTP 數字、明碼密碼、明碼 recovery code 都不是 SSOT。

TOTP seed 因驗證時必須可用，不能只做不可逆 hash；必須由獨立於資料庫的 key 做 authenticated
encryption，DB 只保存 ciphertext、key version 與必要 metadata。QR／`otpauth://` URI 只顯示一次，
不得進 log、audit detail、例外或長期 cache。

#### 狀態機

```text
Admin account:
pending_mfa_enrollment → active ↔ disabled
                       → credential_reset_required

TOTP factor:
unbound → enrollment_pending → active → rotated | revoked

Session:
not_issued → active → expired | revoked
```

規則：

- 正式環境只有 `active account + active TOTP` 可以建立 Session；
- 密碼驗證成功但 TOTP 尚未成功時，不得建立可呼叫業務 API 的 Session；
- 同一 TOTP time-step 對同一 factor 只能成功一次；
- disable、password rotation、TOTP reset／rotation、role 或 capability 變更均撤銷既有 Session；
- 停用不刪除帳號；security audit 與歷史 actor identity 必須保留；
- 禁止停用、降權或破壞最後一位可用的 `system_admin`；
- development bypass 只允許明確的 `local_bypass` profile；`local_auth` 必須走完整 MFA，
  production 對任何 bypass 設定 fail closed。

### 3.3 Subsystems

| Subsystem | 責任 | 交易邊界 |
|---|---|---|
| Authentication | 驗證 username、password、TOTP／recovery code、嘗試限制與泛化錯誤 | 成功驗證、TOTP replay marker、Session、login audit 同交易 |
| MFA Enrollment | 建立短效 enrollment challenge、一次顯示 QR、驗證首碼、啟用 factor | factor activation、recovery code hashes、credential version、audit 同交易 |
| Session | issue、load、sliding expiry、absolute expiry、revoke | token hash 與 revoke facts 由 Access Control UoW 管理 |
| Account Administration | create、enable／disable、role、credential、MFA reset | expected version、last-admin guard、Session revoke、event、receipt、audit 同交易 |
| Authorization | role bundle＋dynamic grant 產生 effective capabilities | 只讀 policy；mutation 委派 Account Administration |
| Security Audit／Alert | 安全決策稽核、重複失敗、異常 Session／時鐘／bypass 告警 | Domain audit 隨主交易；診斷告警可由 outbox 非同步投影 |
| UI Access | 全域登入、首次綁定、帳號管理、登出與跨頁 Session | 無業務寫入；只接受 typed API result |

### 3.4 Modules

最小 Module 清單：

- `UsernameNormalizer`
- `PasswordHasher`／`PasswordVerifier`
- `TotpSecretGenerator`
- `TotpSecretCipher`
- `TotpProvisioningUriBuilder`
- `TotpVerifier`
- `TotpReplayGuard`
- `RecoveryCodeGenerator`／`RecoveryCodeVerifier`
- `LoginAttemptPolicy`
- `AdminAuthenticator`
- `EnrollmentChallengeIssuer`
- `SessionTokenIssuer`
- `SessionPolicy`
- `AdminPrincipalLoader`
- `CapabilityPolicy`
- `LastSystemAdminGuard`
- `AccountCommandFingerprint`
- `AccessControlRepository`／`AccessControlUnitOfWork`
- `SecurityAuditAppender`

每個 Module 先以純 input／output、clock／randomness ports 與 typed errors 驗證；不得讓 Router、
Streamlit render function 或 generic Data Browser 承擔上述規則。

## 4. API 與 UI 邊界

### 4.1 建議 API

| 類型 | Operation | 說明 |
|---|---|---|
| Public | `POST /api/v1/admin/auth/login` | 接收 username、password、TOTP；成功後才回 Session |
| Public-limited | `POST /api/v1/admin/auth/enrollment/challenges/{id}/verify` | 僅能完成短效、綁定使用者的首次 MFA challenge |
| Authenticated | `GET /api/v1/admin/auth/me` | 回 typed `AdminPrincipalView` |
| Authenticated | `POST /api/v1/admin/auth/refresh`、`logout` | 沿用 idle／absolute Session policy |
| `admin.user.manage` | admin account query／create／enable／disable／role／credential／MFA reset | Query 與 Command 分離；mutation 要 expected version、reason、idempotency key |
| `admin.session.revoke` | 查詢／撤銷指定帳號 Session | 不回傳原始 token |

Login failure 對外固定回泛化的 `invalid_credentials_or_factor`，不可揭露帳號存在、disabled、
password 正確但 TOTP 錯誤等資訊；內部 audit 保存 privacy-safe reason code。

### 4.2 UI

- 建立全域 Access Control 登入／登出入口，取代頁面各自重複登入；
- 建立獨立 `AccessControlApiClient`，不得把帳號管理 endpoint 加進 `LineAdminApiClient`；
- client 將成功 payload 驗證成 Pydantic view，transport／schema error 轉為 typed client error；
- 帳號管理頁至少提供清單、建立、啟停、角色／能力、撤銷 Session、發起 MFA reset、稽核摘要；
- 管理員不可查看既有 TOTP seed、明碼 recovery code 或 password hash；
- MFA reset、停權、降權等高風險操作必須二次確認並輸入 reason；
- 首次綁定由帳號本人登入短效 enrollment flow 後掃描 QR 並輸入首個 TOTP，不由管理員代持 seed。

## 5. Idempotency、retry、conflict 與 typed errors

### 5.1 Command 規則

- 建立帳號、啟停、角色／能力、password rotation、MFA reset、Session revoke 都使用
  `idempotency_key + canonical command fingerprint + expected_authorization_version`；
- 相同 key＋相同 payload 回原 receipt；相同 key＋不同 payload 回 conflict；
- stale version、last-admin guard、TOTP replay、已失效 enrollment challenge 不自動 retry；
- 只有 deadlock、暫時性 storage unavailable 可使用相同 command identity bounded retry；
- 登入嘗試不是一般業務 command replay；必須受 account＋來源的 rate limit、退避與告警保護。

### 5.2 Typed errors

| Code | HTTP／處理 |
|---|---|
| `invalid_credentials_or_factor` | 401；對外泛化 |
| `authentication_rate_limited` | 429；回 retry-after，不揭露帳號狀態 |
| `mfa_enrollment_required` | 403 或受限 challenge result；不得取得一般 Session |
| `mfa_challenge_expired` | 409；重新發起 enrollment |
| `mfa_factor_replay` | 401；audit／風險計數 |
| `mfa_secret_unavailable` | 503；fail closed、告警 |
| `admin_session_expired` | 401；重新完整登入 |
| `admin_user_disabled` | 對外併入泛化 401；內部 typed audit |
| `insufficient_capability` | 403 |
| `admin_version_conflict` | 409；重新載入 |
| `last_system_admin_protected` | 409 |
| `idempotency_payload_conflict` | 409 |
| `security_audit_persistence_failed` | rollback、503、告警 |

## 6. 安全參數與人工操作入口

- TOTP 採 RFC 6238、30 秒 time-step；預設接受 current step，時鐘漂移容忍最多前後各一格，
  並記錄最後成功 step 防 replay；
- TOTP、password、recovery code 永不寫 log；recovery codes 僅首次顯示，DB 只存 hash；
- 伺服器與資料庫主機需監測時鐘同步；漂移超標時登入 fail closed 並告警；
- repeated login failure、rate-limit burst、disabled account usage、TOTP replay、MFA reset、
  recovery code use、production bypass attempt、最後管理員變更、audit rollback 都需告警；
- MFA 遺失不設隱藏 bypass／萬用碼。由另一位具 `admin.user.manage` 的管理員在帳號管理頁
  發起 reset，填寫原因、撤銷 Session，帳號回到 `pending_mfa_enrollment`；
- 若只剩最後一位 system admin 且 MFA 遺失，使用受控離線維運程序重新建立 enrollment，
  不提供 production HTTP break-glass endpoint。

參考基線：

- [RFC 6238: TOTP](https://datatracker.ietf.org/doc/html/rfc6238)
- [OWASP Multifactor Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Multifactor_Authentication_Cheat_Sheet.html)
- [NIST SP 800-63B](https://pages.nist.gov/800-63-4/sp800-63b.html)

TOTP 可顯著提高帳密被竊後的防護，但不是 phishing-resistant；本期以符合需求的 TOTP 上線，
後續可另案評估 WebAuthn／passkey，不擴大本次範圍。

## 7. 分階段待辦

### P0：重現並修復 authenticated development profile

- [ ] `AC-P0-01` 備份後將 `.env` 轉為 strict UTF-8 無 BOM，不輸出任何 secret；
- [ ] `AC-P0-02` 以明確 profile 取代隱含預設：`local_bypass`、`local_auth`、`production`；
- [ ] `AC-P0-03` 建立安全的本機測試管理員 bootstrap／reset runbook；
- [ ] `AC-P0-04` 依核准 migration／cutover 流程補齊 live candidate schema，不直接 init 或改正式資料；
- [ ] `AC-P0-05` 建立現況登入診斷矩陣：profile、schema version、account state、API status、typed error；
- [ ] `AC-P0-06` 修正 login 與一般 Session 401 的 typed client error mapping，避免錯誤訊息失真；
- [ ] `AC-P0-07` 驗證現有帳密 login endpoint、Session、`/me`、跨頁 token 與 logout；
- [ ] `AC-P0-08` 補 login route＋disposable MySQL contract E2E，不以 hash／bypass 單元測試代替；
- [ ] `AC-P0-09` 補齊啟動時的 auth profile／bypass 醒目訊息，禁止輸出 credential；
- [ ] `AC-P0-10` 產出故障根因與修復 receipt，避免把 bypass 誤認成 authenticated PASS。

### P1：確認架構、風險與資料遷移

- [ ] `AC-P1-01` 人工確認本文件全部架構與下方待確認決策；
- [ ] `AC-P1-02` inventory 所有 internal key caller、route、script、test、README、batch 與部署設定；
- [ ] `AC-P1-03` 區分 human UI、public login、worker／migration 等 machine caller；
- [ ] `AC-P1-04` 定義 MFA tables／columns、encryption key ownership、key version 與 rotation runbook；
- [ ] `AC-P1-05` 定義既有 admin users 的 `mfa_enrollment_required` 遷移與首位 system admin bootstrap；
- [ ] `AC-P1-06` 更新 Access Control 正式規格、schema release／rollback 與 API contracts。

### P2：Module 實作與驗證

- [ ] `AC-P2-01` TOTP secret generation、encryption、provisioning URI、verification、replay guard；
- [ ] `AC-P2-02` recovery code generation、hash、single-use consume；
- [ ] `AC-P2-03` login attempt policy、generic response、rate limit 與 deterministic clock tests；
- [ ] `AC-P2-04` account／factor／session state transition 與 typed error tests；
- [ ] `AC-P2-05` command fingerprint、last-admin guard、idempotency／conflict tests；
- [ ] `AC-P2-06` 新增直接第三方 dependency 時同步 `pyproject.toml`、`uv.lock`，以 `pytest -W error` 驗證。

### P3：Subsystem 與資料層

- [ ] `AC-P3-01` additive schema migration：factor、recovery、attempt／receipt／event 所需 SSOT；
- [ ] `AC-P3-02` Authentication＋MFA Enrollment UoW；
- [ ] `AC-P3-03` Account Administration commands／queries 與 affected-session revoke；
- [ ] `AC-P3-04` security audit、outbox／alert projection；
- [ ] `AC-P3-05` disposable MySQL 驗證 row lock、unique、rollback、replay、stale、partial failure；
- [ ] `AC-P3-06` 保存資料 migration rehearsal，禁止對正式資料或 fixture snapshots 誤操作。

### P4：API 與 typed UI client

- [ ] `AC-P4-01` 擴充 typed auth schemas，login 成功前強制 TOTP；
- [ ] `AC-P4-02` 新增獨立 account administration router；
- [ ] `AC-P4-03` 新增 `AccessControlApiClient` 與 Pydantic views／typed client errors；
- [ ] `AC-P4-04` 建立全域 login／enrollment UI，移除 LINE 與系統狀態頁的重複登入；
- [ ] `AC-P4-05` 建立帳號管理頁與 capability-based visibility；
- [ ] `AC-P4-06` UI 驗證不得有 raw dict 穿透 render function，且 secret／QR 不持久化。

### P5：退役 INTERNAL_API_KEY

- [ ] `AC-P5-01` login route 移除 internal service dependency，改由 rate-limit＋MFA policy 保護；
- [ ] `AC-P5-02` human admin routes 的 `require_admin` 改為純 Bearer Session＋capability；
- [ ] `AC-P5-03` UI shared transport 移除 `X-Internal-API-Key` 與 configured gate；
- [ ] `AC-P5-04` machine callers 逐一改成明確 scoped identity，或以證據確認無需保留；
- [ ] `AC-P5-05` 更新 smoke／E2E／migration rehearsal、startup scripts、README 與部署設定；
- [ ] `AC-P5-06` source／runtime scan 證明 `INTERNAL_API_KEY` 與 header 已無 active caller；
- [ ] `AC-P5-07` 不提供 legacy fallback、雙軌 key＋Session 或 query-string credential。

### P6：Domain／Global 驗收

- [ ] `AC-P6-01` 帳號建立 → 本人綁定 → MFA login → Session → 跨頁 → logout E2E；
- [ ] `AC-P6-02` wrong password／wrong TOTP／replay／expired challenge／rate limit／clock drift；
- [ ] `AC-P6-03` disable、role change、password rotation、MFA reset 後舊 Session 全失效；
- [ ] `AC-P6-04` concurrent last-admin、stale version、same-key replay、different-payload conflict；
- [ ] `AC-P6-05` security audit persistence failure 導致整筆 mutation rollback；
- [ ] `AC-P6-06` production profile 拒絕 bypass、未綁 MFA、未加密 seed 與 legacy internal key；
- [ ] `AC-P6-07` 所有既有管理頁在 Bearer-only transport 下通過 capability 與 thin-UI 驗收。

### P7：上線、觀測與回滾

- [ ] `AC-P7-01` 先部署 additive schema／code，但保持 production cutover 關閉；
- [ ] `AC-P7-02` 對既有管理員完成 MFA enrollment，確認至少兩位可用 system admin；
- [ ] `AC-P7-03` 備份與驗證 TOTP encryption key、DB migration、時鐘同步與稽核告警；
- [ ] `AC-P7-04` 維護窗切換 production profile，執行登入與高權限操作 smoke；
- [ ] `AC-P7-05` 移除 runtime internal key secret，驗證沒有舊 caller；
- [ ] `AC-P7-06` 回滾只允許回前一版程式與 schema 相容路徑；不得以重新啟用共用 key 或 MFA bypass
  作長期回滾。若登入不可用，停止管理寫入、保留 audit，走離線維運程序修復。

## 8. 四層完成證據

| 層級 | 必須證明 |
|---|---|
| Module | TOTP vectors、encryption round-trip／wrong key、single-use step、recovery hash、policy、typed errors |
| Subsystem | enrollment、login、Session、account commands、replay、stale、retry、rollback、partial failure |
| Domain | disposable MySQL 的 schema、FK／unique、row lock、last-admin、session revocation、audit atomicity |
| Global | production fail-closed、Bearer-only 全管理 UI、帳密＋TOTP 跨頁 E2E、internal key 零 active caller |

Mock PASS 不得取代 Domain／Global 的真實 MySQL 與 runtime evidence。測試資料與正式資料庫必須隔離。

## 9. 人工確認決策

本計畫預設並建議一次確認以下決策：

1. `local_bypass` 僅供本機快速開發；另設 `local_auth` 強制走與 production 相同的帳密＋TOTP；
2. 新帳號由 system admin 建立，但 TOTP seed 只在帳號本人的短效 enrollment session 顯示；
3. 每次 enrollment 產生一次性 recovery codes；管理員只能 reset factor，不能查看 seed 或 recovery code；
4. MFA reset、password rotation、disable、role／capability change 全部撤銷既有 Session；
5. 不提供 production HTTP break-glass endpoint，最後管理員復原走受控離線維運程序；
6. 本期採 RFC 6238 TOTP；WebAuthn／passkey 另案，不阻擋本期；
7. `INTERNAL_API_KEY` 完整退役；若 inventory 找到真實 machine caller，必須另建 scoped machine
   identity contract，不得保留同一把全域共用 key。

人工確認後，實作順序固定為 `P0 → P1 → P2/P3 → P4 → P5 → P6 → P7`。只有在寫入範圍互不
重疊且共享契約已確認時，production code 與同層測試才可平行派工。
