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
- Current owner-local coverage includes holiday maintenance/router; multi-caregiver schedule read and assignment-list routes; the historical-baseline Scheduling owner adapter; Matching coordination compatibility/owner-adapter contracts; and the scheduling replacement-writer empty-resolution compatibility guard used by Orders terms rebuilds.
- `matching-coordination` — `tests/test_matching_coordination_repository.py` remains a bounded `layout_gap` because it reads a schema using a repo-relative `__file__` path.
- `service-before-replacement` — `tests/test_service_before_replacement_schema_contract.py` remains a relocation-sensitive `layout_gap`.
- `tests/test_staff_service_day_log_api.py` remains at the external-identity/API boundary because it binds LINE identity before issuing a Scheduling command.
- `tests/test_service_end_date_calculation_correctness.py` remains at the higher cross-implementation/MySQL boundary because it compares import and live Scheduling calculators.
- Service-before-replacement anomaly projection is owned by `tests/domains/anomalies/subsystems/anomalies/integration/`.
- Matching schedule confirmation and staff leave LIFF intake live under the canonical LINE subsystem integration root.
- Matching is a Scheduling responsibility in the current architecture map; no separate top-level Matching test domain is invented.
