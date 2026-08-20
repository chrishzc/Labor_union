---
doc_type: work-package
declared_status: proposed
identity: PROV-20260817-react-admin-phase4b-cf-r-client-finance-react
date: 2026-08-17
base_branch: main
base_head: late-bound-at-approval
dirty_baseline: integration-owner-must-capture-before-writer
base_drift_rule: any relevant path drift requires fresh read and re-freeze before edits
owner: Client Finance / React Integration
domain: Client Finance
prerequisites: PROV-20260817-react-admin-phase4-scenario-lineage-governance PASS; PROV-20260817-global-fastapi-typed-error-boundary PASS; PROV-20260817-react-admin-phase4b-client-finance-public-contract-hardening PASS; PROV-20260817-react-admin-phase4b-ap-r-react PASS
approval_required: 核准此 exact Phase 4B-CF-R Work Package
scenario_governance: Part_00_全域測試資料治理與Scenario契約.md
scenario_lineage: ../03_追蹤清單與證據/evidence/PROV-20260817-react-admin-phase3-6-planning/phase4-scenario-lineage-matrix.md
ui_execution_mode: browser-required
---

# Phase 4B-CF-R：Client Receipt／Refund／Reversal React工作包

## Exact write set

- `ui_react/src/api/client_finance/receipt_reconciliation/receipt_reconciliation_schemas.ts`（new）
- `ui_react/src/api/client_finance/receipt_reconciliation/receipt_reconciliation_errors.ts`（new）
- `ui_react/src/api/client_finance/receipt_reconciliation/receipt_reconciliation_client.ts`（new）
- `ui_react/src/api/client_finance/refund_reversal/refund_reversal_schemas.ts`（new）
- `ui_react/src/api/client_finance/refund_reversal/refund_reversal_errors.ts`（new）
- `ui_react/src/api/client_finance/refund_reversal/refund_reversal_client.ts`（new）
- `ui_react/src/adapters/client_finance/receipt_reconciliation_adapter.ts`（new）
- `ui_react/src/adapters/client_finance/refund_reversal_adapter.ts`（new）
- `ui_react/src/pages/FinancePage.tsx`
- `ui_react/src/pages/FinancePage.css`
- `ui_react/src/tests/client_receipt_client.test.ts`（new）
- `ui_react/src/tests/client_refund_reversal_client.test.ts`（new）
- `ui_react/src/tests/finance_client_receipt_refund_flows.test.tsx`（new）
- `ui_react/src/tests/finance_no_fake_mutation.test.tsx`（new）

## Acceptance

保留現有receipt/refund drawers，接Query→Preview→Apply→receipt→re-query；server金額/status唯一權威，
禁止local calculation/settled state。Strict Zod、fresh token、idempotency/stale/outcome_unknown、PII masking、
native single-flight與Part00 controlled browser。FinancePage共享writer必須與Staff Payout/AP/Subsidy lanes串行。
Presentation固定依AP-R→CF-R→SP-R→FI-R；開始前fresh-read前一包diff／tests，Subsidy只擁有ReportsPage，
不得平行修改FinancePage。

DB：Scope PASS（UI only）；其餘NOT_RUN；`DB_CHANGE_NOT_READY`。
