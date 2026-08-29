subsystem: scheduling
parent_domain: scheduling
architecture: ../../../../../domains/scheduling/subsystems/scheduling/index.md
test_root: tests/domains/scheduling/subsystems/scheduling/
integration_root: tests/integration/
fixtures_root: tests/fixtures/
modules:
  matching-coordination:
    test_root: tests/domains/scheduling/subsystems/scheduling/modules/matching-coordination/
  service-before-replacement:
    test_root: layout_gap

# Exceptions
- `matching-coordination` — `tests/test_matching_coordination_repository.py` remains a bounded `layout_gap` because it reads a schema using a repo-relative `__file__` path; the other focused tests have moved to the module-owned root.
- `service-before-replacement` — focused tests are flat under `tests/` with prefix `test_service_before_replacement`; MySQL adapter integration is `tests/integration/test_service_before_replacement_mysql_adapter.py`.
These are routing exceptions only; move them only with relocation/import/reference verification.
