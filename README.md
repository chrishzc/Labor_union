# 新竹市月子照顧服務人員職業工會 - LINE 應用與行政流程自動化系統

本專案旨在為「新竹市月子照顧服務人員職業工會」開發地端運作的 **LINE 客服與行政流程自動化系統**。透過將行政人員手動下載的 Excel 名冊自動化匯入資料庫，未來將延伸串接 LINE Messaging API 實現半自動化客戶配對、合約發送與 RAG 客服問答。

---

## 📂 專案檔案結構與設計緣由

本專案的目錄與檔案結構設計如下：

```text
Lobar_union---solo/
├── .venv/                      # Python 虛擬環境 (Git 已忽略)
├── .github/                    # Git/GitHub 相關配置
├── .obsidian/                  # Obsidian 筆記軟體配置
├── db/                         # 資料庫 Schema
│   └── schema.sql              # MySQL 資料庫建表語句 (含 5 階段狀態機、對帳 payments 表與防編碼截斷重置設定)
├── document/                   # 專案設計與規格說明文件
│   ├── API/                    # API 整合設計文件
│   ├── line/                   # LINE 平台整合相關說明
│   ├── 地端部屬/               # 地端部署指南與安全架構
│   ├── 管理端UI/               # Streamlit 管理介面原型與規格
│   │   └── 表格需求模板/       # 管理端所需的 Excel 報表設計模板 (帳務.xlsx、所需表格.xlsx、週報.xlsx)
│   └── 資料庫、資料處理/        # 資料庫欄位對應、SSOT 業務規則與 Data Pipeline 設計
├── downloads/                  # 檔案監控下載根目錄 (由 File Watcher 監聽)
│   ├── bank/                   # 存放銀行對帳單 Excel 來源檔
│   ├── client_beclass/         # 存放客戶 BeClass Excel 來源檔
│   ├── hcm/                    # 存放 HCM 月子平台 - 市府 Excel 來源檔
│   └── staff_beclass/          # 存放月嫂 BeClass Excel 來源檔
├── services/                   # 業務邏輯與資料庫存取服務層
│   └── db_service.py           # 核心 DB 服務 (含訂單 CRUD、出勤天數動態精算引擎與 36 欄位 safe_int 防護)
├── ui/                         # Streamlit Web 管理前端專區
│   ├── app.py                  # 側邊欄動態導覽殼層 (AppShellUI)
│   └── pages/                  # 獨立頁面模組專區
│       ├── 01_data_browser.py  # 🗄️ 原始資料庫瀏覽與國定假日管理 (DataBrowserUI)
│       ├── 02_orders.py        # 📊 訂單與帳務管理系統 (OrderUI - Tab 1 總覽/Tab 2 配對/Tab 3 財務)
│       ├── 03_calendar.py      # 📅 服務人員行事曆與檔期調控 (CalendarUI - 四色 HTML 月曆與天數精算)
│       └── 04_edit_order.py    # 📄 單筆訂單動態試算與維護 (EditOrderUI - 36欄位單據與 Formula Lock)
├── scripts/                    # 核心 Python 運作與 Pipeline 腳本
│   ├── imports/                # 微匯入 Pipeline 專屬目錄 (Micro-Pipelines)
│   │   ├── import_client_beclass.py # 處理 BeClass 客戶匯入
│   │   ├── import_client_hcm.py     # 處理 HCM 客戶匯入 (初始化訂單為「洽談中」)
│   │   ├── import_finance_excel.py  # 處理銀行對帳流水單
│   │   └── import_staff_beclass.py  # 處理 BeClass 月嫂匯入
│   ├── file_watcher.py         # 地端檔案自動監控服務
│   ├── generate_fake_data.py   # 測試假資料生成腳本
│   └── init_db.py              # 資料庫初始化與 Schema 導入
├── tests/                      # 單元測試與整合測試目錄
├── docker-compose.yml          # Docker Compose 配置文件，一鍵啟動 MySQL 8.0 持久化容器
├── main.py                     # 專案主程式入口
├── pyproject.toml              # uv 專案管理配置文件
├── requirements.txt            # 從 pyproject.toml 自動編譯導出的相容性依賴清單
├── system_map.yaml             # ADAD 系統架構 SSOT 記憶與狀態事實來源 (Version 25)
├── system_map.md               # ADAD 系統架構 SSOT 說明文件 (Version 25)
└── uv.lock                     # uv 依賴鎖定檔
```

---

## 📄 本次更新說明 (開發實作收尾)

在此次更新中，我們針對資料庫底層、Data Pipeline 以及 Streamlit UI 管理前端進行了完整的大升級：

### 1. 微服務 Pipeline 拆分 (`scripts/imports/`)
* **`import_client_hcm.py`**：匯入 HCM 政府平台案件，自動建立初始狀態為 `洽談中` 之訂單。
* **`import_client_beclass.py`**：匯入 BeClass 客戶名冊 (以「姓名+生日」組合鍵去重)。
* **`import_staff_beclass.py`**：匯入 BeClass 服務人員 (支援 7 張子表 Delete-and-Insert)。
* **`import_finance_excel.py`**：讀取銀行對帳單，自動解碼虛擬帳號並完成 payments 財務核銷。

### 2. Streamlit Web 管理介面四頁版圖 (`ui/`)
* **`01_data_browser.py`**：原始 7 大資料表檢視與國定假日管理面板。
* **`02_orders.py`**：訂單與帳務管理 (Tab 1 36欄位總覽 / Tab 2 案件配對中心 / Tab 3 實收財務)。
* **`03_calendar.py`**：服務人員行事曆與檔期調控 (四色 HTML 月曆、出勤天數精算、7天緩衝自動解鎖)。
* **`04_edit_order.py`**：單筆訂單動態試算與維護 (36 個欄位工整試算單據、公式鎖定防呆 `Formula Lock Guardrail`)。

### 3. ADAD 架構規範與 SSOT 保障 (`system_map.yaml`)
* 現已推進至 Version 25，全模組狀態皆為 `validated`，並導入 `safe_int()` 防護杜絕 `NaN` 崩潰點。

---

## 🛠️ 開發環境架設指南

### 1. 啟動 Docker 服務 (MySQL 8.0)
```powershell
docker-compose up -d
```

### 2. 啟動 Streamlit 管理介面
```powershell
python -m streamlit run ui/app.py
```
