---
doc_type: work-package
declared_status: completed-local-validated
date: 2026-08-16
owner: Access Control / Global Security
domain: Internal Access
subsystem: Authentication, MFA, account administration and legacy-key retirement
implementation_authorization: user-authorized-2026-08-16
---

# Access Control：TOTP、帳號管理與內部金鑰退役工作包

> 狀態：`completed-local-validated`（2026-08-16 closeout）；production deployment、external alert sink 與
> target-specific 驗收均為 `NOT_RUN`，已移交後續 Work Package，不得解讀為已上線。
> 日期：2026-08-16
> 使用者已於 2026-08-16 指示開始完成落地，並確認唯一 root 僅額外可管理帳號中心；所有 enabled
> 帳號（含 root）具相同完整業務權限。實作仍須依本文件的 `Global → Domain → Subsystem → Module`
> 架構、write set 與驗收門檻進行。

## 1. 目標與業務場景

管理後台目前主要以開發模式運行。正式上線前必須完成：

1. 完整退役 human authorization 對 `LEGACY_SHARED_KEY` 與 `X-Legacy-Shared-Key` 的依賴；machine caller
   身份驗證另依既有 private-operations contract 管理；
2. 正式環境的管理員登入必須同時通過帳號、密碼與 Google Authenticator 相容的 TOTP；
3. 新增獨立的帳號管理頁，僅供唯一 root 帳號建立、停用、啟用、重設 credential／MFA、撤銷 Session、
   發起 TOTP 綁定或重設；
4. 修復並驗收本機「實際登入模式」，使開發者可明確選擇 bypass 或完整驗證帳密＋TOTP；
5. 保留所有安全決策的不可否認稽核、衝突保護與人工復原入口；
6. 在非開發模式（`ENABLE_ADMIN_AUTH=true`）下，系統載入時若未持有有效 Session，必須強制直接顯示全域登入畫面，未通過身份驗證前阻斷所有背景業務頁面與功能操作。

「Google Authenticator」在此是使用者端 App；伺服器實作的是 vendor-neutral RFC 6238 TOTP，
不得綁定 Google 帳號或依賴 Google API。相同 QR code 亦可由其他相容 TOTP App 使用。

## 2. 現況證據與已知問題

### 2.1 現況

| 項目 | 現況證據 | 判定 |
|---|---|---|
| human 與 service 認證已分離 | `api/dependencies/admin_auth.py` 的 `require_admin` | human route 已是 Bearer Session；不得重新引入 internal key |
| public login 已不依賴 internal key | `api/routes/admin_auth.py` 的 `/login` | 仍缺 TOTP、rate limit 與泛化 failure policy |
| UI 不再附加 legacy key | `ui/pages/shared.py`、`ui/api_clients/line_api_client.py` | human transport 已是 Bearer-only；需移除過時註解與測試／文件殘留 |
| 開發 bypass | `APP_ENV` 為開發環境且 `ENABLE_ADMIN_AUTH=false` 時跳過人員登入 | 可供本機快速開發，但無法驗證真實登入流程 |
| 帳密與 Session 已存在 | `admin_users`、`admin_sessions`、`authentication_session.py` | 已有 scrypt 密碼與 30 分鐘 idle／8 小時 absolute Session |
| 帳號管理未完成 | 這是開工時快照；root-only 帳號中心、typed API 與 thin UI 已於本包完成，legacy capability surface 不作完成依據 | 已由本包實作收斂 |
| TOTP 尚不存在 | schema、request model、authentication flow 均無 TOTP seed／challenge／recovery facts | 正式 MFA 缺口 |

### 2.3 2026-08-16 已完成的 schema 驗證證據

- 已依人工授權重排序 fresh canonical assembly：`203_line_notification_rule_catalog.sql` 緊接
  `155_line_identity_review_configuration.sql`，`204`–`208` 緊接
  `156_line_publication_media_order_group.sql`；並重建 validation release、manifest 與 digest。
- `scripts/bootstrap_disposable_mysql_schema.py` 已在隔離資料庫
  `lu_test_access_control_challenge_fresh_v2` 成功建立 fresh schema（126 schema parts、46 base statements）；
  未操作 `union_db`。
