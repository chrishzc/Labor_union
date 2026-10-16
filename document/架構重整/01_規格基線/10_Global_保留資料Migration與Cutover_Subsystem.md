# Global Preserve-data Migration／Cutover Subsystem

## 1. 定位

本 Subsystem 是 Global infrastructure capability，不是 Orders、Finance、Payroll 或 Anomalies Domain。

它只負責把一個既有 production-compatible source database，在不修改 source 的前提下，
建立、驗證並切換至一個新的 candidate database。

它不擁有業務資料修正、資料補猜、ledger recovery、Domain migration decision 或自動刪除舊資料庫。

## 2. SSOT

| 概念 | 唯一權威 |
|---|---|
| source database identity | server identity、database name、schema fingerprint |
| backup artifact | mysqldump bytes、digest、tool identity、receipt |
| target schema contract | versioned release manifest、ordered additive parts 與 descriptor |
| migration plan | source identity、candidate identity、part states、plan fingerprint |
| statement progress | durable per-statement receipt |
| candidate validation | schema、row、PK、fingerprint、trigger、view comparison receipt |
| config switch | exact `.env` before/after digest 與 switch receipt |
| rollback switch | original source identity 與 prior switch receipt |

Console output、README、測試名稱、候選 DB 名稱或人工記憶不是 SSOT。

## 3. 安全不變量

1. Source database 全程唯讀；不得執行 DDL、UPDATE、DELETE、TRUNCATE 或 DROP。
2. Source dump/read 使用唯讀 principal；Candidate DDL/DML 使用另一個 write principal。
3. Candidate 必須是明確的新 database，執行前不存在。
4. 不得用 DROP candidate 當成重跑或清場策略。
5. Backup digest、source identity 或 restore tool evidence 不符時 fail closed。
6. Schema part 狀態只能是 `absent | exact | resumable_partial | drift`。
7. `drift` 及未知 partial 一律停止；只有 versioned descriptor 明確允許的 statement boundary
   才可續跑。
8. MySQL DDL 可能 implicit commit；每個 statement 前後都要 append durable journal，
   不能用外層 rollback 假裝原子。
9. Candidate 驗證必須同時涵蓋 schema、owned columns、indexes、constraints、triggers、
   views、routines、events、row counts、primary keys 與 deterministic full-row fingerprints。
10. Plan 到 switch 期間必須具備 maintenance／write-freeze token；source facts 改變即 stale。
11. `.env` 只允許原子修改唯一 `DB_DATABASE`；其他 bytes、註解、引號與換行保持不變。
12. Switch 前重新驗證 plan fingerprint、source/candidate identity 及 config digest。
13. Switch 後必須 restart API、Streamlit、Watcher／worker 並通過 DB identity 與 read smoke，
    才能標記 cutover completed。
14. Rollback 只切回原 database；不得刪除 candidate。
15. Receipt 不得保存 credential、完整 `.env`、客戶資料或銀行 raw payload。
16. `db/schema.sql` 與 `scripts/init_db.py` 屬 fresh bootstrap／disposable test；
    不得由 preserve-data workflow 呼叫。
17. 開發者明確捨棄本機資料時，`scripts/launchers/reset_DB.bat` 是獨立 destructive fresh-bootstrap
   入口，只接受 localhost／development 的 `union_db`、exact `RESET` 確認與 current hash-locked schema
   assembly。它不載入業務 fixture；canonical schema artifacts 明列的 system seed 仍可建立。靜態 catalog／
   digest 預檢必須在 DROP 前完成，重建後必須驗證 validation manifest 宣告的 database objects。
   依 2026-10-12 人工指示，operator reset 必須保留既有 root 帳號完整值、root designation、
   encrypted MFA factor／key version／防重放 step、recovery-code consumed facts 與 enrollment challenges；
   root 有 LINE 外鍵時只保留其必要 identity parent。不保留 session、password login challenges 與非 root 帳號。
   DROP 前以既有 TOTP encryption keyring 加密 root-only durable backup 並確認可讀，缺 key／factor 無法解密／
   root 資料不完整時 fail closed。重建後依 FK 順序還原並比對完整值才可回 committed receipt。
   不生成固定或新的 MFA seed、不把 pending 改成 active；原本未綁定仍須完成首次綁定。
   DDL 失敗保留 encrypted backup 並回報路徑，不宣稱 rollback；保留現有 keyring 才能復原該備份。

