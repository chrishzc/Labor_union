domain: external-integration
architecture: ../../domains/external-integration/index.md
test_root: layout_gap
integration_root: unknown
fixtures_root: tests/fixtures/

# Routing notes
- LINE-focused tests currently live under `tests/line/`.
- Access-focused tests are primarily flat `tests/test_access_*`.
Neither physical root matches the canonical architecture-owned layout yet. Use `subsystems/access/` or `subsystems/line/` source ownership first, then admit only matching focused tests; do not index every file here.
