subsystem: scheduling
parent_domain: scheduling
architecture: ../../../../../domains/scheduling/subsystems/scheduling/index.md
test_root: tests/domains/scheduling/subsystems/scheduling/
integration_root: tests/domains/scheduling/subsystems/scheduling/integration/
fixtures_root: tests/fixtures/
modules:
  matching-coordination:
    test_root: tests/domains/scheduling/subsystems/scheduling/modules/matching-coordination/
  staff-monthly-calendar:
    test_root: tests/domains/scheduling/subsystems/scheduling/modules/staff-monthly-calendar/
    layout_status: custom_current
    presentation_test_roots:
      - ui_react/src/tests/staff_monthly_schedule_client.test.ts
      - ui_react/src/tests/scheduling_current_page.test.tsx
  staff-availability:
    module: modules/staff-availability.md
    test_root: ui_react/src/tests/domains/scheduling/subsystems/scheduling/modules/staff-availability/
    layout_status: custom_current
  holiday-maintenance:
    module: modules/holiday-maintenance.md
    test_file: ui_react/src/tests/domains/scheduling/subsystems/scheduling/modules/holiday-maintenance/holiday_csv.test.tsx
    test_file: ui_react/src/tests/domains/scheduling/subsystems/scheduling/modules/holiday-maintenance/holiday_adapter.test.ts
    layout_status: custom_current
  matching-schedule-confirmation:
    layout_status: custom_current
    test_root: ui_react/src/tests/matching_schedule_confirmation_actions.test.tsx
  leave-substitution:
    layout_status: custom_current
    test_root: ui_react/src/tests/substitution_payables_readback.test.tsx
  service-before-replacement:
    test_root: tests/domains/scheduling/subsystems/scheduling/modules/service-before-replacement/
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
- `current-anomaly-facts` has no dedicated test root: `SCHEDULE-002/003/006` are retired from runtime Anomalies; live correctness remains in existing Scheduling owner module/integration tests, while migration/historical readback is covered by `tests/domains/scheduling/subsystems/scheduling/integration/test_historical_baseline_scheduling_owner_adapter.py`.
- `service-before-replacement` — `tests/test_service_before_replacement_schema_contract.py` remains at the higher release/schema verification boundary; its repo-relative artifact paths bind an explicit schema/release contract rather than an owner-local test-layout dependency.
- `tests/test_staff_service_day_log_api.py` remains at the external-identity/API boundary because it binds LINE identity before issuing a Scheduling command.
- `tests/domains/scheduling/subsystems/scheduling/integration/test_service_end_date_calculation_correctness.py` remains at the higher cross-implementation/MySQL boundary because it compares import and live Scheduling calculators.
- Service-before-replacement anomaly projection is owned by `tests/domains/anomalies/subsystems/anomalies/integration/`.
- Matching schedule confirmation and staff leave LIFF intake live under the canonical LINE subsystem integration root.
- Matching is a Scheduling responsibility in the current architecture map; no separate top-level Matching test domain is invented.

# Placement refresh — 2026-09-09
- `tests/domains/scheduling/subsystems/scheduling/modules/staff-monthly-calendar/test_staff_monthly_calendar_service.py` and `tests/domains/scheduling/subsystems/scheduling/modules/staff-monthly-calendar/test_staff_monthly_schedule_route.py` now share the existing monthly-calendar module root. Their direct SUTs are the Scheduling projection and its single-router transport; mocked facts/authentication do not make them application-wide integration tests.
- `tests/domains/scheduling/subsystems/scheduling/test_staff_leave_intake_domain.py` tests the Scheduling-owned leave-request state rules. LINE ingress remains a separate verification boundary; the filename does not transfer ownership to Staff or LINE.

The three files were moved without content changes. This bounded correction supersedes the earlier blanket flat-test audit claim; it does not assert that all remaining flat tests have been audited. Existing higher-boundary and React `custom_current` exceptions remain unchanged.
