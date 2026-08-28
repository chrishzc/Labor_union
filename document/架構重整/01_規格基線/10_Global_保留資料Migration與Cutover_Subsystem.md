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
