subsystem: scheduling
parent_domain: scheduling
architecture: ../../../../../domains/scheduling/subsystems/scheduling/index.md
test_root: tests/domains/scheduling/subsystems/scheduling/
integration_root: tests/domains/scheduling/subsystems/scheduling/integration/
fixtures_root: tests/fixtures/
modules:
  matching-coordination:
    test_root: tests/domains/scheduling/subsystems/scheduling/modules/matching-coordination/
  matching-schedule-confirmation:
    layout_status: custom_current
    test_root: ui_react/src/tests/matching_schedule_confirmation_actions.test.tsx
  leave-substitution:
    layout_status: custom_current
    test_root: ui_react/src/tests/substitution_payables_readback.test.tsx
  service-before-replacement:
    test_root: tests/domains/scheduling/subsystems/scheduling/modules/service-before-replacement/
  current-anomaly-facts:
    test_root: tests/domains/scheduling/subsystems/scheduling/modules/current-anomaly-facts/
  waiting-deposit-lock:
    test_root: tests/domains/scheduling/subsystems/scheduling/modules/waiting-deposit-lock/
  service-before-replacement-presentation:
    layout_status: custom_current
    test_root: ui_react/src/tests/service_before_replacement_actions.test.tsx
  matching-coordination-presentation:
    layout_status: custom_current
    test_root: ui_react/src/tests/matching_coordination_workbench.test.tsx

# Exceptions
- Current owner-local coverage includes holiday maintenance/router; multi-caregiver schedule read and assignment-list routes; the historical-baseline Scheduling owner adapter; Matching coordination compatibility/owner-adapter/repository contracts; and the scheduling replacement-writer empty-resolution compatibility guard used by Orders terms rebuilds.
- `service-before-replacement` — `tests/test_service_before_replacement_schema_contract.py` remains at the higher release/schema verification boundary; its repo-relative artifact paths bind an explicit schema/release contract rather than an owner-local test-layout dependency.
- `tests/test_staff_service_day_log_api.py` remains at the external-identity/API boundary because it binds LINE identity before issuing a Scheduling command.
- `tests/test_service_end_date_calculation_correctness.py` remains at the higher cross-implementation/MySQL boundary because it compares import and live Scheduling calculators.
- Service-before-replacement anomaly projection is owned by `tests/domains/anomalies/subsystems/anomalies/integration/`.
- Matching schedule confirmation and staff leave LIFF intake live under the canonical LINE subsystem integration root.
- Matching is a Scheduling responsibility in the current architecture map; no separate top-level Matching test domain is invented.

# Flat-test audit
The current flat-test audit found no additional high-confidence Scheduling owner-local tests outside the documented release/schema, LINE external-identity, cross-implementation/MySQL, Anomalies verification, or true cross-owner orchestration boundaries. Admit future cases by direct SUT/current ownership rather than filename alone.
