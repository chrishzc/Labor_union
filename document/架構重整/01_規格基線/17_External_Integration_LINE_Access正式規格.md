# LINE、Access Control 與 Knowledge Retrieval 正式規格

## 1. 文件邊界與所有權

- 狀態：`current-spec`
- Owner：External Integration Boundary、Access Control Domain、Knowledge Retrieval Domain
- 單一負責範圍：外部平台整合共同安全不變量（`SystemPrincipal`、去敏安全回條、durable inbox／outbox 與 Reply 5xx 不確認處理）、Access Control（統一業務授權、單一 enabled `root` 生命週期、兩段式登入／MFA、8 小時 session 上限、統一網頁建帳 bootstrap 與離線 root 重置、NAS DB P01–P10 受限權限程序與 worker TLS 憑證、`Security Audit` 兩年遮罩查詢與歸檔、`Data Browser` 六源相容唯讀契約），以及 Knowledge Retrieval 審查發布與來源 citation 契約。
- 關聯引用：見 [Global 共同契約](00_Global_共同契約.md)、[Global Migration 與 Cutover](10_Global_保留資料Migration與Cutover_Subsystem.md)、[LINE Gateway、Inbox 與通知投遞](17A_LINE_Gateway_Inbox與通知投遞正式規格.md)、[Case Import 與非市民 Redis 待審](17B_Case_Import與非市民Redis待審正式規格.md)、[Global Deployment 與治理](18_Global_Deployment與治理正式規格.md)、[Global Entry Point Governance](19_Global_Entry_Point_Governance.md)、[LINE 客服與月嫂自助服務](20_LINE客服與月嫂自助服務正式規格.md)、[Access Control Production Cutover](25_Access_Control_Production_Cutover與External_Security_Alert正式規格.md)、[Controlled File Storage NAS](30_Controlled_File_Storage_NAS正式規格.md)、[案件與月嫂整合名冊](33_案件與月嫂整合名冊正式規格.md)。

## 2. Global External Integration Boundary

### 2.1 共同安全不變量

1. 外部平台 Adapter 僅驗證、正規化並保存事件；外部 payload、URL、actor、case mapping 與 provider status 一律視為不受信任輸入，絕不直接寫入 Orders status、服務日期、排班、金額或付款狀態。
2. Ingress 先寫入無敏感 raw payload 的 request-level security receipt（驗簽失敗只入隔離／頻率指標）；驗簽與格式通過後立 durable inbox event，由獨立 consumer 轉呼 owning Domain typed command。
3. Egress 僅經已提交 outbox／durable delivery task 發送（HTTP request 或畫面渲染不得直呼外部 provider；專員申請即時回覆僅限當次 LINE Reply API，遇 HTTP 5xx 回傳 `line_reply_outcome_uncertain`，嚴禁自動重試或回退補發 Push）。
4. Provider event 與下游 Domain command 使用獨立 idempotency identity（同 key＋同 payload 為 exact replay，同 key＋異 payload 固定 409 quarantine）。
5. Consumer 採固定 `SystemPrincipal`（僅含固定服務識別、版本能力與來源 event identity；禁止由 UI／webhook 指定），不可覆寫需要人工裁決的 blocker。

### 2.2 Provider-Neutral Ports 與 Typed Errors

- **Ports**：`ExternalSignatureVerifier`、`ExternalEventNormalizer`、`DurableInboxRepository`、`DurableDeliveryQueue`、`ExternalEventConsumer`、`DomainCommandGateway`、`ProviderDeliveryGateway`、`ExternalEvidenceArchive`、`IntegrationClock`（LINE 與 BeClass 共用介面契約但隔離 payload 表與 idempotency namespace）。
- **Global Errors**：`external_signature_invalid` (401)、`external_payload_invalid` (400/422)、`external_event_duplicate` (回原回條)、`external_event_conflict` (409+quarantine)、`external_mapping_not_found` (404)、`external_mapping_ambiguous` (409)、`external_provider_unavailable` (503 retryable)、`external_retry_exhausted`、`integration_storage_unavailable` (503)。

