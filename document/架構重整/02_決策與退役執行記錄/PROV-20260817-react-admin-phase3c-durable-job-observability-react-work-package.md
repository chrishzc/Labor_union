---
doc_type: work-package
declared_status: proposed
identity: PROV-20260817-react-admin-phase3c-durable-job-observability-react
date: 2026-08-17
base_branch: main
base_head: late-bound-at-approval
dirty_baseline: integration-owner-must-capture-before-writer
base_drift_rule: any relevant path drift requires fresh read and re-freeze before edits
owner: React Durable Jobs Integration Owner
domain: Global Durable Jobs / Access Presentation
prerequisites: PROV-20260817-react-admin-phase3-scenario-lineage-governance PASS; PROV-20260817-global-fastapi-typed-error-boundary PASS; PROV-20260817-access-account-center-public-contract-hardening PASS; PROV-20260817-react-admin-phase3c-access-audit-react PASS; PROV-20260817-durable-job-public-outcome-contract PASS
approval_required: 核准此 exact Phase 3C Durable Job Observability React Work Package
evidence_directory: document/架構重整/03_追蹤清單與證據/evidence/PROV-20260817-react-admin-phase3c-durable-job-observability-react/
required_receipts: candidate-change-inventory.md; contract-matrix-freeze-receipt.md; verification-receipt.md; browser-smoke-receipt.md; open-findings.md
scenario_governance: Part_00_全域測試資料治理與Scenario契約.md
ui_execution_mode: browser-required
---

# Phase 3C Durable Job safe observability React工作包

## Scope與exact write set

只把Account Management Jobs tab改接Global Durable Job frozen public outcome Query；不解析domain-specific raw receipt/error，
不新增run/retry，cancel只有Global契約明確允許的queued-only命令，且可選擇先維持disabled。本包不修改Global backend。

- `ui_react/src/api/jobs/job_observability_schemas.ts`（new）
- `ui_react/src/api/jobs/job_observability_errors.ts`（new）
- `ui_react/src/api/jobs/job_observability_client.ts`（new）
- `ui_react/src/adapters/jobs/job_observability_adapter.ts`（new）
- `ui_react/src/pages/AccountManagementPage.tsx`
- `ui_react/src/pages/AccountManagementPage.css`
- `ui_react/src/tests/job_observability_client.test.ts`（new）
- `ui_react/src/tests/account_jobs_observability_flow.test.tsx`（new）
- `ui_react/src/tests/account_management_no_fake_mutation.test.tsx`
- `ui_react/src/tests/fixtures/jobs/job_public_outcome_contract_fixtures.ts`（new）

AccountManagementPage sole-writer順序固定為Account Center → Access Audit → Jobs。本包開始前兩個 exact prerequisites
皆須PASS。Global prerequisite產出的`validation/scenarios/durable_job_public_outcome.json`為read-only contract
input，不得由React writer改寫。backend、worker/repository、shared transport、其他page、DB/schema不在write set。

## Acceptance

- strict closed union區分queued/running/succeeded/failed/cancelled/outcome_unknown；job accepted不等於Domain成功。
- UI只顯示safe job identity/type/status/timestamps/bounded public outcome；raw command/receipt/error/provider/PII禁止。
- GET lazy/poll具Abort、stale guard與request budget；頁面關閉後不得繼續poll。
- `account.jobs.refresh|table|detail|status|retry-unavailable|cancel` stable IDs；未核准mutation原生disabled。
- 不得使用generic raw `dict` fallback、local fake jobs、alert/confirm或硬編healthy狀態。
- Focused/full React tests、lint/build、UTF-8/diff、真TOTP browser success/empty/error/reload；缺受控job資料時
  G1～G6仍須完成，最高標`implemented-awaiting-controlled-browser-data`。

## DB gate

| Gate | 狀態 | 理由 |
|---|---|---|
| Scope gate | PASS | React observability，0 DB |
| Change inventory | PASS | 0 schema/seed/backfill/destructive |
| Static release gate | NOT_RUN | 不適用 |
| Descriptor gate | NOT_RUN | 不適用 |
| Read-only plan gate | NOT_RUN | 不適用 |
| Engine verification gate | NOT_RUN | 不適用 |
| Developer acceptance gate | NOT_RUN | 不適用 |

總結：`DB_CHANGE_NOT_READY`。