- 專屬 209 release 的 preserve-data rehearsal 已在 `lu_test_ac209_source_v1` →
  `lu_test_ac209_candidate_v1` 成功執行 dump、restore、apply、verify。`admin_users` 與
  `admin_sessions` 各 1 筆的列數、primary-key 與既有欄位投影均保留，五個 209 Access Control
  owned objects 為 exact。receipt 位於忽略的 `scratch/access-control-totp/rehearsal/`。
- 在全新 `lu_test_access_control_e2e_v3` 已完成實際 MySQL 閉環：唯一 root bootstrap →
  首次 MFA enrollment → recovery codes → 不同 TOTP time-step 登入 → root Session 載入；結果為
  `passed`，且未使用 mock 或操作 `union_db`。可重跑 helper 位於忽略的
  `scratch/access-control-totp/verify_runtime_e2e.py`。
- `lu_test_access_control_e2e_v4` 進一步驗證 root 可建立同權子帳號、同 key create replay 回原帳號，
  並停用子帳號；隔離庫結果為 1 個 root、2 個帳號、1 筆 `account-create` receipt，子帳號為
  `enabled=0`、`access_control_version=2`。
- `lu_test_access_control_e2e_v5` 已重新完成 fresh bootstrap 與真實 MySQL 閉環：root → MFA
  enrollment → TOTP Session → root 建立同權子帳號 → same-key replay → 停用子帳號，結果為
  `passed`。此驗證使用一次性 disposable credential，不依賴操作者尚未設定的本機 root。
- 已新增 `local_developer_session` profile：僅 development/dev/local/test 且 auth enabled 時，以
  `.env` 的 `DEV_ROOT_USERNAME`／`DEV_ROOT_PASSWORD` 建立真實 root Bearer Session 並寫入 audit；
  不執行 TOTP，但 production 與錯誤 profile fail closed。2026-08-16 已以 `.env` 既有 root
  credential 建立並立即撤銷真實 Session，確認為 root principal；驗收輸出不含帳密或 Bearer。
  正式 MFA 仍須由操作者在受保護終端配置 TOTP keyring，未配置時固定 fail closed。
- `tests/test_access_control_disposable_mysql_e2e.py` 已在完整 fresh schema
  `lu_test_access_control_e2e_contract_v6` 驗證：root 建立同權帳號、停用／password reset／MFA reset
  均撤銷既有 Session、root 不可被線上停用，且強制 security audit 寫入失敗時整筆帳號 mutation rollback。
  此測試只接受明確指定且預先 bootstrap 的 `lu_test_*` database，絕不操作 `.env` 的 source database。
- 同一 MySQL E2E 已驗證同一 username/source 的五次失敗後，第六次被 `AdminLoginRateLimitedError`
  拒絕；public Stage 1 route 則固定回 typed 429 `login_rate_limited`。時間窗透過注入 clock boundary
  的 unit test 驗證，避免測試依賴資料庫或主機的即時時鐘。
- `211_access_control_security_alert_outbox.sql` 將 root bootstrap、帳號建立／狀態變更、credential／MFA
  reset、Session revoke、MFA enrollment、recovery-code 使用、rate limit、TOTP replay 與 disabled-account
  usage 的高風險 audit intent 與主交易一併保存；既有 incident worker 以可重試 outbox 投影
  `ACCESS_CONTROL` 系統告警。
  `tests/test_access_security_alert_outbox.py` 覆蓋成功、失敗重試與輸入邊界，完整 fresh MySQL E2E
  `lu_test_access_control_outbox_v3` 已驗證 audit → outbox → `system_alerts` 的閉環（2026-08-16）。
- 2026-08-16 對 `.env` 指向的 `lu_test_dataset_contract_signing_v4` 已完成 source backup → isolated
  candidate → apply → verify → protected replacement。候選驗證證明既有資料 projection 保留、新 outbox
  owned object exact；本機資料庫其後 `--require-current` 為 current。去敏 receipt 位於忽略的
  `scratch/ac-totp-outbox-rehearsal/` 與 `scratch/local_database_updates/`，未操作 production database。
- `lu_test_access_control_e2e_contract_v9` 亦驗證實際 TOTP Session 可被 `/me` 讀取，`/logout` 後
  同一 Bearer 不再可載入；此項不依賴 `local_bypass` 或 developer-session。
