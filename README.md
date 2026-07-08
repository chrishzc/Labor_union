# 新竹市月子照顧服務人員職業工會 - LINE 應用與行政流程自動化系統

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
│   ├── generate_fake_data.py   # 測試假資料生成腳本
│   ├── fix_schedule_conflicts.py # 月嫂檔期衝突檢測與自動修復工具
│   ├── init_db.py              # 資料庫初始化與 Schema 導入
│   └── wait_for_db.py          # 輪詢檢測 MySQL 連線就緒腳本
├── docker-compose.yml          # Docker Compose 配置文件，一鍵啟動 MySQL 8.0 持久化容器
├── main.py                     # 專案主程式入口 (FastAPI 與 Streamlit 同時啟動或導向)
├── start.bat                   # 一鍵啟動開發測試環境 (啟動 Docker, init_db, generate_fake_data, 啟動服務)
├── online.bat                  # 一鍵啟動生產上線服務 (啟動 Docker, wait_for_db, 啟動 services / watcher)
├── pyproject.toml              # uv 專案管理配置文件
├── requirements.txt            # 從 pyproject.toml 自動編譯導出的相容性依賴清單
├── system_map.yaml             # ADAD 系統架構 SSOT 記憶與狀態事實來源 (Version 53)
├── system_map.md               # ADAD 系統架構 SSOT 說明文件 (Version 53)
└── uv.lock                     # uv 依賴鎖定檔
```

---

## 📄 本次更新說明 (開發實作收尾)

在本次更新中，我們主要進行了以下優化與擴展：
* **API 服務層與 UI 前端整合**：全面導入 FastAPI RESTful API 後端與 Streamlit 前端分離架構，並擴展 UI 表單與履歷問卷管理頁面（Tab 3 變數代理 EPPP 契約引擎）。
* **Data Pipeline 優化**：重構並優化微服務 Pipeline 導入流程，支援客戶、月嫂 BeClass 名冊及 HCM 系統的自動化去重與安全防護。
* **ADAD 架構更新**：系統架構已升級至 Version 53.0，確保 SSOT 一致性並加入 `safe_int()` 邊界防護防止程式崩潰。

---

## 🛠️ 開發環境與部署架設指南

本專案提供了兩個 Windows 批次檔，以簡化不同環境下的啟動程序：

### 1. 批次檔說明

#### 🚀 `start.bat` (開發與測試環境一鍵啟動)
此腳本適合開發、測試或重新初始化資料時使用。執行流程如下：
* 以背景模式啟動 Docker 中的 MySQL 8.0 容器。
* 使用 `wait_for_db.py` 腳本輪詢，直到 MySQL 資料庫成功建立並可接受連線。
* **⚠️ 注意**：自動執行 `init_db.py` 重置資料庫，並透過 `generate_fake_data.py` 重新生成乾淨的測試假資料。
* 最後，並行啟動 FastAPI 後端與 Streamlit 管理前端。

#### 🌐 `online.bat` (生產上線環境一鍵啟動)
此腳本適合生產環境正式上線使用。執行流程如下：
* 啟動 Docker 中的 MySQL 8.0 容器。
* 等待 MySQL 資料庫連線就緒。
* **⚠️ 安全防護**：**不會**執行資料庫初始化與假資料生成，以確保歷史生產資料的安全。
* 並行啟動 FastAPI 後端、Streamlit 網頁前端，以及 `file_watcher.py` 地端 Excel 檔案自動監控匯入服務。

---

### 2. 啟動方式

#### 使用一鍵批次檔 (推薦)
直接在 Windows 終端機 (PowerShell) 中執行所需的批次檔：
```powershell
# 開發/測試環境啟動
.\start.bat

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
