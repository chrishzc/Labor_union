# NAS Fresh 初始化、結構精簡與維護復原規格

## 1. 文件邊界與所有權

- 狀態：`current-spec`
- Owner：Global Migration Infrastructure Subsystem（`scripts/initialize_nas_schema.py`、`scripts/compact_fresh_schema.py`、`scripts/nas_database_maintenance.py`、`scripts/update_nas_database.py`、`scripts/retire_client_payment_destination.py`）
- 單一負責範圍：NAS 空白資料庫安全初始化與互動確認契約、精簡新庫 schema（371 retained tables）與全域退役表清單（`labor_union_fresh_table_retirements_v1.json`）、舊全域收款帳戶資料表退役（`retire_client_payment_destination.py`）、DSM 冷備份副本升級入口（`deployment/nas/upgrade-database.sh`），以及 Windows 工會端三大維護入口、每日 18:00 NAS SQL 備份、復原與排程設定 UI。
- 關聯引用：見 [Global 共同契約](00_Global_共同契約.md)、[Global Migration 與 Cutover Subsystem](10_Global_保留資料Migration與Cutover_Subsystem.md)、[Global Deployment 與治理](18_Global_Deployment與治理正式規格.md)、[Global Entry Point Governance](19_Global_Entry_Point_Governance.md)、[Controlled File Storage NAS](30_Controlled_File_Storage_NAS正式規格.md)。

## 2. NAS 空白資料庫首次初始化與重建（`initialize_nas_schema.py`）

- **環境與目標限定**：僅讀取專案 `.env` 且固定要求 `APP_ENV=development`、remote `DB_HOST`、`DB_DATABASE=union_db`（process override 與設定衝突即停止，TLS 沿 `DB_SSL_*`，禁止暴露 credential）；僅限於開發者受控目標。
- **空庫預檢與雙態啟動**：
  - Python／Unix 無參數執行零寫入連線與空庫檢查；`--dry-run` 零連線；`--apply` 僅接受空庫。
  - Windows `--interactive` 先執行唯讀預檢（驗證 MySQL 8.0.16+ 非 MariaDB、InnoDB、writable、有效 grants／`CURRENT_ROLE`、binlog trigger policy 與 current manifest）；無表時輸入 `Y` 才初始化；`--apply` 拒絕對非空庫執行。
- **缺庫建立與清空重建（互動專用）**：
  - 初次連線 errno `1049`（缺庫）時，`--interactive` 透過無選定資料庫連線檢查伺服器與權限並顯示 host／port／db，輸入 `Y`/`y` 後記錄 durable journal 執行 `CREATE DATABASE CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci`（不用 `IF NOT EXISTS`、最後撞名 1007 fail closed）接續空庫初始化。
  - 目標非空且操作員明確點選 `R` 時，須先驗證全域無外部 schema incoming FK 與 schema CREATE／DROP 權限，手動輸入完整 `RESET union_db` 始依 durable journal 執行 `DROP DATABASE → CREATE DATABASE → USE` 並重跑空庫初始化（保留現況失敗不自動重試或備份；`lock_wait_timeout=15`，重建連線 read budget `600` 秒；errno `2006/2013` 回報結果未明、errno `1205` 提示停止 writer 後重查）。
