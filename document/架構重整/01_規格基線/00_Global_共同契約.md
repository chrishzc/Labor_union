# Global 共同契約

## 1. Global 的責任

Global 只定義跨 Domain 不得被破壞的不變量及共用技術契約，不擁有任何特定業務公式，也不形成可任意呼叫的巨大 Service。

共同契約包括：

- `ActorContext`
- `ExpectedVersion`
- `IdempotencyKey` 與 `IdempotencyReceipt`
- `PreviewFingerprint`
- `TypedResult` 與 `TypedError`
- `UnitOfWork`
- `BusinessClock`
- `CorrelationId`
- transactional outbox

## 2. 跨 Domain 不變量

1. 所有正式業務規則只存在後端；Streamlit 不得計算日期、狀態、工時、金額或帳務結果。
2. Query 為唯讀，不修資料、不持久化重算結果、不轉移狀態。
3. Preview 零寫入；Apply 必須在鎖定 fresh facts 後使用同一 candidate builder 重算。
4. Apply 必須驗證 aggregate version 與 Preview fingerprint；任一過期即零寫入 conflict。
5. 相同 idempotency key 與相同 canonical payload 回傳原 receipt；相同 key 搭配不同 payload 固定拒絕。
6. 正式收款、付款、退款、adjustment、reversal、服務更正及狀態事件一律 append-only。
7. 所有金額為整數新台幣。相容的 `DECIMAL(...,2)` 欄位不得讓新流程產生小數義務。
8. 客戶與月嫂是兩套獨立帳務，不要求兩端總額相等。每筆被選銀行 row 必須完整
   allocation；Staff payout 所選 obligation 必須完整核銷。Client refund 可以逐筆部分
   清償，allocation 後允許保留明確 remaining amount，但不得超額或留下不明銀行差額。
9. `actual_hours = 有效 assignment-owned 正式服務日數 × orders.service_hours_per_day`；不得 fallback 到 `planned_hours` 或 `orders.staff_id`。
10. cancelled assignment 保留歷史，但不得參與目前排班、檔期、日期、工時或薪資。
11. 服務資料鎖只在「訂單完成且客戶全部正式應付款結清」後形成，形成後不可逆。
12. 全部約定服務完成後不得取消訂單；即使服務資料鎖尚未形成也相同。月嫂薪資與服務結算按完整履約計算。
13. 所有服務日期、完成時刻及到期日政策固定以 `Asia/Taipei` 解讀；測試必須注入 clock。
14. Alert workflow 不是 Domain 門禁。Domain 直接檢查根事實；Alert 只投影同一 predicate。
15. 任何無法從根事實唯一判定原因或修復方式的問題都必須停止自動更正；系統不得自行猜測並建立 adjustment／reversal、改差額或改狀態。對人員的 current surface 依最新 owner 分類導向 `#anomalies` current issue 或 owning Domain review／work queue；不得為一般待辦建立 anomaly occurrence。
16. `#anomalies` 只對 current issue 提供足以判斷的去敏來源事實、影響範圍、建議合法操作及 Preview 入口；一般 review／work item 只顯示在 owning Domain page。兩者在人員確認後都只能呼叫 owning Domain typed command，不得直接寫 Domain 資料。
17. 人工處理的正式操作仍須遵守 Preview／Confirm／Apply、版本、fingerprint、冪等、權限、完整稽核與交易門禁。Anomalies 不使用人工 claim／resolve 作為生命週期；只有 owner root predicate 不再成立且 fresh recheck 完成時，current row 才可刪除。
18. UI 可立即顯示 local draft、loading 或 pending，但正式 Apply 只有收到 server receipt
    才能顯示成功；不得以 optimistic UI 冒充正式帳務、排班或狀態已完成。
19. Cache、read model、HTTP conditional response 與 background notification 都不是 SSOT。
    Apply 永遠鎖定 fresh facts 重算，cache unavailable 只能影響速度。
