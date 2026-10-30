# Controlled File Storage／NAS 正式規格

2026-10-30 儲存標的精簡與 NAS 目錄架構裁決：依人工明確指示，NAS 儲存標的精簡為正式簽約本（客戶正式合約、月嫂承攬協議）、照護照片（寶寶、餐點）、月嫂資格主檔（履歷、證照、體檢與良民證）、LINE 選單底圖與資料庫每日冷備份；待簽約草案合約書改為動態產製不落地永久儲存，紙本簽到工作單、服務日期確認書、排班行事曆圖卡與客服對話截圖移出永久儲存清單。NAS 實體目錄依人員查核習慣劃分直覺編號結構，實體檔案命名規範中文業務標記與防竄改雜湊。實體路徑連線格式由環境與部署變數配置，本規格維持技術中立抽象儲存邊界。

2026-10-21 管理端互動裁決：依 `00_Global_共同契約.md` §2.4，檔案容量／等待時間設定及營運清理改為一次點擊送出、人工原因選填。保留受控根目錄、候選合法性、權限、版本／digest、正式執行與 readback 邊界，不以查看預覽或核對勾選作為前置條件。

## 1. 文件狀態與 Authority

- 狀態：`consolidated-current-baseline`
- 收斂日期：2026-09-09
- 最新修訂日期：2026-10-30
- Owner：Controlled File Storage / Infrastructure boundary
- 上位共同契約：`00_Global_共同契約.md`
- 關聯規格：各 owning Domain 的文件產生、送出、核銷、簽署、報表與附件契約
- 歷史來源：`document/功能開發計畫/NAS_檔案庫與資料中心管理介面正式規範.md`（完成遷移後只保留於 Git history）

本文件承接 Controlled File Storage 與 NAS-backed storage 的 exact machine contract。`00_Global_共同契約.md` 保留跨 Domain 不變量；本文件負責 purpose registry、管理 API、Preview／Apply、receipt、Freeze-Before-Send、staging、reconciliation、readiness、backup／restore 與管理 UI 的正式邊界。

本文件不授權任何特定 production NAS mount、credential、外部傳送、付款、簽署或資料庫 migration。實作存在不等於外部／production acceptance 已完成。

## 2. 核心原則

1. 所有受治理業務檔案必須經 typed Controlled File Storage boundary；不得由 generic Data Browser、任意檔案上傳、前端、script 或直接 filesystem write 建立另一套正式寫入路徑。
2. DB metadata 與 storage bytes 必須可用 stable `file_id`、`version`、`purpose`、hash 與 owning business reference 對帳。
3. Preview 零 durable 副作用；Apply 才可建立正式檔案／版本或執行明確允許的 cleanup／reconciliation command。
4. 同一正式檔案 identity 不可覆寫既有 frozen revision；更正使用 additive revision 並保留 lineage。
5. 外送、列印、下載供正式用途或提交政府／合作方前，必須引用 immutable frozen artifact，不得讀取仍可變動的 live workspace 檔案。
6. NAS 只是 storage backend；「NAS 上有檔案」本身不是 business Authority、publication receipt、簽署成功或 owner state。

## 3. FILE_PURPOSE_REGISTRY

系統必須維護唯一的 `FILE_PURPOSE_REGISTRY`。現行正式收斂之長期受控儲存標的如下：

- `final_signed_contract`：客戶正式簽約完成本（PDF / Excel，客戶線上簽署或紙本簽署回傳）
- `signed_staff_agreement`：已簽約的月嫂承攬協議書（PDF / Excel，月嫂接案承攬確認與報酬結算簽署正本）
- `staff_resume`：月嫂正式履歷書（PDF，月嫂主檔完備之個人履歷正本）
- `staff_certificate`：月嫂專業證照（PDF / JPG，保母人員技術士證、急救證照等專業資格）
- `staff_health_exam`：月嫂體檢合格證明與良民證（PDF / JPG，法定必備之年度健康檢查與警察刑事紀錄）
- `baby_log_photo`：寶寶照護日誌照片（JPG / PNG，月嫂每日到府照護打卡上傳之佐證相片）
- `meal_photo`：每日月子餐點照片（JPG / PNG，月嫂每日到府備餐上傳之佐證相片）
- `rich_menu_background`：LINE 圖文選單底圖（PNG，官方帳號發布圖文選單之圖片資源）
- `database_backup`：資料庫 SQL 快照備份（SQL.GZ + SHA256，正式 Windows 每日預設 18:00 觸發並寫至 NAS；時間可於「稽核與系統」修改，Global migration §9.5 擁有執行與復原契約）。此為 InnoDB 不停機一致性快照，不代表關閉 MySQL 後的實體資料卷冷備份。

