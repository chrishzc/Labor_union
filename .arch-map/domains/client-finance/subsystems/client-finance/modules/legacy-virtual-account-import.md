# Module: legacy-virtual-account-import

## Parent
- domain: `client-finance`
- subsystem: `client-finance`

## Responsibility
由 Client Finance 匯入舊流程的案件／虛擬帳號實際對照。現行案件編號產生規則保持不變；空白、格式不符或查無訂單的來源列直接略過。相同帳號命中多個案件時不得自動核銷。

## Implementation
- `subsystems/client_finance/legacy_virtual_account_workbook.py`
- `infrastructure/mysql/legacy_virtual_account_repository.py`
- `api/dependencies/legacy_virtual_account_import.py`
- `api/routes/legacy_virtual_account_import.py`
- `api/schemas/legacy_virtual_account_import.py`
- `ui_react/src/components/LegacyVirtualAccountImport.tsx`
- `db/schema_parts/225_client_legacy_virtual_accounts.sql`
- `db/schema_parts/1042_client_legacy_virtual_accounts.sql`

## Dependencies
- outbound: `orders` — 只接受已存在的 canonical `case_no`，不存在即略過。
- inbound: `receipt-reconciliation` — 虛擬帳號解析合併舊流程對照與現行公式候選。

## Contracts
- `document/架構重整/01_規格基線/04_Client_Finance_Domain.md`

## Verification
- layout_status: `custom_current`
- test_root: `tests/domains/client-finance/subsystems/client-finance/modules/legacy-virtual-account-import/`
- presentation_test_root: `ui_react/src/tests/domains/client-finance/subsystems/client-finance/integration/legacy_virtual_account_import.test.tsx`

## Provenance
- 匯入、略過與人工核銷語意 — `architecture_declared` — 2026-09-15 使用者裁決。
- 實作與驗證路徑 — `source_observed` — current implementation。

## Change triggers
匯入欄位、帳號格式、案件存在條件、核銷唯一性或 UI 入口改變時重新核對。
