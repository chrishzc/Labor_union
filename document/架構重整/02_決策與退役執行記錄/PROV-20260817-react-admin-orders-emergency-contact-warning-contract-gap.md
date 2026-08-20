---
doc_type: gap-package
declared_status: proposed
identity: PROV-20260817-react-admin-orders-emergency-contact-warning-contract-gap
date: 2026-08-17
owner: Case Intake / Orders Integration Owner
domain: Case Intake / Orders
---

# Orders 緊急聯絡電話 warning-only contract 缺口

## 0. 人工裁決

缺少緊急聯絡電話只顯示警告，仍允許繼續媒合；它不得出現在matching blocker predicate或讓媒合控制disabled。

## 1. 尚缺契約

目前尚未凍結欄位owner、PII masking、stable warning code、修復入口、audit與何時消除warning。UI不得因人工裁決已存在而
自造fixture或在前端檢查電話空白。

## 2. Gap acceptance

owner需提供typed warning projection（stable code、masked presence、repair route identity、observed version），證明與matching blocker
集合互斥。之後才建立小型backend與React WPs；React僅顯示server warning，所有媒合disabled判斷不得引用它。

## 3. DB gate

| Gate | Status | Evidence |
|---|---|---|
| Scope gate | BLOCKED | field owner／repair contract未凍結 |
| Change inventory | NOT_RUN | 無DB write set |
| Static release gate | NOT_RUN | 無release |
| Descriptor gate | NOT_RUN | 無schema變更 |
| Read-only plan gate | NOT_RUN | 不適用 |
| Engine verification gate | NOT_RUN | 不適用 |
| Developer acceptance gate | NOT_RUN | 不操作資料庫 |

結論：`DB_CHANGE_NOT_READY`。
