---
doc_type: work-package
declared_status: proposed
identity: PROV-20260817-line-notification-rule-mutation-public-contract-hardening
date: 2026-08-17
owner: LINE Configuration Integration Owner
domain: LINE Configuration / LINE Delivery
prerequisites: PROV-20260817-react-admin-phase4-scenario-lineage-governance PASS; PROV-20260817-global-fastapi-typed-error-boundary PASS; PROV-20260817-line-knowledge-authorization-normalization PASS
base_branch: main
base_head: late-bound-at-approval
dirty_baseline: integration-owner-must-capture-before-writer
base_drift_rule: any relevant path drift requires fresh read and re-freeze before edits
approval_required: 核准此 exact Phase 4C-NR-H Work Package
scenario_governance: Part_00_全域測試資料治理與Scenario契約.md
scenario_lineage: ../03_追蹤清單與證據/evidence/PROV-20260817-react-admin-phase3-6-planning/phase4-scenario-lineage-matrix.md
ui_execution_mode: not-applicable
---

# Phase 4C-NR-H：Notification Rules mutation public contract hardening

## 0. Scope

本包尚未核准。只收斂rule Preview／Save／Delete；manual replay明確由
`PROV-20260817-line-notification-manual-replay-contract-gap`管理，React與provider rollout另案。現行整份`PUT`可能藉移除／
disabled rule繞過DELETE的pending-intent kill switch，必須在同一outer LINE UoW封堵。

G0 另要求 `PROV-20260817-line-knowledge-authorization-normalization` PASS；不得讓舊 role→capability
漂移成為 mutation authorization，亦不得由 React 自行補救。

## 1. Exact write set

- `api/routes/line_notification_rules.py`
- `api/schemas/line_notification_rules.py`
- `subsystems/line/notification_rule_administration.py`
- `subsystems/line/configuration_application.py`
- `infrastructure/mysql/line_notification_repository.py`
- `tests/line/subsystems/test_line_notification_rule_api.py`
- `tests/line/subsystems/test_line_notification_rule_administration.py`
- `tests/line/subsystems/test_line_notification_rule_mutation_contract.py`（new）
- `tests/test_line_notification_rule_mutation_route.py`（new）

Integration Owner另可更新正式17規格、本WP、evidence/index。manual replay、React、worker/provider、DB/schema不在write set。

## 2. Invariants

- Closed Pydantic request/result，不允許`Any`、`dict[str, Any]`或raw definition穿透；predicate/target/frequency使用
  approved discriminated grammar/registry，optional/default materialization逐欄凍結。
- Preview 0 write；Save/Delete fresh-read revision/CAS/fingerprint/reason/key/correlation。
- removed/disabled rules、new revision、typed receipt、audit與pending-intent cancellation在同一outer LINE UoW。
- G1前必須凍結`rule revision → pending delivery intent/task`的lineage、canonical owner、lock順序、port與repository
  method。若真正取消需要上列write set以外的LINE Delivery repository、task owner、worker contract或schema，固定
  `WRITE_SET_AMENDMENT_REQUIRED`，不得由`line_notification_repository.py`隱藏跨owner寫入，也不得把狀態字串更新
  冒充已完成kill switch。
- worker/provider call前仍重讀cancellation；HTTP command本身0 provider call/wakeup。
- 未登錄owner event只能保存為disabled/shadow，不能啟用或猜root fact。
- same-key replay回同receipt；collision/stale typed 409；所有route/domain errors為Global typed envelope，raw
  internal/provider錯誤不外洩。manual replay endpoint若仍存在，只作characterization並保持不可由React呼叫，
  不得在本包順手修成正式命令。

## 3. Lanes／Gates

Contract Scout→Application/Repository Writer→Route/Test Writer→fresh Auditor；正式spec/index只有Integration Writer。
G0 approval及全部frontmatter prerequisite fresh PASS；G1 grammar/view/error與rule→intent owner矩陣；G2 Preview zero-write；G3 kill-switch atomic；G4 replay/stale；G5 registered source；
G6 auth/redaction/negative extra-missing-null/zero raw error；G7 focused/full regression/UTF-8/diff；G8 0 React/provider/DB越界。

## 4. Completion boundary

完成只允許後續React rule mutation successor開工。source-event manual replay會建立新的delivery intent，另立exact WP。

## 5. DB gate

| Gate | Status | Evidence |
|---|---|---|
| Scope gate | PASS | existing schema/public contract hardening |
| Change inventory | PASS | 0 schema/seed/backfill/destructive |
| Static release gate | NOT_RUN | 無release |
| Descriptor gate | NOT_RUN | 無schema變更 |
| Read-only plan gate | NOT_RUN | 不適用 |
| Engine verification gate | NOT_RUN | 不藉本包改DB |
| Developer acceptance gate | NOT_RUN | 不操作既有資料庫 |

結論：`DB_CHANGE_NOT_READY`。