- `lu_test_access_control_e2e_contract_v11` 驗證錯誤 factor、已成功使用的 TOTP step replay、過期
  password challenge，以及 rate-limit 都不會簽發 Session；replay 在 `admin_login_attempts` 保存為
  `mfa_replay` outcome。
- `tests/test_access_control_ui_app_test.py` 以 Streamlit AppTest 驗證全域 guard：未登入只渲染
  public login、有效 Session 才建立業務導航、過期 token 會先清除、logout 會撤除 session state。
- enrollment UI 現在只在短效 challenge 尚有效時，將 `otpauth://` provisioning URI 於本機記憶體編碼為
  QR PNG 供驗證器掃描；不寫檔、不快取、不呼叫外部 QR service，手動 URI 僅在使用者展開時顯示。
- 第二段登入送出期間鎖定按鈕；任何 factor failure 都清除一次性 password challenge 並要求重新從
  帳密第一步開始，避免重送已使用或逾期 challenge 造成誤判。enrollment 的錯誤碼仍可在有效期內重試。
- 210 的 preserve-data rehearsal 已在 `lu_test_dataset_contract_signing_v4` →
  `lu_test_access_control_challenge_candidate_v5` 成功執行 dump、restore、apply、verify；既有資料投影與
  primary key 保持一致，`admin_password_login_challenges` 為 exact。receipt 位於忽略的
  `scratch/access-control-totp/challenge-rehearsal-v5/`。來源既有 MFA factor 為 0 筆，故本項不以它宣稱
  舊 factor row 的資料遷移覆蓋。
- 對 `.env` 指定的 `lu_test_dataset_contract_signing_v4`，已經由
  `scripts.update_local_database --apply --confirm-configured-database --mysql-container mysql_db` 完成
  replacement flow，最新 `--require-current` 回 `current`；209、210 與既有 owned objects 均為 exact。
  backup、candidate 與 replacement receipt 位於忽略的
  `scratch/access-control-totp/developer-upgrade-v1/`。
- `scripts.update_local_database --drift-report --mysql-container mysql_db` 是新增的唯讀處置入口：逐一
  列出 partial／drift artifact、缺失／意外欄位、是否已審核可在 candidate 續跑，以及必要的保留資料
  驗證。未知 drift 固定要求 per-artifact 修復裁決，絕不對 source 直接 DDL；本次 source 報告為
  `ready`、無待處置 artifact。

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

- 正式環境不得使用 auth bypass 或任何 legacy key 作為 human authorization；machine caller 必須使用既有
  private-operations identity contract（本機 scoped shared key、production Google OIDC），且不得冒充 human actor；
- UI 主框架在非開發模式下必須具備 Global Initial Auth Guard，載入時未持有效 Session 立即鎖定於全域登入頁面，禁止初始化或洩漏背景業務選單與功能；
- 未登入 public surface 只保留健康檢查、登入、TOTP enrollment challenge 所需的最小入口；
- 所有一般業務操作對 enabled human account 同權；僅 Access Control 帳號中心以 root identity 作最終授權；
- Streamlit 只保存短效 Session token、呼叫 typed API client、顯示 typed result；
- 所有帳號、MFA、授權變更都撤銷受影響 Session 並留下同交易 security audit；
- TLS、可信反向代理、Secure／HttpOnly／SameSite cookie 或等價的 server-side Session 傳輸方案，
  必須在 production cutover 前確認；TOTP 不可補償明文傳輸。

Global release invariant：正式 profile 中 human runtime source、startup、文件與部署設定不得再存在
`LEGACY_SHARED_KEY`、`X-Legacy-Shared-Key` 或以它作為 human authorization 的 fallback。此 invariant
不等同移除 machine-only `INTERNAL_SERVICE_SHARED_KEY` 或 production Google OIDC。

### 3.2 Domain：Access Control

#### 責任與 SSOT

Access Control 唯一擁有：

