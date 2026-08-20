---
doc_type: work-package
declared_status: proposed
identity: PROV-20260817-react-admin-phase4c-richmenu-mutation-react
date: 2026-08-17
owner: React LINE Integration Owner
domain: LINE Configuration
prerequisites: PROV-20260817-react-admin-phase4-scenario-lineage-governance PASS; PROV-20260817-global-fastapi-typed-error-boundary PASS; PROV-20260817-line-knowledge-authorization-normalization PASS; PROV-20260817-line-rich-menu-publication-contract-saga-hardening PASS; PROV-20260817-react-admin-phase4c-k-r-react PASS
base_branch: main
base_head: late-bound-at-approval
dirty_baseline: integration-owner-must-capture-before-writer
base_drift_rule: any relevant path drift requires fresh read and re-freeze before edits
approval_required: 核准此 exact Phase 4C-RM-R Work Package
scenario_governance: Part_00_全域測試資料治理與Scenario契約.md
scenario_lineage: ../03_追蹤清單與證據/evidence/PROV-20260817-react-admin-phase3-6-planning/phase4-scenario-lineage-matrix.md
ui_execution_mode: browser-required
---

# Phase 4C-RM-R：Rich Menu publication React successor

## 0. Prerequisites

frontmatter列出的所有prerequisite均須有fresh PASS，並取得本包exact核准。
真provider rollout不是本包驗收。

## 1. Exact write set

- `ui_react/src/api/line_configuration/rich_menu_mutation_schemas.ts`（new）
- `ui_react/src/api/line_configuration/rich_menu_mutation_errors.ts`（new）
- `ui_react/src/api/line_configuration/rich_menu_mutation_client.ts`（new）
- `ui_react/src/adapters/line_configuration/rich_menu_mutation_adapter.ts`（new）
- `ui_react/src/pages/LineManagementPage.tsx`
- `ui_react/src/pages/LineManagementPage.css`
- `ui_react/src/tests/rich_menu_mutation_client.test.ts`（new）
- `ui_react/src/tests/line_rich_menu_publication_flow.test.tsx`（new）
- `ui_react/src/tests/line_management_no_fake_mutation.test.tsx`

Shared transport/Auth、其他LINE clients/pages、backend/DB/provider不在write set。`LineManagementPage.tsx`為共享hot spot，sole writer。

## 2. Acceptance

Strict Zod；fresh bearer；Preview→Apply→receipt→LINE Configuration bounded publication-status re-query；
禁止呼叫generic `/api/v1/jobs`；accepted/provider ack不顯示published；outcome_unknown同key retry；
stale重新Preview；stable IDs `line.richmenu.publish.preview/apply/receipt/requery/retry`；其餘controls維持native disabled；
0 alert/confirm/local business mutation。真browser只用受控non-production scenario；缺scenario為blocked。

G1契約矩陣必須逐一抄錄已PASS backend receipt中的exact method/path、request schema、success union、typed error與
resource-specific publication status/detail Query；production client只允許該allowlist。backend未凍結任何一欄時固定
`BLOCKED_BACKEND_PUBLIC_CONTRACT`，不得由React writer自行命名route、解析generic Jobs或從HTTP 202推導成功。

## 3. Lanes／G0–G7

Contract Scout唯讀freeze DOM/API matrix；G0逐一驗證frontmatter所有prerequisite的fresh PASS，不得只驗證數量或依賴傳遞；Client Writer只寫client/adapter/tests；Presentation Writer須等freeze且獨占page；Auditor唯讀，
Integration Owner唯一寫evidence/index。G0 prerequisite/approval；G1 strict matrix；G2 client negative tests；G3 exhaustive state machine；
G4 exact stable controls與0 fake mutation；G5 full build/lint/tests；G6真browser Network↔DOM；G7write-set/UTF-8/secret/PII receipts。
Auth或browser blocker只能阻擋G6，不能成為G1–G5不做的理由。

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
