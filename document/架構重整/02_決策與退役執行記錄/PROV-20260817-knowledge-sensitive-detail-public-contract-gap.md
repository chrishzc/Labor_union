---
doc_type: gap-package
declared_status: proposed
identity: PROV-20260817-knowledge-sensitive-detail-public-contract-gap
date: 2026-08-17
owner: Knowledge Retrieval / Access Integration Owner
priority: P0
blocks: React Knowledge detail／jobs／indexes／answer request exposure
---

# Knowledge legacy sensitive detail public contract 缺口

## Business scenario

管理端FAQ catalog只需要安全的id、title、lifecycle、version與updated time；但current Knowledge routes仍可
回傳全文、source identity／URI、question／answer／citations、correlation與LINE delivery task identity。
Catalog hardening不能用文字聲明把這些既有routes當成已修復，也不能讓React client偷偷呼叫它們。

## Current gap

- `GET /api/v1/knowledge/items/{item_id}`會回`content`與`source_uri`。
- jobs／indexes／questions routes仍是raw list/dict，且可能暴露runtime、answer、citation、correlation或delivery identity。
- current Streamlit／operator caller與下載／全文檢視需求尚未完成entry/capability/retention裁決。
- 直接mask或410可能破壞合法的restricted operator workflow；直接保留又不能宣稱public query安全。

## Required human decision／successor

逐route裁決`retain-restricted | replace-with-masked-view | operator-only | retire-410`，凍結capability、PII class、
redaction、audit、pagination、typed errors、download/content visibility與entrypoint replacement。任何全文／URI
輸出都必須有purpose-specific capability與security audit；React FAQ catalog固定不得呼叫這些routes。

決策完成後另立exact backend public-contract／entry-governance Work Package。本gap不授權production、API、
Streamlit、React、external index、LINE provider或DB變更。

## DB gate

Scope `PASS`（文件盤點）；Change Inventory、Static Release、Descriptor、Read-only Plan、Engine Verification、
Developer Acceptance均`NOT_RUN`；結論`DB_CHANGE_NOT_READY`。
