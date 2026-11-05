# Module: current-service-projection

## Parent
- domain: `scheduling`
- subsystem: `scheduling`

## Responsibility
依 effective assignment 的正式服務日與 service-time terms 產生目前服務期間狀態；日期型歷史資料缺少完整時間時，以最後正式服務日的台北日終判定完成。

## Implementation
- primary:
  - `domains/scheduling/current_projection.py`
  - `infrastructure/mysql/scheduling_current_projection_repository.py`
  - `api/schemas/scheduling_current.py`

## Dependencies
- inbound: `orders/operational-stage-projection` — 讀取 service-period status 顯示於 Orders 七階段。

## Contracts
- `domains/orders/terms.py` — completion instant fallback。
- 同人同日可並列不同案件班次。只把正式工作班、等待訂金保留及不可服務的實際相交時段視為占用衝突；休息日及緩衝可與班次並列。

## Provenance
- Effective assignment current projection — `source_observed` — `domains/scheduling/current_projection.py`.

## Verification
- test_root: `tests/domains/scheduling/subsystems/scheduling/modules/current-service-projection/`
- `test_scheduling_current_projection.py` — buffer reminders, hard occupancy integrity and actual conflicts.

## Change triggers
Reconcile when service-period status, completion-instant handling, or effective assignment facts change.