## 4. Subsystems

### 4.1 Release Manifest

Modules：

- `MigrationReleaseManifest`
- `MigrationReleaseManifestValidator`
- `MigrationArtifactHasher`
- `SupportedSourceBaselinePolicy`

Manifest 定義 release id、支援的 source baseline、ordered schema parts、backfills、
verification queries、application compatibility、artifact hashes 與 dependencies。
程式內硬編碼固定 schema part 清單不得成為長期 SSOT。

Canonical release chain／catalog 必須明確列出所有允許交付的 release，不得以容易漏掉命名變體的
檔名 glob 或目錄排序推導目前版本。新增 schema part、altered parent column 或 seed／backfill 時，
同一變更必須更新 chain、manifest、descriptor、fresh-bootstrap manifest、開發者操作文件與驗證測試；
任一入口無法辨識最新 artifact 時，該 release 仍是 `live-drift`，不得標記 completed 或封存。
Qualification receipt 必須綁定 runner 實際選中的單一 `release_id` 與該 release 的 canonical
fingerprint。整條 release chain／bundle 的 aggregate fingerprint 只證明 catalog 組合身分，不得拿來
取代 selected-release fingerprint；兩者混用時必須 fail closed，不能以「有 receipt」解鎖 Apply。

### 4.2 Preflight／Identity

Modules：

- `DatabaseIdentityReader`
- `SourceReadOnlyGuard`
- `CandidateAbsenceGuard`
- `MigrationEnvironmentValidator`
- `SchemaPartCatalog`
- `CutoverPlanFingerprint`
- `MaintenanceWindowTokenValidator`

輸出：

- typed source identity；
- typed candidate identity；
- ordered schema part contract；
- zero-write migration plan。

### 4.3 Backup／Restore

Modules：

- `MySqlDumpCommandBuilder`
- `BackupArtifactHasher`
- `AtomicBackupPublisher`
- `BackupReceiptRepository`
- `CandidateDatabaseCreator`
- `RestoreCommandBuilder`
- `RestoreEvidenceValidator`

Backup 或 restore failure 保留 artifacts 與 bounded diagnostic receipt，但不得將 candidate 宣稱為可 migration。

### 4.4 Schema State Classification

Modules：

- `SchemaMetadataReader`
- `OwnedObjectDescriptor`
- `SchemaStateClassifier`
- `ResumableStatementBoundary`
- `SchemaDriftReporter`

每個 schema part 必須列出自己擁有的 columns、indexes、constraints、triggers 與 views。
「table 已存在」不等於 exact。

Descriptor 亦必須明列既有 parent table 被新增或修改的欄位，並驗證 column type、nullability、default、
generated expression、index、foreign key 與 check constraint。分類器忽略 `altered_tables`、只檢查新表，
或只確認 required column name 是 subset，都不得宣稱 `exact`。

Parent-table ALTER 只擁有該 artifact 明列的新欄位與 metadata object，不擁有 parent table 既存的
indexes、foreign keys、checks 或 triggers；這些既存物件不得被誤判為該 artifact 的 unknown drift。
對 artifact 自己建立的新 table，unknown owned object 仍固定 fail closed。較早 artifact 的 exactness
檢查若遇到後續 canonical release 加入的 object，只能依「successor artifact identity ＋ 完整 object
contract」allowlist 接受；同名但 columns、uniqueness 或其他契約不同仍必須判定 `drift`。每次新增會
修改既有 owned table 的 release，都必須補 earlier-artifact successor regression，不能只驗證最新
artifact 自己為 exact。

### 4.5 Additive Migration Runner

Modules：

- `SqlStatementSplitter`
- `OrderedSchemaPartExecutor`
- `DdlStepJournal`
- `SchemaPartExactnessVerifier`
- `MigrationResumePlanner`

每執行一個 DDL statement：

```text
append prepared journal
→ verify prior journal and current metadata
→ execute one statement
→ fresh-read metadata
→ append applied／exact／failed journal
→ classify part state
```

中斷後只依 current metadata 加 durable receipt 決定是否續跑，不以記憶或最後 console line 猜測。
Additive journal identity 必須至少包含 `source_database + release_id`；同一 source 的已完成舊 release
journal 保留供追溯，但不得被新 release 當成 resume chain。新 release 只能讀取自己相同 identity、
statement hashes 與 baseline schema fingerprint 的事件；identity 不同不得合併、覆寫或刪除舊鏈。

