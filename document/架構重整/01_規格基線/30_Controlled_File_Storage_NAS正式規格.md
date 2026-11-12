# Controlled File Storage／NAS 正式規格

## 1. 文件邊界與所有權

- 狀態：`current-spec`
- Owner：Controlled File Storage / Infrastructure Boundary
- 單一負責範圍：Controlled File Storage 與 NAS-backed storage 的 `FILE_PURPOSE_REGISTRY`、管理 API、Preview／Apply／receipt、Freeze-Before-Send、staging／cleanup、reconciliation、readiness、backup／restore、NAS 實體目錄架構與單一根目錄規範。
- 關聯引用：見 [Global 共同契約](00_Global_共同契約.md)、[Global Migration 與 Cutover](10_Global_保留資料Migration與Cutover_Subsystem.md)、[NAS Fresh 初始化與維護復原](10A_NAS_Fresh初始化與維護復原規格.md)、[Global Entry Point Governance](19_Global_Entry_Point_Governance.md)

本文件不授權任何特定 production NAS mount、credential、外部傳送、付款、簽署或資料庫 migration。

## 2. 核心原則

1. 所有受治理業務檔案必須經 typed Controlled File Storage boundary；不得由任意檔案上傳、前端、script 或直接 filesystem write 建立另一套正式寫入路徑。
2. DB metadata 與 storage bytes 必須可用 stable `file_id`、`version`、`purpose`、hash 與 owning business reference 對帳。
3. Preview 零 durable 副作用；Apply 才可建立正式檔案／版本或執行明確允許的 cleanup／reconciliation command。
4. 同一正式檔案 identity 不可覆寫既有 frozen revision；更正使用 additive revision 並保留 lineage。
5. 外送、列印、下載供正式用途或提交政府／合作方前，必須引用 immutable frozen artifact，不得讀取仍可變動的 live workspace 檔案。
6. NAS 只是 storage backend；「NAS 上有檔案」本身不是 business Authority、publication receipt、簽署成功或 owner state。

## 3. FILE_PURPOSE_REGISTRY 與排除範圍

系統維護唯一的 `FILE_PURPOSE_REGISTRY`，現行長期受控儲存標的如下：

- `final_signed_contract`：客戶正式簽約完成本（PDF / Excel）
- `signed_staff_agreement`：已簽約的月嫂承攬協議書（PDF / Excel）
- `staff_resume`：月嫂正式履歷書（PDF）
- `staff_certificate`：月嫂專業證照（PDF / JPG）
- `staff_health_exam`：月嫂體檢合格證明與良民證（PDF / JPG）
- `baby_log_photo`：寶寶照護日誌照片（JPG / PNG；由 Scheduling 服務紀錄使用，公開 LIFF `staff_baby_log.html` 已退役回傳 `410`）
- `meal_photo`：每日月子餐點照片（JPG / PNG）
- `rich_menu_background`：LINE 圖文選單底圖（PNG）
- `database_backup`：資料庫 SQL 快照備份（`SQL.GZ + SHA256`，正式 Windows 每日預設 18:00 觸發並寫至 NAS，時間可於 `database-backup` 修改，復原契約由 [NAS Fresh 初始化與維護復原](10A_NAS_Fresh初始化與維護復原規格.md) 擁有）

**非永久儲存排除項目**：`unsigned_contract`（待簽約草案動態產製不落地永久儲存）、紙本簽到工作單、服務日期確認書、排班行事曆圖卡與 LINE 客服對話截圖及附件，均不列入 NAS 永久儲存清單。

每個 purpose 至少定義 `owner_domain`、`file_format`、`source_of_truth`、`generation_cadence`、`db_reference`、`consumers`、`overwrite_policy`、`retention_policy`、`backup_required`、`restore_owner`；新增 purpose 須先有唯一 owner 與 typed consumer。

## 4. 正式檔案 metadata 與 Closed management routes

### 4.1 正式 record metadata

至少可 read back：`file_id`、`version`、`purpose`、`domain`、owning business `ref`、`storage_backend`、`storage_locator`、`content_sha256`、`mime_type`、`size_bytes`、`status`、`source_kind`、uploader／actor、`created_at`、`updated_at`、audit／lineage。`storage_locator` 不得被前端用來繞過 typed download boundary。

### 4.2 Closed management routes

```text
GET  /api/v1/storage/transfer-settings
POST /api/v1/storage/staging
POST /api/v1/storage/files/preview
POST /api/v1/storage/files/apply
GET  /api/v1/storage/files
GET  /api/v1/storage/files/{file_id}
GET  /api/v1/storage/files/{file_id}/download
GET  /api/v1/storage/receipts/{receipt_id}
GET  /api/v1/storage/settings
PUT  /api/v1/storage/settings
GET  /api/v1/system/database-backup
PUT  /api/v1/system/database-backup/schedule
GET  /api/v1/system/storage-retention
POST /api/v1/system/storage-retention/preview
POST /api/v1/system/storage-retention/apply
```