20. 長任務可回 `202 Accepted` 與 durable job identity，但 worker 仍執行同一原子
    application command；不得把 ledger、allocation、lifecycle 或 receipt 拆成多次 commit。
21. 自動化、外部 provider callback、排程與 worker 只能追加其實際觀察到的 immutable event、
    durable task 或 derived projection；不得成為唯一的業務狀態推進來源。每個會影響業務
    lifecycle 的自動化流程，owner Domain 都必須提供等價語意的受控人工入口，讓已授權人員
    以實際確認的來源事實完成同一種 root-fact transition；人工入口必須要求 actor、非空
    reason、依業務風險所需的 evidence／確認方式、fresh version、Preview fingerprint、
    idempotency 與 receipt/readback。人工入口不是任意 target-status 編輯器，不能偽造
    provider delivery、缺失文件、簽章、付款或其他根事實；只在命令驗證到足夠證據後，才可
    追加可稽核的人工確認 event。自動化未送達、未回呼或未綁定本身不得把已有合法人工
    確認途徑的案件永久卡住。

### 2.1 Durable Job canonical equality（2026-08-21 Option A）

本節是已核准的Global契約，production adoption仍須依Core、Bridge及各caller successor完成，不因文件裁決而自動生效：

- business equality固定為`command_type + command_version + canonical_payload + submitted_by`；correlation ID只供
  觀測，不參與equality。
- canonical payload只接受JSON object、string keys與finite JSON values；UTF-8 serialization固定sorted keys、compact
  separators、`ensure_ascii=False`及`allow_nan=False`。Typed schema下`1`與`1.0`是不同payload；若MySQL JSON
  round-trip無法保存此差異，Option A固定`BLOCKED_DB_SUCCESSOR_REQUIRED`。
- canonical idempotency key必須先符合`^[a-z0-9][a-z0-9._:-]{0,190}$`；uppercase在進DB前拒絕，禁止silent lowercase。
- `submitted_by`必須是immutable actor identity，例如`admin_user_id:<positive-id>`或已核准的`system:<owner>`；不得用
  display username。
- 僅於`APP_ENV`為development/dev/local/test、`ACCESS_CONTROL_PROFILE=local_bypass`且
  `ENABLE_ADMIN_AUTH=false`的本機驗收，固定可用`system:local_bypass`；production或一般無ID principal一律拒絕。
- terminal receipt/error必須使用closed command-type discriminator與schema version；禁止raw map穿透public view。
- canonical repository不得hidden commit／rollback；application composition是唯一outer Unit of Work與commit owner。

### 2.2 地端 NAS 受控檔案與投影契約（2026-08-25 人工裁決）

既有工會 NAS 是契約、月嫂履歷／證明、寶寶日誌附件、餐食照片及其他大型檔案的實體 bytes
來源；MySQL 只保存 Domain 關聯、opaque object reference、content digest、MIME、size、版本、狀態、
actor 與時間等可查詢 metadata，不保存大型 binary。各 Domain 仍擁有檔案的業務關聯、可見範圍、
完成條件與生命週期；共用檔案能力只負責受控探索、完整性核對、版本讀取與傳輸，不得藉此接管
Staff、Orders、Scheduling、Contract Signing 或 LINE 的根事實。

- 工會人員可把既有檔案移入已配置的 Domain／subject 投放區。受控 watcher／reconciliation job
  只在檔案穩定、類型／大小／digest 驗證與唯一 subject 關聯成立後建立或更新索引；未知 subject、
  重名歧義、檔案仍在寫入、digest 漂移、mount unavailable 或權限錯誤固定 fail closed 並進人工待辦。
- 投放區的可變檔名不是正式 identity。每個被接受的內容版本以系統 object identity＋digest 識別；
  同內容可 replay，同 object reference 指向不同內容固定為 conflict／anomaly，不得靜默覆寫舊版本。
