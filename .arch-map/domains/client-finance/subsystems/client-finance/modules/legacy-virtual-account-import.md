# Module: legacy-virtual-account-import

## Parent
- domain: `client-finance`
- subsystem: `client-finance`

## Responsibility
由 Client Finance 匯入舊流程的案件／虛擬帳號實際對照。只要案件存在匯入對照，收款解析與契約顯示皆以匯入帳號為優先且不得回退公式；唯一對照可直接使用，多筆不同對照須人工處理。只有完全沒有匯入對照時才使用現行案件編號公式；空白、格式不符或查無訂單的來源列直接略過。相同帳號命中多個案件時不得自動核銷。

客戶名冊可經同一 owner 的單案 Query／Apply 直接儲存，將全部舊匯入對照原子取代為一個帳號；不填原因、不預覽、不改內建公式。
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
- outbound: `orders` — 只接受已存在的 canonical `case_no`，不存在即略過。
- inbound: `receipt-reconciliation`／`contract-signing` — 虛擬帳號解析先判斷匯入對照；不存在時才建立現行公式候選。

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
