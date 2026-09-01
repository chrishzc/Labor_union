# Module: order-card-projection

## Parent
- domain: `orders`
- subsystem: `orders`

## Responsibility
將既有 Orders card typed projection轉為管理端可讀的案件根事實與正式指派摘要，並保護同一current Orders page既有workflow surface的業務／技術資訊分層。取消影響的一般畫面只呈現日期、正式服務量、客戶帳務與服務人員薪資調整；條款、服務日期與實際開工表單使用變更前後及稽核必填等業務語言。技術識別、raw action/direction、raw field name及owner/version只保留在按需技術詳情。不得改寫Orders lifecycle、cancellation rule或Scheduling／Finance／Payroll root facts。

## Implementation
- primary:
  - `ui_react/src/adapters/orders/order_card_projection_adapter.ts`
  - `ui_react/src/pages/OrdersPage.tsx`
  - `ui_react/src/pages/OrdersPage.css`
  - `subsystems/orders/card_projection_query.py`
  - `infrastructure/mysql/orders_card_projection_repository.py`

## Dependencies
- inbound: Orders React route — 只讀取既有typed projection。
- outbound: `scheduling/scheduling` — 正式指派資料只顯示typed owner projection，不由React重算。

## Contracts
- `document/架構重整/01_規格基線/01_Orders_Domain.md` — Orders root facts。
- `document/架構重整/01_規格基線/12_Global_效能與UX體感架構.md` — 管理端資訊層級與技術詳情邊界。

## Verification
- layout_status: `custom_current`
- test_root: `ui_react/src/tests/orders_page_real_data.test.tsx`
- test_root: `ui_react/src/tests/challenger_g5_adversarial_suite.test.tsx`
- test_root: `ui_react/src/tests/orders_no_fake_mutation.test.ts`
- routing: `.arch-map/tests/domains/orders/subsystems/orders/modules/order-card-projection.md`

## Provenance
- Orders／Scheduling owner boundary — `architecture_declared` — current formal specs。
- React source與既有focused regression — `source_observed` — current repository。

## Change triggers
Reconcile when card projection contract、Orders cancellation presentation、營運摘要欄位、technical-details boundary、React entry或focused test location changes。
