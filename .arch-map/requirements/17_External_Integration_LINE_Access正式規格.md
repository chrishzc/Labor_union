# LINE、Access Control 與 Knowledge Retrieval 正式規格

## 1. 文件邊界與所有權

- 狀態：`current-spec`
- Owner：External Integration Boundary、Access Control Domain、Knowledge Retrieval Domain
- 單一負責範圍：外部平台整合共同安全不變量（`SystemPrincipal`、去敏安全回條、durable inbox／outbox 與 Reply 5xx 不確認處理）、Access Control（統一業務授權、單一 enabled `root` 生命週期、兩段式登入／MFA、8 小時 session 上限、統一網頁建帳 bootstrap 與離線 root 維護、管理員密碼雜湊與帳號命令收據、資料庫 P01–P10 受限權限程序、`Security Audit` 兩年遮罩查詢與歸檔、`Data Browser` 六源相容唯讀契約），以及 Knowledge Retrieval 審查發布與來源 citation 契約。
- 關聯引用：見 [Global 共同契約](00_Global_共同契約.md)、[Global Migration 與 Cutover](10_Global_保留資料Migration與Cutover_Subsystem.md)、[LINE Gateway、Inbox 與通知投遞](17A_LINE_Gateway_Inbox與通知投遞正式規格.md)、[Case Import 與非市民 Redis 待審](17B_Case_Import與非市民Redis待審正式規格.md)、[Global Deployment 與治理](18_Global_Deployment與治理正式規格.md)、[Global Entry Point Governance](19_Global_Entry_Point_Governance.md)、[LINE 客服與月嫂自助服務](20_LINE客服與月嫂自助服務正式規格.md)、[Access Control Production Cutover](25_Access_Control_Production_Cutover與External_Security_Alert正式規格.md)、[Controlled File Storage 正式規格](30_Controlled_File_Storage正式規格.md)、[案件與月嫂整合名冊](33_案件與月嫂整合名冊正式規格.md)。

## 2. Global External Integration Boundary

### 2.1 共同安全不變量

1. 外部平台 Adapter 僅驗證、正規化並保存事件；外部 payload、URL、actor、case mapping 與 provider status 一律視為不受信任輸入，絕不直接寫入 Orders status、服務日期、排班、金額或付款狀態。
2. Ingress 先寫入無敏感 raw payload 的 request-level security receipt（驗簽失敗只入隔離／頻率指標）；驗簽與格式通過後立 durable inbox event，由獨立 consumer 轉呼 owning Domain typed command。
3. Egress 僅經已提交 outbox／durable delivery task 發送（HTTP request 或畫面渲染不得直呼外部 provider；專員申請即時回覆僅限當次 LINE Reply API，遇 HTTP 5xx 只能回報結果未確認（`line_reply_outcome_uncertain`），不當成已送達或已確定失敗，也不得自動重試或回退補發 Push）。
4. Provider event 與下游 Domain command 使用獨立 idempotency identity（同 key＋同 payload 為 exact replay，同 key＋異 payload 固定 409 quarantine）。
5. Consumer 採固定 `SystemPrincipal`（僅含固定服務識別、版本能力與來源 event identity；禁止由 UI／webhook 指定），不可覆寫需要人工裁決的 blocker。

### 2.2 Provider-Neutral Ports 與 Typed Errors

- **Ports**：`ExternalSignatureVerifier`、`ExternalEventNormalizer`、`DurableInboxRepository`、`DurableDeliveryQueue`、`ExternalEventConsumer`、`DomainCommandGateway`、`ProviderDeliveryGateway`、`ExternalEvidenceArchive`、`IntegrationClock`（LINE 與 BeClass 共用介面契約但隔離 payload 表與 idempotency namespace）。
- **Global Errors**：`external_signature_invalid` (401)、`external_payload_invalid` (400/422)、`external_event_duplicate` (回原回條)、`external_event_conflict` (409+quarantine)、`external_mapping_not_found` (404)、`external_mapping_ambiguous` (409)、`external_provider_unavailable` (503 retryable)、`external_retry_exhausted`、`integration_storage_unavailable` (503)。

## 3. Domain：Access Control

### 3.1 統一業務授權與資料庫權限分層隔離

