# Module: staff-qualification-master

## Parent
- domain: `staff`
- subsystem: `staff`

## Responsibility
提供單一 Staff 的 bounded、authenticated qualification master 唯讀投影，包含 Staff-owned 一般資格證明與既有能力、有效性及不可服務狀態 sections；不建立資格 mutation 或重算 Scheduling root facts。

## Implementation
- primary:
  - `subsystems/staff/qualification_master_query.py`
  - `infrastructure/mysql/staff_qualification_master_repository.py`
  - `api/routes/staff_qualification_master.py`
  - `api/schemas/staff_qualification_master.py`
  - `api/dependencies/staff_qualification_master.py`
  - `ui_react/src/api/staff/qualification_master_client.ts`
  - `ui_react/src/adapters/staff/qualification_master_adapter.ts`
  - `ui_react/src/pages/StaffPage.tsx`

## Contracts
- `document/架構重整/01_規格基線/24A_Staff_Roster_Case_Preference_Read_Model正式補充契約.md` §2.1

## Verification
- layout_status: `custom_current`
- test_root: `tests/test_staff_qualification_master.py`
- routing: `.arch-map/tests/domains/staff/subsystems/staff/modules/staff-qualification-master.md`

## Change triggers
Reconcile when qualification/certification sources, bounded sections, Staff roster consumer or focused verification paths change.