- admin identity、normalized username、display name、enabled state；
- 唯一 root-account designation；
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
- disable、password rotation、TOTP reset／rotation 與 root 執行的帳號狀態變更均撤銷受影響 Session；
- 停用不刪除帳號；security audit 與歷史 actor identity 必須保留；
- 恰有一個 enabled root；root 不可被線上 command 停用、降級、移轉或重設為非 root。root 遺失走受控
  離線維運程序，沒有 production HTTP break-glass endpoint；
- development bypass 只允許明確的 `local_bypass` profile；`local_auth` 必須走完整 MFA，
  production 對任何 bypass 設定 fail closed。

### 3.3 Subsystems

| Subsystem | 責任 | 交易邊界 |
|---|---|---|
| Authentication | 驗證 username、password、TOTP／recovery code、嘗試限制與泛化錯誤 | 成功驗證、TOTP replay marker、Session、login audit 同交易 |
| MFA Enrollment | 建立短效 enrollment challenge、一次顯示 QR、驗證首碼、啟用 factor | factor activation、recovery code hashes、credential version、audit 同交易 |
| Session | issue、load、sliding expiry、absolute expiry、revoke | token hash 與 revoke facts 由 Access Control UoW 管理 |
| Account Administration | root-only create、enable／disable、credential、MFA reset、Session revoke | root identity、expected version、root guard、event、receipt、audit 同交易 |
| Authorization | 驗證 enabled human session；僅帳號中心驗證 root identity | 不產生一般業務 role bundle 或 dynamic grant；mutation 委派 Account Administration |
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
- `RootAccountGuard`
- `AccountCommandFingerprint`
- `AccessControlRepository`／`AccessControlUnitOfWork`
- `SecurityAuditAppender`

每個 Module 先以純 input／output、clock／randomness ports 與 typed errors 驗證；不得讓 Router、
Streamlit render function 或 generic Data Browser 承擔上述規則。

## 4. API 與 UI 邊界

### 4.1 建議 API

| 類型 | Operation | 說明 |
|---|---|---|
| Public Stage 1 | `POST /api/v1/admin/auth/login/challenges` | 只驗 username＋password；成功回短效、一次性的 password challenge，不建立 Session |
| Public Stage 2 | `POST /api/v1/admin/auth/login/challenges/{id}/verify` | 驗證 challenge token＋TOTP／recovery code；成功後才建立 Session |
| Public-limited | `POST /api/v1/admin/auth/enrollment/challenges/{id}/verify` | 僅能完成短效、綁定使用者的首次 MFA challenge |
| Authenticated | `GET /api/v1/admin/auth/me` | 回 typed `AdminPrincipalView` |
| Authenticated | `POST /api/v1/admin/auth/refresh`、`logout` | 沿用 idle／absolute Session policy |
| root-only account center | admin account query／create／enable／disable／credential／MFA reset、指定帳號 Session revoke | Query 與 Command 分離；mutation 要 expected version、reason、idempotency key；不得調整一般業務 role／capability |

Stage 1 對帳號不存在、disabled 或密碼錯誤固定回泛化 `invalid_credentials`；Stage 2 對 challenge／
TOTP／recovery failure 固定回泛化 `invalid_challenge_or_factor`。短效 challenge 必須綁定帳號、
credential version、active factor identity、account access-control version、來源風險資料與 absolute expiry，保存 hash 並 single-use；不得把
username／password 暫存在 browser storage。現有 combined `/login` 是 `live-drift`，在新舊 client
相容與 entrypoint 裁決完成前不得直接刪除，也不得作為 React 正式兩段式完成證據。

### 4.2 UI

- 保留已確認的兩畫面 UI：第一畫面只有帳密，且只有 Stage 1 server challenge 成功後才顯示第二畫面；
  第二畫面輸入 TOTP／recovery code，Stage 2 成功後才取得 Session。前端非空驗證或換頁不算帳密通過；
