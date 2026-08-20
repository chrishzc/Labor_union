---
doc_type: work-package
declared_status: proposed
identity: PROV-20260817-react-admin-phase4a-cw-r-case-workbooks-react
date: 2026-08-17
base_branch: main
base_head: late-bound-at-approval
dirty_baseline: integration-owner-must-capture-before-writer
base_drift_rule: any relevant path drift requires fresh read and re-freeze before edits
owner: Case Import / Orders Historical Adoption / React Integration
domain: Case Import / Staff / Orders
prerequisites: PROV-20260817-react-admin-phase4-scenario-lineage-governance PASS; PROV-20260817-global-fastapi-typed-error-boundary PASS; PROV-20260817-case-import-workbook-policy-decision PASS; PROV-20260817-react-admin-phase4a-case-workbooks-public-contract-hardening PASS; PROV-20260817-react-admin-phase4a-r-hcm-apply-react PASS
approval_required: 核准此 exact Phase 4A-CW-R Work Package
scenario_governance: Part_00_全域測試資料治理與Scenario契約.md
scenario_lineage: ../03_追蹤清單與證據/evidence/PROV-20260817-react-admin-phase3-6-planning/phase4-scenario-lineage-matrix.md
ui_execution_mode: browser-file-dialog-assisted
---

# Phase 4A-CW-R：Case workbooks React接線工作包

## Scope／write set

三family使用獨立bounded clients，禁止generic import client：

- `ui_react/src/api/case_import/client_beclass_workbook/client_beclass_workbook_schemas.ts`（new）
- `ui_react/src/api/case_import/client_beclass_workbook/client_beclass_workbook_errors.ts`（new）
- `ui_react/src/api/case_import/client_beclass_workbook/client_beclass_workbook_client.ts`（new）
- `ui_react/src/api/case_import/staff_historical_workbook/staff_historical_workbook_schemas.ts`（new）
- `ui_react/src/api/case_import/staff_historical_workbook/staff_historical_workbook_errors.ts`（new）
- `ui_react/src/api/case_import/staff_historical_workbook/staff_historical_workbook_client.ts`（new）
- `ui_react/src/api/orders/historical_order_workbook/historical_order_workbook_schemas.ts`（new）
- `ui_react/src/api/orders/historical_order_workbook/historical_order_workbook_errors.ts`（new）
- `ui_react/src/api/orders/historical_order_workbook/historical_order_workbook_client.ts`（new）
- `ui_react/src/adapters/case_import/client_beclass_workbook_adapter.ts`（new）
- `ui_react/src/adapters/case_import/staff_historical_workbook_adapter.ts`（new）
- `ui_react/src/adapters/orders/historical_order_workbook_adapter.ts`（new）
- `ui_react/src/pages/DataImportPage.tsx`
- `ui_react/src/pages/DataImportPage.css`
- `ui_react/src/tests/client_beclass_workbook_client.test.ts`（new）
- `ui_react/src/tests/staff_historical_workbook_client.test.ts`（new）
- `ui_react/src/tests/historical_order_workbook_client.test.ts`（new）
- `ui_react/src/tests/case_workbook_adapters.test.ts`（new）
- `ui_react/src/tests/data_import_case_workbooks_flow.test.tsx`（new）

HCM Historical卡維持410 retired。`DataImportPage.tsx`是shared hot spot，只由Integration Writer修改。

## Acceptance

strict Zod、file bytes/digest、Preview 0 write、Apply receipt/re-query、same-key replay/conflict、partial/atomic
依server contract呈現；未來unavailable不可用mock填滿。真browser以Part00去敏xlsx覆蓋三family；0 random sample、
0 alert/confirm、0 unsafe cast。Phase5 cutover另案。

DB：Scope PASS（UI only）；其餘NOT_RUN；`DB_CHANGE_NOT_READY`。