開發者本機的 qualified schema-only fast path 不以固定 DB 前綴判斷合法目標。它只接受 local host
與 development／validation profile 下的合法非 MySQL 系統 schema；remote host、production profile、
`information_schema`、`mysql`、`performance_schema` 與 `sys` 必須 fail closed。Committed
qualification receipt 只證明 selected release、SQL hash、descriptor、prerequisite 與代表性 evidence
table scope，不得把 runtime 綁到 qualification 製作環境的 database、host、port、schema fingerprint
或資料指紋。

每台機器第一次 Apply 前必須建立自己的 release-scoped 完整 mysqldump 與 local backup receipt。
Local receipt 至少綁定 `source_database + release_id + server + host + port + baseline schema
fingerprint + dump digest + representative row fingerprints`；DDL 前、取得 maintenance lock 後與
DDL 完成後都要 fresh-read 驗證。若同一 journal 已開始但原始 local dump／receipt 遺失、不完整或
身分不符，固定以 `backup_required` 停止，不得重做新備份冒充原始 baseline。唯讀 plan 不建立 dump。

### 4.6 Candidate Backfill

Modules：

- `BackfillPlanBuilder`
- `BackfillPlanFingerprint`
- `BackfillExecutor`
- `BackfillReceiptRepository`
- `BackfillVerifier`

Backfill 必須先 dry-run，綁定 candidate identity、source facts、expected affected rows 與
before／after fingerprint。Apply 使用單一或明確 bounded transaction，exact replay
回原 receipt；不得在 DDL runner 內隱藏資料補猜。

System definition seed 可與 schema release 同版，但必須在 metadata 中獨立標示；從既有業務資料
建立新 root／profile／event／review row 屬 backfill，不得偽裝成 schema-only 或 system seed。
無法唯一轉換的 row 必須進 bounded unresolved review，且 migration completion receipt 必須記錄
converted、unresolved、skipped 與 replay counts。開發者本機 backfill 授權不等於 production data
migration 授權。

### 4.7 Candidate Data Validation

Modules：

- `SchemaContractVerifier`
- `RowCardinalityVerifier`
- `PrimaryKeySetVerifier`
- `DataFingerprintVerifier`
- `TriggerContractVerifier`
- `ViewContractVerifier`
- `LegacyProjectionCompatibilityVerifier`
- `CandidateAcceptanceReceiptBuilder`
- `ApplicationCompatibilityQueryRunner`

所有差異必須有 typed path、expected、actual 與 severity。任何受管 object drift 都阻擋 switch。

### 4.8 Configuration Switch／Recovery

Modules：

- `EnvironmentFileStrictReader`
- `DatabaseSettingLocator`
- `EnvironmentSwitchCandidateBuilder`
- `EnvironmentFileAtomicWriter`
- `CutoverSwitchReceiptRepository`
- `RollbackSwitchCandidateBuilder`
- `SwitchStateReconciler`
- `ApplicationRestartCoordinator`
- `PostCutoverSmokeRunner`

Switch 是獨立明確 Command，不由 migration success 自動觸發。寫入前後都要 strict UTF-8、
唯一 key、digest 與 target identity 驗證。Journal 採 append-only，不原地覆寫。

若程序在 config 寫入後、final receipt 前中止，`SwitchStateReconciler` 依目前 config hash
判定：

- 等於 before hash：prepared／尚未切換；
- 等於 after hash：已切換，續做 restart／smoke；
- 其他 hash：停止並交人工處理。

## 5. Commands／Results／Errors

Commands：

- `PlanPreservedDatabaseCutover`
- `CreateCandidateFromBackup`
- `ApplyAdditiveSchemaToCandidate`
- `ValidateCandidateDatabase`
- `SwitchApplicationDatabase`
- `RollbackApplicationDatabaseSwitch`
- `QueryCutoverReceipt`
- `RecoverInterruptedDatabaseSwitch`

Stable errors：

- `source_identity_mismatch`
- `source_not_read_only`
- `candidate_already_exists`
- `backup_receipt_mismatch`
- `restore_evidence_mismatch`
- `schema_partial_not_resumable`
- `schema_drift_detected`
- `statement_receipt_conflict`
- `candidate_data_mismatch`
- `config_identity_conflict`
- `config_digest_conflict`
- `switch_receipt_missing`
- `switch_state_ambiguous`
- `post_cutover_health_failed`
- `external_tool_failed`

