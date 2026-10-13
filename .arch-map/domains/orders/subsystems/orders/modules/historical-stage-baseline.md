# Module: historical-stage-baseline

## Parent
- domain: `orders`
- subsystem: `orders`

## Responsibility
將已採納 Historical Orders 的可證明作業位置，以唯讀 baseline overlay 投影到七階段與 11 步流程；只補齊不可回復的歷史前置操作，不建立付款、簽章、排班或其他 owner root。

## Implementation
- primary:
  - `subsystems/orders/historical_stage_baseline_overlay.py`
  - `infrastructure/mysql/historical_stage_baseline_repository.py`
  - `infrastructure/mysql/historical_orders_stage_projection_repository.py`
- entrypoints:
  - `api/dependencies/orders_stage_projection.py`

## Dependencies
- inbound: `orders/orders/module:historical-adoption` — 只讀已提交 adoption receipt 與 current Orders lifecycle。
- outbound: `orders/orders/module:operational-stage-projection` — overlay 既有 typed timeline，不改寫 base owner facts。
- outbound: `orders/orders/module:historical-completion` — 歷史服務完成／帳務完成案件的結算子階段沿用 fresh completion oracle，逐 owner 顯示完成、未完成或不可用；Orders 版本變動時拒絕混用快照，不由 lifecycle 標籤推定付款。

## Contracts
- `document/架構重整/01_規格基線/01_Orders_Domain.md` §3.8 — Historical Operational Baseline semantics。
- `document/架構重整/01_規格基線/27_歷史訂單生命週期與服務天數帳務正式規格.md` — 歷史服務天數及雙邊結清權威。

## Verification
- test_root: `tests/domains/orders/subsystems/orders/modules/historical-stage-baseline/`

## Provenance
- Baseline ownership and predecessor-bypass boundary — `architecture_declared` — `document/架構重整/01_規格基線/01_Orders_Domain.md` §3.8。
- Query overlay and repository paths — `source_observed` — current source。
- Owner-local test routing — `architecture_declared` — this leaf。

## Change triggers
Reconcile when baseline source identity, selected-step mapping, stage/SOP projection relationship, repository read model or verification root changes.
