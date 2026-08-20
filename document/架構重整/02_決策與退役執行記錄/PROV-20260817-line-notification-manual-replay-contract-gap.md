---
doc_type: gap-package
declared_status: proposed
identity: PROV-20260817-line-notification-manual-replay-contract-gap
date: 2026-08-17
owner: LINE Delivery Architecture Owner
domain: LINE Delivery
---

# Notification source-event manual replay contract缺口

Manual replay不是rule configuration mutation：它會從既有immutable source lineage建立新的delivery intent。須另行凍結可重播終態、
source owner、reason、preview zero-write、same-key identity、duplicate suppression、receipt、outbox、retry/exhausted與PII政策；不得由rule
save WP順手實作。React `line.notification-rule.replay.preview/apply`維持disabled。0 production write set。

DB Gate：Scope BLOCKED，其餘NOT_RUN；`DB_CHANGE_NOT_READY`。

| Gate | Status | Evidence |
|---|---|---|
| Scope gate | BLOCKED | source/replay command contract未freeze |
| Change inventory | NOT_RUN | 0 DB |
| Static release gate | NOT_RUN | 無release |
| Descriptor gate | NOT_RUN | 無schema |
| Read-only plan gate | NOT_RUN | 不適用 |
| Engine verification gate | NOT_RUN | 不適用 |
| Developer acceptance gate | NOT_RUN | 不操作DB |