任何 validation／identity／drift conflict 不自動 retry。只有外部工具暫時 unavailable 且目前
metadata 證明零新增效果時，才可 bounded retry；DDL 中斷必須先重新分類 metadata。

## 6. Transaction 與持久化邊界

- Source read-only inspection：零寫入。
- Backup：外部 artifact transaction，以 digest receipt 完成。
- Candidate creation／restore：獨立 infrastructure phase。
- DDL：逐 statement durable boundary，不宣稱全批 rollback。
- Candidate validation：零業務資料寫入，只新增 receipt。
- `.env` switch：單檔 atomic replace boundary。
- Process restart／smoke：獨立 post-switch phase，通過後才完成 cutover。
- Rollback switch：新的 append-only switch receipt，不改寫舊 receipt。

## 7. pytest／真實引擎驗收

### Module

- SQL splitter 保留 quoted semicolon。
- descriptor normalization 不吞掉語意差異。
- exact／partial／drift 分類。
- parent-table 既有 metadata 不會被 ALTER artifact 誤判為 owned drift。
- 後續 canonical release 的精確 successor metadata 可共存；同名錯誤契約仍 fail closed。
- `.env` quoted value、註解與 newline round-trip。
- fingerprint deterministic 與 stale conflict。

### Subsystem

- statement 中斷後 receipt 與 metadata 對齊。
- resumable partial 可續跑，unknown partial／drift fail closed。
- backup digest mismatch 在 restore 前停止。
- restore row mismatch 阻擋 migration acceptance。
- config staleness 在寫檔前停止。
- rollback switch 不刪 source 或 candidate。
- config publish 前後各 crash point 可由 hash reconcile。
- post-switch restart／smoke failure 不宣稱完成。
- receipts、journal 與 backup artifact 使用固定 archive policy，不由任意 CLI path
  決定唯一保存位置。

### Global

- 真實 MySQL source → dump → new candidate → additive schema → validation → switch。
- Source schema／rows／fingerprints 全程不變。
- source read-only principal 與 zero-write audit 必須有機械證據。
- Candidate exact 且完整通過後才可 switch。
- 測試只能使用明確 disposable source/candidate database；不得使用正式 `union_db`。
- Mock PASS 不能取代真實 mysqldump、restore、DDL、metadata 與 switch 驗收。
- 每個 schema release 必須同時通過：(a) 空白 disposable DB 的 fresh bootstrap；(b) 含上一支援版
  schema 與代表性舊資料的 source → dump → candidate → latest release → verify。`update_local_database`
  的唯讀 migration plan 必須列出最新 release id、待套 artifact 與任何 blocked partial／drift；
  launcher `--dry-run` 只驗證入口 wiring 與依賴，不構成 DB plan，啟動腳本成功也不構成 schema
  compatibility 證據。

## 8. 現況吸收與退出

可吸收：

- `scripts/migrate_preserved_database_additive_schema.py`
- `tests/test_preserved_database_additive_upgrade_cutover.py`
- schema parts 61、104～108 的 versioned descriptors。

開始實作前必須確認：

- migration runner 拆成上述單一職責 modules；
- 所有超過 20 行函式符合 Clean Code Rule 2 或有真實 Why；
- receipt repository 不保存 secret；
- release manifest 取代 runner 內固定 schema parts；
- source/candidate 使用分權 principals；
- append-only switch journal 可處理 crash window；
- restart 後執行 Orders、Finance Import、Scheduling、Payroll／Payables、Anomalies read smoke；
- ASUS 或其他主機的特定 row counts 只屬 acceptance evidence，不是 Global invariant；
- 舊 `system_map` 的 Task、Checkpoint、Source binding 與 timeout 不搬入新架構。

## 9. Agent 與開發者 DB 變更執行門

只要 diff、錯誤或規格出現 table／column／constraint／index／trigger／view／seed／backfill 變更，
必須依序執行下列 gate，不得先直接修改 SQL：

1. **Scope**：固定 business scenario、owner、current spec 與涵蓋本次 write set／acceptance 的 approved
   package。缺少 scope 時為 `BLOCKED_SCOPE`。
2. **Change inventory**：分開列出 `schema-only`、`system-seed`、`business-row-backfill`、
   `destructive` 的 source、target、data effect、replay、rollback 與 unresolved policy。無法分類時為
   `BLOCKED_CLASSIFICATION`。
