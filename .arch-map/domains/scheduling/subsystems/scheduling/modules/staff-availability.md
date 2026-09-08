# Module: staff-availability

## Parent
- domain: `scheduling`
- subsystem: `scheduling`

## Responsibility
擁有月嫂長假、暫停接案與不可服務期間的 typed Query／Preview／Apply；不可服務紀錄本身不得被 presentation 推論為完整可派工結論。

## Implementation
- primary:
  - `domains/scheduling/staff_availability.py`
  - `subsystems/scheduling/staff_availability_workflow.py`
  - `infrastructure/mysql/staff_availability_repository.py`
  - `ui_react/src/pages/StaffPage.tsx`
- entrypoints:
  - `api/routes/staff_availability.py`
  - `api/schemas/staff_availability.py`
  - `ui_react/src/api/staff_availability/`

## Contracts
- `document/架構重整/01_規格基線/24_Staff_Matching_Preferences與不可服務期間正式規格.md`

## Verification
- layout_status: `custom_current`
- test_root: `ui_react/src/tests/domains/scheduling/subsystems/scheduling/modules/staff-availability/`