**明確排除與非永久儲存規範**：
1. `unsigned_contract`（待簽約草案）：需要時由系統依即時事實動態產製供即時下載，不於 NAS 落地永久儲存。
2. 紙本簽到工作單、服務日期確認書、排班行事曆圖卡、LINE 客服對話截圖與附件，依 2026-10-30 人工指示移出 NAS 永久儲存清單。

每個 purpose 至少定義：

- `owner_domain`
- `file_format`
- `source_of_truth`
- `generation_cadence`
- `db_reference`
- `consumers`
- `overwrite_policy`
- `retention_policy`
- `backup_required`
- `restore_owner`

新增 purpose 必須先有唯一 owner 與 typed consumer；不得用自由字串繞過 registry。

## 4. 正式檔案 metadata

正式 record 至少可 read back：

- `file_id`
- `version`
- `purpose`
- `domain`
- owning business `ref`
- `storage_backend`
- `storage_locator`
- `content_sha256`
- `mime_type`
- `size_bytes`
- `status`
- `source_kind`
- uploader／actor
- `created_at`
- `updated_at`
- audit／lineage

`storage_locator` 是 storage adapter 的定位資訊，不得被前端解釋成可繞過 typed download boundary 的任意 OS path。

## 5. Closed management routes

Controlled File Storage 的管理介面使用 closed typed route set：

```text
GET  /api/v1/data-center/files
GET  /api/v1/data-center/files/{file_id}
GET  /api/v1/data-center/files/{file_id}/download
POST /api/v1/data-center/files/preview
POST /api/v1/data-center/files/apply
GET  /api/v1/data-center/storage/readiness
GET  /api/v1/data-center/backup/readiness
GET  /api/v1/data-center/reconciliation
POST /api/v1/data-center/reconciliation/preview
POST /api/v1/data-center/reconciliation/apply
POST /api/v1/data-center/staging/preview
POST /api/v1/data-center/staging/cleanup
GET  /api/v1/storage/transfer-settings
GET  /api/v1/storage/settings
PUT  /api/v1/storage/settings
```

不得建立 generic alternate upload route、Data Browser table mutation 或直接 filesystem endpoint 來取代上述 owner boundary。若 current implementation 的 exact route 變更，必須先更新本 formal contract 與 consumer／test，再移除舊 route；不得雙軌長期並存。

## 6. Preview／Apply／idempotency

### 6.1 File Preview

`POST /api/v1/data-center/files/preview`：

- 只驗證輸入、purpose、owner、格式、大小、reference、readiness、預期版本與 policy；
- 可計算 hash／計畫，但不得留下 DB row、正式 storage bytes、publication task 或其他 durable business side effect；
- backend／permission／purpose／owner 不明確時 fail closed。

### 6.2 File Apply

`POST /api/v1/data-center/files/apply`：

- 必須使用 typed command 與 idempotency identity；
- exact replay 回原 committed receipt；
- 相同 idempotency identity 搭配不同 payload 必須 conflict／fail closed；
- bytes staging 與 DB metadata commit 的順序／補償必須避免 metadata 指向不存在檔案或失敗後遺留被誤認為正式的 provisional bytes。

成功 receipt 至少包含：

```json
{
  "kind": "controlled-file-apply-receipt.v1",
  "status": "committed",
  "payload": {
    "kind": "controlled-file-record.v1",
    "file_id": "...",
    "version": 1,
    "purpose": "...",
    "storage_backend": "...",
    "storage_locator": "...",
    "content_sha256": "...",
    "size_bytes": 0,
    "created_at": "...",
    "updated_at": "..."
  }
}
```

欄位可 additive 擴充，但既有 discriminator 與 business identity 不得被前端自行重解釋。

## 7. Query／download 邊界

- `GET /files` 與 `GET /files/{file_id}` 回 structured metadata／read model。
- `GET /files/{file_id}/download` 只能透過 typed boundary 串流 committed bytes。
- authorization 必須同時檢查 actor、purpose／domain 與 owning business reference；知道 `file_id` 不代表可下載。
- UI 不得顯示 filesystem 路徑作為直接操作入口。
- missing／hash mismatch／storage unavailable／unauthorized 一律 fail closed，不以空檔或舊快取偽裝成功。

