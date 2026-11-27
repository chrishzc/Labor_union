# Module: current-service-projection

## Parent
- domain: `scheduling`
- subsystem: `scheduling`

## Responsibility
依 effective assignment 的正式服務日與 service-time terms 產生目前服務期間狀態；日期型歷史資料的服務時間三欄皆未設定時，以最後正式服務日的台北日終判定完成；只有部分缺漏時，回報時間驗證錯誤。

## Implementation
- primary:
  - `domains/scheduling/current_projection.py`
  - `infrastructure/mysql/scheduling_current_projection_repository.py`
  - `api/schemas/scheduling_current.py`

## Dependencies
- inbound: `orders/operational-stage-projection` — 讀取 service-period status 顯示於 Orders 七階段。

## Contracts
- 有效服務日讀回包含 nullable `service_hours_override` 與實際工時；明確覆寫的班次時段顯示「月嫂跟客戶自行協調」，NULL 沿原每日時數及時段。只讀取有效班次，停用的合併來源日不回到日曆。見 `02_Assignments_Scheduling_Domain.md#service-date-merge-split`。
- `domains/orders/terms.py` — completion instant fallback。
- 同人同日可並列不同案件班次。跨案衝突資格與歷史預定提醒沿 `02_Assignments_Scheduling_Domain.md` §3.1；Query 保留各來源案號、服務時段與實際開始日供 presentation 使用，休息日及緩衝可與班次並列。

- 生效指派由 `scheduling_current_projection_repository.py` 依目前 effective generation 與有效班次讀回；替換後的舊世代不參與現在投影。待訂金鎖及歷史預定／唯讀歷史可提供占用或提醒訊號，不等於有效班次；不能從日曆有一列推定已出勤、已完成或可發薪。出勤／薪資須讀各自的正式資料。

## Provenance
- Effective assignment current projection — `source_observed` — `domains/scheduling/current_projection.py`.

## Verification
- test_root: `tests/domains/scheduling/subsystems/scheduling/modules/current-service-projection/`
- `test_scheduling_current_projection.py` — buffer reminders, hard occupancy integrity and actual conflicts.

- 情境對照：同日新世代生效且舊世代已取代時，現行投影只取新世代有效班次。只有待訂金鎖或唯讀歷史預定時，即使可見占用資訊，也不得將該資料當成現行班次或薪資證據。

## Change triggers
Reconcile when service-period status, completion-instant handling, or effective assignment facts change.
