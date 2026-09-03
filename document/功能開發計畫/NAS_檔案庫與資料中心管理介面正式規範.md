---
doc_type: feature-spec
declared_status: approved
date: 2026-08-25
owner: Data-Center-and-Controlled-Storage-Integration
related_tasks:
  - CUR-DATA-CENTER-01
  - CUR-FILE-NAS-01
  - CUR-CONTRACT-01
spec_references:
  - document/架構重整/01_規格基線/00_Global_共同契約.md (§2.2)
  - document/架構重整/01_規格基線/19_Global_Entry_Point_Governance.md (§5)
  - document/架構重整/02_決策與退役執行記錄/96_Current_剩餘代辦任務總表.md
---

# NAS 檔案庫與資料中心管理介面正式規範 (NAS Storage & Data Center Workbench Specification)

## 1. 緣起與業務目標

本規範定義新竹市月子照護工會後台管理系統之 **「資料中心 (Data Center)」** 整合架構，以及專屬 **「NAS 檔案庫管理 (NAS Storage Manager)」** 的資料夾結構、檔案範圍、存檔與發送時序、結構化防呆命名規則、容量監控與安全刪除防呆機制。

工會實體大型檔案（契約 PDF、月嫂證件、照護日誌照片、餐食驗證照片、派工通知）均保存於地端 **Synology NAS**；MySQL 資料庫僅保存關聯 metadata、版本號、SHA-256 完整性雜湊值與去敏狀態，網頁端不暴露任何實體磁碟路徑（遵循 `00 §2.2` 契約）。

---

## 2. 儲存檔案範圍與排除項目

### 2.1 正式納入 NAS 儲存之 2 大專區與 4 類檔案

1. **📦 訂單專區檔案 (`/orders/{case_no}/`)**：
   - 📑 **已簽名定型化契約 PDF**：產婦與工會簽署完成之正式契約掃描／電子簽署 PDF。
   - 📅 **合約服務日期確認表 PDF / PNG**：排班鎖定與精確服務天數確認單（供後續異動與爭議比對）。
   - 📤 **寄出訂單資訊通知單 PDF (`-1`, `-2`, `-3`...)**：派單與報價通知留底檔案（初版派工、天數修訂、代班接續等歷史留底）。
   - 👶 **寶寶日誌照片 JPG / PNG**：月嫂每日到宅服務上傳之照護重點紀錄照片。
   - 🍲 **月子餐食照片 JPG / PNG**：需要下廚案件之每日月子餐點與藥膳燉湯成果存證。

2. **👩‍🍼 月嫂專區檔案 (`/caregivers/{staff_id}/`)**：
   - 👩‍🍼 **月嫂履歷表 PDF**：月嫂基本資歷、服務年資與專長表。
   - 🛡️ **良民證與專業證照 PDF**：警察刑事紀錄證明、保母結業證書、藥膳催乳證照。
   - 🩺 **定期體檢合格表 PDF**：月嫂合格健康檢查表。

### 2.2 明確排除項目
- ❌ **歷史匯入 Excel 工作簿（HCM / BeClass / 歷史訂單 / 銀行流水）**：僅供匯入時於記憶體中校驗解析並寫入 MySQL 結構化資料表，**不常態保存於 NAS 檔案庫**以節省儲存空間。
- ❌ **即時報表與領據**：可由系統資料庫動態產出之報表，不作為靜態檔案存放在 NAS。

---

## 3. 核心不變量：先存檔鎖定，再從 NAS 寄出 (Freeze-Before-Send Invariant)

為徹底杜絕「**寄給客戶的內容與 NAS 留底不一致**」或「**發送時拿錯舊版檔案**」之爭議，系統嚴格遵循 **Freeze-Before-Send** 處理順序：

```text
┌────────────────┐     1. 生成 PDF 檔案     ┌───────────────────────────────────┐
│  工會後台系統   │ ──────────────────────> │  先寫入 NAS 專屬目錄               │
│  (產生通知單)  │                          │  (鎖定檔名、版本流水號與 SHA-256) │
└────────────────┘                          └─────────────────┬─────────────────┘
                                                              │ 2. 從 NAS 取得已封存檔案
                                                              ▼
┌────────────────┐     3. 確保 100% 一致    ┌───────────────────────────────────┐
│  產婦 / 月嫂   │ <────────────────────── │  LINE 機器人 / Email 執行寄出     │
│  (收訖檔案)    │                          │  (記錄 sent_at 與成功 delivery)   │
└────────────────┘                          └───────────────────────────────────┘
```