## 8. Storage readiness

`GET /api/v1/data-center/storage/readiness` 至少檢查：

- shared storage root；
- local temp／staging directory；
- required root directories；
- read／write／create／rename／delete 等實際需要能力；
- mount／path 存在性與 permission；
- configured backend identity。

缺 path、mount、permission 或 required capability 時 readiness 必須 false；不得因 process 本身健康就宣稱 storage ready。

## 9. Backup／restore readiness

`GET /api/v1/data-center/backup/readiness` 至少 read back：

- backup destination 與 primary storage 的隔離性；
- required credential／permission readiness；
- last successful backup；
- last restore drill；
- applicable RPO／RTO；
- immutable／versioned backup 能力；
- integrity verification 結果。

只有同一 primary storage 內的複本、DB 本機備份或未驗證 restore 的備份，不得宣稱完整 backup readiness。

Production-ready 必須以實際 backup＋restore drill 與其 evidence 判定，不得由設定檔推定。

## 10. Freeze-Before-Send

對至少下列正式格式：

- `application/pdf`
- `application/vnd.openxmlformats-officedocument.wordprocessingml.document`
- `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`

正式外送／列印／提交前必須形成 immutable frozen revision，至少保存：

- `file_id`
- `version`
- `purpose`
- `content_sha256`
- exact bytes／size
- primary location
- backup location（purpose 要求時）
- `frozen_at`
- actor／reason
- integrity manifest

規則：

1. 同一 business identity 的 frozen revision 不得 in-place overwrite。
2. 新 revision 必須 additive 並連回前一 revision。
3. 若來源由多段資料／附件合併，merge 完成後才 freeze。
4. 同一 business event 的多個 outbound references 必須指向同一 frozen `file_id + version + hash`。
5. replacement 必須保留 reason、actor、time 與被取代 revision。
6. outbound print／download／send／government submission 只能消費 frozen revision。
7. live Excel／Word／NAS workspace directory 不是 outbound Authority。
8. outbound receipt 必須保存 exact frozen identity／revision／hash，不能只記 filename。

## 11. Staging／cleanup

相容性 `/data` 或 runtime 暫存內容只能進入明確 `_staging/<runtime namespace>/<category>` 類型目錄；不得被誤認為 formal business storage。

允許的 staging residue category 必須 closed／enumerated。Cleanup：

- Preview 零副作用；
- 只處理 declared operation plan 與 boundary 內的檔案；
- 必須使用 minimum age gate，預設不得低於 30 分鐘，除非另有更嚴格 owner contract；
- 不得刪除 frozen／committed business artifact；
- 每次 cleanup 必須有 actor、plan、deleted set、skipped set、reason 與 receipt；
- cleanup 後重新評估 disk pressure／readiness。

## 12. Reconciliation

Reconciliation 必須能對照四個世界：

1. DB governed root／metadata；
2. storage truth；
3. business page／report／receipt reference；
4. external send／scan／submission evidence（若適用）。

最低檢查：

- committed storage object 存在；
- size／hash 與 metadata 一致；
- purpose／owner／domain／business ref 一致；
- business read model 指向同一 revision；
- outbound receipt 指向同一 frozen `file_id/version/hash`；
- orphan NAS file 不會自動升格為 Authority。

missing file、owner mismatch、reference mismatch、hash mismatch、frozen revision 被覆寫等狀況必須 fail closed，進 anomaly／manual review。

Reconciliation Apply 只可執行 deterministic、預先允許的 technical repair；不得自行修改 business semantics、重送外部訊息、還原備份或修 NAS mount，除非有另一份 owning contract 明確授權。

## 13. 管理 UI

Data Center／檔案庫 UI 只呈現 formal read model 與 typed actions。至少能顯示：

- file identity／version／purpose／domain／business reference；
- filename／mime／size／hash；
- storage backend 與 readiness；
- frozen／status／created／updated；
- download eligibility；
- backup／restore readiness；
- staging／reconciliation preview/result；
- error／unknown／not-ready 狀態。

UI 不能：

- 直接改 DB row 或 filesystem；
- 把 browser local state 當正式狀態；
- 因下載成功就宣稱 business submission 成功；
- 因 NAS path 可見就跳過 owner authorization。

### 13A. NAS 檔案設定（2026-10-19 人工授權）

