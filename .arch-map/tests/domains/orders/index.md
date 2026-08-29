domain: orders
architecture: ../../domains/orders/index.md
test_root: tests/domains/orders/
integration_root: tests/integration/
fixtures_root: tests/fixtures/
subsystems:
  orders:
    index: subsystems/orders/index.md

# Routing notes
`tests/domains/orders/` is the current architecture-aligned Domain root. `tests/integration/` remains a shared higher-boundary root, and additional flat `tests/test_*order*` suites are a `layout_gap`; do not inventory them file-by-file here.
