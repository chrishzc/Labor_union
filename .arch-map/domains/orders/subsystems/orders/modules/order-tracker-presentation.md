# Module: order-tracker-presentation

## Parent
- domain: `orders`
- subsystem: `orders`

## Responsibility
呈現Orders-owned七階段tracker與訂單摘要主清單的既有query、explicit retry及stale response suppression。主清單錯誤不得顯示raw runtime detail；不得改寫跨owner stage projection、drawer資料或LINE notification timeline語意。

## Implementation
- primary: `ui_react/src/pages/OrderTrackerPage.tsx`
- typed stage consumers: `ui_react/src/api/orders/order_stage_projection_client.ts`, `ui_react/src/api/orders/order_stage_projection_schemas.ts`, `ui_react/src/adapters/orders/order_stage_projection_adapter.ts`

## Contracts
- `document/架構重整/01_規格基線/01_Orders_Domain.md` — Orders query與lifecycle owner規則。
- `document/架構重整/01_規格基線/12_Global_效能與UX體感架構.md` — 一般畫面資訊層級與closed error boundary。
- Orders projection routes `/api/orders/government-subsidy-projections` and `/api/orders/terminal-aggregates` — server-owned subsidy status/counts and terminal aggregate facts.

## Presentation invariants

- OrderTracker consumes the government subsidy and terminal aggregate list projections with their own cursor contracts; only the operational-timeline route accepts `lifecycle_scope`. When subsidy filtering is active, summary/stage queries use `all` and the server-returned subsidy case IDs select the visible set; otherwise the existing unfinished/all summary behavior remains.
- The subsidy substatus selector is server-backed: selecting all statuses or a substatus re-queries the projection endpoint, and the UI uses the returned case IDs without filtering a loaded page or recomputing counts.
- A case absent from a projection page is kept as an absent query result; the UI does not infer a data gap or recompute terminal or subsidy facts in React. Historical and cancelled lifecycle filtering remains server-scoped.

## Verification
- layout_status: `custom_current`
- test_root: `ui_react/src/tests/order_tracker_request_budget.test.tsx`
- routing: `.arch-map/tests/domains/orders/subsystems/orders/modules/order-tracker-presentation.md`

## Change triggers
Reconcile when Order Tracker summary presentation、retry/request budget、stale suppression、closed error或focused test location changes。
