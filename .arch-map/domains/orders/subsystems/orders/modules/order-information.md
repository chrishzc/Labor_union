# Module: order-information

## Parent
- domain: `orders`
- subsystem: `orders`

## Responsibility
提供既有案件訂單資訊的 typed Query 與管理端 readback；不改寫 Orders root facts。

## Implementation
- `subsystems/orders/order_information.py`
- `infrastructure/mysql/order_information_repository.py`
- `db/templates/tpl_info_01.json`
- `db/templates/tpl_info_02.json`
- `api/routes/orders.py`
- `api/dependencies/order_information.py`
- `api/schemas/order_information.py`
- `ui_react/src/api/orders/order_query_client.ts`
- `ui_react/src/pages/OrdersPage.tsx`
- `ui_react/src/pages/OrderTrackerPage.tsx`

## Verification
- Python test root: `tests/domains/orders/subsystems/orders/modules/order-information/`
- React client: `ui_react/src/tests/orders_query_client.test.ts`
- React pages: `ui_react/src/tests/orders_page_real_data.test.tsx`, `ui_react/src/tests/order_tracker_real_data.test.tsx`

## Provenance
- Current route, application, MySQL adapter and React callers observed in source.
