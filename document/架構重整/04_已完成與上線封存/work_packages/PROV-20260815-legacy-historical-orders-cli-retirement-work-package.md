---
doc_type: work-package
declared_status: completed
date: 2026-08-15
owner: Orders / Global Entry Governance
domain: Orders
subsystem: Historical order adoption entrypoint retirement
implementation_authorization: granted-by-user-2026-08-15
---

# Legacy Historical Orders CLI 退役工作包

## Scope

退役 `scripts/import_historical_orders.py`：其 CLI 已固定回傳
`legacy_historical_order_writer_retired`，檔內仍殘留 direct SQL historical writer。移除 source、current
entry queue 項目與相關 stale test expectation，保留下列 replacement：

- `api:POST /api/v1/orders/historical-adoption/workbooks/{preview,apply}`
- `cli:scripts/imports/adopt_historical_orders.py`（受控、typed historical 維運入口）

不修改 Orders historical adoption Domain／schema／API、workbook parser 或受控 typed CLI。

## Acceptance

1. source 與所有 current caller 均不存在；queue 不再列該 CLI。
2. typed Web API 與 `adopt_historical_orders.py` 未受影響。
3. focused entrypoint／historical adoption regression 與 `git diff --check` 通過。

## 完成證據

2026-08-15 已移除 retired CLI 與 queue 項目，保留 typed Web API 和受控維運 CLI。
驗收收據：
`../03_追蹤清單與證據/evidence/legacy_historical_orders_cli_retirement_receipt_20260815.md`。
