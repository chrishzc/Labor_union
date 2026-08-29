subsystem: orders
parent_domain: orders
architecture: ../../../../domains/orders/subsystems/orders/index.md
test_root: layout_gap
integration_root: tests/integration/
fixtures_root: tests/fixtures/
modules:
  historical-adoption:
    test_root: tests/domains/orders/

# Exceptions
- `historical-adoption` — owner-local unit/domain coverage currently sits directly under `tests/domains/orders/`; MySQL workbook integration is under `tests/integration/`. Status: `layout_gap`, not duplicated.
- Other Orders focused tests may still be flat under `tests/`; admit by current behavior/contract search rather than broad scan.
