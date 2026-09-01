# Module: matching-coordination

## Parent
- domain: `scheduling`
- subsystem: `scheduling`

## Responsibility
維護 Scheduling-owned matching coordination 的 candidate/decision/plan/package lineage 與 typed Query／Preview／Apply contract，並向 API／React 暴露可驗證的 current coordination state。

## Implementation
- primary:
  - `domains/scheduling/matching_coordination.py`
  - `subsystems/scheduling/matching_coordination_contracts.py`
- `subsystems/scheduling/matching_coordination_workflow.py`
- `subsystems/scheduling/matching_notification_application.py` (zero-pool client decision response owner)
  - `subsystems/scheduling/matching_coordination_application.py` — P3 typed leave/date handoffs
  - `infrastructure/mysql/matching_coordination_repository.py`
  - `infrastructure/mysql/matching_coordination_facts_adapter.py`
  - `infrastructure/mysql/segmented_availability_repository.py`
- entrypoints:
  - `api/routes/matching_coordination.py`
  - `api/schemas/matching_coordination.py`
  - `ui_react/src/api/matching_coordination/matching_coordination_client.ts`
  - `ui_react/src/components/MatchingCoordinationWorkbench.tsx`
  - `ui_react/src/pages/SchedulingPage.tsx`

## Dependencies
- outbound: `orders/orders` — case/lifecycle boundary.
- inbound: Scheduling UI/LINE adapters — transport invokes typed coordination commands, not direct DB writes.
- P3 handoff: committed M3 intents carry immutable `LU96-M3-*` source identity and recipient selector; P5 owns delivery task/provider consumption.

## Contracts
- `document/架構重整/01_規格基線/02_Assignments_Scheduling_Domain.md` — Scheduling ownership.
- `document/架構重整/01_規格基線/24_Staff_Matching_Preferences與不可服務期間正式規格.md` — matching preference/unavailability facts.

## Verification
- test_root: `tests/domains/scheduling/subsystems/scheduling/modules/matching-coordination/`
- layout_status: `custom_current`
- test_root: `ui_react/src/tests/matching_coordination_workbench.test.tsx`
- higher_boundary:
  - tests/integration/ (shared legacy higher-boundary root)
- layout_gap:
  - `tests/test_matching_coordination_repository.py` — still uses a repo-relative schema path and remains at its observed path until that path dependency is reconciled.
- routing: `.arch-map/tests/domains/scheduling/subsystems/scheduling/index.md`.

## Provenance
- Domain ownership — `architecture_declared` — Scheduling specs.
- Source/API/UI paths — `source_observed` — current repository search.
- Module-owned contract/domain/workflow/facts/API-route tests — `source_observed` — architecture-aligned test root.
- Scheduling React entry contract — `source_observed` — same architecture-aligned module test root.
- Repository test exception — `source_observed` — current flat path with relocation-sensitive schema lookup.

## Change triggers
Reconcile when coordination owner, package/event contract, presentation hierarchy, API route/schema, persistence adapter or focused test root moves.
