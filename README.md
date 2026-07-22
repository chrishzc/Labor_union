# 新竹市月子照顧服務人員職業工會－LINE 應用與行政流程自動化系統

> 目前版本：**v0.2.0**（2026-07-22）｜ADAD Master System Map：**56.0**

## 2026-07-22 待推送更新

- 應付帳款匯出改依預定付款／退款日期月份取數；月嫂款按 `staff_id` 彙總，補助退款保留原始應退金額，固定九欄與分銀行流水號契約不變。
- `GenerateFakeData` 已正式凍結：`scripts/generate_fake_data.py` 僅供人工參考，直接執行或匯入都會立即停止。新增假資料條件必須另建用途明確的腳本與測試；ADAD 登記由專案維護者在審查時處理，一般開發者不需操作 ADAD 工具。
- 客戶 BeClass 匯入未指定路徑時，固定讀取 `document/資料庫、資料處理/假資料_模板.xlsx`。
- 已移除會重設資料庫並執行假資料產生器的 `start.bat`；開發環境請依下方手動啟動步驟操作。

## v0.2.0 版本重點

- 正式導入 assignment-owned 多月嫂排班：支援兩位／三位月嫂連續交接、個別排班、雙薪日與實際時數隔離。
- 訂單修改改採 preview／apply 同步流程，明確處理指派配置、排班移除、薪資鎖定與 append-only 稽核快照。
- 客戶資格唯一來源統一為 `clients.identity_status`，移除訂單層重複資格來源並補上安全遷移與 UI／API 驗證。
- 強化帳務匯入、客戶收款對帳、應付帳款摘要／固定九欄匯出，以及補助核銷資料流。
- 擴充 50 筆既有生命週期假資料：加入多月嫂交接、雙薪、超收、退款與跨批次重複匯入，同時保留原有狀態與排班多樣性。
- 完成案件日期防呆：服務中涵蓋基準日、已完成案件不得出現未來實際服務日期、取消案件維持零實際時數。
- 財務警示判斷器與警示生命週期仍列為後續 post-seed 工作；本版假資料不建立 `finance_alerts`／`finance_alert_events`。
- `file_watcher.py` 明確使用 UTF-8 開啟監控檔案，避免 Windows 預設編碼造成非 ASCII 路徑或內容處理差異。

驗證基準：本版 30 個變更測試檔共 `177 passed`；整合 commits 為 `aecca9b` 至 `3cabb4c`。

---

## 2026-07-20 最近更新

- 完成財務導入與核帳流程的第二階段：新增 Legacy / Sinopac / Taishin 匯入格式支援，並補齊帳務正規化驗證測試（`tests/imports/*`）。
- 新增/修訂服務層與資料庫 schema：支援月嫂逐月薪酬、行政補助歸還、補助對帳流程、財務警報管道，並同步調整 `system_map`/`services_system_map`/`api_system_map`。
- 新增「財務警報」後台頁面（`ui/pages/06_finance_alerts.py`）與對應 API/Service；並擴充測試覆蓋（帳務、補助、交易分類、交易指紋、匯入與移轉）。
- 新增 ADAD 遷移腳本與資料清理腳本：`migrate_remove_other_addition.py`、`migrate_adad_task_snapshots.py`，確保欄位清理與快照遷移可受控執行。
- 同步更新 `CHANGES_UI_CHANG.md`，並補齊新 schema 分拆 SQL（`db/schema_parts/*`）以便版本升級。

---

## 2026-07 帳務與管理介面更新

- 全系統訂單關聯鍵統一為 `case_no`，不再使用 `orders.id`／`order_id`。
- 帳務拆分為 `client_payments` 與 `staff_payments`：客戶三期收款與月嫂逐指派應付分開管理。
- 管理端「帳務明細總覽」分開顯示客戶收款、月嫂應付，可依案件編號、訂單狀態與付款狀態篩選；選擇案件後才載入交易明細。
- 新增應付帳款 Excel：月嫂款使用永豐銀行代碼 31，退還補助款使用台新銀行代碼 633。
- 新增分季核銷補助清冊與年度總表，補助天數固定顯示至小數點後 2 位。
- 新增服務人員契約 Excel 鏡像輸出，以及對應的契約、帳務與財務報表 FastAPI。
- FastAPI 的正式 ASGI 入口為 `api.main:app`；LINE、LIFF 與 Webhook 以子路由掛載。

