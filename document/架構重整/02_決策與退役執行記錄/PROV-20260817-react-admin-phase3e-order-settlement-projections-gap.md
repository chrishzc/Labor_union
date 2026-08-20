---
doc_type: gap-package
declared_status: proposed
identity: PROV-20260817-react-admin-phase3e-order-settlement-projections-gap
date: 2026-08-17
owner: Orders Read-model Integration Owner
domain: Orders / Client Finance / Staff Payables
---

# Phase 3E：三個獨立結清 projection 協調缺口

## 0. 已確認業務語意

服務完成、客戶款項結清、月嫂薪資核銷是三個獨立狀態，不得收斂成一個「已完成／結案」Badge，也不得由React
用金額、筆數或`every()`推導。

Stable UI slots：

- `orders.settlement.service-completed`
- `orders.settlement.client-finance-settled`
- `orders.settlement.staff-payout-reconciled`

## 1. Required query contract

只讀coordinator以各owner的canonical version／receipt／terminal predicate輸出三個nullable projections，並逐一帶source lineage與
observed_at。部分owner失敗時只使該projection unavailable；不可產生aggregate completed。coordinator 0 commit、0 repair、0 mutation。

## 2. Gap acceptance

人工凍結三個terminal predicate、reopen/reversal語意與PII政策後，建立backend query-only WP及React wiring WP。component tests須逐個
projection驗證 independent transitions、partial error與不產生總結Badge。

## 3. DB gate

| Gate | Status | Evidence |
|---|---|---|
| Scope gate | BLOCKED | terminal predicates與read owner尚未共同freeze |
| Change inventory | NOT_RUN | 不改DB |
| Static release gate | NOT_RUN | 無release |
| Descriptor gate | NOT_RUN | 無schema變更 |
| Read-only plan gate | NOT_RUN | 不適用 |
| Engine verification gate | NOT_RUN | 不適用 |
| Developer acceptance gate | NOT_RUN | 不操作資料庫 |

結論：`DB_CHANGE_NOT_READY`。
