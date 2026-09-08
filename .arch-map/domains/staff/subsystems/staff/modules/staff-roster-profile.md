# Module: staff-roster-profile

## Parent
- domain: `staff`
- subsystem: `staff`

## Responsibility
提供選定單一月嫂的 bounded、authenticated 個人、聯絡與銀行帳戶唯讀投影；已認證內部管理 UI 依正式規格取得完整身分證、緊急聯絡電話與全部銀行帳戶，且不輸出 IP、LINE User ID 或 raw source。

## Implementation
- primary:
  - `subsystems/staff/profile_query.py`
  - `infrastructure/mysql/staff_profile_query_repository.py`
  - `api/schemas/staff_profile.py`
  - `api/dependencies/staff_profile.py`
  - `api/routes/staff.py`
  - `ui_react/src/api/staff_profile/`
  - `ui_react/src/adapters/staff/staff_profile_adapter.ts`
  - `ui_react/src/pages/StaffPage.tsx`
- entrypoint: `GET /api/v1/staff/{staff_id}/profile`

## Contracts
- `document/架構重整/01_規格基線/24A_Staff_Roster_Case_Preference_Read_Model正式補充契約.md` §2.1

## Verification
- layout_status: `custom_current`
- test_root: `tests/domains/staff/subsystems/staff/modules/staff-roster-profile/`
- test_root: `ui_react/src/tests/domains/staff/subsystems/staff/modules/staff-roster-profile/`
- routing: `.arch-map/tests/domains/staff/subsystems/staff/modules/staff-roster-profile.md`

## Change triggers
Reconcile when Staff personal-profile or bank-account fields, complete-value boundary, authenticated entrypoint, UI consumer, or test roots change.
