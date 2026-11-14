# Module: legacy-virtual-account-import

## Parent
- domain: `client-finance`
- subsystem: `client-finance`

## Responsibility
由 Client Finance 匯入舊流程的案件／虛擬帳號實際對照。115 年含以前一般案依原匯入對照，非市民案可用實際對照，無對照時使用公式；116 年起沿用公式。已登錄的歷史非市民案退出公式反查候選。匯入對照保留優先順位；歧義待確認。空白、格式不符或查無訂單的來源列直接略過。

客戶名冊可經同一 owner 的單案 Query／Apply 直接儲存，將本案舊匯入對照原子取代為一個帳號。歷史非市民的單案與批次可經 NAS 專用程序轉入取消案的指定對照，仍有效的占用案回報衝突案號。一般案批次保留既有新增語意，遇到已由非市民案生效的實際號碼時略過該列並回報占用案號。
人工命令與批次匯入共用鎖，Query 的 mapping IDs 作集合版本，Apply fresh-lock 比較 expected IDs 防 stale；receipt 與對照同一 outer UoW。

## Implementation
- `subsystems/client_finance/legacy_virtual_account_workbook.py`
- `domains/client_finance/virtual_account.py`
- `subsystems/client_finance/case_virtual_account.py`
- `subsystems/client_finance/virtual_account_resolution.py`
- `infrastructure/mysql/legacy_virtual_account_repository.py`
- `api/dependencies/legacy_virtual_account_import.py`
- `api/routes/legacy_virtual_account_import.py`
- `api/schemas/legacy_virtual_account_import.py`
- `api/routes/case_virtual_account.py` — `GET /api/v1/admin/client-finance/cases/{case_no}/virtual-account`、`POST /apply`；名冊 writer 權限。單案 `/preview` 依 2026-10-15 人工裁決移除；批次 XLSX Preview 保留。
- `api/schemas/case_virtual_account.py`
- `ui_react/src/api/client_finance/case_virtual_account_client.ts`
- `ui_react/src/components/ClientRegistryVirtualAccount.tsx` — 名冊帳號直接儲存、同 key 結果核對與正式回讀。
- `ui_react/src/components/LegacyVirtualAccountImport.tsx`
- `db/schema_parts/225_client_legacy_virtual_accounts.sql`
- `db/schema_parts/1042_client_legacy_virtual_accounts.sql`

## Dependencies
- outbound: `orders` — 只接受已存在的 canonical `case_no`，轉移時重查正式取消狀態。
- inbound: `receipt-reconciliation`／`contract-signing` — 虛擬帳號解析依案件年度及類型決定帳號來源。

## Contracts
- `document/架構重整/01_規格基線/04_Client_Finance_Domain.md`

## Verification
- layout_status: `custom_current`
- test_root: `tests/domains/client-finance/subsystems/client-finance/modules/legacy-virtual-account-import/`
- presentation_test_root: `ui_react/src/tests/domains/client-finance/subsystems/client-finance/integration/legacy_virtual_account_import.test.tsx`
- presentation_test_root: `ui_react/src/tests/domains/client-finance/subsystems/client-finance/modules/legacy-virtual-account-import/`

## Provenance
- 匯入、略過與人工核銷語意 — `architecture_declared` — 2026-09-15 使用者裁決。
- 實作與驗證路徑 — `source_observed` — current implementation。

## Change triggers
匯入欄位、帳號格式、案件存在條件、核銷唯一性或 UI 入口改變時重新核對。
