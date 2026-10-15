# Module: payroll-rebuild

## Parent
- domain: `payroll`
- subsystem: `payroll`

## Responsibility
依正式 Scheduling assignment 與 Orders terms 重建 Payroll projection；不得反向改寫來源排班或條款。
既有正式排班缺漏應付日時，以正式 actual_end_date、Client Finance 衍生客戶應付與補助資格套用既有付款日政策；保留已形成日期，建立 obligation 時保存 candidate 日期。

## Implementation
- primary:
  - `infrastructure/mysql/payroll_rebuild_repository.py`
  - `api/schemas/payroll_rebuild.py`

## Dependencies
- inbound: `scheduling/scheduling` — 正式 assignment 與服務時數。
- inbound: `orders/orders` — current order terms。
- inbound: `case-import/case-import/pairing-current-facts` — 服務前正式 BeClass 胎數 correction 的 effective rate override。

## Verification
- integration_root: `tests/domains/payroll/subsystems/payroll/integration/test_payroll_rebuild_workflow.py`

## Provenance
- Rebuild repository、HTTP schema 與既有整合測試 — `source_observed` — current repository。

## Change triggers
Reconcile when rebuild input facts、projection contract or verification root changes.