- Web／LIFF 只提供去敏檔案清單或邏輯資料夾樹投影與 authenticated download；邏輯資料夾只表達
  已核准的 Domain／文件用途／subject 分類，不等於 NAS 實體目錄，也不得由前端任意拼接路徑。一般 UI、API、LINE payload、URL、
  log、receipt 不得出現 drive letter、UNC path、NAS mount path、原始 storage locator 或公開下載網址。
  檔案的實際查看／修改採「下載 → 外部工具處理 → 放回指定投放區或受控上傳形成新版本」。Web UI
  不模擬作業系統檔案總管、實體路徑瀏覽或原地編輯；只有已實際掛載 NAS 的工會地端作業環境可在作業系統操作資料夾。
- 系統傳送指定文件時，owner command 必須鎖定 subject、文件用途、版本與 digest，再建立 committed
  download receipt 或 durable delivery task；worker 讀取時重新核對相同 object identity／digest。掃描到
  檔案不等於授權發送，也不得直接呼叫 LINE 或其他 provider；檔案缺失／漂移時 delivery fail closed。
- MySQL metadata 與 NAS bytes 必須成對備份、還原與定期對帳；health 需區分 DB、mount、read、capacity、
  watcher lag 與 orphan／missing-object 狀態。NAS adapter、投放區配置、權限、retention、實際搬移與任何
  schema 變更仍須各自 Work Package／deployment／DB gate；本文件同步不授權 DDL、migration 或 production 操作。
- Controlled-file 的 exact management routes、認證、closed owner／purpose registry、opaque identity、24 小時
  staging、cleanup、receipt 與 reconciliation machine contract，由
  `document/功能開發計畫/NAS_檔案庫與資料中心管理介面正式規範.md` §9 單一擁有；本節保留 Global 不變量，
  不複製 machine fields。owner Domain／LIFF 仍須以自己的 verified identity 與 root facts 呼叫 typed port。

Runtime 狀態（2026-08-26）：`in-progress`。共用 typed port、owner-scoped metadata／version、24 小時
staging、零寫入 Preview、fresh-fact Apply／terminal replay、authenticated list／download、cleanup 與五種
reconciliation outcome 已完成本機實作；schema-only release `1004_controlled_file_storage_foundation.sql`
已通過 static／descriptor／fresh／preserve-data candidate／唯讀 developer plan gates，且未執行
`union_db`、production、replacement 或 `--switch`。focused Python `115 passed`、React `15 passed`；
fresh Chrome 的未登入／local-bypass 403 fail-closed 已確認，enabled human Session 的正向 list／download
仍待執行，因此不得把本狀態解讀為 production NAS mount、部署或 O1 最終 browser completion。

## 3. 依賴方向

```text
Streamlit
  → typed API client
    → FastAPI adapter
      → Application Workflow Coordinator
        → owning Domain typed Commands / Queries
          → Domain Modules
          → typed Ports
            ← Persistence / Provider / Queue / Cache adapters
```

- Module 不得 import FastAPI、Streamlit、requests 或資料庫 driver。
- Domain 不得 import UI 或 concrete repository。
- 跨 Domain 協調只能由 workflow/application coordinator 透過 typed ports 完成。
- 同一資料庫內要求原子性的跨 Domain 操作，共用外層 `UnitOfWork`；內層 adapter 不得自行 commit。
- Alert、通知及外部平台採 outbox，可在正式交易後重試；不得把外部呼叫放進核心交易。

## 4. Typed errors

所有 API 使用相同 error envelope：

```text
category
code
message
field_errors
domain_blockers
retryable
correlation_id
current_version
```

`category` 固定為：

- `validation`
- `forbidden`
- `not_found`
- `domain_blocked`
- `conflict`
- `idempotency_mismatch`
- `unavailable`
- `internal`

只有 `unavailable` 可提示以相同 idempotency key 重試。`conflict` 必須重新 Query／Preview；不得自動 Apply。UI 不得依 message 字串判斷流程。

### 4.1 FastAPI 管理端公開邊界

- `/api/v1/**`與`/internal/v1/**`的非2xx JSON固定使用`{"detail":{"error":{...}}}`，error只含上述
  八欄；LINE webhook／LIFF／gateway與legacy public namespace維持各自provider contract。