不得建立 generic alternate upload route、table mutation 或直接 filesystem endpoint 取代上述邊界；`staging/cleanup`（`subsystems/controlled_files/cleanup.py`、`gc.py`）、`reconciliation`（`subsystems/controlled_files/reconciliation.py`）與 `ControlledFileStoragePort.readiness()` 目前維持 subsystem／application port 邊界。

## 5. Preview／Apply／Idempotency 與 Query／Download

- **Staging 與 Preview**（`POST /api/v1/storage/staging`、`POST /api/v1/storage/files/preview`）：僅驗證輸入、purpose、owner、格式、大小、reference、readiness、預期版本與 policy，零持久寫入；條件不明確時 fail closed。
- **Apply 與回執**（`POST /api/v1/storage/files/apply`、`GET /api/v1/storage/receipts/{receipt_id}`）：使用 typed command 與 idempotency identity（exact replay 回原 committed receipt；同鍵異 payload 回 conflict），確保 bytes staging 與 DB metadata commit 一致，失敗不遺留可誤認為正式的 provisional bytes。回傳 `ControlledFileReceiptView`，並維持 `"controlled-file-apply-receipt.v1"` 與 `"controlled-file-record.v1"` 語意。
- **Query／Download**：`GET /api/v1/storage/files`、`GET /api/v1/storage/files/{file_id}` 與 `GET /api/v1/storage/files/{file_id}/download` 限經 authorization（同時驗 actor、purpose／domain 與 owning business ref）串流 committed bytes；missing／hash mismatch／unavailable／unauthorized 一律 fail closed，不暴露 filesystem 實體路徑。

## 6. Storage／Backup Readiness

- **Storage readiness**：由 `ControlledFileStoragePort.readiness()`（`FileSystemControlledFileStorage.readiness()`）檢查 shared storage root、temp／staging directory、必要目錄、read／write／create／rename／delete 能力、mount 與 backend identity，並透過 `GET /api/v1/system/database-backup` 唯讀投影 `storage_ready`／`disaster_recovery_ready`；任一缺失即 `false`。
- **Backup／restore readiness**：依 `GET /api/v1/system/database-backup` 與維護驗證檢查備份目的地與 primary storage 隔離性、credential／permission、last backup、restore drill、RPO／RTO、immutable／versioned 能力與 integrity verification。僅有同機複本或未驗證 restore drill 不得宣稱完整 readiness。

## 7. Freeze-Before-Send、Staging／Cleanup 與 Reconciliation

### 7.1 Freeze-Before-Send

對 `application/pdf`、`.docx`、`.xlsx` 等正式外送／列印／提交文件，必須形成 immutable frozen revision（保存 `file_id`、`version`、`purpose`、`content_sha256`、size、locations、`frozen_at`、actor／reason、integrity manifest）：

1. 同一 business identity 之 frozen revision 不得覆寫，更正采 additive revision 連回前版；多來源附件須合併完成後才 freeze。
2. 同一事件多個 outbound references 指向同一 frozen `file_id + version + hash`；outbound receipt 必須保存 exact frozen identity／revision／hash。
3. live workspace 目錄不是 outbound Authority。

### 7.2 Staging／Cleanup

暫存內容只進入 `_staging/<runtime namespace>/<category>`（enum category）；Cleanup Preview 零副作用，受 minimum age gate（預設 ≥30 分鐘）約束，嚴禁刪除 frozen／committed business artifact，每次 cleanup 保存 actor、plan、deleted／skipped sets、reason 與 receipt。

### 7.3 Reconciliation

Reconciliation 對照 DB metadata、storage truth、business reference 與 outbound evidence，檢查檔案存在、hash、owner、read model 與 outbound receipt 一致性；missing／mismatch／overwrite 一律 fail closed 交人工處理，Apply 僅執行預先允許之 deterministic technical repair。

## 8. NAS 設定檔契約與單一根目錄實體架構

### 8.1 檔案傳輸設定與儲存限制（`/api/v1/storage/settings`）

依 [Global Entry Point Governance](19_Global_Entry_Point_Governance.md) 邊界，管理端側欄不設獨立「檔案設定」維護畫面，既有後端與 API 契約保持運作：

