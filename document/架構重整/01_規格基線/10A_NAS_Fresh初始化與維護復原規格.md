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

<a id="windows-nas-maintenance"></a>

## 5. Windows 三大維護入口與每日 NAS SQL 備份（`nas_database_maintenance.py`）

- **系統架構定位**：Windows 工會電腦執行應用與管理腳本，NAS 執行 Docker MySQL 與共用檔案儲存。維護入口沿用設定中的 MySQL TLS 模式，不啟用 SSH 或遠端修改容器設定，保留 `.env` 的存取權限與切換一致性檢查。備份、升級及復原的備份位置均可使用本機磁碟、映射磁碟或網路共用。
- **入口收斂**：獨立批處理 `backup_nas_database.bat`、`initialize_nas_schema.bat`（安全升級，不提供清空重建）、`restore_nas_database.bat` 與根目錄 `Windows管理.bat`（選項 `6 備份`、`7 安全升級`、`8 復原備份`）統一委派 `scripts/nas_database_maintenance.py`；選項 7 的操作與受管服務檢查見[安全升級契約](#windows-管理器的安全升級契約)；選項 8 偵測同一安裝仍有受管服務時，立即停止並要求先停止服務。
- `Windows管理.bat` 選項 `11 管理 root 帳號` 見 [Access Control 的 Windows 主機離線管理](17_External_Integration_LINE_Access正式規格.md#34-windows-主機離線管理-root-帳號)。
- **設定邊界**：選項 6、7、8 為內部維護入口，以指定 `.env` 的實際主機、連接埠及資料庫為準，不限制維護啟用旗標、部署名稱、固定目標或庫名前綴，也不因程序環境變數與檔案不同而阻擋。程序中的連線覆寫不取代指定檔案。未另填維護帳密時沿用 `.env` 的原帳密；明確提供的維護帳密仍可使用。備份目的目錄優先使用 `.env` 的 `NAS_BACKUP_DIR`，其次使用選填維護設定檔的同名值；未指定時使用 `CONTROLLED_FILE_STORAGE_ROOT/05_資料庫冷備份 (db_backups)`，根目錄未設定則使用專案 `backups/05_資料庫冷備份 (db_backups)`。允許本機、映射磁碟或 UNC 路徑，寫入時可建立所需目錄，不要求預建 NAS 根目錄。升級及復原顯示停機提醒，不再要求額外輸入確認。`--dry-run` 零連線零寫入；路徑不得越界或經 symlink／junction，寫入前仍須通過可讀寫檢查。遠端升級持續使用備份與新副本流程，不使用原庫直連快速升級。
- **Windows 本機 NAS 測試部署**：`.env` 指向 loopback 的 `lu_nas_*` 測試庫時，選項 7 與正式遠端 NAS 共用保留資料的副本預檢。預檢列出待套用的遷移檔案，再備份、建立副本並升級；直連升級回條僅用於直連升級。若來源已通過正常啟動使用的現行版本檢查，結束而不建立備份或副本。副本通過相同的啟動版本檢查後才可切換。此部署沿用該安裝的測試備份位置。
- **NAS 資源受限時的讀取成本**：維持原庫唯讀、完整備份、新副本升級及切換前完整驗證。只有 trigger 的逐步結構核對不查詢投影必為空的欄位、索引、約束、外鍵及 view；trigger 查詢在資料庫端限定該步需要的名稱與資料表，保留 metadata 原順序與完整定義。逐表資料驗證在每次呼叫中一次取得各表主鍵定義，逐表筆數、checksum 及主鍵內容雜湊仍逐一重新核對，不跨階段快取。不得以效能優化取消備份或完整驗證，也不自動刪除原庫。
- **來源問卷胎數預檢**：來源已具備雙胞胎政策與查詢前提時，選項 7 在備份前唯讀檢查單一綁定問卷的 Case Import 胎數投影；無法判定時僅回報筆數及 `multi_birth_count_ambiguous`，不輸出案件號或原始問卷。來源尚未具備查詢前提時仍由副本上的標準回填檢查。Case Import 對已確認的舊答案 `雙胞胎(+150時薪)` 正規化為 `雙胞胎`，不改寫原始問卷或由標籤加價文字推算費率；既有費率衝突與多筆綁定仍由標準回填拒絕。
- **1080 直連中斷的副本恢復**：既有原庫若因直連 DDL 逾時停在 1080 的已驗證前綴，選項 7 只讀核對原 `fast_additive` journal、升級前備份及目前完整結構。歷史備份仍須通過檔案完整性、主機／庫別／版本／基線結構身分、資料證據範圍及 journal 所記指紋核對，但不要求目前資料列仍等於中斷前的歷史備份，允許維護期間修正來源資料。規劃及套用仍重新讀取目前來源資料，另建完整備份並核對新副本；一般原庫直連升級與接續仍要求歷史備份資料列一致。原始 trigger 定義取自已驗證備份，依原 MySQL metadata 排序規則重建並核對原基線完整 SHA，包含已被 DROP 的名稱，不改用 Python 排序。已套用 trigger 先比較 canonical SQL 契約，再以現況原始定義及快照原順序核對前綴完整 SHA，不因 SQL 匯入格式或排序差異而誤擋。僅 hash-bound 的 canonical 前綴可進入副本恢復；修復 DDL 由原 runner 在新副本執行，原庫與原紀錄不改寫。缺少備份、紀錄或結構不符，以及 DDL 結果未明時，停止且保留現況，不在原庫盲目續跑。

| 維護操作 | 核心契約與失敗保護 |
|---|---|
| **每日／手動 SQL 備份** | `mysqldump --single-transaction --quick` 串流輸出至 `_partial/` 暫存 `.sql.gz`（含 InnoDB SQL、views、routines、triggers、events，禁止期間執行 DDL），通過 UTF-8、SQL 尾註、schema 一致與寫後讀回檢核後，打包成單一 `union_db_YYYYMMDD_HHMMSS.zip`（內含 `.sql.gz`、`.sql.gz.sha256` 與成功紀錄 `.json`）原子發布至 `YYYY-MM/`（不再另寫 `_receipts/`）；寫入前驗證 `write/rename/readback probe` |
| **安全資料升級（Upgrade）** | 顯示停機提醒，無額外輸入確認 → zero-write canonical plan → 完整備份 → 建立全新 `lu_nas_upgrade_*` schema 執行 `restore → schema／backfill → verify → switch`（已 exact 物件共用入場快照，最後完整 fresh-read 不省略）→ 僅等量授予原雙帳號 schema 權限並實測原 credential 登入 |
| **備份復原（Restore）** | 由 NAS 專區或手動單選無 symlink `.zip`（或向下相容選取保留完整 `.sha256` 與 `_receipts/` 之既有 `.sql.gz` 備份組）檔案（非預設路徑可叫用 Windows 原生選檔窗），驗封裝結構、校驗碼、gzip CRC、解壓後 digest 與 current schema 相容性後，串流匯入全新 `lu_nas_restore_*`（含 SQL events 且全域開啟 `event_scheduler` 時停機隔離處理），通過逐表 CHECK 與帳號認證檢查後方原子切換 `.env` 唯一 `DB_DATABASE`（先複製原 `.env` ACL 規則至暫存檔，digest 變動即停止；SQL 不包含實體照片與 MFA keyring，須另作災難備份） |
| **排程與管理端 UI** | 正式機可安裝每日預設臺灣時間 `18:00` 之工作排程（僅限 backup）；管理端「稽核與系統 → 資料庫備份」（[Global Entry Point Governance](19_Global_Entry_Point_Governance.md) 核准路由 `database-backup`）顯示設定時間、最近成功／失敗狀態並提供 CAS version 控制之安全修改（409 stale；不外洩帳號／設定／SQL 或提供檔案下載） |

### Windows 管理器的安全升級契約

| 情境（S） | 任務（T） | 操作（A） | 可觀察結果（R） |
|---|---|---|---|
| 維護人員已停止同一安裝的受管服務，且遠端來源有待套用遷移，或 loopback 的 `lu_nas_*` 測試庫未達現行版本。 | 執行保留資料的安全升級，不清空重建。 | 開啟 `Windows管理.bat`，選「7 安全升級資料庫」。 | 顯示停機提醒，不要求額外輸入確認；先做零寫入預檢，再依本節的安全升級流程備份、建立副本與驗證。驗證通過後才切換，可依 [§5.1](#51-切換後清理舊資料庫) 由 `switch.json` 核對新舊庫；驗證未通過不切換，原庫保留。 |
| 同一安裝仍有受管服務運作。 | 避免在服務運作中開始升級。 | 從 Windows 管理器要求安全升級。 | 顯示先選「2 停止全部」的提示，這次不進入資料庫維護。不會代替維護人員停止服務。 |
| Loopback 的 `lu_nas_*` 測試庫已通過正常啟動使用的現行版本檢查。 | 確認是否還需要升級。 | 從 Windows 管理器要求安全升級。 | 判定為現行版本後結束，不另建備份、不另建副本，也不切換資料庫。 |

### 5.1 切換後清理舊資料庫

Windows 選項 7／8 切換後暫留原庫，供本次維護驗收與必要回復。驗收通過後，由有權限的維護人員逐庫清理，日常只保留現役庫與可還原的備份。

1. 停止寫入後，選項 7 沿用該次升級產生的原庫備份。選項 8 若要替換仍可讀取的原庫，先用選項 6 備份原庫，再復原所選備份。核對原庫備份的來源、時間與完整性，確認備份可還原。原庫無可還原備份時保留原庫。
2. 切換後重啟服務，完成登入和業務資料讀回。將實際連線的 MySQL 主機及連接埠與原庫備份紀錄核對，再用該次 `switch.json` 核對新舊庫完整名稱，確認服務使用新庫、原庫已無服務使用。
3. 維護人員在 MySQL 使用 `DROP DATABASE`，逐一明確指定已確認的完整庫名，再讀回確認舊庫已移除、現役庫仍可用。保留原庫的備份與清理紀錄。升級或復原失敗、切換結果不明、驗收未通過或刪除目標不明時，停止清理並保留資料庫與維護紀錄。既有測試舊庫亦按相同方式核對，不以庫名前綴批次刪除。

### 5.2 每日排程備份滾動保存

使用者核定的保存政策為每日 14 天、每週 8 週、每月 12 個月。仍只執行原每日 SQL 備份，不另做週備份或月備份，也不複製代表檔。

- 以 Asia/Taipei 日曆與備份檔名時間選取：今天及前 13 天保留全部排程備份；當週及前 7 週各保留最新成功的一份，週一開始；當月及前 11 個月各保留最新成功的一份。三者取聯集，同一份只占一個檔案。週或月未備份時不虛構檔案；跨年依 ISO 週與日曆月份計算。
- 僅新版每日排程建立且成功收據標記 `retention_managed=true` 的 ZIP 納入自動淘汰。既有未標記、手動、升級前、legacy `.sql.gz`、來源不符、未知檔案及 `_partial/` 一律不自動刪除。新政策不回溯接管既有檔案。
- 沿既有 maintenance lock，在本次排程備份成功並完整驗證後才清理；最新成功備份及未來時間檔案保留。當次備份失敗不執行清理。
- 清理前核對 target host／port／database、固定備份根目錄、精確月份子目錄及檔名，拒絕 symlink／junction 或超出根目錄的路徑；待刪 ZIP 必須通過既有完整封裝、checksum、gzip 及 SQL digest 驗證。驗證不完整不刪除。
- 沿備份根目錄 `_retention/` 保留本次清理計畫與逐檔處理結果，不保存 credential 或 SQL。只刪計畫內已驗證過期 ZIP，不遞迴清空資料夾；重跑按現況重新判定。
- 本節只管理 SQL 排程備份，不取代受控檔案與登入驗證金鑰的獨立備份，也不變更寄送紀錄六個月政策或防重送憑證。

| ID | S | T | A | R |
|---|---|---|---|---|
| NAS-RET-01 | 同一目標已有跨年、跨週及跨月的排程備份 | 保留日、週、月代表檔 | 以固定臺灣日期建立清理計畫並執行隔離檔案測試 | 14 日全留、8 週與12 月各最新代表取聯集；邊界外非代表檔移除，不複製檔案 |
| NAS-RET-02 | 有既有、手動、升級前、來源不符及未知檔案 | 保護未授權淘汰的備份 | 成功排程後執行清理 | 僅標記且同目標的過期 ZIP 可刪，其餘位元內容不變 |
| NAS-RET-03 | 新備份失敗，或候選損壞／路徑越界 | 避免失去可用備份 | 注入失敗、checksum 錯誤與 symlink／junction | 失敗時不刪除，最新成功備份保留；清理有可追溯結果 |
| NAS-RET-04 | 清理已完成或中途中斷 | 安全重跑 | 重新執行相同日期的隔離清理 | 已移除檔案不重刪、現有代表檔保留，紀錄反映實際結果 |

## 6. 驗收標準

1. **`FRESH-01～05`**：compact profile（371 tables＋canonical seeds）於空庫 bootstrap 與 `reset_DB` 結果與 full canonical 一致；register 內退役表不進新庫，既有庫存在退役表不報錯而保留物件之欄位／約束 tamper 立即 fail closed。
2. **NAS Init／DSM／Windows 三入口**：驗證缺庫 1049 建立、非空 1049／`RESET union_db` 明確確認與防重、三支批處理目標 opt-in／cancel／hash negative、隔離 MySQL 完整 `dump → restore → upgrade → 原庫零異動 → 原憑證登入 → .env 原子替換`、排程時間修改 409 stale 與介面不外洩敏感資訊。
3. **Windows 舊庫清理**
   - **S**：隔離 MySQL 已成功切換新庫並通過上線驗收，原庫已有可還原的備份，且無服務使用原庫。
   - **T**：維護人員在保有原庫復原資料的前提下釋放舊庫空間。
   - **A**：用原庫備份紀錄核對主機及連接埠，用切換紀錄核對完整庫名，刪除原庫並讀回。另以現役庫、缺少原庫備份及切換失敗三種情境執行清理前核對。
   - **R**：正向情境只有指定的舊庫被刪除，現役庫仍可讀，保留的備份可還原。負向情境停止清理，資料庫均保留。
4. **Windows 本機 NAS 跨版本升級**
   - **S**：隔離 MySQL 的 `lu_nas_*` 來源庫停在 1053，尚未套用其後遷移，且有可辨識的保留資料。
   - **T**：維護人員在同一次維護中升級副本至現行版本並啟動系統。
   - **A**：執行選項 7，核對備份、來源與副本的資料、設定切換及啟動檢查，再對新庫重跑選項 7。以結構不符或啟動版本檢查失敗的副本驗證切換保護。
   - **R**：正向情境產生一份來源備份，原庫結構及資料保留，只切換 `DB_DATABASE`，且新庫通過啟動檢查。重跑不新增備份或副本。負向情境不切換資料庫。
5. **內部維護不受部署政策阻擋**
   - **S**：`.env` 指向維護資料庫，備份目的地為可寫入的本機、映射磁碟或網路目錄。選填維護檔可能缺少、停用或保有過期固定目標；可不另填維護帳密。
   - **T**：維護人員透過 Windows 選項 6 備份、7 安全升級及 8 復原資料庫。
   - **A**：依序執行三項維護；升級及復原前停止系統，不再次輸入確認。使用自訂備份目錄、未建立的本機備份目錄與預設備份目錄；另以缺少 MySQL 工具、無寫入權限、損壞備份及未知結構驗證失敗處理。
   - **R**：三項維護採用指定 `.env` 的實際連線與可用帳密，政策旗標、固定目標、庫名前綴、非 UNC 路徑及殘留程序環境不阻擋。遠端升級沿完整備份、副本升級與驗證流程，復原只匯入新副本。負向情境不切換設定，不偷偷改用另一備份位置；中斷紀錄及原庫保留供核對。
6. **1080 直連逾時後的部分結構恢復**
   - **S**：原 journal 已驗證至 1080 第 29 條 DROP，對應 trigger 尚未重建，原始備份與資料指紋完整；備份 SQL 可能具有不同排版或換行，MySQL metadata 名稱順序也可能與 Python 排序不同。
   - **T**：維護人員保留原庫，將新副本恢復至現行版本。
   - **A**：執行選項 7；另以錯誤來源、缺少備份、改動 journal、非 canonical 結構及未確認完成的 DDL 驗證拒絕行為。
   - **R**：只有完整身分及雜湊核對通過時才備份與建立新副本，合法匯入格式差異可通過，非 canonical 定義仍拒絕；副本由原 runner 完成並驗證。原庫、journal 與升級前備份不變。負向情境不建立副本或切換設定。