- **全體內部人員同等業務權限**：所有已登入且 `enabled` 的內部使用者擁有完整業務功能集合（包含刪除假日／資格／偏好、替換匯入／虛擬帳號／排班、異常重查、封存與知識清理）；不以職稱、部門或 role bundle 做業務功能差異授權。唯「帳號中心」僅供唯一 enabled `root` 使用（非業務權限差異）。
- **人工操作極簡化互動**：依 [Global 共同契約 §2.4](00_Global_共同契約.md#24-管理端一次點擊送出與選填原因)，內部寫入操作改採一次點擊送出、原因選填。
- **資料庫權限分離（`NAS-DB-01～03`）**：日常執行帳號無直接 `DELETE`／`DDL`／`GRANT OPTION`／`CREATE USER`；刪除一律透過專用不可登入 DEFINER 預存程序 `P01`–`P10` 執行（P01 日期、P02 資格／交通差、P03 六項關聯、P04 偏好集合、P05 歷史人員替換、P06 案號虛擬帳號 mapping、P07 被替換排班世代、P08 失效異常投影、P09 過期已封存 audit、P10 核准刪除之 knowledge target），不自開 COMMIT／ROLLBACK；runtime profile 持有作用域內 `LOCK TABLES` 供 `FOR UPDATE` 鎖定讀取。LINE 對外帳號僅讀寫 LINE 自身必要邊界，嚴禁持有 `P01`–`P10` 或管理端寫入憑證。
- **Worker 內部服務驗證與邊界隔離**：Worker 與 monitor 透過 loopback `local_shared_key`（至少 32 字元之共享金鑰與 `X-Internal-Service-Name` 操作端點綁定，缺漏、過短或非支援模式皆 fail closed）呼叫 Private Operations API，嚴禁攜帶 DB 帳密或冒充他服務操作。
- **禁止 legacy key**：human mutation 嚴禁接受 `X-Legacy-Shared-Key`。

### 3.2 根事實、登入、統一網頁 Bootstrap 與離線 Root 重置

- **根事實與狀態機**：管理員帳號（`enabled ↔ disabled`，`root` 不可停權／降級／線上轉移）、10–256 字元密碼 hash、加密 TOTP factor（`unbound → enrollment_pending → active → rotated | revoked`）、single-use recovery code、password／enrollment challenge（`issued → consumed | expired`）、hashed session token（最多 `8` 小時絕對有效期、無閒置續期，缺期限 fail closed）及 hashed rate-limit 記錄。
- **兩段式安全登入**：Stage 1 驗證帳密；未綁 MFA 時 `POST /api/v1/admin/auth/login/challenges` 回 HTTP `200` `mfa_enrollment` 短效 challenge＋provisioning URI（限記憶體畫面顯示，禁進錯誤回應／log／URL／WebStorage），已綁定回 `factor_verification`；Stage 2 驗 TOTP／復原碼建立 bearer session。兩段錯誤一律回泛化 `invalid_credentials_or_factor` 或 `429`。
- **統一網頁首次建帳 Bootstrap（`GET／POST /api/v1/admin/setup`）**：
  - 不分主機環境皆以 MySQL `admin_root_account` 是否存在 `root` 決定首次設定（全面移除環境變數自動建 root 分支；需同源與 HTTPS 或 loopback）。
  - `bootstrap_root_admin` 於同一 UoW 建立 `root` 與 `enrollment_pending` factor（競爭回 `409`）；流程固定「建 root → 立即顯示 QR → 驗證綁定 → 保存復原碼 → 清除機密返回登入頁」。缺少 TOTP 加密金鑰須停機執行離線工具 `scripts.configure_initial_totp_key --apply`（確認空帳號與空安全表後原子寫入 `.env`，不於網站啟動時自動生鑰）。
- **錯誤初始 Root 本機離線重置（`scripts.reset_incomplete_root_setup`）**：僅限 `localhost` 資料庫連線（`configure_initial_totp_key` 與 `reset_incomplete_root_setup` 皆不限 `APP_ENV` 或資料庫名稱），確認安全版本仍為 `1`、零登入／LINE 綁定／業務 FK 且人工輸入 `RESET ROOT <database> <id>` 後，於單一 UoW 移除未完成建帳狀態並保留稽核記錄（禁止新增 HTTP 重置或 break-glass 端點）。

### 3.3 帳號指令、Security Audit 與 Data Browser 相容查詢

- **Commands & Errors**：僅限 root session 操作 `CreateAdminUser`、`DisableAdminUser`、`EnableAdminUser`、`RevokeAdminSessions`、`RotateAdminCredential`、`ResetAdminMfa`（綁定 expected version 與 idempotency key）。帳號中心的命令以一般帳號為對象，後端拒絕以 root 本身為操作對象。Errors：`authentication_unavailable` (503)、`invalid_internal_service_credential` (401)、`missing_or_invalid_admin_session` (401)、`admin_session_expired` (401)、`admin_user_disabled` (401/403)、`admin_version_conflict` (409)、`security_audit_persistence_failed`。
- **Security Audit 兩年遮罩查詢**：帳號中心已移除「安全操作與登入稽核」分頁。管理員登入、線上帳號與 MFA 管理，以及一般管理 API 操作停止追加 `admin_audit_logs` 紀錄及由該紀錄產生的告警。登入限流保留雜湊後的失敗計數，帳號命令保留冪等收據。離線 root 維護與各業務領域專用證據依原契約保存。所有 enabled 管理員皆可透過既有唯讀 API 免填原因查閱最近 2 年之遮罩稽核摘要與明細（遮罩 IP、token、password、LINE ID、電話、身分證）。既有紀錄保留，超過 2 年由每日排程轉入非對外唯讀封存（不自動刪除）。
- **Data Browser 六源相容唯讀查詢**：`GET /api/v1/admin/data-browser/sources/{source_id}` 僅接受 `orders | clients | staff | beclass_intake | hcm_review | bank_facts` 六個列舉，limit `1..100`，嚴格遮罩輸出（`bank_facts` 金額遮罩且不外洩帳號／對象／指紋）；管理端日常導航 `#data-browser` 依 [整合名冊規格](33_案件與月嫂整合名冊正式規格.md) 導向客戶名冊，原 raw table metadata 入口（`GET /api/v1/admin/data-browser/{table}`）與 generic PATCH 維持退役移除。

### 3.4 Windows 主機離線管理 root 帳號

- 例行入口為工會 Windows 主機上的 `Windows管理.bat` → `11 管理 root 帳號`。由授權維運人員依 `.env` 資料庫連線設定操作（不限 `APP_ENV`、資料庫名稱，亦不要求 `.env.nas-maintenance` 或強制 TLS），提交前須停止受管管理服務並等已受理的請求結束。帳號中心與 HTTP API 不提供這項維運操作。憑證遺失時依 [正式環境離線復原規格](25_Access_Control_Production_Cutover與External_Security_Alert正式規格.md#2-業務場景與不變量) 處理。
- 選擇 `11` 後，先互動輸入目前的 root 登入帳號、密碼與已啟用驗證器的 TOTP 動態碼。沿用登入的限流與防重放規則。只有同一個啟用中的 root 三項均驗證成功，才顯示操作選單。失敗或取消即結束本次操作。驗證結果只在本次互動有效，綁定 root ID 與帳號安全版本，且最多允許提交一項操作。

| 選項 | 操作與確認 |
|---|---|
| `1 修改登入帳號` | 輸入新登入名稱，檢查格式與唯一性，確認後更新同一個 root 帳號。 |
| `2 修改密碼` | 隱藏輸入新密碼兩次，符合 §3.2 的長度限制且兩次一致後，確認以 §3.5 的 scrypt 參數更新密碼雜湊。 |
| `3 重新綁定 TOTP` | 確認加密金鑰與時鐘可用，產生新種子，在主機互動介面短暫顯示綁定資訊。驗證新裝置的動態碼後才允許確認切換。提交時啟用新驗證器、撤銷原驗證器與原復原碼，換發單次使用的復原碼。 |
| `0 返回` | 返回主選單，維持帳號設定與既有登入。 |

- 提交時在 Access 的同一筆交易鎖定並重讀唯一 root 與版本。保留帳號 ID、root 身分、權限和業務關聯，只更新所選項目。增加安全版本、撤銷 root 的所有既有 session，使未完成的登入及綁定挑戰失效，並原子保存去敏維運稽核。修改登入名稱或密碼時保留目前 TOTP 及復原碼。
- 取消、版本衝突、新驗證器驗證失敗或交易失敗，均不提交帳號、驗證器或 session 變更。切換 TOTP 期間原驗證器維持啟用，直到新驗證器隨交易生效。若提交結果不明，先以 root 安全版本和稽核確認結果再決定後續動作。提交後若驗收失敗，維持維護狀態並走受控離線復原。
- 密碼、動態碼、TOTP 種子及復原碼明文只經主機互動介面處理，不得寫入命令列引數、設定、歷史、日誌或收據。新復原碼在成功提交後只顯示一次。稽核保留操作者、時間、操作種類、目標 ID、原因與結果。

### 3.5 帳號命令收據與密碼雜湊

- **一般帳號的建立與密碼重設收據。** 以有版本的 HMAC 為請求指紋，使用專用金鑰，與資料庫及 SQL 備份分開保管。單靠收據、資料庫及 SQL 備份，無法用收據指紋快速驗證密碼猜測。相同 idempotency key 和相同請求回原收據，不再次寫入。相同 key 但請求不同（包含密碼不同）回 `idempotency_key_conflict`。所需金鑰無法取得時停止命令，禁止改用無金鑰指紋。
- **既有收據與備份。** 在受控資料升級中將一般帳號建立與重設收據的密碼相關指紋轉為金鑰保護格式，保留原操作紀錄與重送語意。轉換不得要求取得原密碼，也不得在有效資料中保留原快速指紋。轉換前的備份沿用現行保存期限與存取限制。從這類備份復原時，須完成相同轉換才可開放帳號命令。
- **scrypt 參數。** 管理員密碼採 scrypt 並為每次產生的雜湊建立獨立隨機鹽。新建、重設與 root 密碼輪替使用通過目標部署量測的參數。以 `N=2^17, r=8, p=1` 為首選量測組合。正式組合須符合 [OWASP scrypt 建議](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html#scrypt)，並在同款部署驗證單次及併發登入的延遲、記憶體與失敗率，符合上線前記錄的資源與延遲上限。
- **既有雜湊升級。** 依已儲存的參數驗證既有密碼。使用較弱參數的一般帳號驗證密碼成功時，用當次輸入重新產生符合正式參數的雜湊，並以原雜湊仍相同為更新條件，避免覆蓋併發的密碼重設。錯誤密碼不觸發升級。更新雜湊不改變原密碼，也不影響第二階段 MFA。

## 4. Domain：Knowledge Retrieval

- **責任與邊界**：擁有 FAQ／政策來源、content digest、版本與核准索引 freshness；嚴禁修改業務根事實或讓無來源模型輸出充當業務命令、報價與法律依據。
- **狀態機與分權核准**：Knowledge Item 為 `draft → reviewed → published → retired`；**內容建立者不得自審或自發發布（必須經他人覆核發布）**，僅 `published` 條目可進入檢索；來源異動立即標示 index `stale` 並於查詢明確降級轉人工，禁止無 citation 回答。
- **Query／Commands／Errors**：Query 回傳安全摘要、source URI、content digest、published version、index version，並固定回傳 `authoritative=false`。摘要附來源不代表它是業務根事實，也不授權改寫任何業務資料。Commands：`IngestKnowledgeSource`、`SubmitKnowledgeReview`、`PublishKnowledgeItem`、`RetireKnowledgeItem`、`RequestKnowledgeIndexBuild`、`RetryKnowledgeJob`、`QueryKnowledge*`。Errors：`knowledge_source_invalid`、`knowledge_review_required`、`knowledge_index_stale`、`knowledge_index_unavailable`、`knowledge_answer_unsupported`。

## 5. 驗收標準

1. Unit／Subsystem 驗證簽章與 payload 分層隔離、Reply 5xx 不確認禁止重送 Push、兩段 MFA／setup bootstrap／離線重置守衛、`P01–P10` 定點授權刪除與直接 DELETE 拒絕、Knowledge 作者不得自審發布及無來源 fail closed。
2. Global／隔離 MySQL 驗證同源 setup 競爭 409、worker 內部服務驗證與操作邊界隔離、兩年稽核遮罩與 Data Browser 唯讀 6 源穩定契約。

### 5.1 Access Control 驗收

以 Windows 實際管理入口、隔離 MySQL 及正常管理登入入口驗證。scrypt 效能另以與正式部署同款的環境量測。

| ID | S 情境 | T 任務 | A 操作 | R 通過條件 |
|---|---|---|---|---|
| `AC-ROOT-01` | Windows 維運者具有有效的 root 帳密和 TOTP | 驗證後才選操作 | 從 `Windows管理.bat` 選 `11`。分別以一般帳號、錯誤密碼、錯誤或重放的 TOTP 和有效 root 憑證嘗試 | 只有有效 root 憑證顯示 `1`、`2`、`3`、`0`。其他嘗試不進入選單、不更新帳號。後台與 HTTP 入口無法執行 root 維運。 |
| `AC-ROOT-02` | root 有多裝置既有登入與未完成的登入挑戰 | 單獨更新登入名稱或密碼 | 分別執行 `1`、`2`，從維護終端確認後，用變更前後的憑證和 session 存取正常管理入口 | 每次只更新所選欄位。root ID 和權限一致，原 TOTP 及復原碼仍有效。新組合可完成兩段式登入，原登入組合、所有舊 root session 與既有挑戰遭拒，一般帳號 session 仍可用。 |
| `AC-ROOT-03` | 原 TOTP 已啟用，準備切到新驗證器 | 安全換綁 | 執行 `3`，先試錯誤的新動態碼，再以正確動態碼完成切換 | 錯誤碼不變更原綁定。提交後新 TOTP 可登入，舊 TOTP、原復原碼、舊 root session 及先前的登入或綁定挑戰遭拒。新復原碼只顯示一次且每組只可使用一次。登入名稱及密碼維持原狀。 |
| `AC-ROOT-04` | 操作可能取消、撞名、遇到併發修改或儲存失敗 | 安全停止及確認提交結果 | 選 `0`、輸入重複名稱、改變安全版本或注入交易／稽核失敗。另模擬交易提交後終端失去回應 | 未提交的操作保留原帳號、驗證器及 session。版本變更回報衝突。提交結果不明時可由版本與稽核確認，無重複寫入。檢查命令列、日誌及稽核，皆無憑證原文。 |
| `AC-ROOT-05` | 主機可能連錯目標、管理服務仍在執行或 TOTP 環境異常 | 驗證維護前置條件 | 分別用錯誤的目標、無法驗證的 TLS 連線、仍在運作的管理服務、無法使用的加密金鑰或異常時鐘嘗試對應操作 | 工具指出失敗的前置條件，停止提交且保留原帳號設定與登入。 |
| `AC-RECEIPT-01` | 一般帳號建立或重設可能在提交後重送 | 維持冪等與收據機密性 | 對新收據及完成轉換的既有收據，重送相同請求，再用同 key 送不同密碼。另模擬金鑰缺失 | 相同請求回原收據且只寫入一次。更換密碼輸入回 `idempotency_key_conflict`。金鑰缺失時停止寫入。有效資料只保存金鑰保護指紋，不含原快速指紋或密碼原文。 |
| `AC-RECEIPT-02` | 備份仍含未轉換的建立與重設收據 | 完成保留資料升級 | 將備份還原至隔離 MySQL，先嘗試送出帳號命令，再完成指紋轉換並比對收據 | 轉換前禁止帳號命令。轉換後保留原操作紀錄，同一請求仍可重送，且有效資料移除原快速指紋。 |
| `AC-SCRYPT-01` | 庫內同時有既有及較強參數的雜湊 | 升級且維持登入相容 | 用正確及錯誤密碼測登入，完成 TOTP，另讓密碼重設與雜湊升級併發。驗證新建、重設及 root 密碼輪替後的雜湊，量測代表性併發負載 | 正確憑證可完成登入，使用較弱參數的一般帳號完成雜湊升級。錯誤密碼被拒且不更新雜湊，升級不得覆蓋新密碼。新寫入使用驗收過的參數，目標部署負載符合上線前記錄的資源與延遲上限。 |
