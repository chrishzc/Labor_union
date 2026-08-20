---
doc_type: work-package
declared_status: proposed
identity: PROV-20260817-react-admin-phase4b-s-r-react
date: 2026-08-17
base_branch: main
base_head: late-bound-at-approval
dirty_baseline: integration-owner-must-capture-before-writer
base_drift_rule: any relevant path drift requires fresh read and re-freeze before edits
owner: Government Subsidy Reporting React Integration Owner
domain: Government Subsidy / Reporting
prerequisites: PROV-20260817-react-admin-phase4-scenario-lineage-governance PASS; PROV-20260817-global-fastapi-typed-error-boundary PASS; PROV-20260817-react-admin-phase4b-subsidy-report-authority-hardening PASS
approval_required: 核准此 exact Phase 4B-S-R Work Package
evidence_directory: document/架構重整/03_追蹤清單與證據/evidence/PROV-20260817-react-admin-phase4b-s-r-react/
required_receipts: candidate-change-inventory.md; contract-matrix-freeze-receipt.md; verification-receipt.md; browser-smoke-receipt.md; open-findings.md
scenario_governance: Part_00_全域測試資料治理與Scenario契約.md
ui_execution_mode: browser-required
---

# Phase 4B-S-R：Subsidy reconciliation query／export React工作包

## Scope與write set

ReportsPage是本slice唯一presentation owner；只接quarterly/annual subsidy sheet。週報總表與每週在職服務
無typed backend時顯示unavailable，不保留假數字或假完整Excel。

- `ui_react/src/api/finance/subsidy_report_client.ts`
- `ui_react/src/api/finance/subsidy_report_schemas.ts`
- `ui_react/src/api/finance/subsidy_report_errors.ts`
- `ui_react/src/adapters/finance/subsidy_report_adapter.ts`
- `ui_react/src/pages/ReportsPage.tsx`
- `ui_react/src/pages/ReportsPage.css`
- `ui_react/src/tests/subsidy_report_client.test.ts`
- `ui_react/src/tests/subsidy_report_adapter.test.ts`
- `ui_react/src/tests/reports_subsidy_page.test.tsx`
- `ui_react/src/tests/subsidy_report_export_download.test.ts`
- `ui_react/src/tests/fixtures/finance/subsidy_report_contract_fixtures.ts`

新增`reports.subsidy.tab|period|refresh|summary|table|export|unavailable`。禁止前端重算資格、時數、rate、
amount或aggregate。

## Gates

G0 authority/backend/exact approval；G1 root-fact/formula/field matrix；G2 strict decoder/binary metadata；
G3 adapter conservation零公式；G4 period/empty/error/abort/download；G5 other sheets unavailable/zero mock；
G6 full React/build/lint/UTF-8/diff/PII；G7真browserperiod query/download。

DB：Scope PASS，其餘NOT_RUN；`DB_CHANGE_NOT_READY`。
