---
doc_type: work-package
declared_status: proposed
identity: PROV-20260817-react-admin-phase4a-r-hcm-apply-react
date: 2026-08-17
base_branch: main
base_head: late-bound-at-approval
dirty_baseline: integration-owner-must-capture-before-writer
base_drift_rule: any relevant path drift requires fresh read and re-freeze before edits
owner: Case Import React Integration Owner
domain: Case Import / Anomalies
prerequisites: PROV-20260817-react-admin-phase4-scenario-lineage-governance PASS; PROV-20260817-global-fastapi-typed-error-boundary PASS; PROV-20260816-react-admin-phase4a-hcm-current-preview PASS; PROV-20260817-react-admin-phase4a-hcm-apply-transaction-public-contract PASS; PROV-20260817-react-admin-phase3d-warning-transition-receipt-hardening PASS
approval_required: 核准此 exact Phase 4A-R Work Package
scenario_governance: Part_00_全域測試資料治理與Scenario契約.md
scenario_lineage: ../03_追蹤清單與證據/evidence/PROV-20260817-react-admin-phase3-6-planning/phase4-scenario-lineage-matrix.md
ui_execution_mode: browser-file-dialog-assisted
---

# Phase 4A-R：HCM Apply／receipt／re-query React工作包

## Scope

只在4A-H whole-workbook UoW、Source Archive Option A、warning disposition與receipt lookup全數通過後，
於既有HCM Drawer啟用Apply。其他五個import families維持鎖定。

## Exact write set

- `ui_react/src/api/case_import/hcm_workbook_client.ts`
- `ui_react/src/api/case_import/hcm_workbook_schemas.ts`
- `ui_react/src/api/case_import/hcm_workbook_errors.ts`
- `ui_react/src/adapters/case_import/hcm_workbook_adapter.ts`
- `ui_react/src/adapters/case_import/hcm_workbook_flow_store.ts`（new）
- `ui_react/src/pages/DataImportPage.tsx`
- `ui_react/src/pages/DataImportPage.css`
- `ui_react/src/tests/hcm_workbook_client.test.ts`
- `ui_react/src/tests/hcm_workbook_adapter.test.ts`
- `ui_react/src/tests/data_import_hcm_apply_flow.test.tsx`（new）
- `ui_react/src/tests/data_import_no_fake_mutation.test.tsx`
- `ui_react/src/tests/fixtures/hcm_workbook_contract_fixtures.ts`

`DataImportPage.tsx/.css`是shared hot spot，本包同批只能有一位Presentation Writer；client/adapter/tests可與
其他bounded lanes平行，但頁面固定依HCM-R→CW-R→FI-R串行整合。

## State machine與IDs

`idle→preview_loading→preview_ready→apply_pending→receipt_received→requery_loading→observed`，並有
`outcome_unknown`；相同key/payload才能重試。保留現有六個`imports.hcm-current.*` IDs，新增
`receipt-lookup|requery|outcome-unknown`。Apply readiness、warning與fingerprint全由server提供；禁止UI放行、
optimistic success或更換unknown command的key。

## Gates

G0 prerequisite/exact approval；G1 Preview/Apply/receipt schemas；G2 negative decode/header/multipart tests；
G3 immutable file bytes/fingerprint lineage；G4 timeout/replay/receipt/requery/close lock；G5其他import mutation全disabled；
G6 full React suite/build/lint/UTF-8/diff/secret/PII；G7 controlled `.xlsx` 真browser。G7只要求receipt中的
warning以safe navigation進入既有query-only Anomalies／Import Warning surface；在3D-W-H與其React mutation
successor完成前，不要求也不得假造warning transition／repair成功。

DB：本React包Scope PASS，其餘NOT_RUN；`DB_CHANGE_NOT_READY`。
