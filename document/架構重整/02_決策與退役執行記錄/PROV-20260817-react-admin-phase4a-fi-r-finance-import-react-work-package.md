---
doc_type: work-package
declared_status: proposed
identity: PROV-20260817-react-admin-phase4a-fi-r-finance-import-react
date: 2026-08-17
base_branch: main
base_head: late-bound-at-approval
dirty_baseline: integration-owner-must-capture-before-writer
base_drift_rule: any relevant path drift requires fresh read and re-freeze before edits
owner: Finance Import / React Integration
domain: Finance Import
prerequisites: PROV-20260817-react-admin-phase4-scenario-lineage-governance PASS; PROV-20260817-global-fastapi-typed-error-boundary PASS; PROV-20260817-react-admin-phase4a-finance-import-public-contract-hardening PASS; PROV-20260817-durable-job-public-outcome-contract PASS; PROV-20260817-react-admin-phase4a-r-hcm-apply-react PASS; PROV-20260817-react-admin-phase4a-cw-r-case-workbooks-react PASS; PROV-20260817-react-admin-phase4b-ap-r-react PASS; PROV-20260817-react-admin-phase4b-cf-r-client-finance-react PASS; PROV-20260817-react-admin-phase4b-sp-r-staff-payout-react PASS
approval_required: 核准此 exact Phase 4A-FI-R Work Package
scenario_governance: Part_00_全域測試資料治理與Scenario契約.md
scenario_lineage: ../03_追蹤清單與證據/evidence/PROV-20260817-react-admin-phase3-6-planning/phase4-scenario-lineage-matrix.md
ui_execution_mode: browser-file-dialog-assisted
---

# Phase 4A-FI-R：Finance Import／Bank Facts React接線工作包

## Exact write set

- `ui_react/src/api/finance_import/finance_import_schemas.ts`（new）
- `ui_react/src/api/finance_import/finance_import_errors.ts`（new）
- `ui_react/src/api/finance_import/finance_import_client.ts`（new）
- `ui_react/src/adapters/finance_import/finance_import_adapter.ts`（new）
- `ui_react/src/pages/DataImportPage.tsx`
- `ui_react/src/pages/DataImportPage.css`
- `ui_react/src/pages/FinancePage.tsx`
- `ui_react/src/pages/FinancePage.css`
- `ui_react/src/tests/fixtures/finance_import_contract_fixtures.ts`（new）
- `ui_react/src/tests/finance_import_client.test.ts`（new）
- `ui_react/src/tests/finance_import_adapter.test.ts`（new）
- `ui_react/src/tests/finance_import_flow.test.tsx`（new）

兩頁為shared hot spots，必須由同一Integration Writer施工。`DataImportPage` presentation固定在HCM-R、CW-R
完成後接入FI-R；`FinancePage`則依AP-R→CF-R→SP-R→FI-R順序fresh-read整合。其他lane只交client/adapter/tests。

## Acceptance

Ingest→batch/manifest/review→Preview→JobAccepted→job status→terminal receipt/re-query完整state machine；
JobAccepted絕不顯示匯入成功。Strict enums/Zod、masked bank facts、Abort/stale、outcome_unknown同key retry、
warning navigation與Part00真檔browser；未核准correction/reprocess保持disabled，0 generic client/mock success。

DB：Scope PASS（UI only）；其餘NOT_RUN；`DB_CHANGE_NOT_READY`。