## 3. Domain：Access Control

### 3.1 統一業務授權與 NAS 分層隔離

- **全體內部人員同等業務權限**：所有已登入且 `enabled` 的內部使用者擁有完整業務功能集合（包含刪除假日／資格／偏好、替換匯入／虛擬帳號／排班、異常重查、封存與知識清理）；不以職稱、部門或 role bundle 做業務功能差異授權。唯「帳號中心」僅供唯一 enabled `root` 使用（非業務權限差異）。
- **人工操作極簡化互動**：依 [Global 共同契約 §2.4](00_Global_共同契約.md#24-管理端一次點擊送出與選填原因)，內部寫入操作改採一次點擊送出、原因選填。
- **NAS 資料庫權限分離（`NAS-DB-01～03`）**：日常執行帳號無直接 `DELETE`／`DDL`／`GRANT OPTION`／`CREATE USER`；刪除一律透過專用不可登入 DEFINER 預存程序 `P01`–`P10` 執行（P01 日期、P02 資格／交通差、P03 六項關聯、P04 偏好集合、P05 歷史人員替換、P06 案號虛擬帳號 mapping、P07 被替換排班世代、P08 失效異常投影、P09 過期已封存 audit、P10 核准刪除之 knowledge target），不自開 COMMIT／ROLLBACK；runtime profile 持有作用域內 `LOCK TABLES` 供 `FOR UPDATE` 鎖定讀取。LINE 對外帳號僅讀寫 LINE 自身必要邊界，嚴禁持有 `P01`–`P10` 或管理端寫入憑證。
- **Worker 機器身分隔離（`NAS-WORKER-01～02`）**：NAS production 使用 `nas_service_token`（逐服務獨立憑證＋隔離網段 HTTPS/mTLS，嚴禁攜帶 DB 帳密或以 `X-Internal-Service-Name` 冒充他服務）；私人操作僅於隔離網路開放，Local 開發共用金鑰嚴禁延伸至正式環境。
- **禁止 legacy key**：human mutation 嚴禁接受 `X-Legacy-Shared-Key`。

### 3.2 根事實、登入、統一網頁 Bootstrap 與離線 Root 重置

- **根事實與狀態機**：管理員帳號（`enabled ↔ disabled`，`root` 不可停權／降級／線上轉移）、10–256 字元密碼 hash、加密 TOTP factor（`unbound → enrollment_pending → active → rotated | revoked`）、single-use recovery code、password／enrollment challenge（`issued → consumed | expired`）、hashed session token（最多 `8` 小時絕對有效期、無閒置續期，缺期限 fail closed）及 hashed rate-limit 記錄。
- **兩段式安全登入**：Stage 1 驗證帳密；未綁 MFA 時 `POST /api/v1/admin/auth/login/challenges` 回 HTTP `200` `mfa_enrollment` 短效 challenge＋provisioning URI（限記憶體畫面顯示，禁進錯誤回應／log／URL／WebStorage），已綁定回 `factor_verification`；Stage 2 驗 TOTP／復原碼建立 bearer session。兩段錯誤一律回泛化 `invalid_credentials_or_factor` 或 `429`。
- **統一網頁首次建帳 Bootstrap（`GET／POST /api/v1/admin/setup`）**：
  - 不分主機環境皆以 MySQL `admin_root_account` 是否存在 `root` 決定首次設定（全面移除環境變數自動建 root 分支；需同源與 HTTPS 或 loopback）。
  - `bootstrap_root_admin` 於同一 UoW 建立 `root` 與 `enrollment_pending` factor（競爭回 `409`）；流程固定「建 root → 立即顯示 QR → 驗證綁定 → 保存復原碼 → 清除機密返回登入頁」。缺少 TOTP 加密金鑰須停機執行離線工具 `scripts.configure_initial_totp_key --apply`（確認空帳號與空安全表後原子寫入 `.env`，不於網站啟動時自動生鑰）。
- **錯誤初始 Root 本機離線重置（`scripts.reset_incomplete_root_setup`）**：僅限 `localhost` development／test（`union_db`／`lu_test_*`），確認安全版本仍為 `1`、零登入／LINE 綁定／業務 FK 且人工輸入 `RESET ROOT <database> <id>` 後，於單一 UoW 移除未完成建帳狀態並保留稽核記錄（禁止新增 HTTP 重置或 break-glass 端點）。

### 3.3 帳號指令、Security Audit 與 Data Browser 相容查詢

- **Commands & Errors**：僅限 root session 操作 `CreateAdminUser`、`DisableAdminUser`、`EnableAdminUser`、`RevokeAdminSessions`、`RotateAdminCredential`、`ResetAdminMfa`（綁定 expected version 與 idempotency key）。Errors：`authentication_unavailable` (503)、`invalid_internal_service_credential` (401)、`missing_or_invalid_admin_session` (401)、`admin_session_expired` (401)、`admin_user_disabled` (401/403)、`admin_version_conflict` (409)、`security_audit_persistence_failed`。
- **Security Audit 兩年遮罩查詢**：帳號中心已移除「安全操作與登入稽核」分頁。管理員登入、線上帳號與 MFA 管理，以及一般管理 API 操作停止追加 `admin_audit_logs` 紀錄及由該紀錄產生的告警。登入限流保留雜湊後的失敗計數，帳號命令保留冪等收據。離線 root 維護與各業務領域專用證據依原契約保存。所有 enabled 管理員皆可透過既有唯讀 API 免填原因查閱最近 2 年之遮罩稽核摘要與明細（遮罩 IP、token、password、LINE ID、電話、身分證）。既有紀錄保留，超過 2 年由每日排程轉入非對外唯讀封存（不自動刪除）。
- **Data Browser 六源相容唯讀查詢**：`GET /api/v1/admin/data-browser/sources/{source_id}` 僅接受 `orders | clients | staff | beclass_intake | hcm_review | bank_facts` 六個列舉，limit `1..100`，嚴格遮罩輸出（`bank_facts` 金額遮罩且不外洩帳號／對象／指紋）；管理端日常導航 `#data-browser` 依 [整合名冊規格](33_案件與月嫂整合名冊正式規格.md) 導向客戶名冊，原 raw table metadata 入口（`GET /api/v1/admin/data-browser/{table}`）與 generic PATCH 維持退役移除。

## 4. Domain：Knowledge Retrieval

- **責任與邊界**：擁有 FAQ／政策來源、content digest、版本與核准索引 freshness；嚴禁修改業務根事實或讓無來源模型輸出充當業務命令、報價與法律依據。
- **狀態機與分權核准**：Knowledge Item 為 `draft → reviewed → published → retired`；**內容建立者不得自審或自發發布（必須經他人覆核發布）**，僅 `published` 條目可進入檢索；來源異動立即標示 index `stale` 並於查詢明確降級轉人工，禁止無 citation 回答。
- **Query／Commands／Errors**：Query 回傳安全摘要、source URI、content digest、published version、index version 與強制 `authoritative=false`。Commands：`IngestKnowledgeSource`、`SubmitKnowledgeReview`、`PublishKnowledgeItem`、`RetireKnowledgeItem`、`RequestKnowledgeIndexBuild`、`RetryKnowledgeJob`、`QueryKnowledge*`。Errors：`knowledge_source_invalid`、`knowledge_review_required`、`knowledge_index_stale`、`knowledge_index_unavailable`、`knowledge_answer_unsupported`。

## 5. 驗收標準

1. Unit／Subsystem 驗證簽章與 payload 分層隔離、Reply 5xx 不確認禁止重送 Push、兩段 MFA／setup bootstrap／離線重置守衛、`P01–P10` 定點授權刪除與直接 DELETE 拒絕、Knowledge 作者不得自審發布及無來源 fail closed。
2. Global／隔離 MySQL 驗證同源 setup 競爭 409、worker 憑證防冒充、兩年稽核遮罩與 Data Browser 唯讀 6 源穩定契約。
