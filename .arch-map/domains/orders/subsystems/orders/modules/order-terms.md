# Module: order-terms

## Parent
- domain: `orders`
- subsystem: `orders`

## Responsibility
編排 Orders Terms 的 Query／zero-write Preview／fresh-lock Apply，以單一 outer Unit of Work 套用 Orders、Scheduling、Client Finance 與 Payroll 影響並產生可追溯 receipt。尚未建立 assignment 時，起始日平移不虛構排班 segment，並以相同天數平移預計結束日；已有 current confirmed service dates 時保留日期間隔、建立新的 immutable current version 取代舊版。

Issue #326：同一 Terms command 可承接完整替代日期與明確既有指派分配；原有跨 owner transaction 與 immutable versions 保持不變。

既有歷史案件缺少約定服務開始日／服務天數，且尚未建立 Client Finance、Payroll 或服務資料鎖定時，沿用同一 owner-local Query／Preview／Apply 補齊契約條件；保留歷史 lifecycle、實際開工日與既有歷史排班證據。

## Implementation
- primary:
  - `domains/orders/terms.py`
  - `subsystems/orders/terms_workflow.py`
  - `subsystems/orders/order_intake_terms_bootstrap.py`
  - `infrastructure/mysql/order_terms_read_model.py`
  - `infrastructure/mysql/order_terms_repository.py`
  - `infrastructure/mysql/order_intake_terms_bootstrap_repository.py`
  - `api/schemas/order_terms.py`
  - `api/dependencies/order_terms.py`
- entrypoints:
  - `api/routes/order_terms.py` — Orders Terms Query／Preview／Apply HTTP transport 與輸入驗證。
  - `ui_react/src/api/orders/order_terms_mutation_client.ts` — strict typed client 與 nullable service-time tuple decoder。
  - `ui_react/src/components/OrderTermsMutationPanel.tsx` — Terms Preview／Apply 操作面板；未修改的全空服務時段可原樣保存。
  - `api/routes/order_intake_terms_bootstrap.py` — 早期進件及受限歷史案件的服務條件修正，以及進件完成的 Preview／Apply HTTP transport。

## Dependencies
- outbound: `scheduling/schedule-generation` — 由 Scheduling typed candidate 判定排班 generation 影響；Orders 不自行寫入 assignment。
- outbound: `scheduling/matching-coordination` — 正式日期 replacement 使既有 matching schedule snapshot 失效；候選與方案 owner facts 不由 Orders 改寫。
- outbound: `client-finance/client-finance` — 條款變更的客戶應收影響。
- outbound: `staff-payables/payroll` — 條款變更的薪資影響。

## Contracts
- `document/架構重整/01_規格基線/01_Orders_Domain.md` — Orders Terms 與 Query／Preview／Apply 語意。
- `document/架構重整/01_規格基線/02_Assignments_Scheduling_Domain.md` — Scheduling generation ownership。

## Verification
- layout_status: `custom_current`
- test_root: `tests/test_order_terms_preassignment_correction.py`
- test_root: `tests/domains/orders/subsystems/orders/modules/order-terms/`
- test_root: `ui_react/src/tests/domains/orders/subsystems/orders/modules/order-terms/`
- test_root: `tests/domains/orders/subsystems/orders/modules/intake-terms-bootstrap/unit/`

## Provenance
- Workflow owner and cross-owner transaction boundary — `architecture_declared` — Orders formal spec and current source.
- Preassignment start-date、confirmed-service-date replacement projection and focused regression — `source_observed` — current workflow, MySQL adapter and test listed above.
- Nullable service-time HTTP／UI preservation and disposable-MySQL round trip — `source_observed` — canonical module and subsystem integration roots listed above.
- Intake terms bootstrap and intake completion owner-local unit regression — `source_observed` — current bootstrap workflow and canonical unit root.

## Change triggers
Reconcile when Orders Terms public contract, cross-owner impact, transaction boundary, preassignment generation semantics, receipt, or focused test root changes.
