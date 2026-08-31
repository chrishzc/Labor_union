# Module: current-service-projection

## Parent
- domain: `scheduling`
- subsystem: `scheduling`

## Responsibility
依 effective assignment 的正式服務日與 service-time terms 產生目前服務期間狀態；日期型歷史資料缺少完整時間時，以最後正式服務日的台北日終判定完成。

## Implementation
- primary:
  - `domains/scheduling/current_projection.py`

## Dependencies
- inbound: `orders/operational-stage-projection` — 讀取 service-period status 顯示於 Orders 七階段。

## Contracts
- `domains/orders/terms.py` — completion instant fallback。

## Provenance
- Effective assignment current projection — `source_observed` — `domains/scheduling/current_projection.py`.

## Change triggers
Reconcile when service-period status, completion-instant handling, or effective assignment facts change.
