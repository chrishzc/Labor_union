---
doc_type: work-package
declared_status: proposed
identity: PROV-20260817-react-admin-phase4c-notification-rules-mutation-react
date: 2026-08-17
owner: React LINE Integration Owner
domain: LINE Configuration
prerequisites: PROV-20260817-react-admin-phase4-scenario-lineage-governance PASS; PROV-20260817-global-fastapi-typed-error-boundary PASS; PROV-20260817-line-knowledge-authorization-normalization PASS; PROV-20260817-line-notification-rule-mutation-public-contract-hardening PASS; PROV-20260817-react-admin-phase4c-richmenu-mutation-react PASS
base_branch: main
base_head: late-bound-at-approval
dirty_baseline: integration-owner-must-capture-before-writer
base_drift_rule: any relevant path drift requires fresh read and re-freeze before edits
approval_required: 核准此 exact Phase 4C-NR-R Work Package
scenario_governance: Part_00_全域測試資料治理與Scenario契約.md
scenario_lineage: ../03_追蹤清單與證據/evidence/PROV-20260817-react-admin-phase3-6-planning/phase4-scenario-lineage-matrix.md
ui_execution_mode: browser-required
---

# Phase 4C-NR-R：Notification Rules mutation React successor

## 0. Prerequisites

frontmatter列出的所有prerequisite均須有fresh PASS；manual replay不在本包。

## 1. Exact write set

- `ui_react/src/api/line_configuration/notification_rule_mutation_schemas.ts`（new）
- `ui_react/src/api/line_configuration/notification_rule_mutation_errors.ts`（new）
- `ui_react/src/api/line_configuration/notification_rule_mutation_client.ts`（new）
- `ui_react/src/adapters/line_configuration/notification_rule_mutation_adapter.ts`（new）
- `ui_react/src/pages/LineManagementPage.tsx`
- `ui_react/src/pages/LineManagementPage.css`
- `ui_react/src/tests/notification_rule_mutation_client.test.ts`（new）
- `ui_react/src/tests/line_notification_rule_flow.test.tsx`（new）
- `ui_react/src/tests/line_management_no_fake_mutation.test.tsx`

Page sole writer；shared/backend/DB/provider/manual replay不在write set。

## 2. Acceptance

Strict decode；server revision/grammar權威；Preview→Save/Delete receipt→re-query；無uncontrolled defaults；stable IDs
`line.notification-rule.create/edit/preview/save/delete`；unknown predicate/extra field fail closed；0 provider call/fake success；
真browser需controlled disabled/shadow及enabled scenario，否則blocked。

G1契約矩陣必須逐一抄錄已PASS backend receipt中的exact Preview／Save／Delete／receipt／re-query method、path與
closed schema；client network allowlist以外一律fail closed。manual replay、generic Jobs、raw definition或未凍結
status endpoint不得出現在production dependency closure；缺任一resource-specific authority即
`BLOCKED_BACKEND_PUBLIC_CONTRACT`。

## 3. Lanes／G0–G7

Contract Scout唯讀freeze；Client Writer只寫bounded client/adapter/tests；Presentation Writer等freeze並獨占page；Auditor唯讀；
Integration Owner唯一寫evidence/index。G0逐一驗證全部frontmatter prerequisite；G1 exact endpoint/schema matrix；G2 strict negative decode；G3 Preview/Save/Delete state machine；
G4 native disabled allowlist與0 fake mutation；G5 full suite；G6真browser revision/stale/re-query；G7scope/UTF-8/secret receipts。
不得以空/unavailable整頁或component fixture宣稱real-data完成。

## 4. DB gate

| Gate | Status | Evidence |
|---|---|---|
| Scope gate | PASS | React-only successor |
| Change inventory | NOT_RUN | 0 DB/schema |
| Static release gate | NOT_RUN | 無release |
| Descriptor gate | NOT_RUN | 無schema |
| Read-only plan gate | NOT_RUN | 不適用 |
| Engine verification gate | NOT_RUN | 不適用 |
| Developer acceptance gate | NOT_RUN | 不操作DB |

結論：`DB_CHANGE_NOT_READY`。
