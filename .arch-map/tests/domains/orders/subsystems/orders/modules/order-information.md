module: order-information
parent_subsystem: orders
architecture: ../../../../../../domains/orders/subsystems/orders/modules/order-information.md
layout_status: canonical
test_root: tests/domains/orders/subsystems/orders/modules/order-information/

## Owned verification
- `contract/test_order_information.py` — exact target, Case Import-to-Orders typed projection, field-local fail-closed behavior, and template metadata contract.
