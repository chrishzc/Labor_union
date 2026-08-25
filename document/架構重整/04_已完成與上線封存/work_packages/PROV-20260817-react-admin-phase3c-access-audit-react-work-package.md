---
doc_type: work-package
declared_status: completed
identity: PROV-20260817-react-admin-phase3c-access-audit-react
date: 2026-08-17
base_branch: main
base_head: 0641ed62d20a85289c82aa5a272b73feff715f59
dirty_baseline: integration-owner-must-capture-before-writer
base_drift_rule: any relevant path drift requires fresh read and re-freeze before edits
owner: React Access Integration Owner
authority: exact-human-approved-2026-08-22
domain: Access / Security Audit
prerequisites: PROV-20260817-react-admin-phase3-scenario-lineage-governance PHASE3_SCENARIO_LINEAGE_METADATA_READY; PROV-20260817-global-fastapi-typed-error-boundary PASS; PROV-20260817-access-account-center-public-contract-hardening PASS; PROV-20260817-access-audit-public-query-hardening PASS
approval_required: 核准此 exact Phase 3C Access Audit React Work Package
evidence_directory: document/架構重整/03_追蹤清單與證據/evidence/PROV-20260817-react-admin-phase3c-access-audit-react/
required_receipts: candidate-change-inventory.md; contract-matrix-freeze-receipt.md; verification-receipt.md; browser-smoke-receipt.md; open-findings.md
scenario_governance: Part_00_全域測試資料治理與Scenario契約.md
ui_execution_mode: browser-required
---

# Phase 3C Access Audit React工作包

人工於2026-08-22批次核准本existing exact Work Package，保持原scope、write set與acceptance並依序施工。

## Scope與exact write set

只把既有Account Management Audit tab由hard-coded rows改為masked list/detail GET。不得開啟帳號mutation、MFA setup、
Jobs或root policy；backend prerequisite未PASS時原位顯示unavailable。

- `ui_react/src/api/access/audit_query_schemas.ts`（new）
- `ui_react/src/api/access/audit_query_errors.ts`（new）
- `ui_react/src/api/access/audit_query_client.ts`（new）
- `ui_react/src/adapters/access/audit_query_adapter.ts`（new）
- `ui_react/src/pages/AccountManagementPage.tsx`
- `ui_react/src/pages/AccountManagementPage.css`
- `ui_react/src/tests/access_audit_query_client.test.ts`（new）
- `ui_react/src/tests/account_audit_query_flow.test.tsx`（new）
- `ui_react/src/tests/account_management_no_fake_mutation.test.tsx`（new）
- `ui_react/src/tests/fixtures/access/audit_query_contract_fixtures.ts`（new）

AccountManagementPage為shared hot spot，串行次序固定為Account Center → Audit React → Durable Job observability；一次
只准一位Presentation Writer。Backend prerequisite產出的
`validation/scenarios/react_admin_access_audit_query.json`為read-only contract input，不得由React writer改寫。
Integration Owner唯一更新evidence/index。其他page、backend/shared/DB不在write set。

## Acceptance

- strict Zod與fresh memory bearer；只呼叫兩個核准GET，lazy load、Abort/generation guard、bounded pagination。
- 0 inline audit sample、0 raw details、0 full IP/PII/secret、0 alert/confirm/non-GET。
- Stable IDs：`account.audit.refresh|filter|table|row|detail|pagination|empty|unavailable`。
- Success/empty/401/403/404/timeout/schema mismatch/stale切換皆fail closed；component fixture須追到backend matrix。
- Focused/full React tests、lint/build、UTF-8/diff、真TOTP browser Network↔DOM。真browser前不得標completed。

## DB gate

| Gate | 狀態 | 理由 |
|---|---|---|
| Scope gate | PASS | React query-only，0 DB |
| Change inventory | PASS | 0 schema/seed/backfill/destructive |
| Static release gate | NOT_RUN | 不適用 |
| Descriptor gate | NOT_RUN | 不適用 |
| Read-only plan gate | NOT_RUN | 不適用 |
| Engine verification gate | NOT_RUN | 不適用 |
| Developer acceptance gate | NOT_RUN | 不適用 |

總結：`DB_CHANGE_NOT_READY`。
