# Module: staff-roster-profile

## Parent
- domain: `staff`
- subsystem: `staff`

## Responsibility
提供選定單一月嫂的 bounded、authenticated 個人、聯絡與銀行帳戶投影及 owner-routed mutation；管理 UI 可讀完整身分證與緊急聯絡電話，但銀行帳號固定只讀末四碼，且不輸出 IP、LINE User ID 或 raw source。Staff Profile 與 Staff Bank Account 各自維持 version、Preview／Apply、稽核與 readback。

## Implementation
- primary:
  - `subsystems/staff/profile_query.py`
  - `domains/staff/profile.py`
  - `subsystems/staff/profile_workflow.py`
  - `infrastructure/mysql/staff_profile_mutation_repository.py`
  - `domains/staff/bank_account.py`
  - `subsystems/staff/bank_account_workflow.py`
  - `infrastructure/mysql/staff_bank_account_repository.py`
  - `infrastructure/mysql/staff_profile_query_repository.py`
  - `api/schemas/staff_profile.py`
  - `api/dependencies/staff_profile.py`
  - `api/dependencies/staff_registry_mutation.py`
  - `api/routes/staff.py`
  - `api/routes/staff_registry_mutation.py`
  - `api/schemas/staff_registry_mutation.py`
  - `ui_react/src/api/staff_profile/`
  - `ui_react/src/adapters/staff/staff_profile_adapter.ts`
  - `ui_react/src/pages/StaffPage.tsx`
  - `ui_react/src/api/staff_registry/`
  - `ui_react/src/components/StaffRegistryEditor.tsx`
- entrypoint: `GET /api/v1/staff/{staff_id}/profile`
- entrypoint: `POST /api/v1/staff/{staff_id}/profile/{preview|apply}`
- entrypoint: `POST /api/v1/staff/{staff_id}/bank-accounts/{preview|apply}`

## Contracts
- `document/架構重整/01_規格基線/24A_Staff_Roster_Case_Preference_Read_Model正式補充契約.md` §2.1
- `document/架構重整/01_規格基線/33_案件與月嫂整合名冊正式規格.md`

## Verification
- layout_status: `custom_current`
- test_root: `tests/domains/staff/subsystems/staff/modules/staff-roster-profile/`
- test_root: `ui_react/src/tests/domains/staff/subsystems/staff/modules/staff-roster-profile/`
- routing: `.arch-map/tests/domains/staff/subsystems/staff/modules/staff-roster-profile.md`

## Change triggers
Reconcile when Staff personal-profile or bank-account fields, complete-value boundary, authenticated entrypoint, UI consumer, or test roots change.