上一個帳務整合版本：`0f9c11f`。

---

本專案旨在為「新竹市月子照顧服務人員職業工會」開發地端運作的 **LINE 客服與行政流程自動化系統**。透過將行政人員手動下載的 Excel 名冊自動化匯入資料庫，並提供 Streamlit 管理後台，未來將延伸串接 LINE Messaging API 實現半自動化客戶配對、合約發送與 RAG 客服問答。

---

## 📂 專案檔案結構與設計緣由

本專案的目錄與檔案結構設計如下：

```text
Lobar_union/
├── .venv/                      # Python 虛擬環境 (Git 已忽略)
├── .agents/                    # ADAD 工作流 / 代理自定義配置目錄
├── db/                         # 資料庫 Schema
│   └── schema.sql              # MySQL 資料庫建表語句 (含 5 階段狀態機、對帳 payments 表與防編碼截斷重置設定)
├── document/                   # 專案設計與規格說明文件
│   ├── API/                    # API 整合設計文件
│   ├── line/                   # LINE 平台整合相關說明
│   ├── 地端部屬/               # 地端部署指南與安全架構
│   ├── 管理端UI/               # Streamlit 管理介面原型與規格
│   │   └── 表格需求模板/       # 管理端所需的 Excel 報表設計模板 (帳務.xlsx、所需表格.xlsx、週報.xlsx、服務人員契約.xlsx)
│   └── 資料庫、資料處理/        # 資料庫欄位對應、SSOT 業務規則與 Data Pipeline 設計
├── downloads/                  # 檔案監控下載根目錄 (由 File Watcher 監聽)
│   ├── bank/                   # 存放銀行對帳單 Excel 來源檔
│   ├── client_beclass/         # 存放客戶 BeClass Excel 來源檔
│   ├── hcm/                    # 存放 HCM 月子平台 - 市府 Excel 來源檔
│   └── staff_beclass/          # 存放月嫂 BeClass Excel 來源檔
├── api/                        # 後端 FastAPI RESTful API 服務
│   ├── main.py                 # FastAPI 入口程式
│   ├── routes/                 # API 路由模組 (orders, matches, schedule, payments, clients, staff, holidays)
│   └── schemas/                # Pydantic 資料驗證 Schema 模型
├── services/                   # 業務邏輯與資料庫存取服務層
│   └── db_service.py           # 核心 DB 服務 (含訂單 CRUD、出勤天數動態精算引擎與 36 欄位 safe_int 防護)
├── ui/                         # Streamlit Web 管理前端專區
│   ├── app.py                  # 側邊欄動態導覽殼層 (AppShellUI)
│   └── pages/                  # 獨立頁面模組專區
│       ├── 01_data_browser.py  # 🗄️ 原始資料庫瀏覽與國定假日管理 (DataBrowserUI)
│       ├── 02_orders.py        # 📊 訂單與帳務管理系統 (OrderUI - Tab 1 總覽/Tab 2 配對/Tab 3 財務)
│       ├── 03_calendar.py      # 📅 服務人員行事曆與檔期調控 (CalendarUI - 四色 HTML 月曆與天數精算)
│       ├── 04_edit_order.py    # 📄 單筆訂單動態試算與維護 (EditOrderUI - 36欄位單據與 Formula Lock)
│       └── 05_form_management.py # 📝 表單與履歷問卷管理專頁 (FormManagementUI - EPPP 契約引擎)
├── scripts/                    # 核心 Python 運作與 Pipeline 腳本
│   ├── imports/                # 微匯入 Pipeline 專屬目錄 (Micro-Pipelines)
│   │   ├── import_client_beclass.py # 處理 BeClass 客戶匯入
│   │   ├── import_client_hcm.py     # 處理 HCM 客戶匯入 (初始化訂單為「洽談中」)
│   │   ├── import_finance_excel.py  # 處理銀行對帳流水單
│   │   └── import_staff_beclass.py  # 處理 BeClass 月嫂匯入
│   ├── file_watcher.py         # 地端檔案自動監控服務
│   ├── generate_fake_data.py   # 已凍結的歷史假資料腳本（僅供人工參考，不可執行或匯入）
│   ├── fix_schedule_conflicts.py # 月嫂檔期衝突檢測與自動修復工具
│   ├── init_db.py              # 資料庫初始化與 Schema 導入
│   └── wait_for_db.py          # 輪詢檢測 MySQL 連線就緒腳本
├── docker-compose.yml          # Docker Compose 配置文件，一鍵啟動 MySQL 8.0 持久化容器
├── main.py                     # 專案主程式入口 (FastAPI 與 Streamlit 同時啟動或導向)
├── online.bat                  # 一鍵啟動生產上線服務 (啟動 Docker, wait_for_db, 啟動 services / watcher)
├── pyproject.toml              # uv 專案管理配置文件
├── requirements.txt            # 從 pyproject.toml 自動編譯導出的相容性依賴清單
├── system_map.yaml             # ADAD 系統架構 SSOT 記憶與狀態事實來源 (Version 54)
├── system_map.md               # ADAD 系統架構 SSOT 說明文件 (Version 54)
└── uv.lock                     # uv 依賴鎖定檔
```

