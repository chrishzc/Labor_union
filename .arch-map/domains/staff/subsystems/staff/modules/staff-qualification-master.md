# Module: staff-qualification-master

## Parent
- domain: `staff`
- subsystem: `staff`

## Responsibility
詳情以同頁分區呈現完整資格主檔及下方接案狀態管理；保留個資、銀行、履歷 PDF、接案條件與人事／不可服務期間功能，移除接案偏好摘要及其頁面查詢。不可服務期間成功 owner 回讀後重新查詢資格摘要，不推算 root facts。
提供單一 Staff 的 bounded、authenticated qualification master 投影，並擁有既有技能、按摩證書、一般證照、care_babies 及交通值的 manual Query／Preview／Apply。醫療、有效期與 Scheduling 狀態維持唯讀，不重算外部 root facts。

同一 MySQL read adapter 提供名冊頁選取 IDs 的批次 `fetch_service_profiles`：重用 typed service profile、canonical 六項能力 relation 與唯讀交通方式，另攜帶下廚 detail；不讀每人完整 qualification／不可服務期間、不推定交通其他說明、不新增 writer。

## Implementation
- primary:
  - `domains/staff/qualification_editing.py`
  - `subsystems/staff/qualification_editing_workflow.py`
  - `infrastructure/mysql/staff_qualification_editing_repository.py`
  - `api/routes/staff_qualification_editing.py`
  - `api/schemas/staff_qualification_editing.py`
  - `ui_react/src/api/staff/qualification_editing_client.ts`
  - `ui_react/src/components/StaffQualificationEditor.tsx`
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
- `document/架構重整/01_規格基線/33_案件與月嫂整合名冊正式規格.md` §4 完整資格主檔直接編輯

## Verification
- layout_status: `custom_current`
- test_root: `tests/test_staff_qualification_master.py`
- test_root: `ui_react/src/tests/domains/staff/subsystems/staff/modules/staff-qualification-master/`
- routing: `.arch-map/tests/domains/staff/subsystems/staff/modules/staff-qualification-master.md`

## Change triggers
Reconcile when qualification/certification sources, bounded sections, Staff roster consumer or focused verification paths change.
