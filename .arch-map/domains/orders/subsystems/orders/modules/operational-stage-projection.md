# Module: operational-stage-projection

## Parent
- domain: `orders`
- subsystem: `orders`

## Responsibility
將 Orders、Scheduling、Client Finance 與 Payroll 的唯讀根事實整合為七階段營運投影；單一 owner fact 不可用時只局部標示 unavailable，不使整頁訂單清單失效。

## Implementation
- primary:
  - `subsystems/orders/stage_projection_query.py`
  - `infrastructure/mysql/orders_stage_projection_repository.py`
- entrypoints:
  - `api/routes/orders_stage_projection.py`
  - `api/dependencies/orders_stage_projection.py`

## Dependencies
- outbound: `scheduling/scheduling` — 讀取正式服務期間與 service-time terms。
- outbound: `client-finance/client-finance` — 讀取定金與客戶 obligation projection。
- outbound: `payroll/payroll` — 讀取月嫂薪資 obligation projection。

## Contracts
- `api/routes/orders_stage_projection.py` — `/api/orders/operational-timelines` typed read-only contract。

## Provenance
- Query composition and API entry — `source_observed` — `subsystems/orders/stage_projection_query.py` and `api/routes/orders_stage_projection.py`.

## Change triggers
Reconcile when stage identity, availability semantics, owner facts, API route, or projection test root changes.
