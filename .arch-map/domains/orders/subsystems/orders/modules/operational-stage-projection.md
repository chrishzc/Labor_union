# Module: operational-stage-projection

## Parent
- domain: `orders`
- subsystem: `orders`

## Responsibility
將 Orders、Scheduling、Client Finance 與 Payroll 的唯讀根事實整合為營運階段投影；單一 owner fact 不可用時只局部標示 unavailable，不使整頁訂單清單失效。既有七階段／十一 SOP 契約保持相容，待辦看板 Beta 另由同一正式根事實轉成十三核心階段唯讀契約。

## Implementation
- primary:
  - `subsystems/orders/stage_projection_query.py`
  - `subsystems/orders/core_stage_projection_query.py`
  - `infrastructure/mysql/orders_stage_projection_repository.py`
- entrypoints:
  - `api/routes/orders_stage_projection.py`
  - `api/routes/orders_core_stage_projection.py`
  - `api/dependencies/orders_stage_projection.py`

## Dependencies
- outbound: `scheduling/scheduling` — 讀取正式服務期間與 service-time terms。
- outbound: `client-finance/client-finance` — 讀取定金與客戶 obligation projection。
- outbound: `payroll/payroll` — 讀取月嫂薪資 obligation projection。

## Contracts
- `api/routes/orders_stage_projection.py` — `/api/orders/operational-timelines` typed read-only contract。
- `api/routes/orders_core_stage_projection.py` — `/api/orders/core-stage-timelines` Beta typed read-only contract；十三核心階段中的 11～13 直接沿用 service completion、client settlement、staff payout owner 子投影。

## Provenance
- Query composition and API entry — `source_observed` — `subsystems/orders/stage_projection_query.py`, `subsystems/orders/core_stage_projection_query.py`, `api/routes/orders_stage_projection.py`, and `api/routes/orders_core_stage_projection.py`.

## Change triggers
Reconcile when stage identity, availability semantics, owner facts, API route, or projection test root changes.
