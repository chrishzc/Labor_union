# Module: template-management

## Parent
- domain: `contract-signing`
- subsystem: `contract-signing`

## Responsibility
管理上傳 XLSX 的 typed 欄位映射、零寫入示範預覽與不可變核准版本。保存及啟用只更新模板目錄，不改既有案件、文件或其他 owner facts。正式產製依單一模板／映射 pair，歷史來源依保存摘要解析。

## Implementation
- `domains/contract_signing/template_management.py`
- `subsystems/contract_signing/template_management.py`
- `subsystems/contract_signing/template_catalog.py`
- `infrastructure/file/contract_template_store.py`
- `infrastructure/file/contract_template_workbook.py`
- `infrastructure/file/contract_template_images.py` — 原 XLSX raster anchor、尺寸與內嵌 bytes，供管理及 PDF renderer 共用。
- `api/dependencies/contract_templates.py`
- Production archive/template roots derive from the single NAS root's `01_案件合約 (orders)` via shared storage_layout; writes inherit the NAS layout and reads do not create directories. Existing explicit development archive roots stay unchanged.
- `api/routes/contract_templates.py`
- `api/schemas/contract_templates.py`
- `ui_react/src/pages/ContractTemplatesPage.tsx`
- `ui_react/src/pages/ContractTemplatesPage.css`
- `ui_react/src/api/contract_templates/contract_templates_client.ts`

## Contracts
- `document/架構重整/01_規格基線/21_Contract_Signing_Commitment與正常驗收資料鏈正式規格.md` — CTM-01～06。

## Verification
- layout_status: `custom_current`
- layout_basis: 同一 Module 的 Python 行為測試與 React/Vitest 呈現測試沿專案既有雙 runtime roots；不跨用彼此的 runner。
- test_root: `tests/domains/contract-signing/subsystems/contract-signing/modules/template-management/`
- higher_boundary: 共用整合測試由 [parent Subsystem](../index.md) 擁有，本 Module 不重複宣告歸屬。
- frontend_test_root: `ui_react/src/tests/domains/contract-signing/subsystems/contract-signing/modules/template-management/`

## Change triggers
核准目錄、歷史解析、typed 欄位來源、上傳格式、入口或驗證歸屬改變時更新。
