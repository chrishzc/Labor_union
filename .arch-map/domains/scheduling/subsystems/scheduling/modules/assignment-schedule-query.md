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
- `document/架構重整/01_規格基線/02_Assignments_Scheduling_Domain.md`

## Verification
- layout_status: `custom_current`
- test_root: `tests/test_multi_caregiver_schedule_read.py`
