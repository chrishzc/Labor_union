---
doc_type: work-package
declared_status: proposed
identity: PROV-20260817-line-rich-menu-publication-contract-saga-hardening
date: 2026-08-17
owner: LINE Configuration Integration Owner
domain: LINE Configuration / LINE Delivery
prerequisites: PROV-20260817-react-admin-phase4-scenario-lineage-governance PASS; PROV-20260817-global-fastapi-typed-error-boundary PASS; PROV-20260817-line-knowledge-authorization-normalization PASS
base_branch: main
base_head: late-bound-at-approval
dirty_baseline: integration-owner-must-capture-before-writer
base_drift_rule: any relevant path drift requires fresh read and re-freeze before edits
approval_required: 核准此 exact Phase 4C-RM-H Work Package
scenario_governance: Part_00_全域測試資料治理與Scenario契約.md
scenario_lineage: ../03_追蹤清單與證據/evidence/PROV-20260817-react-admin-phase3-6-planning/phase4-scenario-lineage-matrix.md
ui_execution_mode: not-applicable
---

# Phase 4C-RM-H：Rich Menu publication public contract／provider saga hardening

## 0. Scope

本包尚未核准。它只修backend contract與fake-provider可驗證的stepwise saga；不改React、不使用真provider credentials、
不向production LINE發送。現行`publish-preview`會INSERT/commit，且worker把create/upload/link/switch/cleanup視為一個provider
動作後才補記步驟，無法安全從partial failure續跑。

G0 要求 `PROV-20260817-line-knowledge-authorization-normalization` PASS；不得沿用現行 role capability。
本包同時必須提供 LINE Configuration owner 的 strict publication status/detail/receipt Query，供 React re-query；
禁止把 generic `/api/v1/jobs` raw payload 當作 publication outcome。

## 1. Exact write set

- `api/routes/line_rich_menus.py`
- `api/schemas/line_rich_menus.py`
- `subsystems/line/rich_menu_contracts.py`
- `subsystems/line/rich_menu_application.py`
- `subsystems/line/rich_menu_publication_workflow.py`
- `subsystems/line/rich_menu_worker.py`
- `subsystems/line/ports.py`
- `infrastructure/mysql/line_configuration_publication_repository.py`
- `infrastructure/line/rich_menu_api_adapter.py`
- `tests/line/subsystems/test_line_rich_menu_publication_snapshot.py`
- `tests/line/subsystems/test_line_rich_menu_publication_public_contract.py`（new）
- `tests/line/infrastructure/test_line_rich_menu_provider_saga.py`（new）
- `tests/test_line_rich_menu_publication_route.py`（new）

Integration Owner另可更新正式17規格、本WP、evidence及index；React、shared transport/Auth、DB/schema、真provider rollout不在write set。

## 2. Invariants

- Typed PreviewReceipt／QueueReceipt／RetryReceipt與stable errors；reason/key/correlation不得由server替空值生成。
- Publication status/detail為bounded closed union，明確區分queued/running/provider-acknowledged/published/failed；
  job accepted或單一步provider ack不得冒充published，且public view不得洩漏provider raw payload。
- Preview 0 write。Apply fresh lock actor/menu/revision/fingerprint、consume preview、audit/receipt/durable job一個LINE UoW。
- same key+same fingerprint回同receipt；key collision/stale為typed 409。
- provider saga step enum固定為`create → upload → link → switch → cleanup`；每一步都有request fingerprint、
  provider idempotency identity、acknowledged receipt與attempt outcome。provider call在transaction外；lost-ack、
  process crash或timeout後從最後acknowledged step續跑，不得重建已確認asset、重傳已確認內容或跳過cleanup。
- published state與必要fan-out intents原子；wakeup只是non-authoritative hint，失敗不丟工作。
- G1前必須凍結`publication → fan-out intent`的canonical owner、port、repository method、table ownership與outer
  UoW call graph。只有上列exact write set已能透過LINE Configuration正式owned port保存時才可施工；若需要
  未列出的delivery-intent repository/schema/worker或跨owner寫入，固定`WRITE_SET_AMENDMENT_REQUIRED`並停止，
  不得把fan-out藏在generic repository helper或以wakeup冒充durable intent。
- cleanup失敗只能成為typed operational outcome／anomaly，不得把已published的Domain結果改寫成失敗或偷偷刪除新asset。
- raw provider response/error/payload、recipient與credentials不進public result/log/receipt；route/domain errors使用
  Global typed envelope，401/403至少fail closed且零secret/PII。

## 3. Lanes／Gates

1. Contract Scout（Luna，唯讀）：Pydantic/error/step矩陣。
2. Application/Repository Writer（Terra）：contracts/application/repository。
3. Provider Saga Writer（Primary）：ports/worker/adapter，fake provider only。
4. Route/Test Writer（Terra）：route/schema/focused tests。
5. Auditor（Luna，唯讀）：0 React/DB/credential/true provider scan。

G0 approval/base drift與全部frontmatter prerequisite fresh PASS；G1逐步request/receipt/error及fan-out owner矩陣freeze；G2 preview zero-write；G3 one commit；
G4 fake provider逐步lost-ack/crash/timeout resume且不重建asset；G5 replay/stale；
G6 auth/typed errors/redaction；G7 focused/full tests及UTF-8/diff；G8 evidence不含真provider rollout宣稱。

## 4. Completion boundary

通過後只解除React successor的backend prerequisite；真provider rollout與React wiring均須獨立exact WP。

## 5. DB gate

| Gate | Status | Evidence |
|---|---|---|
| Scope gate | PASS | existing schema contract/saga hardening |
| Change inventory | PASS | 0 schema/seed/backfill/destructive |
| Static release gate | NOT_RUN | 無release |
| Descriptor gate | NOT_RUN | 無schema變更 |
| Read-only plan gate | NOT_RUN | 不適用 |
| Engine verification gate | NOT_RUN | 不藉本包改DB |
| Developer acceptance gate | NOT_RUN | 不操作既有資料庫 |

結論：`DB_CHANGE_NOT_READY`。
