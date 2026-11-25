# Module: case-preference-manual

## Responsibility
Staff owner Query／Preview／Apply for the six canonical service-capability relations: regions, time slots, cooking skills, holiday availability, weekly rest, and baby types. 此 manual 入口不寫交通方式；既有交通選項由 [Staff Qualification](staff-qualification-master.md#contracts) 編輯。`source_not_ready` 只適用交通補充說明，不影響已保存選項的唯讀摘要。

## Implementation
- primary:
  - `domains/staff/case_preference_manual.py`
  - `subsystems/staff/case_preference_manual_workflow.py`
  - `infrastructure/mysql/staff_case_preference_manual_repository.py`
  - `subsystems/staff/case_preference_summary_query.py` — 六項 canonical relation 的唯讀摘要及明確未知投影。
  - `infrastructure/mysql/staff_case_preference_summary_query_repository.py`
  - `api/routes/staff_case_preference_manual.py`
  - `api/dependencies/staff_case_preference_manual.py`
  - `api/schemas/staff_case_preference_manual.py`
  - `ui_react/src/api/staff_case_preferences/staff_case_preferences_client.ts`
  - `ui_react/src/api/staff_case_preferences/staff_case_preferences_schemas.ts`
  - `ui_react/src/pages/StaffPage.tsx`

<a id="read-write-boundary"></a>

## Read／write boundary

- [需求書 #24A §5](../../../../../requirements/24A_Staff_Roster_Case_Preference_Read_Model正式補充契約.md#staff-preference-read-boundary)：名冊唯讀摘要使用 `/api/v1/staff/{staff_id}/case-preference-summary`，不把六個摘要母題送往 manual Apply；交通來源未就緒不是未填，也不借用料理備註。
- `/api/v1/staff/case-preference-manual` 由 Staff owner 管理既有關聯的操作與重驗。唯讀摘要契約不能代替 stale Apply 的前端驗證；下方 `staff_preferences_flow.test.tsx` 也不驗證摘要敏感欄位全部被排除。

## Invariants
- Query is read-only and returns a six-relation snapshot fingerprint.
- Preview is zero-write and binds before/after plus snapshot fingerprint.
- Apply locks the staff parent first, then relation tables in sorted table order; it fresh-reads and rejects stale snapshot or preview fingerprints.
- Apply uses command family staff_case_preference_manual/v1 and existing admin_command_receipts; numeric matching-profile QPA remains a separate owner.
- Apply 的 `reason` 為本次修改的選填備註，省略預設空字串；仍納入 command fingerprint 與 receipt，不開放 relation detail 編輯。
- Staff-owned RELATION_OPTIONS backs authenticated `/options`; the roster preference editor exposes only regions and weekly service. The other four imported relations and details are read-only under professional/service information. The existing six-relation QPA payload preserves those untouched facts; no storage or writer retirement.
- Existing Domain clock-window validation and canonical decoding remain available to their owner API; the roster no longer exposes clock, cooking, holiday or baby-type preference controls.

## Verification

Contract: `.arch-map/requirements/24_Staff_Matching_Preferences與不可服務期間正式規格.md` — PREF-21-01～05；兩項服務偏好與其餘匯入資料保留。
- layout_status: `custom_current`
- layout_basis: `.arch-map/tests/index.md` permits documented frontend test exceptions; the canonical Staff component oracle remains under `ui_react/src/tests/` and the owner Python oracles remain under the Staff module test root.
- test_root: `tests/domains/staff/subsystems/staff/modules/case-preference-manual/`
- test_root: `ui_react/src/tests/domains/staff/subsystems/staff/modules/case-preference-manual/`
- test_root: `ui_react/src/tests/staff_preferences_flow.test.tsx` — 既有模擬案例核對套用遇到舊快照時不顯示儲存成功，並提供重新查詢。
