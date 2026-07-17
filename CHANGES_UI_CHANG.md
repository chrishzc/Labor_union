# UI_CHANG 變更說明

## 2026-07-15－帳務拆分、財務報表與契約介面

### 帳務明細總覽（Page 2）

- 客戶帳務與月嫂帳務改成兩張獨立表格，欄位不再交錯。
- 客戶收款總覽顯示訂金、第一期、第二期各自的應收金額、實收金額、應收日期、實收日期，以及應收／實收總額與未收餘額。
- 月嫂應付總覽逐筆顯示案件、服務人員、指派、服務時數、單價、服務薪資、樓層費、調整額、應付／實付／未付餘額、應付日期、實付日期與付款狀態。
- 支援案件編號、訂單狀態及客戶／月嫂付款狀態篩選。
- 選擇案件後，自動透過 `GET /api/v1/client-payments/{case_no}` 與 `GET /api/v1/staff-payments/{case_no}` 取得該案件交易明細；不預先載入其他案件。
- 人工補登或沖正交易必須填寫外部識別與原因，摘要金額仍由交易明細計算。

### 應付帳款查詢／輸出（Page 2）

- 可預覽並下載每月應付帳款 Excel。
- 月嫂薪資由永豐銀行代碼 31 出款；客戶退還補助款由台新銀行代碼 633 出款。
- 「退還補助款」與尚未啟用的「解約退款」已明確分開。

### 核銷補助清冊（Page 2）

- 新增分季核銷與年度總表預覽及 Excel 下載。
- 一般市民與補助市民分區顯示；當季沒有補助市民時不顯示下半部。
- 補助天數依補助時數除以每日服務時數計算，固定顯示至小數點後 2 位。

### 表單管理與 FastAPI

- 新增服務人員契約 Excel 鏡像輸出，不修改原始模板。
- 新增客戶收款、月嫂應付、契約內容、應付帳款及補助核銷報表 API。
- FastAPI 正式啟動入口改為 `api.main:app`；`line.main` 僅保留舊程式相容匯入。

對應整合 commit：`0f9c11f`。

---

本文件彙整 `UI_CHANG` 分支相較於 `main` 的主要功能異動，供組長 review 時快速掌握改動重點與影響範圍。

---

## a. 訂單與帳務管理系統 - 訂單總覽與計算對帳（`ui/pages/02_orders.py` 分頁一）

**異動內容**：原本分頁一是一張唯讀的完整資料表（`st.dataframe`），列出所有訂單的全部欄位供瀏覽。現在改為「清單 + 點入展開」模式：每筆訂單顯示為一條可點擊的摘要列（案件編號、客戶姓名、訂單狀態、月嫂、預期開始日、服務天數、雇主自費合計），點擊該列後會直接在同一列下方展開完整的 36 欄位編輯面板（重用 `04_edit_order.py` 的編輯邏輯），可直接調整數值並儲存，不需跳轉頁面。同一時間僅會展開一筆，點選其他筆會自動收合前一筆（手風琴效果）。

**影響範圍**：因改為列表 + 展開模式，**預覽列表所呈現的欄位數量會比原本的完整表格少**（僅保留摘要用欄位），完整欄位需點開該筆訂單才能看到與編輯。

---

## b. 訂單與帳務管理系統 - 案件與配對中心（`ui/pages/02_orders.py` 分頁二，4步智慧配對）

**異動內容**：
- **步驟 1「發送 訂單資訊-1（粗篩）」**：原本僅能單選一位月嫂發送，現改為可**複選多位月嫂**，一次批次發送。
- **步驟 2「發送 訂單資訊-2（精篩）」**：候選名單為步驟 1 已發送過的所有月嫂，清單同時呈現每位月嫂目前的意願回覆狀態（待回覆／願意接案／拒絕接案，可直接於清單中更新），並可自由勾選要發送訂單資訊-2 的對象（不限制僅能選已接案者，保留人工判斷彈性）。
- **步驟 3、4（傳送履歷、成立訂單並定案指派）**：維持僅能選擇單一位月嫂執行，但下拉選單僅列出目前意願為「願意接案」的月嫂，避免誤選尚未回覆或已拒絕的人選。

---

## c. 資料庫原始資料瀏覽（`ui/pages/01_data_browser.py`）

**異動內容**：原本為唯讀表格，現改為可直接於網頁表格上點選儲存格進行即時編輯（`st.data_editor`），編輯後需另外點擊「儲存變更」按鈕才會正式寫入資料庫。系統自動管理欄位（如 `id`、建立/更新時間等）已設為鎖定唯讀，無法從表格上誤改。

**待確認事項**：**目前尚未排除「哪些訂單/資料狀態下不可修改」的情境**（例如訂單已進入「服務中」或「訂單完成」後，某些欄位理論上不應再被隨意覆寫）。此限制邏輯尚待與組長/組員確認規則後再補上，目前是全欄位（除系統唯讀欄位外）皆可編輯。

---

## 其他一併包含於本分支的異動

- 資料庫連線設定（host/port/user/password/database）改為讀取專案根目錄 `.env` 檔案，涵蓋 `services/db_service.py`、4 支 `scripts/imports/*.py`、`scripts/init_db.py`、`scripts/wait_for_db.py`，並保留原寫死數值作為 fallback 預設值。
- `docker-compose.yml` 的 `ports`／`MYSQL_DATABASE`／`MYSQL_ROOT_PASSWORD` 改用 Docker Compose 的 `${VAR:-default}` 語法讀取 `.env`。
- `document/資料庫、資料處理/假資料_範例.xlsx` 新增測試用假資料（HCM 市府、beclass 各 10 筆），供測試匯入流程使用。
- `.gitignore` 新增 `graceAdd/`，排除個人協作用的異動紀錄資料夾。

---

如需查看更詳細的逐次修改歷程（含每次修改的問題背景、實作細節與測試注意事項），可參考 `graceAdd/alterContent.md`（此檔案已被 `.gitignore` 排除，不會出現在本分支的 GitHub 內容中，僅存在於本機）。


---

## 2026-07-13 - Case number normalization

- All customer-facing order and case identifiers now use clients.case_no exclusively.
- Removed the legacy order_no specification and obsolete order-number labels from the UI, forms, API examples, and LINE documents.
- LINE binding, LIFF screens, database relations, and APIs now use `case_no`; the former internal numeric order key has been removed.
- When a LINE-native registration has not yet received a case number, the user is informed that administrative issuance is pending instead of receiving an internal ID.
