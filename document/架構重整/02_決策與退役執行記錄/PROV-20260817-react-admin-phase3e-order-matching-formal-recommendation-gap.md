---
doc_type: gap-package
declared_status: proposed
identity: PROV-20260817-react-admin-phase3e-order-matching-formal-recommendation-gap
date: 2026-08-17
owner: Assignments / Scheduling Integration Owner
domain: Assignments / Scheduling / Orders
---

# Phase 3E：候選池、媒合方案與正式推薦契約缺口

## 0. 已確認業務規則

- 內部候選池可有多位，但客戶正常只收到一位正式推薦。
- 只有 server 證明單一月嫂無法覆蓋全部已確認服務日期時，才可把2–4位月嫂的連續、無重疊分段方案視為
  一個整體正式推薦。
- React不得以候選數、日期加總、local availability或多選狀態自行推導上述例外。

## 1. Current gap

`candidate_contact_pool`／matching routes與現有UI仍混有raw dict及未凍結的formal-plan identity。候選聯絡、Info-1／Info-2、
willingness、shortlist、客戶決定、waiting lock與正式推薦不是同一狀態機。現階段不能把多選履歷寄送直接接成正式推薦。

## 2. 待裁決 public contract

1. `shortlist_id`、`formal_recommendation_id`、`matching_plan_id`與segments的身份及版本關係。
2. single-caregiver coverage proof；2–4 segments的日期全集、連續性、無重疊、同一package fingerprint。
3. 客戶收到／接受／拒絕／逾期、staff willingness及LINE delivery receipt的獨立事實。
4. Query／Preview／Apply、stale、lock conflict、same-key replay及外部通知outbox。
5. server blocker與warning分離；UI不可由`order_status`推stage或eligibility。

## 3. Gap acceptance

由Scheduling owner凍結typed Pydantic views與commands、formal package不變量、單一outer UoW及focused MySQL evidence；再拆成
backend hardening與React wiring WPs。未完成前Matching Drawer保留結構，但所有mutation native disabled且顯示contract unavailable。

## 4. DB gate

| Gate | Status | Evidence |
|---|---|---|
| Scope gate | BLOCKED | formal recommendation identity／transaction未凍結 |
| Change inventory | NOT_RUN | 本gap不改DB |
| Static release gate | NOT_RUN | 無release |
| Descriptor gate | NOT_RUN | 無schema變更 |
| Read-only plan gate | NOT_RUN | 不適用 |
| Engine verification gate | NOT_RUN | 不適用 |
| Developer acceptance gate | NOT_RUN | 不操作資料庫 |

結論：`DB_CHANGE_NOT_READY`。
