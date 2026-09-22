module: order-terms
parent_subsystem: orders
architecture: ../../../../../../domains/orders/subsystems/orders/modules/order-terms.md
layout_status: custom_current
test_root: tests/test_order_terms_preassignment_correction.py
test_root: tests/domains/orders/subsystems/orders/modules/order-terms/
test_root: ui_react/src/tests/domains/orders/subsystems/orders/modules/order-terms/
test_root: tests/domains/orders/subsystems/orders/modules/intake-terms-bootstrap/unit/

## Owned verification
- `tests/test_order_terms_preassignment_correction.py` — preassignment Orders Terms Query／Preview／Apply、跨 owner no-op／fail-closed 影響、receipt 與起訖日平移回歸。
- `tests/domains/orders/subsystems/orders/modules/order-terms/` — Orders Terms domain、HTTP input 與 nullable service-time contract。
- `ui_react/src/tests/domains/orders/subsystems/orders/modules/order-terms/` — Terms 操作面板 payload、readback 與再次編輯回歸。
- `tests/domains/orders/subsystems/orders/modules/intake-terms-bootstrap/unit/` — intake terms bootstrap、client-name repair 與 intake completion 的 owner-local Preview／Apply、fresh-version、receipt regression。
