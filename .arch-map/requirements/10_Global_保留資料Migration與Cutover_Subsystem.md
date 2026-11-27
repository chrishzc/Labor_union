# Global Preserve-data Migration／Cutover Subsystem

## 1. 文件邊界與所有權

- 狀態：`current-spec`
- Owner：Global Migration Infrastructure Subsystem
- 單一負責範圍：跨環境資料庫保留升級（preserve-data migration）、Schema State Classification（`absent | exact | resumable_partial | drift`）、Release Manifest 與 Descriptor 驗證契約、Candidate Verification、Configuration Switch／Rollback，以及 Agent／開發者 DB 變更七道執行門（§9）與本機開發庫受控驗收規範（§9.1）。
- 關聯引用：見 [Global 共同契約](00_Global_共同契約.md)、[Client Finance Domain](04_Client_Finance_Domain.md)、[NAS Fresh 初始化與維護復原規格](10A_NAS_Fresh初始化與維護復原規格.md)、[Global Deployment 與治理](18_Global_Deployment與治理正式規格.md)、[Global Entry Point Governance](19_Global_Entry_Point_Governance.md)、[Controlled File Storage NAS](30_Controlled_File_Storage_NAS正式規格.md)、[案件與月嫂整合名冊](33_案件與月嫂整合名冊正式規格.md)。

## 2. 定位與 SSOT