3. **Static release**：schema part、fresh assembly、canonical release chain、manifest hash／dependency、
   descriptor 與操作文件必須互相引用；runner 實際解析的 latest release 必須包含本次 artifact。
4. **Descriptor**：新表與 altered parent columns 均驗完整 columns、indexes、foreign keys、checks、
   triggers 與 views；`absent | exact | partial | drift` 可機械區分，未知 partial／drift fail closed。
5. **Read-only plan**：launcher `--dry-run` 只證明 wiring；真正 plan 使用
   `.venv\Scripts\python.exe -m scripts.update_local_database`，必須列 latest release、待套／續跑／exact
   artifacts 與 blocked reason，且零 DB 寫入。
6. **Engine verification**：先跑 metadata／manifest／plan focused tests，再以 disposable DB 驗 fresh
   bootstrap，最後以含上一支援版 schema 與代表性舊資料的 source 驗 dump → candidate → apply → verify。
   schema／migration 沒有真 MySQL evidence 時為 `BLOCKED_ENGINE_EVIDENCE`，mock／compile 不能取代。
7. **Developer acceptance**：前六項 PASS 後才驗本機 launcher；保存 source backup、candidate／replacement
   receipts、舊資料 preservation、new object exactness、unresolved rows 與 rollback evidence。

每次 DB 變更交付輸出一張 gate table，狀態只用 `PASS | BLOCKED | NOT_RUN` 並附 evidence path／command。
任一必要 gate 為 `BLOCKED`／`NOT_RUN` 時，總結固定 `DB_CHANGE_NOT_READY`。

### 9.1 既有開發 DB 的受控驗收

依 2026-08-21 人工裁決，一般 API／UI／Domain 驗收不再強制 disposable DB 或 non-root：

- 只允許 `APP_ENV=development` 或等價 validation profile；database 可為 `lu_test_*`，或 localhost 上的
  `union_db`。每次先回讀 environment、host、database 與 credential class，target 不符即 fail closed。
- 可使用目前 development credential（包括 root）執行 approved package 明列的 Q／P／A、API、browser、
  worker replay 與 scenario-owned 測試資料 mutation。使用唯一 scenario identity、before／after readback、
  receipt 與 scoped cleanup；不得碰其他 rows。
- localhost development 的 `union_db` 可在 current task 明確 business scenario 與 row scope 內直接異動；
  已有 owner Query／Preview／Apply 時須使用正式 writer 並保存 before／after、idempotency 與 receipt。
- 仍禁止 production DB／provider、未核准 DDL／migration／seed／backfill、reset、source replacement、
  `--switch`、全庫清理與其他超出 current scope 的破壞性操作。
- schema／migration 仍須完整通過 disposable fresh-bootstrap 與 preserve-data candidate gates；既有 DB
  runtime 不能取代。
- 本裁決不擴張 package 的業務 scope、owner、public contract、external effect 或 write set；更嚴格的
  scenario data policy 繼續適用。

### 9.2 NAS 已存在空庫的首次初始化

依 2026-10-15 人工明確要求，Global migration 增加獨立的 NAS fresh-bootstrap 入口；
本段同時固定這次 bounded execution package 的範圍與驗收。入口為
`scripts/initialize_nas_schema.py` 及 `scripts/launchers/initialize_nas_schema.bat`／`.sh`。

- 只讀專案 `.env`，要求 `APP_ENV=development`、remote `DB_HOST`、`DB_DATABASE=union_db`；
  process 中存在不同的 APP_ENV／DB_* override 時停止。TLS 沿用 DB_SSL_* 設定，credential 不進參數或紀錄。
- 目標必須已存在，且沒有 table、view、routine、event。唯讀預檢與 Apply 都驗 connected identity；
  Apply 取得同名初始化 session lock 後 fresh-read 空庫條件。這個 lock 只協調本入口，operator 必須停止其他 writer。
- 唯一 schema／system-seed 來源是 hash-locked fresh assembly 及 validation manifest；先在記憶體中完成
  manifest／digest 驗證與 SQL 固定，再連線。排除 base schema 的 DROP DATABASE、CREATE DATABASE、USE，
  其餘依 canonical 順序執行，base views 沿用既有 bootstrap 的最後載入規則。出現其他 database control 即停止。
