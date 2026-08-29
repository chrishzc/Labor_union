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
  - `infrastructure/mysql/matching_coordination_repository.py`
  - `infrastructure/mysql/matching_coordination_facts_adapter.py`
- entrypoints:
  - `api/routes/matching_coordination.py`
  - `api/schemas/matching_coordination.py`
  - `ui_react/src/api/matching_coordination/matching_coordination_client.ts`
  - `ui_react/src/components/MatchingCoordinationWorkbench.tsx`

## Dependencies
- outbound: `orders/orders` — case/lifecycle boundary.
- inbound: Scheduling UI/LINE adapters — transport invokes typed coordination commands, not direct DB writes.

## Contracts
- `document/架構重整/01_規格基線/02_Assignments_Scheduling_Domain.md` — Scheduling ownership.
- `document/架構重整/01_規格基線/24_Staff_Matching_Preferences與不可服務期間正式規格.md` — matching preference/unavailability facts.

## Verification
- test_root: `layout_gap` — focused suites currently live in flat `tests/` (`test_matching_coordination_*`).
- higher_boundary:
  - `tests/integration/`
- routing: `.arch-map/tests/domains/scheduling/subsystems/scheduling/index.md`.

## Provenance
- Domain ownership — `architecture_declared` — Scheduling specs.
- Source/API/UI paths — `source_observed` — current repository search.
- Flat focused test layout — `source_observed` — current `tests/test_matching_coordination_*`.

## Change triggers
Reconcile when coordination owner, package/event contract, API route/schema, persistence adapter or focused test root moves.
