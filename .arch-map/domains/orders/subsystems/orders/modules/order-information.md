# Module: order-information

## Parent
- domain: `orders`
- subsystem: `orders`

## Responsibility
提供既有案件訂單資訊的 typed Query 與管理端 readback；不改寫 Orders root facts。
初步候選資訊由 candidate-specific 投影重用相同命名欄位；無正式 assignment 時不虛構指派，未知費用待確認，預覽全文與收件對象綁定後交 Scheduling durable sender。

## Implementation
- `subsystems/orders/order_information.py`
- `infrastructure/mysql/order_information_repository.py`
- `db/templates/tpl_info_01.json`
- `db/templates/tpl_info_02.json`
- `api/routes/orders.py`
- `api/dependencies/order_information.py`
- `api/schemas/order_information.py`
- `ui_react/src/api/orders/order_information_client.ts`
- `ui_react/src/components/OrderInformationSheets.tsx`
- `ui_react/src/pages/OrderWorkbenchV2Page.tsx`
- `ui_react/src/components/OrderWorkbenchV2Drawer.tsx`

## Verification
- Python test root: `tests/domains/orders/subsystems/orders/modules/order-information/`
- React client: `ui_react/src/tests/orders_query_client.test.ts`
- React page: `ui_react/src/tests/order_workbench_v2_page.test.tsx`

## Provenance
- Current route, application, MySQL adapter and React callers observed in source.