- 「稽核與系統 → 檔案設定」提供真實 Query、畫面變更預覽、確認儲存與 server readback；不顯示原設計分類說明，不提供檔案瀏覽或搬移操作。
- `/api/v1/storage/settings` 僅允許 enabled persisted root human session。一般登入工會人員仍可透過既有 `/transfer-settings` 與業務入口使用檔案，不取得 NAS 路徑設定權限；公開 LINE 與機器憑證不能讀寫管理設定。
- 依後續人工確認，取消可編輯 NAS 路徑備註與待部署狀態。設定只保存照片／履歷 bytes 上限、等待秒數與設定 version；Query 的 `container_root` 唯讀顯示 `CONTROLLED_FILE_STORAGE_ROOT` 解析後的程式路徑，未設定回 null。容器無法據此證明 NAS host source path、掛載或 ACL；實體掛載留待 Compose 設定。
- PUT 不接受 `nas_path` 或 `container_root`；前端預覽／儲存僅有容量與等待時間。先前 JSON 裡的 `nas_path` 不再採用或投影，既有容量、版本與讀取容量仍保留，不以舊備註切換儲存位置。
- `FILE_SETTINGS_PATH` 指向部署者配置的持久化 JSON 設定檔；未指定時，正式單一根目錄使用 root 內隱藏的 `.file-settings.json`，不寫到 root 外。
  開發環境保留原受控根目錄父層 `file-settings.json`；無根目錄的本機開發仍使用 `data/runtime/file-settings.json`，不搬移舊設定。
  原子替換與程序間鎖保護同一設定檔；`expected_version` CAS 拒絕 stale／busy，無新 DB table、fingerprint 或 migration。
- 設定檔的明確值優先於環境初值。容量／等待時間於後續操作重新讀取，即時生效；公開 LINE 經既有私人 HTTPS／獨立機器認證讀取同一限制，不掛載或寫入管理設定檔。`0` 僅停用應用層檔案計時，外層仍可能中斷。
- 儲存結果不明時不得宣稱失敗或盲目重送，UI 保留錯誤並要求重新 Query；版本衝突顯示 typed 409。舊版合法大檔的讀取容量保留於內部設定 metadata，降低新上傳容量不因此封鎖既有檔案。

### 13B. NAS 實體目錄架構與檔案命名規範（2026-10-30 人工定案）

為方便工會秘書與管理人員在日常營運、稽核查帳或客戶爭議時，能直接透過檔案總管或 Synology DSM File Station 快速查核，實體檔案依業務主軸劃分直覺編號架構：

```text
{NAS共用資料夾}/
│
├── 01_案件合約 (orders)/
│   └── {案件編號}/                            # 例：2026-A001
│       ├── 客戶合約_{案件編號}_v1_已簽署_{短Hash}.pdf
│       └── 月嫂承攬協議_{案件編號}_{月嫂編號}_已簽署_{短Hash}.pdf
│
├── 02_照護日誌 (scheduling)/
│   └── {案件編號}/                            # 例：2026-A001
│       └── {服務日期_YYYY-MM-DD}/              # 例：2026-11-01
│           ├── 照護照片_{服務日期}_寶寶_{序號}_{短Hash}.jpg
│           └── 照護照片_{服務日期}_餐點_{序號}_{短Hash}.jpg
│
├── 03_月嫂檔案與資格 (staff)/
│   └── {月嫂編號}_{姓名}/                     # 例：ST012_張美月
│       ├── resume/                            # 履歷
│       │   └── 月嫂履歷_{月嫂編號}_{月嫂姓名}_v{版本號}_{短Hash}.pdf
│       ├── certificates/                      # 專業證照
│       │   └── 證照_{月嫂編號}_{證照名稱}_{短Hash}.pdf
│       └── health_and_police/                 # 體檢與良民證
│           ├── 體檢報告_{月嫂編號}_{年份}_{短Hash}.pdf
│           └── 良民證_{月嫂編號}_{年份}_{短Hash}.pdf
│
├── 04_LINE選單資源 (media)/
│   └── rich_menus/                            # LINE 圖文選單圖片
│       ├── 預設選單底圖_{發布日期}.png
│       └── 月嫂專用選單底圖_{發布日期}.png
│
├── 05_資料庫冷備份 (db_backups)/              # Windows 每日／人工 SQL 快照；NAS ACL 保護
│   └── {YYYY-MM}/                             # 依月份歸檔
│       ├── union_db_{YYYYMMDD_HHMMSS}.sql.gz
│       └── union_db_{YYYYMMDD_HHMMSS}.sql.gz.sha256
│
└── _staging/                                  # 系統上傳驗證暫存區（超過24小時由GC自動清理）
```

