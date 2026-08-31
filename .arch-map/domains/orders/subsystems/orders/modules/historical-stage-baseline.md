# Module: historical-stage-baseline

## Parent
- domain: `orders`
- subsystem: `orders`

## Responsibility
以已採納的 Historical Order immutable receipt 與 current Orders lifecycle fact，唯讀補足 operational timeline 的 historical predecessor baseline；不補造 Matching、Contract、Finance 或 Scheduling owner facts，也不執行 mutation。

## Implementation
- primary:
  - `subsystems/orders/historical_stage_baseline_overlay.py`
  - `infrastructure/mysql/historical_stage_baseline_repository.py`
  - `infrastructure/mysql/historical_orders_stage_projection_repository.py`

## Dependencies
- inbound: `historical-adoption` — 只讀取已提交 adoption receipt lineage。
- outbound: existing Orders stage projection Query contract。

## Contracts
- `document/架構重整/01_規格基線/01_Orders_Domain.md` — historical order lifecycle 與 current stage interpretation。

## Verification
- test_root: `tests/domains/orders/subsystems/orders/modules/historical-stage-baseline/`

## Provenance
- Historical stage baseline overlay and adapters — `source_observed` — current repository。
- Owner-local test routing — `architecture_declared` — this leaf。

## Change triggers
Reconcile when historical baseline applicability、stage overlay semantics、repository composition or owner-local test root moves。
