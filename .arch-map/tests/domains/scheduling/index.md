domain: scheduling
architecture: ../../domains/scheduling/index.md
test_root: layout_gap
integration_root: tests/integration/
fixtures_root: tests/fixtures/
subsystems:
  scheduling:
    index: subsystems/scheduling/index.md

# Routing notes
No `tests/domains/scheduling/` root was observed. Scheduling focused suites are primarily flat `tests/test_*` with some MySQL/integration coverage under `tests/integration/`; use the subsystem index to route the two mapped modules.
