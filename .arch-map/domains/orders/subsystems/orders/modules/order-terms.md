# Module: order-terms

## Parent
- domain: `orders`
- subsystem: `orders`

## Responsibility
編排 Orders Terms 的 Query／zero-write Preview／fresh-lock Apply，以單一 outer Unit of Work 套用 Orders、Scheduling、Client Finance 與 Payroll 影響並產生可追溯 receipt。尚未建立 assignment 時，起始日平移不虛構排班 segment，並以相同天數平移預計結束日；已有 current confirmed service dates 時保留日期間隔、建立新的 immutable current version 取代舊版。

## Implementation
- primary:
  - `subsystems/orders/terms_workflow.py`
  - `infrastructure/mysql/order_terms_read_model.py`
  - `infrastructure/mysql/order_terms_repository.py`

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

## Provenance
- Workflow owner and cross-owner transaction boundary — `architecture_declared` — Orders formal spec and current source.
- Preassignment start-date、confirmed-service-date replacement projection and focused regression — `source_observed` — current workflow, MySQL adapter and test listed above.

## Change triggers
Reconcile when Orders Terms public contract, cross-owner impact, transaction boundary, preassignment generation semantics, receipt, or focused test root changes.