本 Subsystem 是 Global 基礎設施能力，不屬於任何業務 Domain。本檔擁有保留資料升級與切換契約：在不更動唯讀 source database 的前提下，建立、驗證並切換至新 candidate database，不負責業務資料補猜、ledger 修復或自動刪除來源庫。遷移是在新候選庫套用並驗證發行內容；切換是把應用程式指向已通過驗證的候選庫。只完成遷移或驗證，不代表已切換。Windows 備份復原另依 [同名復原契約](10A_NAS_Fresh初始化與維護復原規格.md#windows-same-name-restore)。

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

## 3. 核心安全不變量

以下來源庫唯讀、candidate 保留與 `.env` 切換不變量適用於保留資料升級與切換；Windows 備份復原的目標替換與暫存物清理以 [同名復原契約](10A_NAS_Fresh初始化與維護復原規格.md#windows-same-name-restore) 為準。

1. Source database 全程唯讀（禁止 DDL、`UPDATE`、`DELETE`、`TRUNCATE`、`DROP`），並與寫入 candidate 分採獨立權限主體（principal）。
2. Candidate 必須是明確的新建 database，禁止以 `DROP candidate` 作為重跑或清場策略。
3. Backup digest、source identity 或 restore tool evidence 不符即 fail closed。
4. Schema part 狀態僅為 `absent | exact | resumable_partial | drift`；`drift` 與未知 partial 一律停止，僅 versioned descriptor 明定之 statement boundary 可續跑。
5. 因 MySQL DDL 具 implicit commit 特性，每個 DDL statement 前後必須寫入 durable journal。
6. Candidate 驗證須涵蓋 columns、indexes、constraints、triggers、views、routines、events、row counts、primary keys 與 deterministic full-row fingerprints。
7. Plan 至 switch 期間須持有 maintenance／write-freeze token（source 異動即判定 stale）。
8. `.env` switch 僅原子修改唯一 `DB_DATABASE`，其餘 bytes 與註解不變；切換前重驗 fingerprint 與 config digest；切換後重啟 API、管理端前端、Watcher／worker 並完成 read smoke 方標記完成；Rollback 僅切回原庫而不刪 candidate。
9. `db/schema.sql` 與 `scripts/init_db.py` 屬 fresh bootstrap 工具，preserve-data workflow 嚴禁呼叫；所有 receipt 不得包含 credential、完整 `.env`、PII 或銀行 raw payload。
10. **本機受控清空重建（`scripts/launchers/reset_DB.bat`）**：僅於開發者明確捨棄 localhost `union_db` 資料時執行，強制輸入 exact `RESET` 與通過靜態 hash-locked compact schema（見 [共用精簡新庫結構規格](10A_NAS_Fresh初始化與維護復原規格.md#3-nas-新庫結構精簡與退役清單)）驗證，不載入業務 fixture；DROP 前必須使用 TOTP encryption keyring 建立加密之 root-only backup（完整保留 root 帳號、designation、encrypted MFA factor／key version／counter、recovery-code consumed facts、enrollment challenges 與必要 LINE identity parent FK，缺 key／factor 即 fail closed），重建後依 FK 還原驗證後方回 committed receipt；DDL 失敗保留加密備份並回報路徑。

## 4. Subsystems 與核心模組

### 4.1 Release Manifest 與現行 Canonical Chain

- Canonical release chain／catalog 明確列出所有允許交付版本，禁止以 glob 或檔名排序猜測最新版本。
- 現行預設鏈結選取 `labor_union_2026_11_05_subsidy_identity_preservation_v5.json`（沿用 `1055_government_subsidy_periods.sql` 與 owned descriptors，且 `backfills=[]`）：
  - **補助身分與帳務保留契約（`IDENTITY-FIX-04`）**：一般市民、原住民、補助市民、其他既有身分與缺值一律按來源保留，政策綁定、人工更正、舊日誌與已成立帳務不可變；禁止將一般市民轉換或重算為補助市民，亦禁止因身分自動重算退款。
  - **退役回填拒絕**：現行鏈結、執行與 candidate 驗證一律拒絕 `subsidy-period-policy-v1` 及對應回填腳本，呼叫回傳 `subsidy_identity_backfill_retired` 且零寫入（舊 manifest 與歷史 receipts 僅唯讀保留於版本庫）。
  - 既有有效非身分轉換 backfill（如雙胞胎快照與 §9 HCM status backfill）照常受控管理。
- Qualification receipt 必須綁定 runner 實際選中的單一 `release_id` 與該 release canonical fingerprint，禁止以整條 chain aggregate fingerprint 冒充單一選定版本通過。

### 4.2 Preflight、Backup、Schema State 與 Runner

本機開發庫日常升級走 `scripts.update_local_database`。依 ordered release plan 判定已是現行版、可在本機原庫套用的純結構升級，或需另選隔離副本的保留資料升級。原庫直連須符合該版本資格、原庫身分、備份及續跑驗證；不以 NAS 候選、DSM 備份或部署切換為前置。既有 NAS 入口與中斷恢復規則屬相容邊界，不列入現行部署。

正式部署依 [Global Deployment §3](18_Global_Deployment與治理正式規格.md#3-正式部署拓樸)，由工會 Windows 主機在維護期間透過 loopback 維護本機 Docker MySQL。選項 7 在 `APP_ENV=production` 時直接選擇保留資料升級。來源庫唯讀，依發行鏈規劃、備份、還原副本、升級及驗證。切換前須核對保留資料、精確結構及實際目標；切換後仍保留原庫及其資料。

- **Preflight／Backup**：`DatabaseIdentityReader`、`SourceReadOnlyGuard`、`CandidateAbsenceGuard`、`CutoverPlanFingerprint`、`MySqlDumpCommandBuilder`、`AtomicBackupPublisher`、`RestoreEvidenceValidator` 產生 zero-write plan 與驗證備份還原。
- **Schema State Classification**：Descriptor 須同時列明新表及 `altered_tables` 新增／修改欄位與完整 metadata（type、nullability、default、generated expr、index、FK、check）。Parent-table ALTER 不擁有 parent 既有物件；較早 artifact 遇到後續 canonical release 加入的物件僅依「successor artifact identity ＋ 完整契約」allowlist 視為相容，契約不符仍判 `drift`。1060 條件式 trigger 採 hash-bound predecessor／successor 定義（`db/migration_releases/labor_union_2026_10_29_registry_case_deletion_guards_v1.descriptors.json`），共用 SQL loader 採 quote／comment-aware `DELIMITER`。
- **Additive Migration Runner**：
  ```text
  append prepared journal → verify prior journal & metadata → execute 1 statement
  → fresh-read metadata → append applied/exact/failed journal → classify part state
  ```
  - Journal identity 綁定 `source_database + release_id`（不混用先前 release 鏈）；每次 Apply 前須建立該機器專屬之 release-scoped mysqldump 與 local backup receipt（缺原始備份／身分不符回 `backup_required`；schema 已 exact 但既有同 release journal 未完成回 `verification_incomplete`）。
  - **計時與逾時保護**：前置驗證上限 `300` 秒、更新後驗證上限 `300` 秒、單條 DDL 上限 `30` 秒、等鎖上限 `5` 秒、單次 socket 上限 `30` 秒；local receipt 與 completed journal 紀錄 `phase_timings`，超時回 `preparation_duration_exceeded`／`blocked_duration_exceeded`／`verification_duration_exceeded`。若 DDL 結果未明，須先核對該版本的 durable journal 與新讀取的 metadata；只有符合 §3 明定的可續跑邊界才續行，不盲目重跑。
  - schema-only fast path 限 `localhost` development／validation 非 MySQL 系統 schema，遠端與 production 一律拒絕。
  - Windows 遠端 NAS 曾誤入 fast path 而中斷 1080 時，僅接受原 journal 的連續已驗證 canonical 前綴及完整原始備份。先驗證原備份的完整性、來源身分與資料指紋，再以該備份保存的原始 trigger 定義重建 1079 基線，須符合 journal 的原基線完整 schema SHA；不得假設伺服器保存的 SQL 排版與專案 SQL 原文相同。基線 trigger 順序須沿原 MySQL metadata 欄位的排序規則，包含原備份中已被 DROP 的名稱，不得改用 Python 字串排序。已套用 CREATE 的 trigger 以既有 canonical SQL 契約比較，再使用現況原始定義及快照原順序重建已驗證前綴，須符合現況完整 schema SHA。此證明只授權該次新副本恢復實際受影響的 guard parts，納入原 plan fingerprint 並於 Apply fresh-plan 再驗；不得改寫原庫或歷史紀錄、隱藏其他 partial／drift，或略過結果未明的 DDL。
- **Candidate Backfill／Validation／Switch**：Backfill 先 dry-run 驗證 affected rows 與 before／after fingerprint；不可唯一轉換者進 bounded `legacy_unresolved`；Switch 使用 `SwitchStateReconciler` 核對 before／after `.env` hash 決定 crash window 狀態。

## 5. Commands、Stable Errors 與交易邊界

- **Commands**：`PlanPreservedDatabaseCutover`、`CreateCandidateFromBackup`、`ApplyAdditiveSchemaToCandidate`、`ValidateCandidateDatabase`、`SwitchApplicationDatabase`、`RollbackApplicationDatabaseSwitch`、`QueryCutoverReceipt`、`RecoverInterruptedDatabaseSwitch`。
- **Stable Errors**：`source_identity_mismatch`、`source_not_read_only`、`candidate_already_exists`、`backup_receipt_mismatch`、`restore_evidence_mismatch`、`schema_partial_not_resumable`、`schema_drift_detected`、`statement_receipt_conflict`、`candidate_data_mismatch`、`config_identity_conflict`、`config_digest_conflict`、`switch_receipt_missing`、`switch_state_ambiguous`、`post_cutover_health_failed`、`external_tool_failed`、`subsidy_identity_backfill_retired`。
- **交易邊界**：inspection／plan 零寫入；backup 為 artifact digest 邊界；DDL 為逐 statement durable journal 邊界；validation 只寫 receipt；`.env` switch 為單檔 atomic replace；rollback 僅新增 switch receipt。

<a id="9-agent-與開發者-db-變更執行門"></a>

## 6. Agent 與開發者 DB 變更執行門（§9）

凡 diff 或規格涉及 table／column／constraint／index／trigger／view／seed／backfill，必須依序通過七道執行門，任一缺失回報 `DB_CHANGE_NOT_READY`（結果狀態只採 `pass` / `blocked` / `not_run` 並附 evidence）：

1. **Scope**：確認 business scenario、owner、current spec 與 approved scope（缺則 `BLOCKED_SCOPE`）。
2. **Change inventory**：區分 `schema-only`、`system-seed`、`business-row-backfill`、`destructive` 各自來源與重播契約（缺則 `BLOCKED_CLASSIFICATION`）。
3. **Static release**：schema part、fresh assembly、canonical release chain、manifest hash、descriptor 與操作文件互指一致。
4. **Descriptor**：新表與 altered parent 驗完整欄位與約束，明確區分 `absent | exact | partial | drift`。
5. **Read-only plan**：使用 `.\.venv\Scripts\python.exe -m scripts.update_local_database` 輸出零寫入 plan（先檢查 backfill 再看 schema qualification；不復活退役身分回填）。
6. **Engine verification**：實機 MySQL 通過 unit／plan 測試、空白庫 fresh bootstrap 與 source → dump → candidate → apply → verify（無真 MySQL 證據則 `BLOCKED_ENGINE_EVIDENCE`）。
7. **Developer acceptance**：驗證 launcher 與 source backup、candidate receipt、preservation、exactness 與 rollback evidence。

- **HCM 審核狀態獨立升級與回填**：`labor_union_2026_11_06_hcm_review_status_v1.json`（`1069_hcm_review_status.sql`）僅新增 nullable 欄位（無 system seed 或自動回填）。具備原始 HCM Excel 之開發環境透過 `python -m scripts.backfill_hcm_review_status <Excel...> [--apply --confirm-database <db>]`（限 localhost `union_db`／`lu_test_*`）預覽 SHA-256 後僅補寫空白欄位，衝突或重複維持原值。
- **BeClass 多案配對升級**。`labor_union_2026_11_12_client_beclass_query_case_v1.json` 以一個 ALTER 替換 `beclass_records` 的唯一索引，保留既有列、主鍵與查詢索引，無種子或回填。部署與驗證須搭配支援多案配對的 API。一旦同一查詢序號已有多案紀錄，保留新索引及資料，使用相容版本向前修復。
- **歷史未結案的條款收據升級**。`labor_union_2026_11_12_historical_open_terms_receipts_v1.json` 以 `1074_historical_open_order_terms_receipt_status.sql` 在既有狀態值尾端追加「歷史訂單－未服務」與「歷史訂單－服務中」，保留原狀態順序、收據與案件資料。新建與保留資料升級均採同一欄位契約。

- **客戶存摺封面受控檔案**。 `1075_controlled_file_client_passbook_cover.sql` 將現有 `clients / client_passbook_cover` 配對納入兩張受控檔案表的發行契約。新建與保留資料升級採相同結構，保留既有檔案紀錄及版本鏈。完整符合新版欄位、檢查限制與版本外鍵的既有庫不重跑此變更，未知或不完整結構仍阻擋。

- **月嫂暫停接案原因改為選填**。`labor_union_2026_11_13_staff_availability_optional_reason_v1.json`（`1076_staff_availability_optional_reason.sql`）將 `scheduling_staff_unavailability_blocks.chk_scheduling_staff_unavailability_reason` 放寬為僅檢查 `CHAR_LENGTH(TRIM(created_by)) > 0`，與既有 Domain／UI 選填備註契約一致，保留既有列與其餘約束；新建與保留資料升級採相同檢查條件。

- **LINE 案件群組歷程刪除保護**。`labor_union_2026_11_15_line_order_group_history_delete_v1.json`（`1078_line_order_group_history_delete_guards.sql`）精確更新兩個群組事件刪除 trigger，保留既有案件刪除條件，並允許有同案、尚未完成的群組歷程刪除命令且目前無群組綁定時逐案刪除。升級本身不刪除任何既有資料。新建與保留資料升級採相同 trigger 契約。
- **案件永久刪除支援已簽約案件**。`labor_union_2026_11_20_registry_case_deletion_signing_v1.json`（`1080_registry_case_deletion_signing_guards.sql`）移除 trigger 的簽回狀態判斷。更新包含 `1060` 的案件歷程 guard 及 `1078`、`1079` 後續覆蓋版本，保留 pending claim、資料歸屬、LINE 群組歷程及保留期清理條件。Fresh 與保留資料升級使用相同定義。升級只更新 schema，切換後須載入同版本 NAS 固定程序。

- **成立後未服務狀態**。`labor_union_2026_11_23_order_established_unserved_v1.json` 以 `1081_order_established_unserved_status.sql` 在 Orders、Terms 收據與取消收據的狀態 enum 尾端追加「成立後未服務」，並擴充 lifecycle event 的 before／after 檢查限制。此版本只有 schema widening，不回填案件、不重做取消、收付款或 payroll。Fresh assembly 與保留資料升級使用同一 artifact；執行仍須通過上述七道門，正式切換前保留候選與來源回復證據。

- **月嫂有效應付 0 元投影**。`labor_union_2026_11_24_staff_payable_projection_zero_v1.json` 以 `1084_staff_payable_projection_zero.sql` 替換同名金額 CHECK。有效應付允許 0 元，淨實付仍須為非負，差額仍須等於有效應付減淨實付。升級保留狀態 CHECK、付款資料與所有既有列。Fresh 與保留資料升級使用同一 artifact。精確舊 CHECK 待升級，精確新 CHECK 重跑零寫入。已存在的應付投影表若缺少金額 CHECK、未啟用或定義不符，停止升級。產生有效應付 0 元列後，應保留新版 CHECK 及資料並向前修復。

- **FAQ 永久刪除**。`labor_union_2026_11_27_faq_permanent_delete_guard_v1.json`（`1088_faq_permanent_delete_guard.sql`）更新知識版本的刪除觸發器。新建庫及現行 Windows Docker MySQL 的保留資料升級採相同定義，完成升級時須確認既有題目、版本及事件仍在。1087 來源的觸發器符合發行描述才套用 1088。已符合 1088 的副本重跑時跳過該項 DDL。需套用 1087 的來源依發行鏈先執行該版既有的 FAQ 回填與驗證。題庫刪除另經 Knowledge 交易執行，規則見 [LINE FAQ](29_LINE服務說明、客服互動與選單角色正式規格.md#41-共用問答與聊天室版面)。
- **1088 中斷續跑**。隔離副本在移除既有觸發器後中斷，須核對原備份、同一來源及副本的識別、發行與 DDL 收據、資料指紋和目前結構。證據證明僅該移除步驟已生效時，續行建立觸發器，再走正常的副本驗證。證據不足或有其他結構差異時停止該副本，保留來源及維護記錄供重新規劃。驗收以隔離 MySQL 注入中斷後走同一續跑入口，並在同一驗證完成的副本核對合法 FAQ 刪除、原有生效答案及其他題目。

### 6.1 本機開發 DB 受控驗收（§9.1）

- 僅限 `APP_ENV=development`（或等價 validation profile）與 `localhost` 之 `union_db` 或 `lu_test_*`；每次執行前必回讀 environment、host、database 與 credential class（目標不符 fail closed）。
- 核准範圍內可使用開發 credential（含 root）透過既有正式 Query／Preview／Apply 寫入具唯一 `scenario identity` 之測試資料並保存 before／after readback 與 receipt；嚴禁擅觸 scope 外資料、production、未核准 DDL、reset、source replacement、`--switch` 或全庫清除。

## 7. 驗收標準

1. Module 驗證 SQL splitter（含引號內分號）、descriptor exact／partial／drift（parent existing metadata 與 successor allowlist）、`.env` round-trip 與 fingerprint 衝突。
2. Subsystem 與 Global 真實 MySQL 驗證 source read-only、備份／還原 digest 保護、statement 中斷續跑、crash-window `.env` hash 核對、rollback 不刪 candidate，以及每個 release 均同時通過 fresh empty DB bootstrap 與完整 `source → dump → candidate → latest release → verify`。切換中斷時核對收據是否存在及其內容，並比對 `.env` 前後雜湊；收據缺失或狀態不明分別參照 §5 的 `switch_receipt_missing`／`switch_state_ambiguous`。回復原庫後確認候選庫仍保留。
