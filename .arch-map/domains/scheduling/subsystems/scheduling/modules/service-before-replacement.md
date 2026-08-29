# Module: service-before-replacement

## Parent
- domain: `scheduling`
- subsystem: `scheduling`

## Responsibility
處理正式服務開始前的 replacement/successor flow：從 fresh owner facts 建立 typed Query／Preview／Apply、successor lineage、receipt/outbox 與 complete readback；已有 actual-service proof 時轉向代班/替代流程，不讓 replacement workflow 偽造 owner state。

## Implementation
- primary:
  - `domains/scheduling/service_before_replacement.py`
  - `subsystems/scheduling/service_before_replacement_workflow.py`
  - `infrastructure/mysql/service_before_replacement_loader.py`
  - `infrastructure/mysql/service_before_replacement_repository.py`
- entrypoints:
  - `api/routes/service_before_replacement.py`
  - `api/dependencies/service_before_replacement.py`
  - `api/schemas/service_before_replacement.py`
  - `ui_react/src/api/orders/service_before_replacement_client.ts`
  - `ui_react/src/components/ServiceBeforeReplacementActions.tsx`
- migrations:
  - `db/schema_parts/1012_service_before_replacement.sql`
  - `db/migration_releases/labor_union_2026_08_28_service_before_replacement_v1.json`
  - `db/migration_releases/labor_union_2026_08_28_service_before_replacement_v1.descriptors.json`

## Dependencies
- outbound: `orders/orders` — case/order lifecycle boundary.
- outbound: `scheduling/matching-coordination` — successor may consume/create Matching lineage through typed owner adapters.
- outbound: `anomalies/anomalies` — projection/recheck only; anomaly tracking cannot define success.

## Contracts
- `document/架構重整/01_規格基線/02_Assignments_Scheduling_Domain.md` — Scheduling owner facts.
- Global Query/Preview/Apply, UoW, idempotency and outbox contract — `document/架構重整/01_規格基線/00_Global_共同契約.md`.

## Verification
- static:
  - `db/schema_parts/1012_service_before_replacement.sql`
  - `db/migration_releases/labor_union_2026_08_28_service_before_replacement_v1.json`
- test_root: `tests/domains/scheduling/subsystems/scheduling/modules/service-before-replacement/`
- higher_boundary:
  - `tests/integration/`
- cross_owner:
  - `tests/domains/anomalies/subsystems/anomalies/integration/test_service_before_replacement_projection.py` — Anomalies-owned projection contract.
- layout_gap:
  - `tests/test_service_before_replacement_schema_contract.py` — relocation-sensitive schema lookup remains at observed path.
- routing: `.arch-map/tests/domains/scheduling/subsystems/scheduling/index.md`.

## Provenance
- Scheduling ownership/transaction semantics — `architecture_declared` — current specs.
- API/domain/subsystem/infra/UI/migration paths — `source_observed` — current repository search.
- Scheduling-owned focused tests — `source_observed` — module-owned test root.
- Remaining schema exception and Anomalies projection boundary — `source_observed` — current test roots.

## Change triggers
Reconcile when scenario ownership, actual-service referral boundary, matching dependency, route/schema, persistence/migration or test roots change.
