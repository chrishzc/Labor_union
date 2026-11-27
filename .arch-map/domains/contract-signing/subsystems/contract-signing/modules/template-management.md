# Module: template-management

## Parent
- domain: `contract-signing`
- subsystem: `contract-signing`

## Responsibility
管理上傳 XLSX 的 typed 欄位映射、零寫入示範預覽與不可變核准版本。`ContractTemplateManagement.inspect` 先檢查檔名及欄位映射；示範模式產生範例值並回傳 `WorkbookPreview`，此方法不直接呼叫模板儲存寫入。保存及啟用另走模板目錄，不改既有案件、文件或其他 owner facts。正式產製依單一模板／映射 pair，歷史來源依保存摘要解析。

## Implementation
- `domains/contract_signing/template_management.py`
- `subsystems/contract_signing/template_management.py`
- `subsystems/contract_signing/template_catalog.py`
- `infrastructure/file/contract_template_store.py`
- `infrastructure/file/contract_template_workbook.py`
- `infrastructure/file/contract_template_images.py` — 原 XLSX raster anchor、尺寸與內嵌 bytes，供管理及 PDF renderer 共用。
- `api/dependencies/contract_templates.py`
- 正式路徑依[受控檔案正式規格 §8.2](../../../../../requirements/30_Controlled_File_Storage正式規格.md)：`CONTROLLED_FILE_STORAGE_ROOT/01_案件合約 (orders)/template-catalog`。查詢不建立目錄；保留既有明確指定的開發儲存路徑。
- **待驗差異**：目前 Windows 管理器以 `APP_ENV=development` 啟動受管程序。程式碼顯示，在本機根目錄非 UNC 且仍有 `CONTRACT_DOCUMENT_ARCHIVE_ROOT` 時，模板解析可能選到舊目錄；兩值皆無時也可能選到專案內開發預設。這不是正式儲存契約；未核實部署設定或實際檔案位置。
- `api/routes/contract_templates.py`
- `api/schemas/contract_templates.py`
- `ui_react/src/pages/ContractTemplatesPage.tsx`
- `ui_react/src/pages/ContractTemplatesPage.css`
- `ui_react/src/api/contract_templates/contract_templates_client.ts`

## Contracts
### 模板預覽、保存與啟用 ^template-catalog-lifecycle

[需求書 §3.1](../../../../../requirements/21_Contract_Signing_Commitment與正常驗收資料鏈正式規格.md#contract-template-versioning) 定義三個動作的不同效果。

| 負責角色 | 正式約定 | 去哪查 |
| --- | --- | --- |
| 系統管理員／前端 | 上傳 XLSX 並檢查映射。示範只用虛構資料；保存與啟用是兩個獨立操作，不能把保存成功顯示成已啟用。 | `ContractTemplatesPage.tsx`、`contract_templates_client.ts` |
| Contract Signing／後端 | 伺服器驗證格式與映射。示範預覽不寫入，也不讀真實案件；保存及啟用分別交給模板目錄。 | `ContractTemplateManagement.inspect/save/activate`、`api/routes/contract_templates.py` |
| 檔案儲存 | 模板 bytes 與映射保存為不可變版本。目錄更新檢查 `expected_catalog_version`，並記錄操作者及重送識別；不在案件 DB 交易內。啟用只影響後續產製，舊文件仍取原版。 | `infrastructure/file/contract_template_store.py`、下方 Verification |

```yaml archmap-impact
- kind: implements_requirement
  source: template-catalog-lifecycle
  target: '.arch-map/requirements/21_Contract_Signing_Commitment與正常驗收資料鏈正式規格.md#^contract-template-versioning'
```

## Verification
- layout_status: `custom_current`
- layout_basis: 同一 Module 的 Python 行為測試與 React/Vitest 呈現測試沿專案既有雙 runtime roots；不跨用彼此的 runner。
- test_root: `tests/domains/contract-signing/subsystems/contract-signing/modules/template-management/`
- higher_boundary: 共用整合測試由 [parent Subsystem](../index.md) 擁有，本 Module 不重複宣告歸屬。
- frontend_test_root: `ui_react/src/tests/domains/contract-signing/subsystems/contract-signing/modules/template-management/`

## Change triggers
核准目錄、歷史解析、typed 欄位來源、上傳格式、入口或驗證歸屬改變時更新。
