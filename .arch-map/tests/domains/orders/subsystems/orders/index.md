subsystem: orders
parent_domain: orders
architecture: ../../../../../domains/orders/subsystems/orders/index.md
test_root: tests/domains/orders/subsystems/orders/
integration_root: tests/domains/orders/subsystems/orders/integration/
fixtures_root: tests/fixtures/
modules:
  historical-adoption:
    test_root: tests/domains/orders/subsystems/orders/modules/historical-adoption/

# Exceptions
- `historical-adoption` — disposable-MySQL workbook integration remains at `tests/integration/test_historical_order_workbook.py`; it is a higher-boundary `layout_gap`, not duplicate owner-local coverage.
- Other Orders focused tests may still be flat under `tests/`; admit by current behavior/contract search rather than broad scan.
