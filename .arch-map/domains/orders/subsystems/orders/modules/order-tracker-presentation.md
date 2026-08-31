# Module: order-tracker-presentation

## Parent
- domain: `orders`
- subsystem: `orders`

## Responsibility
呈現Orders-owned七階段tracker與訂單摘要主清單的既有query、explicit retry及stale response suppression。主清單錯誤不得顯示raw runtime detail；不得改寫跨owner stage projection、drawer資料或LINE notification timeline語意。

## Implementation
- primary: `ui_react/src/pages/OrderTrackerPage.tsx`

## Contracts
- `document/架構重整/01_規格基線/01_Orders_Domain.md` — Orders query與lifecycle owner規則。
- `document/架構重整/01_規格基線/12_Global_效能與UX體感架構.md` — 一般畫面資訊層級與closed error boundary。

## Verification
- layout_status: `custom_current`
- test_root: `ui_react/src/tests/order_tracker_request_budget.test.tsx`
- routing: `.arch-map/tests/domains/orders/subsystems/orders/modules/order-tracker-presentation.md`

## Change triggers
Reconcile when Order Tracker summary presentation、retry/request budget、stale suppression、closed error或focused test location changes。
