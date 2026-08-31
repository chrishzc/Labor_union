# Module: matching-schedule-confirmation

## Parent
- domain: `scheduling`
- subsystem: `scheduling`

## Responsibility
將 current confirmed-service-date version 與 formal matching plan 投影為客戶／月嫂 recipient snapshots，編排 durable LINE delivery intent，並以 recipient-bound confirmation event 與 fresh Query readback 保護正式排班 gate。

## Implementation
- primary:
  - `subsystems/scheduling/matching_schedule_confirmation.py`
  - `infrastructure/mysql/matching_schedule_confirmation_repository.py`
- entrypoints:
  - `api/routes/matching_schedule_confirmation.py`
  - `ui_react/src/api/scheduling/matching_schedule_confirmation_client.ts`
  - `ui_react/src/components/MatchingScheduleAndAssignmentActions.tsx`
- inbound LINE adaptation:
  - `subsystems/line/matching_postback_application.py`

## Boundaries
- Scheduling owns schedule snapshots, recipient confirmation facts and the assignment gate.
- LINE owns verified user identity, interaction transport, durable delivery task and provider outcome; the postback adapter only forwards a recipient-bound typed decision.
- Zero-pool and candidate-delivery semantics are outside this module's current Task 96 contract.

## Contracts
- `document/架構重整/01_規格基線/02_Assignments_Scheduling_Domain.md`
- `document/架構重整/01_規格基線/17_External_Integration_LINE_Access正式規格.md`

## Verification
- test_root: `ui_react/src/tests/matching_schedule_confirmation_actions.test.tsx`
- layout_status: `custom_current`
- higher-boundary integration:
  - `tests/domains/external-integration/subsystems/line/integration/test_matching_schedule_confirmation.py`
  - `tests/domains/external-integration/subsystems/line/subsystems/test_line_matching_postback_stage7.py`
- compatibility tests:
  - `tests/test_matching_schedule_confirmation_api_client.py`
  - `tests/test_matching_schedule_confirmation_panel.py`

## Provenance
- Owner and recipient-confirmation semantics: `architecture_declared` — Scheduling and LINE formal specs.
- Source, entrypoint and test paths: `source_observed` — current repository.

## Change triggers
Reconcile when schedule snapshot ownership, recipient binding, postback adaptation, delivery intent, assignment gate, API/client/UI entry or focused verification path changes.
