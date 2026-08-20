---
doc_type: work-package
declared_status: proposed
identity: PROV-20260817-knowledge-item-lifecycle-public-contract-hardening
date: 2026-08-17
owner: Knowledge Retrieval Integration Owner
domain: Knowledge Retrieval
prerequisites: PROV-20260817-react-admin-phase4-scenario-lineage-governance PASS; PROV-20260817-global-fastapi-typed-error-boundary PASS; PROV-20260817-line-knowledge-authorization-normalization PASS; PROV-20260817-react-admin-phase4c-knowledge-public-query-hardening PASS
base_branch: main
base_head: late-bound-at-approval
dirty_baseline: integration-owner-must-capture-before-writer
base_drift_rule: any relevant path drift requires fresh read and re-freeze before edits
approval_required: 核准此 exact Phase 4C-KL-H Work Package
scenario_governance: Part_00_全域測試資料治理與Scenario契約.md
scenario_lineage: ../03_追蹤清單與證據/evidence/PROV-20260817-react-admin-phase3-6-planning/phase4-scenario-lineage-matrix.md
ui_execution_mode: not-applicable
---

# Phase 4C-KL-H：Knowledge item lifecycle public contract hardening

## 0. Prerequisite／Scope

本包尚未核准，且Phase 4C-K query hardening必須完成並freeze後才能啟動；兩包共享route/schema/application/repository，
必須串行由同一Integration Owner合併。只處理item ingest/review/publish/retire；reindex/retry、
Chroma/index provider、問答、LINE delivery及React另案。

G0 亦要求 `PROV-20260817-line-knowledge-authorization-normalization` PASS；actor separation依正式 principal
identity 驗證，不得沿用 role capability 或前端選單判斷。

## 1. Exact write set

- `domains/knowledge_retrieval/publication.py`
- `subsystems/knowledge_retrieval/contracts.py`
- `subsystems/knowledge_retrieval/application.py`
- `infrastructure/mysql/knowledge_retrieval_repository.py`
- `infrastructure/mysql/knowledge_retrieval_unit_of_work.py`
- `api/schemas/knowledge_retrieval.py`
- `api/routes/knowledge_retrieval.py`
- `tests/test_knowledge_publication_policy.py`
- `tests/line/subsystems/test_knowledge_item_lifecycle_contract.py`（new）
- `tests/test_knowledge_item_lifecycle_route.py`（new）

Integration Owner另可更新正式17規格、本WP、evidence/index。index worker/provider、React、DB/schema不在write set。

## 2. Invariants

- typed ingest/review/publish/retire receipts，canonical fingerprint；same key same command回同receipt，collision typed 409。
- fresh item lock/version/source digest；合法lifecycle transition與author separation由actor identity驗證，不以role menu推論。
- item root、version、Domain audit、receipt與mandatory `index-stale` marker同一outer UoW；任一失敗0 write。
  marker只表示需重新索引，不授權Chroma/provider/reindex；實際index artifact／publish／rollback仍由
  `PROV-20260817-knowledge-index-runtime-policy-gap`管理。
- source digest只作server-side opaque fingerprint input；source URI/content/digest原文不進public
  result/error/log/snapshot/DOM；retire不physical delete。
- Query維持0 commit。Middleware audit不得冒充Domain transaction內audit。

## 3. Lanes／Gates

Contract Scout→Domain/Application Writer→Repository/UoW Writer→Route/Test Writer→fresh Auditor；shared formal docs僅Integration Writer。
G0 query-hardening已完成、base fresh-read及exact approval；G1 lifecycle/view/error矩陣；G2 canonical
fingerprint、same-key replay與different-payload collision；G3 root/audit/receipt/index-stale one commit/rollback；
G4 actor separation；G5 source URI/content/digest redaction；G6 strict route/auth與Global typed errors；
G7 focused/disposable existing-schema/full tests；G8 0 reindex/provider/React越界。

## 4. Completion boundary

通過後只允許Knowledge lifecycle React successor開工。reindex/retry需先裁決production index artifact、atomic publish、rollback、
retention與provider target。

## 5. DB gate

| Gate | Status | Evidence |
|---|---|---|
| Scope gate | PASS | existing schema item lifecycle hardening |
| Change inventory | PASS | 0 schema/seed/backfill/destructive |
| Static release gate | NOT_RUN | 無release |
| Descriptor gate | NOT_RUN | 無schema變更 |
| Read-only plan gate | NOT_RUN | 不適用 |
| Engine verification gate | NOT_RUN | existing-schema E2E不等於schema gate |
| Developer acceptance gate | NOT_RUN | 不操作既有資料庫 |

結論：`DB_CHANGE_NOT_READY`。