- Data-effect inventory：schema-only 與 system-seed 只重播 current canonical artifacts；
  business-row-backfill、業務 fixture、既有資料轉換、建庫／刪庫、provider、啟動服務及部署均不在範圍。
  既有 local reset／preserve-data upgrade 的 target policy 不變；不為此入口修改 SQL 或重發 release。
- Python／Unix 無參數是零 DDL／DML 的連線與空庫預檢；Windows `.bat` 無參數先委派同一預檢，
  通過後於本機詢問 Y/N，僅 Y 委派 `--apply`，N／輸入中斷取消，預檢失敗不詢問；結果按鍵後關閉。
  這依 2026-10-15 人工雙擊操作需求補上互動，不改變 writer／空庫／schema 邊界。
  除下述明確 `--interactive` 外，傳入參數時不詢問或暫停；`--dry-run` 零連線；`--apply` 重新驗證後執行。
  每個 statement 前後在 ignored scratch 下寫 durable journal，僅保存 artifact、ordinal、hash 與狀態。
  MySQL DDL implicit commit 不宣稱可 rollback；失敗保留 partial 與紀錄，不自動 DROP、cleanup、重試或續跑。
- 完成後驗 validation objects 與既有 runtime canonical descriptor/current gate；兩者通過才回報 passed。
  唯讀查核的連線上限維持 5 秒、單次查詢上限預設 30 秒，明確較短 caller budget 仍有效；不重試或放寬結構驗證。
  SQL 完成但 object/current 驗證失敗仍 blocked；安全錯誤顯示 phase、完成指令數及數字 errno，不輸出 driver 原文。
  依人工要求，所有預檢與錯誤原因整合於同一初始化入口，不要求 operator 額外執行檢查腳本。
  寫入前唯讀驗 MySQL 8.0.16+／非 MariaDB、InnoDB、server writable、SHOW GRANTS 的目前帳號／啟用角色有效
  權限（含 schema patterns 與 partial revokes）、binary log 的 trigger 建立限制、current release validation files
  及既有 metadata snapshot 查詢可執行；不建 probe table、不修改 server setting、不自動增加權限。
  CURRENT_ROLE 回傳值只解析 quoted role pairs 並重新 quote identifier，不能當 SQL 原文執行；grant 原文與帳號不輸出。
  有預檢問題即零 DDL/DML 停止，Windows 不詢問 Y/N；Apply 在確認後重新預檢，並在 metadata checks 後 fresh-read 空庫。
  預檢無法保證後續不會遇到斷線／資源變動，因此 SQL 完成後仍保留 object/current 兩層驗證，失敗直接輸出安全原因。
  目標非空時預設維持拒絕初始化；同一入口以既有 readonly current gate 解釋現有結構是否完整／查核失敗原因，
  不要求額外檢查腳本，不自動清空或續跑；已完整提示可直接啟動服務。人工明確清空路徑依下段。
  測試使用 local disposable `lu_test_*` 呼叫同一 executor，驗完整 fresh、system seed、current gate、
  非空資料與 view 拒絕、重跑拒絕及失敗紀錄；不碰本機既有 union_db 或 NAS。此入口不支援 preserve-data，
  因此驗收不執行無關的 dump／candidate／switch。真正 NAS Apply 留給 operator 明確執行。

本次 write set 限新 initializer／launchers、對應 Module tests、launcher README、本節及 migration 地圖；
沒有新 schema release，current manifest／descriptor 不改。驗收來源為本節與人工空庫初始化要求。

後續 Authority（2026-10-15）：人工確認 NAS `union_db` 只有上次初始化留下的測試資料，要求同一 `.bat`
提供確認後清空並重新初始化。本段為同一 bounded execution package 的 destructive 擴充，取代上方
僅針對明確確認 reset 操作的「不建庫／刪庫」限制；預設空庫初始化、既有資料保留升級及 local reset 契約不變。

- Windows 無參數改委派 Python `--interactive`。非空時先顯示唯讀診斷，再提供 R／N；R 只要求 reset 預檢，
  不是刪除授權。空庫仍先預檢、輸入 Y 並 Enter 才初始化。明確 `--apply` 不接受非空庫，也不啟動 reset。
- reset 預檢須驗 connected identity、同名 session lock、server／trigger policy、release／metadata，並要求
  目標 schema 層級 CREATE／DROP 權限；僅 view-specific DROP 不足。可見其他 schema incoming FK 時拒絕。
  顯示 `.env` host／port、database、server，說明整庫物件及資料不可逆刪除，要求停止其他 writer。
  只有輸入完整 `RESET union_db` 才繼續；N、空白、錯字、EOF 或輸入中斷取消均零 DDL/DML，無 reset journal。
