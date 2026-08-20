---
doc_type: work-package
declared_status: proposed
identity: PROV-20260817-react-admin-phase4c-knowledge-lifecycle-react
date: 2026-08-17
owner: React Knowledge Integration Owner
domain: Knowledge Retrieval
prerequisites: PROV-20260817-react-admin-phase4-scenario-lineage-governance PASS; PROV-20260817-global-fastapi-typed-error-boundary PASS; PROV-20260817-line-knowledge-authorization-normalization PASS; PROV-20260817-react-admin-phase4c-knowledge-public-query-hardening PASS; PROV-20260817-knowledge-item-lifecycle-public-contract-hardening PASS; PROV-20260817-react-admin-phase4c-notification-rules-mutation-react PASS
base_branch: main
base_head: late-bound-at-approval
dirty_baseline: integration-owner-must-capture-before-writer
base_drift_rule: any relevant path drift requires fresh read and re-freeze before edits
approval_required: 核准此 exact Phase 4C-KL-R Work Package
scenario_governance: Part_00_全域測試資料治理與Scenario契約.md
scenario_lineage: ../03_追蹤清單與證據/evidence/PROV-20260817-react-admin-phase3-6-planning/phase4-scenario-lineage-matrix.md
ui_execution_mode: browser-required
---

# Phase 4C-KL-R：Knowledge item lifecycle React successor

## 0. Prerequisites

frontmatter列出的所有prerequisite均須有fresh PASS。reindex/retry/問答不在本包。

## 1. Exact write set

- `ui_react/src/api/knowledge/knowledge_lifecycle_schemas.ts`（new）
- `ui_react/src/api/knowledge/knowledge_lifecycle_errors.ts`（new）
- `ui_react/src/api/knowledge/knowledge_lifecycle_client.ts`（new）
- `ui_react/src/adapters/knowledge/knowledge_lifecycle_adapter.ts`（new）
- `ui_react/src/pages/LineManagementPage.tsx`
- `ui_react/src/pages/LineManagementPage.css`
- `ui_react/src/tests/knowledge_lifecycle_client.test.ts`（new）
- `ui_react/src/tests/knowledge_lifecycle_flow.test.tsx`（new）
- `ui_react/src/tests/line_management_no_fake_mutation.test.tsx`

Page sole writer；shared/backend/index provider/DB不在write set。

## 2. Acceptance

Hard-coded FAQ=0；strict query/lifecycle receipt；ingest/review/publish/retire依server version/digest；stale不自動retry；
source URI/content不進catalog DOM/log；stable IDs `line.faq.create/edit/review/publish/retire/receipt`；reindex/answer controls
native disabled；真browser需controlled multi-actor lifecycle，否則blocked。

G1契約矩陣必須逐一抄錄已PASS lifecycle backend receipt中的exact ingest／review／publish／retire與
resource-specific item/receipt re-query method、path、closed union；production client不得呼叫Knowledge `/jobs`、
generic Jobs、raw detail或index provider endpoint。controlled browser只消費Phase4 Scenario Lineage唯一擁有的
`KN-REACT-LIFECYCLE-001` fixture/expected/receipt identity，React writer不得自造multi-actor oracle。

## 3. Lanes／G0–G7

Contract Scout唯讀freeze；Client Writer只寫bounded client/adapter/tests；Presentation Writer等freeze並獨占page；Auditor唯讀；
Integration Owner唯一寫evidence/index。G0逐一驗證全部frontmatter prerequisite；G1 exact endpoint/field/PII matrix；G2 strict decoder；G3 lifecycle state machine；
G4 hard-coded data與fake mutation為0；G5 full suite；G6真browser multi-actor/reload；G7scope/UTF-8/secret/source-content scan。
不得用同一actor自審自發、job accepted或HTTP 200冒充published。

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
