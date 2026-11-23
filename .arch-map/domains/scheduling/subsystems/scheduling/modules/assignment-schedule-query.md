# Module: assignment-schedule-query

## Parent
- domain: `scheduling`
- subsystem: `scheduling`

## Responsibility
讀取正式指派所屬排班與案件排班衝突快照，以台灣日期判斷排班是否已過期。

## Implementation
- primary:
  - `subsystems/scheduling/assignment_schedule_query.py`
  - `subsystems/scheduling/multi_caregiver_schedule_query.py`
  - `infrastructure/mysql/multi_caregiver_schedule_query_repository.py`

## Contracts
- `.arch-map/requirements/02_Assignments_Scheduling_Domain.md`

## Verification
- layout_status: `custom_current`
- test_root: `tests/test_multi_caregiver_schedule_read.py` — 既有合成案例核對同一人有多筆指派時，只回傳指定指派的班次。
