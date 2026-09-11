module: order-terms
parent_subsystem: orders
architecture: ../../../../../../domains/orders/subsystems/orders/modules/order-terms.md
layout_status: custom_current
test_root: tests/test_order_terms_preassignment_correction.py

## Owned verification
- `tests/test_order_terms_preassignment_correction.py` — preassignment Orders Terms Query／Preview／Apply、跨 owner no-op／fail-closed 影響、receipt 與起訖日平移回歸。
