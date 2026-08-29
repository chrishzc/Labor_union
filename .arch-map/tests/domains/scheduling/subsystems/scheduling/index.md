subsystem: scheduling
parent_domain: scheduling
architecture: ../../../../../domains/scheduling/subsystems/scheduling/index.md
test_root: tests/domains/scheduling/subsystems/scheduling/
integration_root: tests/domains/scheduling/subsystems/scheduling/integration/
fixtures_root: tests/fixtures/
modules:
  matching-coordination:
    test_root: tests/domains/scheduling/subsystems/scheduling/modules/matching-coordination/
  service-before-replacement:
    test_root: tests/domains/scheduling/subsystems/scheduling/modules/service-before-replacement/

# Exceptions
- `matching-coordination` — `tests/test_matching_coordination_repository.py` remains a bounded `layout_gap` because it reads a schema using a repo-relative `__file__` path.
- `service-before-replacement` — `tests/test_service_before_replacement_schema_contract.py` remains a relocation-sensitive `layout_gap`.
- Service-before-replacement anomaly projection is owned by `tests/domains/anomalies/subsystems/anomalies/integration/`.
- Matching schedule confirmation and staff leave LIFF intake now live under the canonical LINE subsystem integration root.
These exceptions are routing facts only; remove them after exact path/owner reconciliation and verification.
