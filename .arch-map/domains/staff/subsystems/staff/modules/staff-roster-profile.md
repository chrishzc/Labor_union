# Module: staff-roster-profile

## Parent
- domain: `staff`
- subsystem: `staff`

## Responsibility
提供選定單一月嫂的 bounded、authenticated 個人、聯絡與銀行帳戶投影及 owner-routed mutation；管理 UI 可讀完整身分證與緊急聯絡電話，但銀行帳號固定只讀末四碼，且不輸出 IP、LINE User ID 或 raw source。Staff Profile 與 Staff Bank Account 各自維持 version、Preview／Apply、稽核與 readback。

## Implementation
- primary:
  - `subsystems/staff/summary_query.py`
  - `infrastructure/mysql/staff_summary_query_repository.py`
  - `api/schemas/staff_summary.py`
  - `ui_react/src/api/staff_directory/`
  - `ui_react/src/adapters/staff/staff_directory_adapter.ts`
  - `ui_react/src/components/StaffIdentityProvider.tsx`
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
- entrypoint: `GET /api/v1/staff/roster` — 與單人 Profile 相同 reader；bounded cursor 批次個資／聯絡／銀行與服務接案主檔，一人一列，最多 200 人；借用 Qualification-owned 七 relation 與 care_babies 批次投影，查詢數不隨人數增加，保留 `/summaries` selector。
- entrypoint: `POST /api/v1/staff/{staff_id}/profile/{preview|apply}`
- entrypoint: `POST /api/v1/staff/{staff_id}/bank-accounts/{preview|apply}`

## Contracts
- 名冊先循既有 bounded Staff id cursor 讀取全部頁面，再以公會編號自然升冪呈現；未設定排最後、相同比較以 id 穩定排序。`staff_directory_adapter.ts` 共用排序與「公會編號 姓名」顯示，排班與候選呈現借用此規則，不改 Staff identity 或 writer。
- `StaffIdentityProvider` 在 authenticated 管理頁共用 bounded 摘要全頁讀取，只保留 id／姓名／公會編號，以 canonical id 提供標籤與選單排序；離頁中止讀取，錯誤可重讀，不以姓名比對或保存跨 session 快取。案件、財務、歷史帳務與 LINE 管理借用此唯讀 presentation，不改人員或段落命令。
- 履歷維持既有 staging／Preview／Apply／版本及 authenticated download。`StaffRegistryEditor` 同頁提供所選 PDF 與目前履歷 Blob 預覽、下載及獨立 loading／error／empty 狀態；`staff_resume_client.ts` 讀 controlled-files runtime settings，檔案操作使用專用 timeout，離頁釋放預覽 URL。
- 規格 33 §3.2：Staff Profile 擁有 nullable `union_no`，以完整 binary 字串唯一性提供人工公會編號；不取代 Staff id／cursor。主頁使用表格列選取與公會編號搜尋，成功 Profile readback 同步清單。重複與 MySQL 編號更新死結分別為 typed `staff_union_no_collision`／`staff_profile_concurrent_conflict`，沿用既有 version／event／receipt／UoW。
- `document/架構重整/01_規格基線/24A_Staff_Roster_Case_Preference_Read_Model正式補充契約.md` §2.1
- `document/架構重整/01_規格基線/33_案件與月嫂整合名冊正式規格.md`
- Profile 修改的 `reason` 為選填備註：省略預設空字串、保留 actor／before／after／receipt／idempotency；Bank Account 仍依既有必填原因契約。

## Verification
- layout_status: `custom_current`
- test_root: `tests/domains/staff/subsystems/staff/modules/staff-roster-profile/`
- test_root: `ui_react/src/tests/domains/staff/subsystems/staff/modules/staff-roster-profile/`
- routing: `.arch-map/tests/domains/staff/subsystems/staff/modules/staff-roster-profile.md`
- integration_root: `tests/test_staff_summary_query.py` — 既有 bounded summary projection 契約。
- integration_root: `tests/test_staff_summary_routes.py` — 既有 authenticated cursor route 契約。
- integration_root: `ui_react/src/tests/staff_directory_adapter.test.ts`
- integration_root: `ui_react/src/tests/staff_directory_client.test.ts`

## Change triggers
Reconcile when Staff personal-profile or bank-account fields, complete-value boundary, authenticated entrypoint, UI consumer, or test roots change.
