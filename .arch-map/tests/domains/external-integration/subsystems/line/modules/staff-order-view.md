module: staff-order-view
parent_subsystem: line
architecture: ../../../../../../domains/external-integration/subsystems/line/modules/staff-order-view.md
test_root: tests/domains/external-integration/subsystems/line/modules/staff-order-view/

# Owned verification
- Staff order page automatically loads the verified staff member's assignment-scoped orders.
- The request schema permits an empty optional filter while preserving the bounded typed contract.
