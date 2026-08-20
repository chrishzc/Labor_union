---
doc_type: gap-package
declared_status: proposed
identity: PROV-20260817-react-admin-phase4c-line-order-group-mutation-owner-gap
date: 2026-08-17
owner: LINE Order Group / Orders Architecture Owner
domain: LINE Order Groups / Orders
---

# Phase 4C：LINE order-group create／close mutation owner缺口

## 0. 結論

現有`api/routes/line_order_groups.py`只提供typed list/detail/events Query。React「建立群組」沒有核准mutation route；不得新增
假`/create`、產生fake LINE group ID或以local state顯示成功。

## 1. 待人工裁決

1. canonical owner是Orders coordination、LINE identity還是獨立Order Group aggregate。
2. case/client/staff membership根事實、provider group identity與create/close/reconcile lifecycle。
3. provider無法由官方API建立群組時的真實人工流程，不得假設可自動化。
4. Preview／Apply、idempotency、receipt、outbox/task、partial membership、retry與manual recovery。
5. PII、群組名稱／成員顯示、audit、retention及rollback entry。

## 2. Gap acceptance

先完成provider capability evidence與owner/state-machine decision；若provider不支持自動create，UI應改成typed readiness/checklist或
人工evidence entry，而不是mutation。只有人工裁決後才建立exact backend/React WP。

## 3. DB gate

| Gate | Status | Evidence |
|---|---|---|
| Scope gate | BLOCKED | owner/provider capability未確認 |
| Change inventory | NOT_RUN | 無DB write set |
| Static release gate | NOT_RUN | 無release |
| Descriptor gate | NOT_RUN | 無schema變更 |
| Read-only plan gate | NOT_RUN | 不適用 |
| Engine verification gate | NOT_RUN | 不適用 |
| Developer acceptance gate | NOT_RUN | 不操作資料庫 |

結論：`DB_CHANGE_NOT_READY`。