---

## 📄 本次更新說明 (開發實作收尾)

在本次更新中，我們主要進行了以下優化與擴展：
* **API 服務層與 UI 前端整合**：全面導入 FastAPI RESTful API 後端與 Streamlit 前端分離架構，並擴展 UI 表單與履歷問卷管理頁面（Tab 3 變數代理 EPPP 契約引擎）。
* **Data Pipeline 優化**：重構並優化微服務 Pipeline 導入流程，支援客戶、月嫂 BeClass 名冊及 HCM 系統的自動化去重與安全防護。
* **ADAD 架構更新**：系統架構已升級至 Version 54.0，補齊跨子地圖帳務 staging 合約、多月嫂內部 helper 所有權及 Task v3 timeout，維持 SSOT 與 pre-commit 一致。

---

## 🛠️ 開發環境與部署架設指南

本專案保留 `online.bat` 作為正式服務啟動腳本。會重設資料庫並產生假資料的 `start.bat` 已移除；開發與測試環境請改用手動啟動流程。

### 1. 批次檔說明

#### 🌐 `online.bat` (生產上線環境一鍵啟動)
此腳本適合生產環境正式上線使用。執行流程如下：
* 啟動 Docker 中的 MySQL 8.0 容器。
* 等待 MySQL 資料庫連線就緒。
* **⚠️ 安全防護**：**不會**執行資料庫初始化與假資料生成，以確保歷史生產資料的安全。
* 並行啟動 FastAPI 後端、Streamlit 網頁前端，以及 `file_watcher.py` 地端 Excel 檔案自動監控匯入服務。

---

### 2. 啟動方式

#### 正式環境批次啟動
直接在 Windows 終端機（PowerShell）中執行：
```powershell
# 生產/上線環境啟動
.\online.bat
```

#### 手動啟動個別服務
若需單獨除錯，可在啟動 Docker 後手動執行以下指令：
```powershell
# 1. 啟動 Docker 容器
docker-compose up -d

# 2. 啟動 FastAPI 後端
uvicorn api.main:app --reload

# 3. 啟動 Streamlit 管理介面
streamlit run ui/app.py

# 4. 啟動檔案監控
python scripts/file_watcher.py
```

`scripts/init_db.py` 會初始化資料庫，僅能在明確確認目標資料庫後個別執行。請勿執行或匯入 `scripts/generate_fake_data.py`；需要新增測試資料時，應建立用途明確的獨立播種腳本及對應測試。一般開發者不需安裝或操作 ADAD，依標準 Git、Python 與 pytest 流程開發即可。

---

## 🤝 開發與協作規範

本專案由固定開發人員維護。請團隊成員在進行開發與提交修改前，詳閱 **[🤝 開發與協作規範指南](CONTRIBUTING.md)** 以瞭解分支開發流程與 Pull Request (PR) 規範。