- 確認與寫入維持同一 connection/session lock；確認後重新預檢並回讀相同 connected identity。
  先建立 durable journal，再依序 DROP DATABASE、CREATE DATABASE（保留原 default charset/collation）、USE；
  每個控制指令前後記 operation／hash／狀態，不記 SQL／credential。只作用於確認的 `.env` union_db。
  重建空庫後共用既有 compact executor／system seed／object/current gate，不複製另一份 schema 或改全域設定。
- Data effect 為 destructive schema/data replacement + canonical schema-only/system-seed；沒有業務 backfill、
  provider 或部署。既有 NAS 資料明確放棄，不自動備份／rollback；失敗不 retry 或繼續，顯示 reset_database
  或既有失敗 phase 及 journal。已刪庫但建庫失敗時也保留錯誤，不宣稱回復成功。
- 驗收限本機自行新建 lu_test_*：取消保留舊 rows、缺權限／跨庫 FK 在寫入前停止、確認後 partial 庫清空且
  compact 結構與 system seed 通過 final gate、neighbor schema/rows 保留、失敗 journal、安全錯誤及實際 Windows
  `.bat` 互動。NAS 真正清空由 operator 在視窗確認執行；Agent 不以本次開發要求直接清空 NAS。

2026-10-16 reset_database errno 2013 修正：重建連線的 read budget 改為 600 秒，避免沿用一般初始化
30 秒而提早中斷慢速 NAS DDL；connect 仍 5 秒、write 仍 30 秒，readonly metadata/current adapter 不變。
確認後、DROP 前只在該 session 設定 `lock_wait_timeout=15`；這是每次 metadata lock attempt 的等待上限，
不是整條 DDL 的總耗時保證。不修改 global setting，不 retry 或強制中止其他連線。
DROP／CREATE／USE 執行前後立即 flush operation／等待上限／耗時；失敗與 journal 保留目前 operation
及最後確認完成項。2006／2013 代表目前 DDL 結果未知，不能宣稱沒刪除、已成功或自動接續；1205 顯示
鎖等待原因及先停止 writer／結束交易再確認現況。驗收涵蓋本機真 metadata lock、慢回應 query 與既有完整 reset。

### 9.3 NAS 新庫結構精簡與退役清單（2026-10-15）

最新人工 Authority：先釐清 18 張用途不明與 15 張舊異常機制表，再整理退役清單、精簡新庫 schema；
既有資料庫先不刪表。本節取代 §9.2 的 NAS 初始化來源，保留空庫、development、identity、lock、
互動、journal、TLS 與 partial fail-closed 契約；不改 Domain business rules。

`db/schema_assembly/labor_union_fresh_table_retirements_v1.json` 是本次逐表 disposition 的 current register，
每筆保留 owner、正式規格、source evidence、replacement／migration-only 理由及 existing-data 保留政策。
包含先前 5 張明確退役候選，共核對 38 張：保留 `government_payers` singleton；其餘 37 張不進 NAS 新庫。
15 張舊異常表只承載已退役的 recovery/projector/reclassification 層，不是 Orders 歷史訂單 root／ledger；
其舊 release/schema tests 是歷史重現證據，不是新庫 requirement。政府入款／reversal／offset 與 payer 保留，
2026-10-15 已退休的政府退款出款／追償／收款帳戶表不進新庫。HCM／請假／補件／指派／projection／LINE
各自改由現行 owner 的 event／receipt／root 保存；只服務舊資料轉換的 review/event 表不進新庫。
舊 LINE binding root、leave substitution batch、staff monthly settlement 因 retained FK／歷史 Query 相依保留。

必要要求與驗收（SPEC_READY，convergence READY；無 blocking research）：