- `/api/v1/storage/settings` 僅允許 enabled persisted root human session；一般登入管理員透過 `/transfer-settings` 讀取限制，公開 LINE 經私人 HTTPS／機器憑證讀取同一限制，無寫入權限。
- 設定僅保存照片／履歷 bytes 上限、等待秒數與 `expected_version`（CAS 防 stale／busy 409），PUT 不接受 `nas_path` 或 `container_root`；Query 唯讀回報解析後之 `CONTROLLED_FILE_STORAGE_ROOT`。
- 持久化檔由 `FILE_SETTINGS_PATH` 指定（未指定時正式單一根目錄用 root 內 `.file-settings.json`，開發環境保留父層 `file-settings.json` 或 `data/runtime/file-settings.json`），採原子替換與程序間鎖；設定檔明確值優先於環境初值，降低上限不封鎖既有合法大檔讀取。

### 8.2 NAS 實體目錄架構與檔案命名規範

```text
{NAS共用資料夾}/
├── 01_案件合約 (orders)/{案件編號}/
│   ├── 客戶合約_{案件編號}_v1_已簽署_{短Hash}.pdf
│   └── 月嫂承攬協議_{案件編號}_{月嫂編號}_已簽署_{短Hash}.pdf
├── 02_照護日誌 (scheduling)/{案件編號}/{服務日期_YYYY-MM-DD}/
│   ├── 照護照片_{服務日期}_寶寶_{序號}_{短Hash}.jpg
│   └── 照護照片_{服務日期}_餐點_{序號}_{短Hash}.jpg
├── 03_月嫂檔案與資格 (staff)/{月嫂編號}_{姓名}/
│   ├── resume/月嫂履歷_{月嫂編號}_{月嫂姓名}_v{版本號}_{短Hash}.pdf
│   ├── certificates/證照_{月嫂編號}_{證照名稱}_{短Hash}.pdf
│   └── health_and_police/{體檢報告|良民證}_{月嫂編號}_{年份}_{短Hash}.pdf
├── 04_LINE選單資源 (media)/rich_menus/
│   └── {預設選單底圖|月嫂專用選單底圖}_{發布日期}.png
├── 05_資料庫冷備份 (db_backups)/{YYYY-MM}/
│   └── union_db_{YYYYMMDD_HHMMSS}.zip   # 單檔封裝 .sql.gz + .sql.gz.sha256 + receipt .json
└── _staging/
```

**單一根目錄與自動建立規則**：

- Windows 正式環境單一設定 `.env` 之 `CONTROLLED_FILE_STORAGE_ROOT` 為唯一 NAS 共用根設定（未設定時不得回存專案或本機預設路徑），優先於 `APP_ENV=development` 等啟動標記。
- 共用根目錄由 NAS 管理者預建並授予子目錄建立 ACL；程式於首次寫入時自動建立 `01`～`05`（含 `04_LINE選單資源 (media)/rich_menus`）與 `_staging` 並繼承 NAS ACL（唯讀 Query 與 dry run 不建立資料夾）；未填 `union_no` 之月嫂以 `ID{staff.id}` 命名快照（後續更名不搬移舊檔）；不合法路徑字元轉底線且嚴防 root escape。
- 新正式受控附件於原 outer transaction 保存 finalize intent，commit 後由 bounded finalize runner 歸檔至 `01`～`04` 新 locator；未綁定 LINE 原始媒體位於 `_staging/line_media`。
- `05_資料庫冷備份 (db_backups)/YYYY-MM/` 衍生於同一共用根（無獨立 `NAS_BACKUP_DIR`），Global migration 使用 `_partial/` 與 `_maintenance/`，備份須經匯出 exit、gzip 解壓、schema 穩定、SHA-256 與讀回全過後封裝為單一 `.zip` 發布（並向下相容讀取既有 `_receipts/YYYY-MM/` 舊三檔備份）；一般受控檔案 adapter 須嚴格排除備份專區存取（含 Windows 大小寫與尾端空白／句點等價路徑）。
- 實體檔案命名固定為 `[中文業務類別]_[業務識別]_[時間/版本]_[檔案雜湊前6碼].[副檔名]`；透過 `FileSystemControlledFileStorage.readiness()` Fail-Closed 保護寫入一致性。

## 9. 驗收標準

1. source contract／focused tests、shared MySQL Apply／replay／constraint／fail-closed 通過。
2. authenticated browser list／detail／download／readiness 與未授權／missing／hash mismatch fail-closed 通過。
3. local preview／staging／cleanup／reconciliation 證明零越權與 deterministic readback。
4. NAS mount／permission／unavailable／recovery 與 `01`～`05`／`_staging` 目錄結構、排除備份專區與 CAS settings 驗證通過。
5. backup＋restore drill、Freeze-Before-Send immutable revision／manifest／lineage，以及 outbound receipt 指向相同 frozen `file_id/version/hash` 驗證通過。
