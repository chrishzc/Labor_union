# 新竹市月子照顧服務人員職業工會 - LINE 應用與行政流程自動化系統

本專案旨在為「新竹市月子照顧服務人員職業工會」開發地端運作的 **LINE 客服與行政流程自動化系統**。透過將行政人員手動下載的 Excel 名冊自動化匯入資料庫，未來將延伸串接 LINE Messaging API 實現半自動化客戶配對、合約發送與 RAG 客服問答。

---

## 📂 專案檔案結構與設計緣由

本專案的目錄與檔案結構設計如下，以下說明各檔案的存在目的與設計考量：

```text
Lobar_union/
├── .venv/                      # Python 虛擬環境 (Git 已忽略)
├── .github/                    # Git/GitHub 相關配置 (選填)
├── .obsidian/                  # Obsidian 筆記軟體配置 (主要用於閱讀與編輯 document 下的 markdown)
├── db/                         # 資料庫 Schema
│   └── schema.sql              # MySQL 資料庫建表語句 (包含主外鍵、狀態約束與欄位擴充)
├── document/                   # 專案設計與規格說明文件
│   ├── API/                    # API 整合設計文件
│   ├── line/                   # LINE 平台整合相關說明
│   ├── 地端部屬/               # 地端部署指南與安全架構
│   ├── 管理端UI/               # Streamlit 管理介面原型與規格
│   ├── 資料庫、資料處理/        # 資料庫欄位對應與 Data Pipeline 設計
│   ├── 自動化系統設計規格書(總覽).md # 系統架構、安全規範與各模組功能規格書 (SRS)
│   └── 規格書缺漏分析報告.md     # 針對目前規格書缺漏與優化方向的分析
├── downloads/                  # 放置行政人員手動下載之原始 Excel 檔案的目錄
├── scripts/                    # 核心 Python 運作與資料處理腳本
│   ├── generate_fake_excel.py  # 隨機生成無隱私疑慮的測試 Excel 資料 (用於開發與測試)
│   ├── import_excel.py         # 核心 Data Pipeline：解析 Excel、清洗資料並去重匯入 MySQL
│   └── init_db.py              # 手動執行 schema.sql 初始化/重建資料庫結構的本機腳本
├── tests/                      # 單元測試與整合測試目錄
├── .dockerignore               # Docker 建置時忽略的檔案清單
├── .env                        # 本地環境變數設定檔 (已在 .gitignore 中，含 LINE 密鑰等，需自行建立)
├── .env.example                # 環境變數範本檔
├── .gitignore                  # Git 忽略檔案清單
├── .python-version             # 指定本專案使用的 Python 版本 (3.14)
├── docker-compose.yml          # Docker Compose 配置文件，一鍵啟動 MySQL 資料庫服務
├── last_count.txt              # 記錄上一次處理的資料筆數 (由腳本自動維護)
├── main.py                     # 專案主程式入口 (目前為 Hello World 骨架)
├── pyproject.toml              # uv 專案管理配置文件 (定義專案元數據與頂層依賴)
├── requirements.txt            # 從 pyproject.toml 自動編譯導出的相容性依賴清單 (供傳統 pip 使用)
├── uv.lock                     # uv 依賴鎖定檔，確保所有開發者安裝完全相同的套件版本
├── 欄位.xlsx                   # 官方提供的欄位模板參考檔
└── 欄位_測試用.xlsx             # 模擬測試用的範例 Excel 檔案 (供開發測試參考，實際測試資料建議透過 scripts 腳本動態生成)
```

### 💡 核心依賴套件選型緣由

為了讓後續開發者理解為什麼引入了這些套件，以下為主要依賴的選型說明：
*   **`pandas` 與 `openpyxl`**：專案需要處理行政人員從政府平台及 BeClass 下載的 Excel 資料。`pandas` 提供強大的資料清洗、欄位映射與去重能力；`openpyxl` 則是 `pandas` 讀寫 `.xlsx` 格式檔案所必須的底層引擎。
*   **`pymysql`**：用作 Python 連接 MySQL 資料庫的輕量化驅動程式。用於 `import_excel.py` 與 `init_db.py` 直接執行 SQL 查詢與寫入。
*   **`playwright`**：預留用於後續網頁自動化或爬蟲任務。例如：當未來需要自動化登入政府登記網站抓取名冊，或是自動化執行某些瀏覽器流程時使用。

---

## 🛠️ 開發環境架設指南

### 1. 前置準備
*   安裝 **Git**。
*   安裝 **Docker** 與 **Docker Desktop** (用於在本機啟動資料庫)。
*   安裝 **Python 3.14** (或使用 Python 版本管理工具如 `pyenv`、`uv` 等)。

### 2. 安裝 Python 依賴環境

本專案推薦使用現代 Python 包管理工具 **`uv`** 以獲得極速且一致的依賴同步體驗。同時亦保留了傳統的 `pip` 安裝方式。

#### 💡 方式 A：使用 `uv`（強烈推薦）
1. 安裝 `uv`（若尚未安裝）：
   ```powershell
   # Windows PowerShell
   irm https://astral.sh/uv/install.ps1 | iex
   ```
2. 在專案根目錄下同步依賴（會自動讀取 `.python-version` 並建立虛擬環境）：
   ```powershell
   uv sync
   ```
3. 初始化 Playwright 瀏覽器驅動：
   ```powershell
   uv run playwright install
   ```

