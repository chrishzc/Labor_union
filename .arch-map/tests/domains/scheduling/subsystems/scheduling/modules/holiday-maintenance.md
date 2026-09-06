# Test Module: holiday-maintenance

## Parent
- subsystem: scheduling
- architecture: ../../../../../../domains/scheduling/subsystems/scheduling/modules/holiday-maintenance.md

## Canonical root
- layout_status: custom_current
- test_file: `ui_react/src/tests/domains/scheduling/subsystems/scheduling/modules/holiday-maintenance/holiday_csv.test.tsx`
- test_file: `ui_react/src/tests/domains/scheduling/subsystems/scheduling/modules/holiday-maintenance/holiday_adapter.test.ts`
- canonical_basis: existing Holiday module test directory under the UI source tree, declared by the Scheduling production module leaf and confirmed by both current tests.

## Coverage
The canonical Holiday module tests call the actual parser, typed transport, adapter and SchedulingPage for official 0/2 parsing, malformed and mixed-year rejection, blank-weekend filtering, preview zero-write, fresh per-date versions, double-pay preservation, identical-row skip, partial failure, replay classification, adapter retry/state transitions, and visible awaited readback failure.