| ID | current requirement／必要驗收 | 直接證據／oracle |
|---|---|---|
| FRESH-01 | NAS 使用 final DDL＋canonical system seed，不重播 ALTER／DROP／PREPARE 升級片段 | compact SQL static shape；真 MySQL 初始化 |
| FRESH-02 | register omit 表與其 triggers 缺席，所有 retain 表／欄位／index／FK／check／trigger／view 不變 | synthetic source → compact target metadata equality；無 retained→omitted FK／trigger／view |
| FRESH-03 | system seed 的有效值／identity／relationships 等價，不帶業務 fixture／PII／credential | 來源必須由 builder 新建 local lu_test_*、執行 canonical bootstrap；seed rows 比較 |
| FRESH-04 | 舊庫 metadata／rows 不改，current gate 接受 omit 表 absent 或 historical present；現行物件 drift 仍失敗 | legacy sentinel before/after；retained column/index tamper negative |
| FRESH-05 | 空庫／非空／重跑／partial／雙擊 Y/N 契約維持 | 重用 initializer 與 Windows focused regressions |

方案（NO_RESEARCH，依已驗證的 source/model）：

- 唯一生成來源仍為既有 hash-locked assembly／validation manifest；其 SQL／preserve-release bytes 不改。
  `scripts/compact_fresh_schema.py` builder 自行建立獨立 local `lu_test_compact_source_*`，不接受既有 source DB。
  完整 canonical bootstrap 通過後，以 SHOW CREATE 匯出 retained final DDL、必要系統資料與 retained triggers/views。
  generation 不啟動 runtime／worker／provider；最後只清理 builder 自己新建的 disposable DB。
- 生成 asset 為 `db/fresh_schema/labor_union_fresh_current.sql` 與 hash-bound manifest；NAS 直接載入此一 current
  profile。manifest 綁 source assembly、validation manifest、retirement register 與 SQL bytes；來源改變就 fail closed，
  必須重生，不 fallback 回舊 replay。語法只含 final CREATE、必要 INSERT 與 session FK-check 設定。
- 建立 final tables 時 session 暫停 FK checks，資料來自同一已驗證的空庫 bootstrap；完成後恢復。
  generated columns 不 INSERT；created-at default CURRENT_TIMESTAMP 沿用執行時預設，不將生成時間固化。
  表／trigger／view 的 definer、來源 DB qualifiers 與 AUTO_INCREMENT counter 不固化部署身分；不改結構語意。
- canonical descriptor comparator 只投影掉 register 明列的 retired table-owned objects；retained descriptors 完整驗證。
  historical present 表不需 DROP，absent 表也不再成為版本落後或重建理由。沒有既有資料的 DDL／DML／backfill。
  依後續人工明確授權，本機完整初始化及 operator reset 也共用此 compact profile；preserve-data artifacts 保留。

後續 Authority（同日）：將原本本機初始化與 `reset_DB` 統一改用精簡 schema，既有資料庫升級維持原路徑、
不刪表；focused 測試通過後僅提交此 slice 並 push origin/main。完整 disposable bootstrap 的預設路徑與
reset runner 均載入同一 hash-checked compact SQL；不得再重播歷史 ALTER。明確 `base_only`／`max_schema_part`
只供既有 preserve-data predecessor／歷史重現 fixture，仍保留原 assembly，不是自動 fallback。
`init_db.py` 僅為 schema-fragment 工具 library，並無獨立可執行初始化入口；其低階歷史片段工具不改。
reset 的 localhost/development、target identity、prior plan、exact RESET、加密 root backup、MFA／recovery
preservation、terminal receipt 與失敗保留備份契約不變。只有明確 reset 才可 DROP 目標；完整初始化仍拒絕覆蓋已存在庫。
驗收沿用 FRESH-01～05，新增本機完整 bootstrap／reset 的 371 表 inventory 與 current gate、reset 前後 root/MFA/
recovery readback／登入、無確認／plan drift／非 localhost 的零 destructive effect；既有升級與歷史重現 focused oracle 不變。

本段同時為 bounded execution package：owner Global migration；write set 限 register、compact builder/asset/loader、
NAS/local bootstrap/reset plan composition、canonical descriptor retirement projection、此 owner 的 focused tests、既有操作說明與地圖。
順序為逐表裁決 → static/hash check → synthetic source generation → compact target metadata/seed/readiness →
legacy read-only preservation 與 drift negative → launcher regression。無並行 writer／Agent requirement。
效果分類：新 disposable／NAS 空庫的 schema-only 與 canonical system-seed；business backfill／既有 DB destructive
效果為零。失敗保留 journal，不修改既有 DB、不自動重跑 partial；權限、schema dependency 或 oracle 不符就停止。
這是單一 current spec 覆蓋的 PACKAGE_REUSED；generation／engine receipt 放 ignored scratch，不建立重複規格或任務文件。