#### 💡 方式 B：使用傳統 `pip`
1. 建立並啟用虛擬環境：
   ```powershell
   python -m venv .venv
   # 啟用虛擬環境 (Windows PowerShell)
   .\.venv\Scripts\Activate.ps1
   ```
2. 使用編譯好的 `requirements.txt` 安裝依賴：
   ```powershell
   pip install -r requirements.txt
   ```
3. 初始化 Playwright 瀏覽器驅動：
   ```powershell
   playwright install
   ```

### 3. 複製並設定環境變數
將專案根目錄下的 `.env.example` 複製一份並命名為 `.env`：
```powershell
cp .env.example .env
```
用文字編輯器開啟 `.env`，填入您的 LINE Messaging API 的 `Channel ID` 與 `Channel Secret` 等私密資訊。

### 4. 啟動 Docker 服務（MySQL）
在專案根目錄下，執行以下命令啟動容器：
```powershell
docker-compose up -d
```
這會啟動以下服務：
*   **MySQL 資料庫 (`mysql_db`)**：
    *   連接埠：`3306`
    *   資料庫名稱：`union_db`
    *   預設 root 密碼：`1234`
    *   **自動建表**：首次啟動時，Docker 會自動掛載並執行 `db/schema.sql` 完成資料表的建立。

---

## 🔄 數據流與運作工作流程

當環境架設完畢後，您可以按照以下流程進行開發測試：

```mermaid
graph TD
    A[Docker 啟動 / init_db.py] -->|1. 初始化資料庫建表| B[(MySQL: union_db)]
    C[generate_fake_excel.py] -->|2. 讀取模板並產生測試資料| D(欄位_測試用.xlsx)
    D -->|3. 放置於專案中| E{import_excel.py}
    E -->|4. 資料清洗、去重並寫入| B
```

### 步驟 1：初始化/建置資料庫表格
在開始進行資料測試前，必須先確保資料庫內已建立好對應的資料表。
*   **自動建表**：若您是以 `docker-compose up -d` 首次啟動容器，Docker 會自動掛載並執行 `db/schema.sql` 完成建表，此時可跳過此步驟。
*   **手動重新整理/清空重來**：若您在開發過程中修改了 `db/schema.sql`，或者想要清空資料庫重新開始，可以執行以下腳本：
    ```powershell
    # 使用 uv
    uv run scripts/init_db.py

    # 或使用啟用虛擬環境後的 python
    python scripts/init_db.py
    ```

### 步驟 2：生成測試 Excel 檔案
由於真實客戶資料具備隱私，請使用模擬腳本產生符合工會欄位格式的測試資料：
```powershell
# 使用 uv
uv run scripts/generate_fake_excel.py

# 或使用啟用虛擬環境後的 python
python scripts/generate_fake_excel.py
```
這會讀取 `欄位.xlsx` 的表頭結構，並產生含有模擬資料的 `欄位_測試用.xlsx`，作為後續匯入測試的資料來源。

### 步驟 3：執行 Excel 資料匯入 (Data Pipeline)
當資料庫初始化完成，且測試資料 Excel 已生成後，即可執行匯入腳本將資料清洗並寫入資料庫：
```powershell
# 使用 uv
uv run scripts/import_excel.py

# 或使用啟用虛擬環境後的 python
python scripts/import_excel.py
```
**導入邏輯特性：**
*   腳本會自動解析 `欄位_測試用.xlsx` 中的 `HCM 月子平台 -市府`、`beclass`、`服務人員` 等工作表 (Sheets)。
*   進行資料清洗（去除非法字元、格式化日期、轉換身分狀態等）。
*   在寫入 MySQL 前會以 `case_no` (案件編號) 等關鍵欄位進行去重比對：若資料已存在則執行 `UPDATE`，若為全新資料則執行 `INSERT`，確保不會產生重複資料。

---

## 🚀 後續接手與開發藍圖

本專案目前已完成**地端資料庫容器化、初始化 Schema 與 Excel 數據清洗匯入 (Data Pipeline)** 的基礎建設。後續接手開發人員可參考 `document/自動化系統設計規格書(總覽).md`，依序實作以下模組：

1.  **FastAPI Webhook 服務**：
    *   撰寫 FastAPI 服務對接 LINE Messaging API。
    *   接收使用者的訊息，並引導繳款或發送服務人員履歷。
2.  **RAG 語意檢索客服核心**：
    *   建置地端向量資料庫 (例如 ChromaDB)。
    *   將工會知識庫 (FAQ) 向量化 (Embedding) 存入。
    *   串接 Embedding API / 地端輕量模型，實作相似度比對與防幻覺客服自動回覆。
3.  **地端檔案自動監控服務 (File Watcher)**：
    *   使用 `watchdog` 庫監控 `downloads/` 資料夾。
    *   當行政人員下載新的 Excel 並丟入資料夾時，背景服務自動偵測並觸發 `import_excel.py` 進行資料更新。
4.  **Streamlit 管理 UI**：
    *   設計視覺化的 Web 介面，供工會行政人員手動調整「服務人員行事曆」及執行「案件與配對中心」的四步配對流程。
    *   串接「好好簽 (Breezysign)」等線上契約 API 進行電子合約發送與狀態追蹤。
5.  **地端部署與邊界網路防護**：
    *   架設地端實體伺服器，配置 Nginx 作為反向代理。
    *   設定防火牆僅允許 LINE 官方 Webhook IP 連入 Port 443。
    *   設定 WireGuard VPN，確保 Streamlit 管理介面僅能在 VPN 內網存取。
