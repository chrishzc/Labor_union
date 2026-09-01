# Module: order-information

## Parent
- domain: `orders`
- subsystem: `orders`

## Responsibility
提供既有案件訂單資訊模板的 typed Query／Preview 與管理端 readback；不改寫 Orders root facts。

## Implementation
- `subsystems/orders/order_information.py`
- `infrastructure/mysql/order_information_repository.py`
- `db/templates/tpl_info_01.json`
- `db/templates/tpl_info_02.json`
- `api/routes/orders.py`
- `api/dependencies/order_information.py`
- `api/schemas/order_information.py`
- `ui/api_clients/order_information_api_client.py`
- `ui/pages/05_form_management.py`
- `ui/pages/form_management/shared.py`
- `ui/pages/form_management/tab2_template_library.py`

## Verification
- test_root: `tests/domains/orders/subsystems/orders/modules/order-information/`

## Provenance
- order-information owner and contract test root — `source_observed` — current Orders route, application, adapter and focused contract test.
