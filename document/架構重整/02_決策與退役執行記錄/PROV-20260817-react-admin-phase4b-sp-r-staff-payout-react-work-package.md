---
doc_type: work-package
declared_status: proposed
identity: PROV-20260817-react-admin-phase4b-sp-r-staff-payout-react
date: 2026-08-17
base_branch: main
base_head: late-bound-at-approval
dirty_baseline: integration-owner-must-capture-before-writer
base_drift_rule: any relevant path drift requires fresh read and re-freeze before edits
owner: Staff Payables / React Integration
domain: Staff Payables
prerequisites: PROV-20260817-react-admin-phase4-scenario-lineage-governance PASS; PROV-20260817-global-fastapi-typed-error-boundary PASS; PROV-20260817-react-admin-phase4b-staff-payout-public-contract-hardening PASS; PROV-20260817-durable-job-public-outcome-contract PASS; PROV-20260817-react-admin-phase4b-ap-r-react PASS; PROV-20260817-react-admin-phase4b-cf-r-client-finance-react PASS
approval_required: 核准此 exact Phase 4B-SP-R Work Package
scenario_governance: Part_00_全域測試資料治理與Scenario契約.md
scenario_lineage: ../03_追蹤清單與證據/evidence/PROV-20260817-react-admin-phase3-6-planning/phase4-scenario-lineage-matrix.md
ui_execution_mode: browser-required
---

# Phase 4B-SP-R：Staff Payout durable job React工作包

## Exact write set

- `ui_react/src/api/staff_payables/staff_payout_schemas.ts`（new）
- `ui_react/src/api/staff_payables/staff_payout_errors.ts`（new）
- `ui_react/src/api/staff_payables/staff_payout_client.ts`（new）
- `ui_react/src/adapters/staff_payables/staff_payout_adapter.ts`（new）
- `ui_react/src/pages/FinancePage.tsx`
- `ui_react/src/pages/FinancePage.css`
- `ui_react/src/tests/staff_payout_client.test.ts`（new）
- `ui_react/src/tests/staff_payout_adapter.test.ts`（new）
- `ui_react/src/tests/finance_staff_payout_flow.test.tsx`（new）

## Acceptance

Query→Preview→Apply(JobAccepted)→Job poll→terminal receipt→re-query；accepted/processing/paid嚴格分離。
Timeout只同payload/key retry，worker/provider failure不得顯示paid；銀行資料server masked。Strict Zod、stale/replay/
conflict、single-flight、Part00 browser及0 alert/local paid。FinancePage由同批唯一Integration Writer修改。
Presentation固定依AP-R→CF-R→SP-R→FI-R串行；開始前fresh-read前一包diff／tests，不得與其他Finance page writer平行。

DB：Scope PASS（UI only）；其餘NOT_RUN；`DB_CHANGE_NOT_READY`。
