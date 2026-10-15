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
    - 已有正式服務 proof 的轉介不讀無關的舊 Matching reuse snapshot；未服務的 replacement 仍 fail closed 核對來源。
  - `infrastructure/mysql/service_before_replacement_repository.py`
    - R-04 同一 UoW 退役 active caregiver matching plans 及原人選 entry，保存 replacement-event lineage；readback 不接受原方案仍 active。
  - `infrastructure/mysql/replacement_matching_query.py` — 以 R-04 receipt、current effective generation 與零 assignment 判定訂單成立案件可續辦候選／客戶確認，舊 round 不授權。
  - `infrastructure/mysql/scheduling_replacement_writer.py`
- entrypoints:
  - `api/routes/service_before_replacement.py`
  - `api/dependencies/service_before_replacement.py`
  - `api/schemas/service_before_replacement.py`
  - `ui_react/src/api/orders/service_before_replacement_client.ts`
  - `ui_react/src/components/ServiceBeforeReplacementActions.tsx`
    - 表單僅必填换人原因，允許空 references 並保留非空歷史 references 的 fingerprint／回讀；推薦頁的已有指派分支重用同一 writer。
    - 推薦頁區分換人啟動與新推薦完成；R-04 後確認舊方案退役再回選人，交接失敗只重讀，不能重送換人或移植舊客戶接受。
    - 客戶名冊 Drawer 重用同一操作；可回報草稿／處理中／結果未明／正式回讀狀態供外層關閉保護，未確認結果不得收合卸載。
- migrations:
  - `db/schema_parts/1012_service_before_replacement.sql`
  - `db/migration_releases/labor_union_2026_08_28_service_before_replacement_v1.json`
  - `db/migration_releases/labor_union_2026_08_28_service_before_replacement_v1.descriptors.json`

## Dependencies
- outbound: `orders/orders` — case/order lifecycle boundary.
- outbound: `scheduling/matching-coordination` — successor may consume/create Matching lineage through typed owner adapters.
- outbound: `anomalies/anomalies` — projection/recheck only; anomaly tracking cannot define success.
- inbound: `clients/profile-change` — 客戶名冊 Drawer 組合同一 Q/P/A，完成後重讀 effective assignments 與案件歷程，不新增 writer 或改變換人分流。

## Contracts
- `document/架構重整/01_規格基線/02_Assignments_Scheduling_Domain.md` — Scheduling owner facts.
- Global Query/Preview/Apply, UoW, idempotency and outbox contract — `document/架構重整/01_規格基線/00_Global_共同契約.md`.

## Verification
- static:
  - `db/schema_parts/1012_service_before_replacement.sql`
  - `db/migration_releases/labor_union_2026_08_28_service_before_replacement_v1.json`
- test_root: `tests/domains/scheduling/subsystems/scheduling/modules/service-before-replacement/`
- layout_status: `custom_current`
- test_root: `ui_react/src/tests/service_before_replacement_actions.test.tsx`
- higher_boundary:
  - tests/integration/ (shared legacy higher-boundary root)
- cross_owner:
  - `tests/domains/anomalies/subsystems/anomalies/integration/test_service_before_replacement_projection.py` — Anomalies-owned projection contract.
- higher_boundary_schema_release: current path-sensitive oracle is classified by the Global Arch Map routing.
- routing: `.arch-map/tests/domains/scheduling/subsystems/scheduling/index.md`.

## Provenance
- Scheduling ownership/transaction semantics — `architecture_declared` — current specs.
- API/domain/subsystem/infra/UI/migration paths — `source_observed` — current repository search.
- Scheduling-owned focused tests — `source_observed` — module-owned test root.
- Remaining schema exception and Anomalies projection boundary — `source_observed` — current test roots.

## Change triggers
Reconcile when scenario ownership, actual-service referral boundary, matching dependency, route/schema, persistence/migration, presentation hierarchy or test roots change.