- **寫入與終態**：使用 [精簡結構](#3-nas-新庫結構精簡與退役清單)，排除 SQL 內嵌之資料庫控制指令後循序執行（含 system seed），完成後須通過 validation objects 與 current descriptor gate 雙重驗證（不輸出 driver 原文、僅顯示 phase、已完成數與數字 errno）。

<a id="compact-fresh-retirements"></a>

## 3. NAS 新庫結構精簡與退役清單

- **精簡設定檔與資產**：
  - `db/schema_assembly/labor_union_fresh_table_retirements_v1.json` 記錄全域已核准逐表退役清單（涵蓋 15 張異常機制表、已退休政府退款與舊業務暫存表共 `37` 張保留現狀不進新庫＋下文 `3` 張舊全域收款帳戶表；保留 `government_payers` singleton）。
  - `scripts/compact_fresh_schema.py` 於本機乾淨空庫完成 canonical bootstrap 後，產出唯一 compact profile：`db/fresh_schema/labor_union_fresh_current.sql` 與 hash-bound manifest（僅含 `CREATE TABLE`、必要 system seed `INSERT`、retained triggers／views 與 session FK 設定，移除 definer／來源 DB qualifiers 與固定 timestamp／counter）。
- **`FRESH-01～05` 不變量**：
  - NAS 新建與開發端 `reset_DB` 統一載入此精簡 compact SQL（不重播歷史 `ALTER`）；既有保留資料升級路徑仍不對舊庫任意刪表。
  - Canonical descriptor comparator 自動略過已列於 register 之退役表及其表屬 trigger；保留物件之欄位、索引、FK、check、trigger、view 任何 drift 仍一律 fail closed。
- **舊全域收款帳戶三表移除（`scripts/retire_client_payment_destination.py`）**：
  - `client_payment_destination_configuration_{current,events,receipts}` 加入 fresh retirement register；針對已有開發庫提供獨立受控清理工具，依 `receipts → current → events` 順序連帶 table-owned trigger 移除三表（限 `localhost` development，Apply 前強制驗證 plan fingerprint、metadata、無外部 FK 與完整備份，不得混充 additive schema）。

## 4. DSM 冷備份副本受控升級（`upgrade-database.sh` / `update_nas_database.py`）

- 專供 NAS 容器離線維護手動執行（禁止排程自動切換）。`--update` 於鎖內串接「冷備份卷身分核對 → 還原副本卷 → network-none 啟動同版 MySQL 並委派 `scripts.update_local_database` 完成 preserve-data 升級與驗證 → 通過後方更新 Compose physical volume 與 `NAS_IMAGE` 並啟動服務」。
- 原營運來源庫保持停機且 SQL 零連線；失敗時保留原卷與備份卷，不自動刪除或覆寫；Switch 前寫入 config before／after hash（保留 `.env` 其他設定、憑證與 MFA keys）。

## 5. Windows 三大維護入口與每日 NAS SQL 備份（`nas_database_maintenance.py`）

- **系統架構定位**：Windows 工會電腦執行應用與管理腳本，NAS 僅執行 Docker MySQL 與共用檔案儲存；**三項入口一律透過加密 TLS MySQL 連線與受控 NAS 路徑執行，絕不啟用 SSH、遠端修改容器設定或放寬 `.env` 保護**。
- **入口收斂**：獨立批處理 `backup_nas_database.bat`、`initialize_nas_schema.bat`（安全升級，不提供清空重建）、`restore_nas_database.bat` 與根目錄 `Windows管理.bat`（選項 `6 備份`、`7 安全升級`、`8 復原備份`）統一委派 `scripts/nas_database_maintenance.py`；選項 7／8 偵測同一 installation 尚有受管 runtime 運作時即停止並要求先停止服務。
- **設定邊界**：讀取獨立 `.env.nas-maintenance` Fixed target NAS host／port（拒絕 `localhost`／開發庫及 process env override），`--dry-run` 零連線零寫入；備份儲存路徑唯一取自 `.env` `CONTROLLED_FILE_STORAGE_ROOT` 下的 `05_資料庫冷備份 (db_backups)`（僅接受 NAS UNC 且禁止 symlink／junction）。

| 維護操作 | 核心契約與失敗保護 |
|---|---|
| **每日／手動 SQL 備份** | `mysqldump --single-transaction --quick` 串流輸出至 `_partial/` 暫存 `.sql.gz`（含 InnoDB SQL、views、routines、triggers、events，禁止期間執行 DDL），通過 UTF-8、SQL 尾註、schema 一致與寫後讀回檢核後，打包成單一 `union_db_YYYYMMDD_HHMMSS.zip`（內含 `.sql.gz`、`.sql.gz.sha256` 與成功紀錄 `.json`）原子發布至 `YYYY-MM/`（不再另寫 `_receipts/`）；寫入前驗證 `write/rename/readback probe` |
| **安全資料升級（Upgrade）** | 人工停機確認 → zero-write canonical plan → 完整備份 → 建立全新 `lu_nas_upgrade_*` schema 執行 `restore → schema／backfill → verify → switch`（已 exact 物件共用入場快照，最後完整 fresh-read 不省略）→ 僅等量授予原雙帳號 schema 權限並實測原 credential 登入 |
| **備份復原（Restore）** | 由 NAS 專區或手動單選無 symlink `.zip`（或向下相容選取保留完整 `.sha256` 與 `_receipts/` 之既有 `.sql.gz` 備份組）檔案（非預設路徑可叫用 Windows 原生選檔窗），驗封裝結構、校驗碼、gzip CRC、解壓後 digest 與 current schema 相容性後，串流匯入全新 `lu_nas_restore_*`（含 SQL events 且全域開啟 `event_scheduler` 時停機隔離處理），通過逐表 CHECK 與帳號認證檢查後方原子切換 `.env` 唯一 `DB_DATABASE`（先複製原 `.env` ACL 規則至暫存檔，digest 變動即停止；SQL 不包含實體照片與 MFA keyring，須另作災難備份） |
| **排程與管理端 UI** | 正式機可安裝每日預設臺灣時間 `18:00` 之工作排程（僅限 backup）；管理端「稽核與系統 → 資料庫備份」（[Global Entry Point Governance](19_Global_Entry_Point_Governance.md) 核准路由 `database-backup`）顯示設定時間、最近成功／失敗狀態並提供 CAS version 控制之安全修改（409 stale；不外洩帳號／設定／SQL 或提供檔案下載） |

## 6. 驗收標準

1. **`FRESH-01～05`**：compact profile（371 tables＋canonical seeds）於空庫 bootstrap 與 `reset_DB` 結果與 full canonical 一致；register 內退役表不進新庫，既有庫存在退役表不報錯而保留物件之欄位／約束 tamper 立即 fail closed。
2. **NAS Init／DSM／Windows 三入口**：驗證缺庫 1049 建立、非空 1049／`RESET union_db` 明確確認與防重、三支批處理目標 opt-in／cancel／hash negative、隔離 MySQL 完整 `dump → restore → upgrade → 原庫零異動 → 原憑證登入 → .env 原子替換`、排程時間修改 409 stale 與介面不外洩敏感資訊。
