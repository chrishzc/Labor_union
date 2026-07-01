# Version: 4

##### Module: InitDB
- Type: script
- Description: 資料庫初始化腳本，執行 schema.sql 以建立與重建 MySQL 資料庫結構。
- Source: scripts/init_db.py
- Dependencies: []
- Input:
  - schema_sql: db/schema.sql
- Output:
  - success: boolean
- Invariants: []
- Preferred Pattern: none
- Verification: []
- Todo:
  - [x] 在 clients 表新增 line_user_id (VARCHAR(100))
  - [x] 在 staff 表新增 line_user_id (VARCHAR(100)), weekly_rest_days (JSON), service_regions (JSON), special_skills (JSON)
  - [x] 新增 orders 表 (包含 status, client_id, staff_id, cancel_reason, line_group_id, actual_start_date, contract_id 等欄位)
  - [x] 新增 matching_records 中介表 (包含 order_id, staff_id, caregiver_accepted, sent_at 等欄位)
  - [x] 在 db/schema.sql 新增帳務相關資料表 (以對照 帳務.xlsx 的收支與月嫂轉帳紀錄)
  - [x] 【架構重構】在 schema.sql 中標註未來將移除 case_no，並全面改用「查詢序號(案件編號)」作為關聯主鍵
- Checkpoint:
  - [x] CP-2.1: 審查 schema.sql 新增之表格與欄位設計是否符合系統擴充需求
  - [x] CP-3.1: 審查 schema.sql 新增之帳務收支資料表結構設計
  - [x] CP-4.1: 審查主鍵重構與「帳務與訂單業務規則.md」的實作對齊狀況

##### Module: ImportClientHCM
- Type: script
- Description: 監控並解析 HCM 月子平台 Excel 案件檔案，以「查詢序號(案件編號)」為唯一識別碼，支援新增與更新複寫寫入 MySQL clients 表。
- Source: scripts/imports/import_client_hcm.py
- Dependencies: [InitDB]
- Input:
  - excel_file: str
  - db_config: dict
- Output:
  - inserted_count: int
  - updated_count: int
- Invariants: []
- Preferred Pattern: none
- Verification: []
- Todo:
  - [x] 撰寫 scripts/imports/import_client_hcm.py 解析 HCM 月子平台分頁
- Checkpoint:
  - [x] CP-5.1: 審查 HCM 月子平台資料清洗與去重更新邏輯

##### Module: ImportClientBeclass
- Type: script
- Description: 監控並解析客戶 beclass 報名名冊 Excel 檔案，以「姓名+出生年月日」為組合唯一鍵，支援資料庫 clients 表的異動偵測與資料更新複寫。
- Source: scripts/imports/import_client_beclass.py
- Dependencies: [InitDB]
- Input:
  - excel_file: str
  - db_config: dict
- Output:
  - inserted_count: int
  - updated_count: int
- Invariants: []
- Preferred Pattern: none
- Verification: []
- Todo:
  - [x] 撰寫 scripts/imports/import_client_beclass.py 解析 BeClass 客戶分頁
- Checkpoint:
  - [x] CP-5.2: 審查 BeClass 客戶資料組合唯一鍵異動更新邏輯

##### Module: ImportStaffBeclass
- Type: script
- Description: 監控並解析服務人員 beclass 報名名冊 Excel 檔案，以「身分證字號」為唯一識別碼，支援資料庫 staff 表的異動偵測與資料更新複寫。
- Source: scripts/imports/import_staff_beclass.py
- Dependencies: [InitDB]
- Input:
  - excel_file: str
  - db_config: dict
- Output:
  - inserted_count: int
  - updated_count: int
- Invariants: []
- Preferred Pattern: none
- Verification: []
- Todo:
  - [x] 撰寫 scripts/imports/import_staff_beclass.py 解析 BeClass 服務人員分頁
- Checkpoint:
  - [x] CP-5.3: 審查 BeClass 服務人員身分證字號異動更新邏輯

##### Module: ImportFinanceExcel
- Type: script
- Description: 監控並解析合作社流水帳對帳單，依據 14 碼虛擬帳號解碼還原案號進行付款核銷與更新寫入 MySQL payments 表。
- Source: scripts/imports/import_finance_excel.py
- Dependencies: [InitDB]
- Input:
  - finance_excel: str
  - db_config: dict
- Output:
  - inserted_count: int
  - updated_count: int
- Invariants: []
- Preferred Pattern: none
- Verification: []
- Todo:
  - [x] 撰寫 scripts/import_finance_excel.py 腳本解析帳務.xlsx
  - [x] 實作帳務數據去重與清洗邏輯並匯入 MySQL 帳務表
- Checkpoint:
  - [x] CP-3.2: 審查帳務資料清洗與匯入邏輯

##### Module: GenerateFakeFinance
- Type: script
- Description: 模擬生成帳務.xlsx 的測試假資料，包含合作社流水帳與案件財務對照表，符合 14 碼虛擬帳號轉換規則與固定金額。
- Source: scripts/generate_fake_finance.py
- Dependencies: []
- Input: {}
- Output:
  - success: boolean
- Invariants: []
- Preferred Pattern: none
- Verification: []
- Todo:
  - [x] 撰寫 scripts/generate_fake_finance.py 生成符合規格的假帳務 Excel
- Checkpoint: []

##### Module: FileWatcher
- Type: service
- Description: 地端檔案監控服務，監控 downloads/ 下各專屬子資料夾，當有新檔案寫入或現有檔案更新時，自動觸發對應的微匯入腳本。
- Source: scripts/file_watcher.py
- Dependencies: [ImportClientHCM, ImportClientBeclass, ImportStaffBeclass, ImportFinanceExcel]
- Input:
  - watch_dir: downloads/
- Output:
  - running: boolean
- Invariants: []
- Preferred Pattern: none
- Verification: []
- Todo:
  - [x] 撰寫 scripts/file_watcher.py 實作 watchdog 檔案監控並分發觸發邏輯
- Checkpoint:
  - [x] CP-6.1: 審查地端檔案監控與對應腳本觸發之穩定性

##### Module: Main
- Type: entrypoint
- Description: 系統主程式入口。
- Source: main.py
- Dependencies: [FileWatcher]
- Input: {}
- Output: {}
- Invariants: []
- Preferred Pattern: none
- Verification: []
- Todo: []
- Checkpoint: []
