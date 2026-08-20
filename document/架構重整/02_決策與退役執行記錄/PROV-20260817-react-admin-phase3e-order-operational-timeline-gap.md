---
doc_type: gap-package
declared_status: proposed
identity: PROV-20260817-react-admin-phase3e-order-operational-timeline-gap
date: 2026-08-17
owner: Orders Read-model Integration Owner
domain: Orders / Scheduling / Contract Signing / LINE / Finance
---

# Phase 3E：7階段、11步SOP與訂單通知 timeline 缺口

## 0. 結論

7階段與11步文案可保留為presentation slots，但目前沒有一個具server lineage的typed read model能提供每步status、timestamp、
owner fact與通知結果。不得以`order_status`、目前頁籤或固定mock自動生成completed／pending。

## 1. Required coordinator contract

- 每個milestone有stable code、owning Domain、source root/version、status、occurred_at、blocker/warning與可用action link。
- 11步不是新的跨域可寫aggregate；coordinator只讀各owner projection，0 commit。
- LINE timeline必須case-scoped，提供safe delivery status、attempt/retryability與receipt lineage；禁止payload、recipient、provider raw error。
- 缺少owner projection的slot顯示`unavailable`，不能猜測或複製上一階段。

## 2. Gap acceptance

人工確認7-stage↔11-step mapping與每步owner後，建立query-only public-contract WP，再建立Orders/Tracker React WP。要求不同case
sentinel、stale/partial owner failure隔離、request budget、PII redaction及真route provenance。

## 3. DB gate

| Gate | Status | Evidence |
|---|---|---|
| Scope gate | BLOCKED | cross-domain read owner與mapping未確認 |
| Change inventory | NOT_RUN | 不改DB |
| Static release gate | NOT_RUN | 無release |
| Descriptor gate | NOT_RUN | 無schema變更 |
| Read-only plan gate | NOT_RUN | 不適用 |
| Engine verification gate | NOT_RUN | 不適用 |
| Developer acceptance gate | NOT_RUN | 不操作資料庫 |

結論：`DB_CHANGE_NOT_READY`。