**單一根目錄與自動建立（2026-10-30 後續人工定案）**：
- Windows 正式環境只設定 `.env` 的 `CONTROLLED_FILE_STORAGE_ROOT` 為 NAS 共用根目錄；合約歸檔、模板目錄、
  受控附件、LINE 媒體與資料庫備份共用此根。正式環境不再採用 `CONTRACT_DOCUMENT_ARCHIVE_ROOT`／
  `MEDIA_STORAGE_ROOT`，即使舊值仍存在也不得覆寫新根；未設定根目錄不得回存專案或本機預設位置。
- 共用 root 由 NAS 管理者準備。第一次寫入時自動建立 01～05、`_staging` 與 `04_LINE選單資源 (media)/rich_menus`，
  繼承 NAS ACL，不建立缺失的 share／root、不更改 Windows／NAS ACL。正式唯讀 Query、建構 storage adapter 及 dry run 不建立資料夾。
- 案件合約沿用案件編號及既有版本／storage key，archive component 位於 `01_案件合約 (orders)`；模板技術材料仍位於該分類的
  `template-catalog`。新註冊的最終／未簽 PDF 依案件編號、文件版本及 digest 歸檔；不改既有文件 identity 或 completion writer。
- 照護照片使用 Scheduling 已驗證的 case／service date／kind／sequence／digest 形成 `02_照護日誌 (scheduling)/{案件編號}/{日期}/`
  與可讀檔名，canonical object key、opaque file_id、reference、日誌與交易規則不變。
- 月嫂附件使用當次 Staff facts 的 `union_no`、`name` 形成 `03_月嫂檔案與資格 (staff)/{編號}_{姓名}/`；未填公會編號時標示
  `ID{staff.id}`，不虛構公會編號。依目的寫入 `resume`／`certificates`／`health_and_police`，並自動建立三個子目錄。
  此名稱為註冊當時的實體顯示快照；後續更名不搬移或覆寫舊檔。Windows 不合法路徑字元轉為底線，不讓資料欄位逸出根目錄。
- 上傳及系統產製的 Rich Menu 圖片共用 `04_LINE選單資源 (media)/rich_menus`，發布 reader 使用相同位置。
  尚未綁定業務附件的 LINE 原始媒體位於 `_staging/line_media`；保留原媒體 owner／retention，不因所在目錄而旁路引用與清理契約。
- 新正式受控附件在原 outer transaction 內保存既有 finalize intent，commit 後由既有 durable cycle 的 bounded finalize runner 驗證並歸檔。
  照護照片維持 Scheduling attachment writer 建立 reference 與 finalize intent，不重複排程。新 runner 只選取 01～04 新 locator，
  不掃描／搬移舊 locator；registered staging identity、下載、digest、CAS、lease、失敗對帳與無 hidden commit 契約不變。
- 開發環境既有明確合約／媒體路徑保留；本次不改任何現存 `.env`、不搬移／刪除資料、不執行 migration。
  新 staging 使用 `_staging`；舊 `.controlled-file-staging` 僅保留必要的讀取與同 idempotency key 重播，不自動改寫舊 bytes／metadata。
  同一 staging ID 在兩處出現時停止核對，不猜測正本；新 NAS finalize cycle 在 development／test 不執行。

**實體檔案命名規範**：
- 規則：`[中文業務類別]_[業務識別]_[時間/版本]_[檔案雜湊前6碼].[副檔名]`
- 兼具人員高可讀性與防篡改雜湊驗證能力。

**連線與部署中立性**：
- 具體實體路徑連線格式由環境與部署變數（`.env`）靈活配置，本規格保持技術中立抽象儲存邊界，不硬性綁定特定 IP 或特定磁碟代號。
- 實體儲存空間必須透過 `FileSystemControlledFileStorage.readiness()` 進行健康檢查，連線中斷或未授權時一律遵循 Fail-Closed 原則，阻擋寫入並報錯，不以本機隨意暫存破壞資料與 NAS 的一致性。