1. **先存檔產出 Snapshot**：系統產生檔案後，立即寫入 NAS 專屬路徑並計算 SHA-256 雜湊值與版本流水號（如 `SEQ-1`）。
2. **從 NAS 讀取並發送**：發送模組直接讀取已封存之 NAS 檔案發送，確保外發內容與庫存證據 100% 相同。
3. **標記發送狀態**：發送成功後在資料庫 metadata 記錄發送時間戳記 (`sent_at`) 與狀態 (`sent_status: success`)。

---

## 4. 結構化防呆命名規則 (Standardized Naming Convention)

檔案名稱嚴格採用結構化命名，管理員與系統可一眼辨識「案件、對象、版本、用途與時間」，杜絕混淆：

### 4.1 訂單專區命名規則 (`/orders/{case_no}/`)

| 檔案類型 | 結構化命名格式 | 範例檔名 | 業務說明 |
| :--- | :--- | :--- | :--- |
| 📤 **寄出訂單資訊 (-1)** | `NOTICE_{case_no}_{client_name}_SEQ-1_{YYYYMMDD-HHmm}.pdf` | `NOTICE_ORD-HC019_林美真_SEQ-1_20260518-1430.pdf` | 第 1 次初版派工與報價通知 |
| 📤 **寄出訂單資訊 (-2)** | `NOTICE_{case_no}_{client_name}_SEQ-2_{YYYYMMDD-HHmm}.pdf` | `NOTICE_ORD-HC019_林美真_SEQ-2_20260520-0915.pdf` | 第 2 次改期／天數異動後通知 |
| 📅 **服務日期確認表** | `DATES_{case_no}_{client_name}_CONFIRMED_{YYYYMMDD}.pdf` | `DATES_ORD-HC019_林美真_CONFIRMED_20260520.pdf` | 排班鎖定與精確日期確認憑證 |
| 📑 **定型化契約 (已簽名)**| `CONTRACT_{case_no}_{client_name}_SIGNED_v{v}.pdf` | `CONTRACT_ORD-HC019_林美真_SIGNED_v1.pdf` | 產婦簽署完成之定型化契約 |
| 👶 **寶寶日誌照片** | `BABY_{case_no}_{YYYYMMDD}_{seq}.jpg` | `BABY_ORD-HC019_20260825_01.jpg` | 每日到宅照護日誌照片 |
| 🍲 **月子餐食照片** | `MEAL_{case_no}_{YYYYMMDD}_{meal_type}_{seq}.jpg` | `MEAL_ORD-HC019_20260825_LUNCH_01.jpg` | 月子餐與藥膳燉湯存證照片 |

### 4.2 月嫂專區命名規則 (`/caregivers/{staff_id}/`)

| 檔案類型 | 結構化命名格式 | 範例檔名 | 業務說明 |
| :--- | :--- | :--- | :--- |
| 👩‍🍼 **月嫂履歷表** | `RESUME_{staff_id}_{staff_name}_v{v}.pdf` | `RESUME_STF-012_張美敏_v1.pdf` | 月嫂履歷與專業年資 |
| 🛡️ **良民證 / 證照** | `CERT_{staff_id}_{staff_name}_{cert_name}_{YYYYMMDD}.pdf` | `CERT_STF-012_張美敏_良民證_20260115.pdf` | 警察刑事紀錄證明、保母證 |
| 🩺 **體檢合格表** | `HEALTH_{staff_id}_{staff_name}_體檢表_{YYYYMMDD}.pdf` | `HEALTH_STF-012_張美敏_體檢表_20260310.pdf` | 定期健康檢查合格證明 |

---

## 5. NAS 空間管理與安全刪除機制

1. **即時容量監控條 (Storage Quota Bar)**：
   - 頂部常駐容量進度條（呈現已用容量、總容量與剩餘容量）。
   - 剩餘容量低於 15% 時自動呈現黃色警戒，低於 5% 時呈現紅色嚴重告警。
