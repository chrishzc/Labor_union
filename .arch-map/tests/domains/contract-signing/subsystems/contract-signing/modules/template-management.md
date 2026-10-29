module: template-management
parent_subsystem: contract-signing
architecture: ../../../../../../domains/contract-signing/subsystems/contract-signing/modules/template-management.md
layout_status: current
test_root: tests/domains/contract-signing/subsystems/contract-signing/modules/template-management/

# Owned verification
- `test_template_management.py` — 零寫入、實際兩模板、合併格、必要欄位、不可變 bytes、CAS、重播及毀損拒絕。
- `test_template_api.py` — authenticated multipart、保存／啟用／重播／核對、下載及來源版本重用。
- `tests/domains/contract-signing/subsystems/contract-signing/integration/test_template_version_lineage.py` — 新版啟用後舊來源 PDF 與內嵌圖完整性。
- `ui_react/src/tests/domains/contract-signing/subsystems/contract-signing/modules/template-management/contract_templates_page.test.tsx` — 真正儲存與啟用分離、映射不繼承、錯誤保留與原命令核對。