- 建立全域 Access Control 登入／登出入口（非開發模式下系統初始化預設直落登入頁面），取代頁面各自重複登入；
- 在非開發模式下（`ENABLE_ADMIN_AUTH=true`），未登入前禁止渲染側邊欄選單、業務頁面與敏感組件，完成登入後始允許操作；
- 建立獨立 `AccessControlApiClient`，不得把帳號管理 endpoint 加進 `LineAdminApiClient`；
- client 將成功 payload 驗證成 Pydantic view，transport／schema error 轉為 typed client error；
- 帳號管理頁至少提供清單、建立、啟停、角色／能力、撤銷 Session、發起 MFA reset、稽核摘要；
- 管理員不可查看既有 TOTP seed、明碼 recovery code 或 password hash；
- MFA reset、停權、降權等高風險操作必須二次確認並輸入 reason；
- 首次綁定由帳號本人登入短效 enrollment flow 後掃描 QR 並輸入首個 TOTP，不由管理員代持 seed。

## 5. Idempotency、retry、conflict 與 typed errors

### 5.1 Command 規則

- 建立帳號、啟停、password rotation、MFA reset、Session revoke 都使用
  `idempotency_key + canonical command fingerprint + expected_account_version`；
- 相同 key＋相同 payload 回原 receipt；相同 key＋不同 payload 回 conflict；
- stale version、root guard、TOTP replay、已失效 enrollment challenge 不自動 retry；
- 只有 deadlock、暫時性 storage unavailable 可使用相同 command identity bounded retry；
- 登入嘗試不是一般業務 command replay；必須受 account＋來源的 rate limit、退避與告警保護。

### 5.2 Typed errors

| Code | HTTP／處理 |
|---|---|
| `invalid_credentials_or_factor` | 401；對外泛化 |
| `login_rate_limited` | 429；回 retry-after，不揭露帳號狀態 |
| `mfa_enrollment_required` | 403 或受限 challenge result；不得取得一般 Session |
| `mfa_challenge_expired` | 409；重新發起 enrollment |
| `mfa_factor_replay` | 401；audit／風險計數 |
| `mfa_secret_unavailable` | 503；fail closed、告警 |
| `admin_session_expired` | 401；重新完整登入 |
| `admin_user_disabled` | 對外併入泛化 401；內部 typed audit |
| `root_account_required` | 403；僅帳號中心使用 |
| `admin_version_conflict` | 409；重新載入 |
| `root_account_protected` | 409 |
| `idempotency_payload_conflict` | 409 |
| `security_audit_persistence_failed` | rollback、503、告警 |

## 6. 安全參數與人工操作入口

- TOTP 採 RFC 6238、30 秒 time-step；預設接受 current step，時鐘漂移容忍最多前後各一格，
  並記錄最後成功 step 防 replay；
- TOTP、password、recovery code 永不寫 log；recovery codes 僅首次顯示，DB 只存 hash；
- 伺服器與資料庫主機需監測時鐘同步；漂移超標時登入 fail closed 並告警；
- repeated login failure、rate-limit burst、disabled account usage、TOTP replay、MFA reset、
  recovery code use、production bypass attempt、root recovery attempt、audit rollback 都需告警；
- MFA 遺失不設隱藏 bypass／萬用碼。由 root 在帳號管理頁發起其他帳號的 reset，填寫原因、撤銷
  Session，帳號回到 `pending_mfa_enrollment`；
- root 的 MFA 遺失使用受控離線維運程序重新建立 enrollment，
  不提供 production HTTP break-glass endpoint。

參考基線：

