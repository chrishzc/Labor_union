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
- outbound: `scheduling` — 同交易沿用相符的有效媒合方案或建立單一 `proposed` 方案，將方案與分段 ID 記入既有重啟事件；撤銷原有效 generation 並建立空 tombstone。
- observed-only: `client-finance`／`payroll` — 重啟只查詢並保存既有版本、基準義務與付款 lineage；後續正常流程才形成差額。
- inbound: authenticated historical-order administration only.

## Contracts
- `document/架構重整/01_規格基線/27_歷史訂單生命週期與服務天數帳務正式規格.md` §8／§9

## Verification
- test_root: `tests/domains/orders/subsystems/orders/modules/historical-precision-restart/`
- higher_boundary: restart → confirmed service dates → matching confirmation → assignment plan → canonical Scheduling／reporting readback。

## Change triggers
Reconcile when restart eligibility, historical accounting bridge, current-root revocation、API/UI entrypoint or provenance receipt semantics change.
eligible 的歷史未服務／服務中狀態都只回到正常 `訂單成立`；重啟不得接受服務日期、直接建立帳務或視為 actual-start reconfirmation。後續沿用既有服務日期與排班 UI／API，但唯一歷史綁定人員不重跑候選、詢問、意願與推薦。
重啟後在工作台確認實際開始日及服務日期，再以重啟事件綁定的方案分段建立正式排班。重啟後的日期保存與正式安排分屬既有操作。
