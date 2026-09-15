# Module: historical-precision-restart

## Parent
- domain: `orders`
- subsystem: `orders`

## Responsibility
只允許歷史未服務／服務中案件由工會人員在原訂單工作台退出歷史分支並回到正常「訂單成立」。單一 outer Unit of Work 撤銷 current confirmed dates 與有效排班、清空 current actual start／end並保留歷史 provenance；已存在歷史帳務的完成訂單不得重啟，改由 `historical-service-accounting` 直接修正實際天數與差額。

## Implementation
- primary:
  - `domains/orders/historical_precision_restart.py`
  - `subsystems/orders/historical_precision_restart_workflow.py`
  - `infrastructure/mysql/historical_precision_restart_repository.py`
  - `infrastructure/mysql/scheduling_replacement_writer.py`（允許本 command 建立空的 tombstone generation）
- entrypoints:
  - `api/routes/historical_service_accounting.py`
  - `api/dependencies/historical_service_accounting.py`
  - `api/schemas/historical_service_accounting.py`
  - `ui_react/src/components/OrderWorkbenchV2Drawer.tsx`
  - `ui_react/src/api/orders/historical_service_accounting_client.ts`

## Dependencies
- outbound: `scheduling` — 撤銷原有效 generation，建立等待正常流程重建的空 tombstone。
- observed-only: `client-finance`／`payroll` — 重啟只查詢並保存既有版本、基準義務與付款 lineage；後續正常流程才形成差額。
- inbound: authenticated historical-order administration only.

## Contracts
- `document/架構重整/01_規格基線/27_歷史訂單生命週期與服務天數帳務正式規格.md` §8／§9

## Verification
- test_root: `tests/domains/orders/subsystems/orders/modules/historical-precision-restart/`
- higher_boundary: restart → confirmed service dates → matching confirmation → assignment plan → canonical Scheduling／reporting readback。

## Change triggers
Reconcile when restart eligibility, historical accounting bridge, current-root revocation、API/UI entrypoint or provenance receipt semantics change.
eligible 的歷史未服務／服務中狀態都只回到正常 `訂單成立`；重啟不得接受服務日期、直接建立帳務或視為 actual-start reconfirmation。後續全部使用既有正常訂單 UI／API。
六欄歷史來源缺少可信排休 root 時，Order Workbench V2 只允許人工確認真實服務日期，不得預設任何 service mode。restart writer 本身仍只建立空 tombstone；其後由既有服務日期 Apply 在同一交易保存 confirmed dates，且僅對待重建的 restart tombstone 呼叫 Scheduling generation replacement writer，讓可追溯的歷史 assignment 與人工日期成為 current canonical `staff_schedule`。
