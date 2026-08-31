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
- entrypoints:
  - `api/dependencies/orders_stage_projection.py`

## Dependencies
- inbound: `orders/orders/module:historical-adoption` — 只讀已提交 adoption receipt 與 current Orders lifecycle。
- outbound: `orders/orders/module:operational-stage-projection` — overlay 既有 typed timeline，不改寫 base owner facts。

## Contracts
- `document/架構重整/01_規格基線/01_Orders_Domain.md` §3.8 — Historical Operational Baseline semantics。

## Verification
- test_root: `tests/domains/orders/subsystems/orders/modules/historical-stage-baseline/`

## Provenance
- Baseline ownership and predecessor-bypass boundary — `architecture_declared` — `document/架構重整/01_規格基線/01_Orders_Domain.md` §3.8。
- Query overlay and repository paths — `source_observed` — current source。

## Change triggers
Reconcile when baseline source identity, selected-step mapping, stage/SOP projection relationship, repository read model or verification root changes.
