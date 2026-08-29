subsystem: scheduling
parent_domain: scheduling
architecture: ../../../../../domains/scheduling/subsystems/scheduling/index.md
test_root: layout_gap
integration_root: tests/integration/
fixtures_root: tests/fixtures/
modules:
  matching-coordination:
    test_root: layout_gap
  service-before-replacement:
    test_root: layout_gap

# Exceptions
- `matching-coordination` — current focused tests are flat under `tests/` with prefix `test_matching_coordination_`; intended owner is this subsystem/module.
- `service-before-replacement` — focused tests are flat under `tests/` with prefix `test_service_before_replacement`; MySQL adapter integration is `tests/integration/test_service_before_replacement_mysql_adapter.py`.
These are routing exceptions only; do not mass-move them without a bounded lifecycle task.
