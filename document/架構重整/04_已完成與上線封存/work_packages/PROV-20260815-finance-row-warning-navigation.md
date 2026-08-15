---
doc_type: work-package
declared_status: completed
date: 2026-08-15
owner: Finance Import / Anomalies
priority: P0
---

# Finance Import Row Warning Navigation Work Package

## Scope

WP90 的第一個 Finance slice 僅處理已建立 canonical bank row、且 Finance Import owning workflow 已標記
`finance_import_manual_review` active 的列。outbox consumer 在同一 committed delivery transaction 建立
`FINANCE-ROW-001` tracking task；warning identity 只使用 canonical finance row id，顯示為去敏 row label，
並導向既有帳務作業中心。異常中心不顯示、組裝或執行任何 finance recovery payload。

`FINANCE-SOURCE-001` 不在此切片：無法正規化的來源列目前沒有 immutable source-review root／outbox，
不得以 raw workbook、暫態 parse error 或 guessed identity 建 task。該缺口保留至 Finance Import owner 建立
source-review contract、write set 與 predicate 後處理。

## Invariants and acceptance

- 同一 canonical row 只建立一個 occurrence／opened event／current task；後續 dispatch/recovery replay 零新增。
- evidence 只保存 batch id、blocker count、reason count，禁止銀行帳號、交易摘要、金額、raw payload。
- manual correction completed 不會由 anomaly center 寫入或自動宣稱 tracking 已 resolved。
- 本包無 schema/migration、bank row rewrite、ledger posting、React runtime 或 LINE side effect；必須以 focused、
  disposable MySQL replay 與 owner-screen navigation evidence 驗收。

## Closure

WP90 的 Finance source-row isolation successor 已承接本 canonical-row navigation 範圍並補齊 source-review
contract；完成驗收見 `2026-08-15_wp90_wp95_completion_receipt.md`。本文件不再保有 active write set。