- [RFC 6238: TOTP](https://datatracker.ietf.org/doc/html/rfc6238)
- [OWASP Multifactor Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Multifactor_Authentication_Cheat_Sheet.html)
- [NIST SP 800-63B](https://pages.nist.gov/800-63-4/sp800-63b.html)

TOTP 可顯著提高帳密被竊後的防護，但不是 phishing-resistant；本期以符合需求的 TOTP 上線，
後續可另案評估 WebAuthn／passkey，不擴大本次範圍。

## 7. 分階段待辦

### P0：重現並修復 authenticated development profile

- [x] `AC-P0-01` `.env` 已確認為 strict UTF-8 無 BOM（2026-08-16；僅驗證 encoding／byte count，
  未讀出、複製或輸出任何 secret）。
- [x] `AC-P0-02` 以明確 profile 取代隱含預設：`local_bypass`、`local_auth`、`production`；
- [x] `AC-P0-03` 建立安全的本機測試管理員 bootstrap／reset runbook；見 `README.md` 的「root bootstrap 與 MFA key rotation」，root 密碼仍僅能由操作者最後在互動終端設定。
- [x] `AC-P0-04` 依核准 migration／cutover 流程補齊 live candidate schema，不直接 init 或改正式資料；
- [x] `AC-P0-05` 建立現況登入診斷矩陣：見下方「登入診斷矩陣」；不記錄 credential。
- [x] `AC-P0-06` 修正 login 與一般 Session 401 的 typed client error mapping，避免錯誤訊息失真；
- [x] `AC-P0-07` 已以 `.env` 的既有 root credential 驗證本機 `local_developer_session` API lifecycle：
  建立真實 Session、Bearer `/me`、logout 與 logout 後舊 Bearer 401；不輸出 credential／token。
  正式帳密＋TOTP lifecycle 另由 disposable MySQL E2E 覆蓋，待操作者配置本機 TOTP keyring 後可手動重跑。
- [x] `AC-P0-08` 補 login route＋disposable MySQL contract E2E，不以 hash／bypass 單元測試代替；
- [x] `AC-P0-09` 補齊啟動時的 auth profile／bypass 醒目訊息，禁止輸出 credential；
- [x] `AC-P0-10` 產出故障根因與修復 receipt，避免把 bypass 誤認成 authenticated PASS。

#### 登入診斷矩陣

| 觀察 | 唯讀檢查 | 預期／處置 |
|---|---|---|
| profile | `ACCESS_CONTROL_PROFILE`、`APP_ENV`、`ENABLE_ADMIN_AUTH` | 只允許 `local_bypass`（local 且 auth=false）、`local_auth`（auth=true）、`local_developer_session`（local 且 auth=true）或 `production`（auth=true）；其他組合視為 fail closed。 |
| schema | `python -m scripts.update_local_database --mysql-container mysql_db` | 必須顯示 209、210、211 為 exact；`partial`／`drift` 先用 `--drift-report` 取得 candidate-only 處置，不得直接 DDL source。 |
| account state | root-only Account Center 或受保護的 MySQL 唯讀查詢 | 必須恰有一個 enabled root；一般帳號首次登入為 pending MFA，不能取得業務 Session。 |
| API | `POST /login`、`/me`、`/logout` 及 enrollment verify | schema 未就緒為 typed 503；帳密或 factor 不正確為泛化 401；未綁 MFA 僅回受限 enrollment challenge。 |
| UI／Session | Streamlit 全域 Guard、Bearer `/me`、logout 後重新載入 | 未登入不得載入選單或業務頁；token 僅存 session state，logout 後不得繼續跨頁使用。 |

此矩陣只收集 profile、版本、狀態與 typed code；不輸出密碼、TOTP seed、recovery code 或 bearer token。

### P1：確認架構、風險與資料遷移

- [x] `AC-P1-01` 人工確認本文件全部架構與下方待確認決策；
- [x] `AC-P1-02` inventory legacy human key 與 machine identity caller、route、script、test、README、batch 與部署設定，兩者不得混淆；
- [x] `AC-P1-03` 區分 human UI、public login、worker／migration 等 machine caller；
- [x] `AC-P1-04` 定義 MFA tables／columns、encryption key ownership、key version 與 rotation runbook；見 `209_access_control_totp_root.sql`、`subsystems/access/totp.py` 與 `README.md`。
- [x] `AC-P1-05` 定義既有 admin users 的 `mfa_enrollment_required` 遷移與唯一 root bootstrap；
- [x] `AC-P1-06` 更新 Access Control 正式規格、schema release／rollback 與 API contracts。

### P2：Module 實作與驗證

- [x] `AC-P2-01` TOTP secret generation、encryption、provisioning URI、verification、replay guard；
- [x] `AC-P2-02` recovery code generation、hash、single-use consume；
- [x] `AC-P2-03` login attempt policy、generic response、rate limit 與 deterministic clock tests；
- [x] `AC-P2-04` account／factor／session state transition 與 typed error tests；
- [x] `AC-P2-05` command fingerprint、root-account guard、idempotency／conflict tests；建立帳號已納入
  receipt replay／payload-conflict 保護，相關 MySQL command 驗收已完成；未覆蓋的真實並發情形已移交 successor。
- [x] `AC-P2-06` 新增直接第三方 dependency 時同步 `pyproject.toml`、`uv.lock`，以 `pytest -W error` 驗證。

### P3：Subsystem 與資料層

- [x] `AC-P3-01` additive schema migration：factor、recovery、attempt、command receipt／event 與 security-alert outbox 所需 SSOT。
- [x] `AC-P3-02` Authentication＋MFA Enrollment UoW；已由 disposable MySQL transaction E2E 覆蓋。
- [x] `AC-P3-03` Account Administration query、非 root enable／disable、credential／MFA reset 與 affected-session revoke；idempotency／version 已由 disposable MySQL E2E 覆蓋。
- [x] `AC-P3-04` local closeout：高風險主交易、disabled-account usage 的 durable outbox 與 retry
  projection 已落地並有 fresh／preserve-data MySQL evidence；production bypass attempt、root recovery attempt
  與 audit rollback 的外部告警 coverage 為 `NOT_RUN`，已移交 successor。
- [x] `AC-P3-05` local closeout：唯一 root、FK／unique、audit rollback、replay 與 Session revoke 已由
  `test_access_control_disposable_mysql_e2e.py` 覆蓋；真實並發 row-lock／stale-version 與 outbox
  partial-failure 競態驗收為 `NOT_RUN`，已移交 successor。
- [x] `AC-P3-06` 保存資料 migration rehearsal，禁止對正式資料或 fixture snapshots 誤操作。

### P4：API 與 typed UI client

- [x] `AC-P4-01` 實作 `POST /login/challenges` → `POST /login/challenges/{id}/verify` 的 typed 兩段式 API，challenge 為 DB hash、短效、single-use 並綁定 credential／active factor identity／account access-control version；combined `/login` 僅為尚待 entrypoint 裁決的相容入口，不作完成證據。
- [x] `AC-P4-02` 新增獨立 account administration router；
- [x] `AC-P4-03` 新增 `AccessControlApiClient` 與 Pydantic views／typed client errors；
- [x] `AC-P4-04` 以既有兩畫面 UI 接入 Stage 1／Stage 2 challenge 與 enrollment（包含非開發模式未登入全域 Guard）；LINE、系統狀態與帳號中心頁僅消費全域 Bearer Session，不再提供重複登入表單。
- [x] `AC-P4-05` 建立僅 root 可見且由 API 再驗證 root identity 的帳號管理頁；
- [x] `AC-P4-06` UI 驗證不得有 raw dict 穿透 render function，且 secret／QR 不持久化。

### P5：退役 LEGACY_SHARED_KEY

- [x] `AC-P5-01` login route 移除 internal service dependency，改由 rate-limit＋MFA policy 保護；
- [x] `AC-P5-02` human business routes 的 `require_admin` 改為純 Bearer Session；帳號中心另以 root identity 驗證；
- [x] `AC-P5-03` UI shared transport 移除 `X-Legacy-Shared-Key` 與 configured gate；
- [x] `AC-P5-04` machine callers 保持或遷移至明確 scoped identity；本機 shared key 與 production OIDC 的現行 contract 不得被誤刪；
- [x] `AC-P5-05` 更新 smoke／E2E／migration rehearsal、startup scripts、README 與部署設定；
- [x] `AC-P5-06` source／runtime scan 證明 legacy human key 與 header 已無 active caller，並分別證明 machine identity caller 仍受 scoped contract 保護；
- [x] `AC-P5-07` 不提供 legacy fallback、雙軌 key＋Session 或 query-string credential。

### P6：Domain／Global 驗收

- [x] `AC-P6-01` local closeout：帳號／MFA／Session／logout 的 API 與 Streamlit guard 已驗證；完整
  browser-level create → enrollment → MFA → cross-page → logout 為 `NOT_RUN`，已移交 successor。
- [x] `AC-P6-02` wrong password／wrong TOTP／replay／expired challenge／rate limit／clock drift；
- [x] `AC-P6-03` disable、password rotation、MFA reset 後舊 Session 全失效；
- [x] `AC-P6-04` root account protection、stale version、same-key replay、different-payload conflict；
- [x] `AC-P6-05` security audit persistence failure 導致整筆 mutation rollback；
- [x] `AC-P6-06` production profile 拒絕 bypass；未綁 MFA 不簽發一般 Session；TOTP seed 僅以
  versioned Fernet ciphertext 保存且錯 key fail closed；legacy human key 無 runtime caller。
  證據：`tests/test_admin_auth_security.py`、`tests/test_admin_auth_runtime.py`、
  `tests/test_access_totp.py`（`31 passed`，以 `-W error -p no:cacheprovider` 執行）。
- [x] `AC-P6-07` local closeout：human transport 已 Bearer-only，帳號中心 API 已 root-only；所有既有
  管理頁 browser-level 同權與 thin-UI 驗收為 `NOT_RUN`，已移交 successor。

### P7：上線、觀測與回滾

- [x] `AC-P7-01` 至 `AC-P7-06` transfer record：全部 production cutover／雙人 enrollment／keyring、
  migration、clock、maintenance-window smoke、machine identity 與 rollback 證據均為 `NOT_RUN`；使用者
  指示暫不部署，已完整移交 successor，沒有 production target 被操作。

## 8. 四層完成證據

| 層級 | 必須證明 |
|---|---|
| Module | TOTP vectors、encryption round-trip／wrong key、single-use step、recovery hash、policy、typed errors |
| Subsystem | enrollment、login、Session、account commands、replay、stale、retry、rollback、partial failure |
| Domain | disposable MySQL 的 schema、FK／unique、row lock、唯一 root、session revocation、audit atomicity |
| Global | production fail-closed、Bearer-only 全管理 UI、帳密＋TOTP 跨頁 E2E、legacy human key 零 active caller、machine identity scoped contract |

Mock PASS 不得取代 Domain／Global 的真實 MySQL 與 runtime evidence。測試資料與正式資料庫必須隔離。

## 9. 人工確認決策

本計畫預設並建議一次確認以下決策：

0. 2026-08-16 已人工確認：所有 enabled 帳號（包含 root）可使用相同、完整的業務功能；唯一 root
   帳號額外可管理帳號中心，此額外權限不得擴張為其他業務功能或一般 capability model；
1. `local_bypass` 僅供本機快速開發；另設 `local_auth` 強制走與 production 相同的帳密＋TOTP；
2. 新帳號由 root 建立，但 TOTP seed 只在帳號本人的短效 enrollment session 顯示；
3. 每次 enrollment 產生一次性 recovery codes；root 只能 reset factor，不能查看 seed 或 recovery code；
4. MFA reset、password rotation、disable 全部撤銷受影響既有 Session；root designation 與 enabled
   state 不可由線上 command 變更，但 root 已驗證時可自行 rotation credential／MFA；
5. 不提供 production HTTP break-glass endpoint，root 復原走受控離線維運程序；
6. 本期採 RFC 6238 TOTP；WebAuthn／passkey 另案，不阻擋本期；
7. legacy human key 完整退役；machine caller 維持或遷移至 scoped machine identity contract。本機
   `INTERNAL_SERVICE_SHARED_KEY` 與 production Google OIDC 不得被誤認為 human authorization。

人工確認後，實作順序固定為 `P0 → P1 → P2/P3 → P4 → P5 → P6 → P7`。只有在寫入範圍互不
重疊且共享契約已確認時，production code 與同層測試才可平行派工。

## 10. Closeout 與移交

2026-08-16 使用者裁決：本工作包以 `completed-local-validated` 結案並封存；尚未部署的事項不再是
本文件的 active action。後續 owner、規格、驗收與啟動門檻唯一移至
[`25_Access_Control_Production_Cutover與External_Security_Alert正式規格.md`](../../01_規格基線/25_Access_Control_Production_Cutover與External_Security_Alert正式規格.md)
與 [`Access_Control_Production_Cutover_and_External_Security_Alert_Work_Package.md`](../../02_決策與退役執行記錄/Access_Control_Production_Cutover_and_External_Security_Alert_Work_Package.md)。

本機完成證據包括 209、210、211 additive releases、fresh／preserve-data disposable MySQL、security alert
outbox E2E、developer-local protected replacement，以及 focused pytest；所有 production／external provider
事項仍是 `NOT_RUN`。未曾部署、未操作 production database、未輸出任何 credential 或 TOTP material。