2. **單檔與批次刪除 (Safe Cleanup)**：
   - 檔案清單提供單檔 `[ 🗑️ 刪除 ]` 按鈕與批次勾選 `[ 🗑️ 批次刪除已選項目 ]`。
3. **刪除確認彈窗 (Confirmation Modal)**：
   - 彈窗明確告知：欲刪除檔案名稱、預計釋放磁碟空間大小（如 `8.5 MB`）。
   - **未結案合約保護警示**：若刪除對象為「進行中或待履約案件之正式契約/日期確認表」，彈窗顯示橘色警示標籤（`⚠️ 此訂單仍在履約中，請確認後再執行`），防止誤刪重要法律證據。
4. **受控補充上傳 (Versioned Additions)**：
   - 支援 `[ 📤 補充上傳新附件 ]`，自動歸入當前選定之案件或月嫂資料夾，若為同名文件自動升版（v1 ➔ v2），確保舊版不被覆寫。

---

## 6. 資料中心 (Data Center) 介面設計與雙欄工作台

### 6.1 側邊欄與分頁整合架構
側邊欄統一命名為 **「🗄️ 資料中心 (Data Center)」**，具備三大分頁：
1. 📁 **分頁 1：`NAS 檔案管理`**（主工作台）
2. 📥 **分頁 2：`資料匯入`**（原 5 大卡片匯入中心）
3. 📊 **分頁 3：`數據瀏覽`**（原數據瀏覽器，`#databrowser` 相容跳轉）

### 6.2 雙欄工作台佈局示意圖 (Two-Column Explorer)

