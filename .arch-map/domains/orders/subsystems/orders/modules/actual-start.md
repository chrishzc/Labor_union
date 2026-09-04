# Module: actual-start

## Parent
- domain: `orders`
- subsystem: `orders`

## Responsibility
以既有正式服務日重建 Actual Start、有效 Scheduling generation 與下游未結清 Client Finance／Payroll projection；歷史來源只能經此 canonical writer 套用 actual-start，不得直接建立付款或通知事實。

## Implementation
- primary:
  - `domains/orders/actual_start.py`
  - `domains/orders/terms.py`
  - `subsystems/orders/actual_start_workflow.py`
  - `infrastructure/mysql/order_actual_start_repository.py`
  - `ui_react/src/api/orders/order_actual_start_client.ts`

## Dependencies
- outbound: `scheduling/scheduling` — replacement generation 擁有正式服務日期與 assignment lineage。
- outbound: `client-finance/client-finance` — 重算未結清的客戶帳務日期與 projection。
- outbound: `payroll/payroll` — 重算 assignment-owned payroll obligation。
- inbound: `orders/historical-adoption` — 已付訂金且來源開始日異於 HCM 預定開始日的 historical actual-start assertion 經 typed delegation 進入。

## Contracts
- `document/架構重整/01_規格基線/01_Orders_Domain.md` — Actual Start、歷史來源與 completion instant 語意。
- `subsystems/orders/actual_start_workflow.py` — Preview／Apply 與單一 outer UoW contract。

## Verification
- layout_status: custom_current
- test_root: `ui_react/src/tests/domains/orders/subsystems/orders/modules/actual-start/`
- higher_boundary: `tests/domains/orders/subsystems/orders/integration/test_order_actual_start_workflow.py`

## Provenance
- Actual Start writer and cross-owner persistence — `source_observed` — `subsystems/orders/actual_start_workflow.py`.
- Historical delegation rule — `architecture_declared` — `document/架構重整/01_規格基線/01_Orders_Domain.md`.

## Change triggers
Reconcile when Actual Start official-date calculation, cross-owner projection, lifecycle completion instant, or historical delegation changes.