- request correlation header固定為`X-Correlation-ID`。缺少時server產生並在parameter validation前注入；
  唯一合法值原樣保留；非法或重複值回422且不呼叫下游、不回顯輸入。
- 既有完整typed error採response-only correlation rebase：只把公開`correlation_id`換成本request值，
  其餘七欄、HTTP status與`Retry-After`／`WWW-Authenticate`保留；不得改Domain command、receipt、audit、
  outbox、job、idempotency或持久correlation。
- legacy detail只允許Global boundary明列的code/string allowlist；未知dict/string依HTTP status去敏，禁止
  request body、credential、MFA provisioning material、raw exception或PII穿透。
- React shared transport只在完整strict八欄通過時採用server code/message/retryable；schema drift保留raw
  payload並退回HTTP status分類，不得以寬鬆cast吞掉錯誤。
- 本邊界是cross-cutting safety contract，不是所有既有typed GET page-slice的無條件migration前置；
  page-specific dependency依`PROV-20260817-react-admin-page-slice-migration-execution-decision`判定。

## 5. SSOT 類型

每個欄位或狀態必須明確歸入下列一種：

- `root_fact`：經正式命令或外部事件確認的原始事實。
- `immutable_event`：記錄曾發生的命令、付款、服務或狀態轉移。
- `derived_projection`：可由根事實重建的目前值。
- `compatibility_projection`：只服務舊 caller，禁止新流程形成依賴。
- `query_view`：跨 Domain 顯示模型，不具寫入權威。

不得把 Alert、UI session state、Excel、SQL View 或 compatibility 欄位升格為根事實。

## 6. 全域完成定義

只有同時具備下列證據，架構才可進入實作：

Activation guard：下列是 architecture readiness／future acceptance condition，不是
自動施工授權。2026-08-03 的原始核准只允許 Inventory v2；後續 production code、pytest
或其他 mutation 必須各自依人工核准的 exact-scope Work Package 執行，不能由本節自動推導。

- 十二個 Domain（Orders、Assignments／Scheduling、Payroll、Client Finance、
  Staff Payables、Government Subsidy、Finance Import、Anomalies、LINE Integration、
  Access Control、Case Import、Knowledge Retrieval）的 SSOT 與
  typed ports 不互相重疊；
- Migration、Deployment、Release、Runtime Supervision／Observability、Performance／UX
  及 Accounts Payable Export 等 Global Subsystem 不得被誤建成業務 Domain；
- 跨 Domain transaction sequence 無隱藏 commit；
- production writers 都有唯一歸屬與退出策略；
- success、failure、replay、stale、partial failure、rollback 均有對應 pytest 層級；
- live MySQL 可在隔離資料庫驗證 schema、constraint、lock、rollback 及 idempotency；
- Streamlit 只呼叫 typed API；
- 所有人工未裁決問題均不會改變即將施工的 contract。
- frontend、network、backend／DB、cache 與 background job 都有可量測 baseline、
  release budget、typed degradation 與分層驗收。

## 7. Human-assisted recovery 共同模式

```text
根事實或正式事件出現不一致
→ source Domain 產生 typed anomaly fact／blocker
→ outbox
→ Anomalies 顯示來源、影響與可執行操作
→ 人員確認實際情況
→ 呼叫 owning Domain Preview
→ 人員確認
→ owning Domain Apply
→ 新增更正／adjustment／reversal／root-fact correction event
→ projector 依新根事實自動解除或更新警報
```

- 若規格可唯一決定安全結果，Domain 可在原正式 command 內自動完成計算。
- 若原因、歸屬或修復動作不唯一，必須停在 anomaly／review，不自動選答案。
- Anomalies Domain 只組合 recovery capability，不擁有實際帳務、排班、薪資或 Orders correction。
- 每個異常代碼都必須列出 owning Domain、可用操作、必要輸入、是否阻擋及解除 predicate。