```text
┌──────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│ 🗄️ 資料中心 (Data Center)                                                                                         │
│  [ 📁 NAS 檔案管理 (作用中) ]    [ 📥 資料匯入 (5大卡片) ]    [ 📊 數據瀏覽 (相容) ]                                       │
├──────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ 💾 NAS 空間狀態：[████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░] 已使用 38.5 GB / 500 GB (7.7%) ｜ 剩餘 461.5 GB 可用         │
├──────────────────────────┬───────────────────────────────────────────────────────────────────────────────────────┤
│ 📂 資料夾目錄 (左欄)       │ 🔍 [ 搜尋訂單編號、產婦姓名、月嫂或檔名...               ]  [ 全部類型 ▾ ]  [ 📅 日期 ▾ ] │
│                          │ 麵包屑：📁 訂單專區 > 📁 ORD-2026-HC019 (林○真) > 📑 契約與服務確認                     │
│ 📁 全部檔案 (1,340)       ├───────────────────────────────────────────────────────────────────────────────────────┤
│                          │ 批次操作：[ 全選 ]  [ 🗑️ 批次刪除已選項目 ]  [ ⬇️ 批次打包下載 ]      ＋ [ 📤 補充上傳新附件 ]  │
│ 📦 訂單檔案庫 (142案)     ├───────────────────────────────────────────────────────────────────────────────────────┤
│   ├─ 📁 ORD-HC019 (林○真)│ ┌───────────────────────────────────────────────────────────────────────────────────┐ │
│   │    ├─ 📑 契約與確認(3)│ │ 📑 CONTRACT_ORD-HC019_林美真_SIGNED_v1.pdf   (850 KB) [ ⬇️ 下載 ] [ 👁️ 預覽 ] [ 🗑️ 刪除 ]│ │
│   │    ├─ 👶 寶寶日誌 (8)│ │ 📅 DATES_ORD-HC019_林美真_CONFIRMED_20260520.pdf (420 KB) [ ⬇️ 下載 ] [ 👁️ 預覽 ] [ 🗑️ 刪除 ]│ │
│   │    └─ 🍲 餐食照片 (6)│ │ 📤 NOTICE_ORD-HC019_林美真_SEQ-1_20260518-1430.pdf (310 KB) [ ⬇️ 下載 ] [ 👁️ 預覽 ] [ 🗑️ 刪除 ]│ │
│   ├─ 📁 ORD-HC020 (陳○萱)│ │ 📤 NOTICE_ORD-HC019_林美真_SEQ-2_20260520-0915.pdf (340 KB) [ ⬇️ 下載 ] [ 👁️ 預覽 ] [ 🗑️ 刪除 ]│ │
│   └─ 📁 ORD-HC021 (黃○婷)│ └───────────────────────────────────────────────────────────────────────────────────┘ │
│                          │ 💡 爭議比對說明：若產婦對服務天數或月嫂排班有疑義，可同時下載「日期確認表」與「寄出訂單資訊」比對。│
│ 👩‍🍼 月嫂檔案庫 (48位)     ├───────────────────────────────────────────────────────────────────────────────────────┤
│   ├─ 📁 STF-012 (張○敏)  │ ⚠️ 刪除防呆機制：                                                                     │
│   ├─ 📁 STF-015 (李○芳)  │ 點擊刪除彈窗提示：「即將從 NAS 永久刪除此檔案並釋放 850 KB 空間，確認刪除？」         │
└──────────────────────────┴───────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 7. 驗收標準 (Acceptance Criteria)

1. **入口相容性**：
   - 頂部導航分頁切換正常，既有 5 大類別工作簿匯入卡片零回歸；數據瀏覽器保留於側邊欄相容運作。
2. **資料夾與檔案展示**：
   - 點擊左側訂單資料夾即時篩選出該案三大資料（契約、日誌照片、餐食照片、寄出通知）。
   - 點擊月嫂資料夾即時呈現該月嫂之履歷與證件 PDF。
3. **防呆發送時序**：
   - 任何外發通知單均先存入 NAS 專屬路徑並獲得 `SEQ-{n}` 檔名與 SHA-256 後，才由傳送服務發送。
4. **安全刪除與容量釋放**：
   - 執行刪除操作跳出容量釋放確認彈窗；刪除完成後 NAS 容量進度條與檔案清單即時更新。
   - 進行中合約刪除具備橘色警告提示。

---

## 8. 前端元件保護與後續 API 串接防覆蓋規範 (UI Component Preservation Guard)

> [!IMPORTANT]
> **🔒 核心防覆蓋不變量 (UI Preservation Invariant)**：
> 1. **本期實作範圍**：本階段重點在於建立 **完整前端視覺架構、雙欄樹狀目錄、容量監控條、結構化命名檔案列表、爭議比對提示、預覽/上傳/安全刪除防呆彈窗**，採用前端高保真狀態機，**目前暫不串接後端 API**。
> 2. **後續 Agent 施工禁令**：未來其他 Agent 進行後端儲存 API（如 `GET /api/v1/storage/files`、`POST /api/v1/storage/upload`、`DELETE /api/v1/storage/files`）串接時，**嚴禁整檔覆蓋、刪除既有 UI 佈局、簡化元件或退回空白畫面**。
> 3. **安全擴充方式**：後續串接必須在既有 React 元件樹結構上，以 Typed Adapter / Query 方式填入真實後端數據，**嚴格保留所有已核准之樹狀目錄、容量條、爭議提示條與三大多功能彈窗**。
> 4. **Current implementation status（2026-08-26）**：資料中心三分頁、canonical 側欄名稱與 `data-browser`／`databrowser` 相容入口已完成；Chrome 已實點三分頁、兩個相容入口、back／forward、canonical active 投影及訂單／客戶真 Query。NAS 分頁明示為本機介面預覽，尚未連接 storage API，真實 storage capability 不屬本項完成範圍。
> 5. **Next-phase authorization（2026-08-26）**：人工已授權建立後端 controlled-file capability、必要的 `lu_test_*` schema gate、typed Query／download／staging／Preview／Apply／receipt／readback 與失敗 reconciliation。實作前仍須先盤點 current storage ports／metadata／schema，並遵守 `00` §2.2、完整 DB change gates 與本節 UI preservation invariant。這項授權不允許猜測 production／`union_db` target、暴露 NAS path、直接搬檔或跳過 rollback／readback。

---

## 9. Controlled-file 後端 exact contract amendment（2026-08-26）

本節依 `CUR-FILE-NAS-01` 已核准的規格補齊、本機實作與受控驗收 Authority，固定後端 machine
contract；不授權 production mount、`union_db`、entry switch、provider delivery 或不可逆正式檔案刪除。

### 9.1 Public route 與認證邊界

管理端共用 prefix 固定為 `/api/v1/storage`，最小 public resources 為：

```text
POST /api/v1/storage/staging
POST /api/v1/storage/files/preview
POST /api/v1/storage/files/apply
GET  /api/v1/storage/files
GET  /api/v1/storage/files/{file_id}
GET  /api/v1/storage/files/{file_id}/download
GET  /api/v1/storage/receipts/{receipt_id}
```

- 管理端 routes 全部要求 authenticated、enabled、persisted internal user，使用現有
  `require_persisted_admin` actor contract；不得新增 `storage.*` capability 造成內部使用者業務權限差異。
- LIFF／LINE consumer 保留 owner route 與 server-verified identity，再由 owner Domain 驗證 assignment、
  service day、document 或 subject facts；不得把 LIFF token 當管理端 bearer，也不得直接建立 storage metadata。
- Preview route 固定以 `/preview` 結尾並保持零寫入；Apply、staging、download 與 receipt readback 進既有
  authenticated audit boundary。download 回 backend attachment bytes，不建立 signed／public URL。

### 9.2 Closed owner／purpose registry

共用 storage 不擁有業務生命週期。public command 只接受下列 closed pairing：

| owner | purpose |
|---|---|
| `contract_signing` | `final_signed_contract` |
| `scheduling` | `service_date_confirmation`、`baby_log_photo`、`meal_photo` |
| `orders` | `order_notice` |
| `staff` | `staff_resume`、`staff_certificate`、`staff_health_exam` |
| `line_integration` | `rich_menu_background` |

owner Domain 仍負責 subject 是否存在、可見範圍、完成條件、版本採用與後續 outbox。新增 pairing 必須先同步
current正式規格、typed enum、schema descriptor／release（若受 DB constraint 管理）與 consumer tests；不得由
任意字串、資料列、前端設定或 storage discovery 動態升格。

### 9.3 Opaque identity 與 public projection

- registered file identity 固定為 `cf_` 加 32 個 lowercase UUIDv4 hex，regex
  `^cf_[0-9a-f]{32}$`；staging identity 固定為 `cfs_` 加 32 個 lowercase UUIDv4 hex，regex
  `^cfs_[0-9a-f]{32}$`。
- identity 不含 owner、subject、purpose、檔名、日期、host、drive、UNC、mount 或 storage locator；SHA-256
  是獨立 integrity fact，不能當 object identity 或 authorization token。
- list／detail／receipt 只回 opaque ID、owner、purpose、subject reference、可理解檔名、logical folder、MIME、
  size、version、status 與時間。一般 UI 不顯示完整 digest；JSON、header、URL、log、audit message 與 receipt
  均不得含 storage locator、raw bytes 或公開下載位置。

### 9.4 Staging、Preview、Apply 與 cleanup

- staging TTL 以 24 小時作為可配置的 operational default，不是不可變 business rule；由 server
  `BusinessClock` 與當次生效的維運設定建立 absolute `expires_at`。staging write 必須使用
  server-generated locator、exclusive create、size／MIME／digest 驗證；same idempotency key＋same canonical
  payload 回原 staging result，same key＋different payload 固定 conflict。
- Preview 零寫入並回 closed candidate、`preview_fingerprint`、expected staging version、owner blockers 與
  expiry。Apply 在單一 outer UoW 重新鎖定 staging、owner subject、purpose、digest、MIME、size、expiry、
  expected version 與 fingerprint；任一 drift 固定零寫入。
- Apply 成功後，registered object version、owner relation 與 terminal receipt 同一 DB transaction 提交；
  registered bytes 不再屬於可清除 staging。commit／response outcome unknown 時先以原 idempotency key 查 receipt，
  不得盲目重送。
- cleanup 只可處理 system-owned、未 Apply、已逾期或明確放棄的 staging bytes；先記 cleanup intent，刪除後記
  terminal cleanup fact。Apply 過、owner registered、operator drop-zone、reconciliation identity 不唯一或唯一
  bytes 的檔案禁止 cleanup。cleanup failure 進 `reconciliation_required`，不得回報正式成功。
- cleanup machine evidence 固定由 immutable `controlled_file_cleanup_events` 擁有。每一事件保存
  `cleanup_id`（`^cfc_[0-9a-f]{32}$`）、`event_id`（`^cfce_[0-9a-f]{32}$`）、staging FK、
  `event_sequence`、`event_type`、`reason`、idempotency／fingerprint、expected staging version／SHA-256、
  actor、correlation、occurred time 與 nullable error code；不得保存 raw bytes 或 public locator。
- sequence 1 只能是無 error 的 `intent`；sequence 2 只能是無 error 的 `completed`，或具非空 error code 的
  `reconciliation_required`。reason 只接受 `expired | abandoned`；同一 cleanup sequence 與同一 idempotency
  sequence 必須唯一，所有 cleanup events 禁止 update／delete。

### 9.5 Receipt／readback 與 reconciliation

Apply receipt discriminator 固定為 `controlled_file_apply`，schema version 固定
`controlled-file-apply-receipt.v1`；payload 至少包含：

```text
receipt_id, outcome(created|replayed), file_id, owner, purpose,
subject_reference, version, sha256_digest, mime_type, size_bytes,
status, applied_at
```

相同 key／相同 canonical command 回原 receipt；相同 key／不同 command fingerprint 固定
`idempotency_mismatch`。reconciliation closed outcomes 固定為 `exact | missing_object | digest_mismatch |
orphan_object | still_writing`；只追加 observation，不自動修復、改 owner root、發送 provider 或刪除 bytes。
mount unavailable、read denied、capacity exhausted 與 watcher lag 屬 storage readiness／health，不偽裝成合法空清單。

### 9.6 Reference-aware finalize、lease 與 Scheduling bridge（2026-08-30 人工裁決）

Task 97 的 additive successor 已核准為 schema-only、no-backfill package；它不把 filesystem 與
MySQL 偽裝成 distributed transaction，也不授權 production／`union_db`、NAS mount、provider、deployment
或不可逆檔案刪除。

1. `controlled_file_finalize_intents` 保存 `pending | processing | available |
   reconciliation_required` 的 durable finalize state；finalize identity 固定為
   `cff_` 加 32 個 lowercase UUIDv4 hex。
2. `controlled_file_references` 首版只允許 Scheduling service-day-log attachment，reference identity
   固定為 `cfrf_` 加 32 個 lowercase UUIDv4 hex。這是 Scheduling-owned relation，不建立
   generic polymorphic owner registry。
3. `controlled_file_leases` 以 staging object 為 bounded key，lease identity 固定為
   `cfl_` 加 32 個 lowercase UUIDv4 hex。lease duration 與 renewal 是可配置 operational policy，
   不得寫成不可變業務期間。
4. Scheduling Apply 在同一 outer UoW 寫入 log、attachment relation、reference、committed outbox
   與 finalize intent；worker 以獨立短交易 claim／lease，DB 交易外執行 storage effect，再以短交易
   寫入 `available` 或 typed reconciliation blocker。DB commit 失敗後不得立即刪除 object。
5. canonical Scheduling object key 固定為
   `scheduling/service-day/v1/{assignment_id}/{service_date}/{attachment_kind}/{sequence}/{sha256}`。
   參數必須使用 owner 已驗證的 canonical scalar，不得含姓名、原檔名或其他 PII。
6. 既有 filesystem `finalize_staged()` 的 `available` 首版只表示bytes 存在且 digest／size
   完整性已驗證；不暗示physical rename／promotion。未來若要變更實體 locator，需獨立
   provider／migration 裁決。
7. pre-successor objects 維持 legacy-readable，排除於新 GC，且不自動 backfill。GC 只能在
   grace period 屆滿、DB 零 authoritative reference 且無 active lease 時處理 staging object；必須
   reference-aware、idempotent、bounded、可 dry-run 並產生 receipt。
8. metadata 存在但 bytes 缺失、或 referenced object 仍留在 staging，分別形成 typed
   repair／blocker 與 reconciler finalize；兩者都不得偽造成功。這些是短期 media processing
   state，不建立永久 media event history。