2026-10-30 備份存放對齊（依後續人工修正方案）：Windows 共用根目錄只由原 `.env` 的
`CONTROLLED_FILE_STORAGE_ROOT` 設定，正式備份須為 NAS UNC；備份位置固定衍生為該根目錄下的
`05_資料庫冷備份 (db_backups)`，移除獨立 `NAS_BACKUP_DIR`，不讀取舊值作為覆寫或退路。
不設定本機預設或故障回存位置；不存在的 share／共用 root 不自動建立。依後續人工核准，程式可在已存在、
可存取且非連結的 NAS 共用 root 下透過共用 layout 建立 01～05 與 `_staging` 子目錄，繼承 NAS ACL；無法建立時於 DB 操作前停止。
唯讀狀態查詢及 dry run 不建立資料夾。既有三個 Windows 操作入口與 18:00 預設保留，
不改成 DSM 03:00、SSH 或每日停機。DSM 舊 SQL／實體冷卷工具仍有獨立管理者 consumer，不因 Windows 排程
而自動啟用。NAS 管理者一次準備共用根目錄及可建立子目錄的 ACL；程式不把 Windows SID／本機 ACL 套在 NAS 共用上。

`05_資料庫冷備份 (db_backups)/YYYY-MM/` 只發布上述 `.sql.gz`／`.sha256` 配對；月份與檔名時間使用
台灣時間，檔名前綴 `union_db` 為此系統的業務識別，實際 source schema／server identity 保存在驗證紀錄。
Global migration 在同一備份區使用 `_partial/` 保留未完成輸出、`_receipts/YYYY-MM/` 保存配對成功紀錄、
`_maintenance/` 保存必要升級／復原 journal 與 canonical runner 所需的技術 artifacts；不套用業務 staging GC。
匯出 exit、gzip 完整解壓、schema 穩定、SHA-256 及發布後讀回全部通過，才發布成功紀錄；缺少成功紀錄的
檔案配對不得進入復原清單或顯示成功。既有備份與失敗材料不自動搬移、刪除或覆寫。

備份 artifact／restore receipt 仍由 Global migration 擁有，不為登記備份而回寫正在備份的 source database，
也不註冊為可透過一般業務附件下載的檔案。共用根目錄時，一般受控檔案 adapter 必須排除備份專區的探索與直接讀取，
包含其成功紀錄與 maintenance 技術材料；Windows 大小寫與尾端空白／句點等價路徑不得繞過此限制。
實體儲存檢查沿用受控儲存 readiness，另對所需 write／rename／readback
執行非敏感 probe。只有排程設定及去敏執行狀態可留在 Windows 本機，SQL 不回存本機。頁面區分設定完成、
NAS 目前可讀與備份結果；這些訊號不得替代 §9 的隔離性及正式 restore drill，不宣稱完整 disaster readiness。


## 14. Current implementation／acceptance 邊界

截至 2026-09-01 的 repository-local evidence 已證明：typed storage port、local storage adapter、staging、Preview／Apply、list／get／download、cleanup／reconciliation、Data Center adapter、source tests 與 shared-MySQL DB gate 已有通過證據。

但下列不得由上述證據推定完成：

- enabled human Session 的 fresh Chrome 正向 list／download acceptance；
- 正式 NAS mount／permission／failure injection；
- 真 backup destination 與 restore drill；
- production credential／network／operator／RPO／RTO；
- 任何真實 outbound send／government submission／external signing。

因此 current overall acceptance 應維持「repository-local foundation 可用；external／production gate 另行驗證」，不得把 source／DB pass 升格成 production-ready。

## 15. Formal acceptance gate

至少需要：

1. source contract／focused tests PASS；
2. shared MySQL Apply／replay／constraint／fail-closed PASS；
3. authenticated browser list／detail／download／readiness PASS；
4. local preview／staging／cleanup／reconciliation 證明零越權與 deterministic readback；
5. NAS mount／permission／unavailable／recovery 測試 PASS；
6. backup＋restore drill PASS；
7. Freeze-Before-Send 的 immutable revision／manifest／replacement lineage PASS；
8. owning business consumer 與 outbound receipt 指向相同 frozen identity／hash；
9. production 外部行為只有在另有明確授權的環境／operator／credential／rollback 下才可執行。

未跑的層級標 `NOT_RUN`，有 blocker 標 `BLOCKED`；不得以「已有 API／UI」代替 acceptance。

## 16. 歷史來源處置

`document/功能開發計畫/NAS_檔案庫與資料中心管理介面正式規範.md` 的仍有效 machine-contract 語意已由本文件承接。其舊 UI 排版、環境假設、歷史實作描述與非 formal wording 不再建立 Authority。

來源文件完成 migration 後應從 working tree 移除；稽核與歷史脈絡由 Git history 取得。
