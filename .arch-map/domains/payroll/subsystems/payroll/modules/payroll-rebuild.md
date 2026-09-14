# Module: payroll-rebuild

## Parent
- domain: `payroll`
- subsystem: `payroll`

## Responsibility
依正式 Scheduling assignment 與 Orders terms 重建 Payroll projection；不得反向改寫來源排班或條款。

## Implementation
- primary:
  - `infrastructure/mysql/payroll_rebuild_repository.py`
  - `api/schemas/payroll_rebuild.py`

## Dependencies
- inbound: `scheduling/scheduling` — 正式 assignment 與服務時數。
- inbound: `orders/orders` — current order terms。

## Verification
- integration_root: `tests/domains/payroll/subsystems/payroll/integration/test_payroll_rebuild_workflow.py`

## Provenance
- Rebuild repository、HTTP schema 與既有整合測試 — `source_observed` — current repository。

## Change triggers
Reconcile when rebuild input facts、projection contract or verification root changes.
