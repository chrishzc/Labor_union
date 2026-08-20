---
doc_type: work-package
declared_status: proposed
identity: PROV-20260817-react-admin-phase4b-ap-r-react
date: 2026-08-17
base_branch: main
base_head: late-bound-at-approval
dirty_baseline: integration-owner-must-capture-before-writer
base_drift_rule: any relevant path drift requires fresh read and re-freeze before edits
owner: Staff Payables Reporting React Integration Owner
domain: Staff Payables / Access
prerequisites: PROV-20260817-react-admin-phase4-scenario-lineage-governance PASS; PROV-20260817-global-fastapi-typed-error-boundary PASS; PROV-20260817-react-admin-phase4b-ap-public-contract-hardening PASS
approval_required: 核准此 exact Phase 4B-AP-R Work Package
scenario_governance: Part_00_全域測試資料治理與Scenario契約.md
scenario_lineage: ../03_追蹤清單與證據/evidence/PROV-20260817-react-admin-phase3-6-planning/phase4-scenario-lineage-matrix.md
ui_execution_mode: browser-required
---

# Phase 4B-AP-R：Accounts Payable query／export React工作包

## Scope與write set

只接server-masked AP preview、metadata archive list與人工XLSX export；不接核銷/出款/退款/補助/銀行匯入。

- `ui_react/src/api/finance/accounts_payable_client.ts`
- `ui_react/src/api/finance/accounts_payable_schemas.ts`
- `ui_react/src/api/finance/accounts_payable_errors.ts`
- `ui_react/src/adapters/finance/accounts_payable_adapter.ts`
- `ui_react/src/pages/FinancePage.tsx`
- `ui_react/src/pages/FinancePage.css`
- `ui_react/src/tests/accounts_payable_client.test.ts`
- `ui_react/src/tests/accounts_payable_adapter.test.ts`
- `ui_react/src/tests/finance_accounts_payable_page.test.tsx`
- `ui_react/src/tests/finance_export_download.test.ts`
- `ui_react/src/tests/fixtures/finance/accounts_payable_contract_fixtures.ts`

`FinancePage.tsx/.css`由唯一Presentation Writer依AP-R→CF-R→SP-R→FI-R串行整合；client/adapter/tests可
在write set不重疊時平行。AP的canonical presentation留在FinancePage，不移入ReportsPage。

新增`finance.ap.tab|target-month|refresh|summary|row.detail|export|archive|drawer`。其餘五個mutation IDs
必須native disabled。XLSX驗證magic/content type/safe filename/size/SHA-256/correlation；完整銀行/身分不得進DOM。

## Gates

G0 backend/exact approval；G1 display/export-only矩陣；G2 strict Zod+binary metadata；G3零金額/付款狀態推導；
G4 loading/empty/error/abort/download integrity；G5 zero fake mutation/mock；G6 full React/build/lint/UTF-8/diff/PII；
G7真browser受控月份download。`accounts-payable-summary`維持410。

DB：Scope PASS，其餘NOT_RUN；`DB_CHANGE_NOT_READY`。
