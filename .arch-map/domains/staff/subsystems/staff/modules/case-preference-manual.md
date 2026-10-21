# Module: case-preference-manual

## Responsibility
Staff owner Query／Preview／Apply for the six canonical service-capability relations: regions, time slots, cooking skills, holiday availability, weekly rest, and baby types. Transportation remains the existing read-only source_not_ready fact.

## Implementation
- primary:
  - `domains/staff/case_preference_manual.py`
  - `subsystems/staff/case_preference_manual_workflow.py`
  - `infrastructure/mysql/staff_case_preference_manual_repository.py`
  - `api/routes/staff_case_preference_manual.py`
  - `api/dependencies/staff_case_preference_manual.py`
  - `api/schemas/staff_case_preference_manual.py`
  - `ui_react/src/api/staff_case_preferences/staff_case_preferences_client.ts`
  - `ui_react/src/api/staff_case_preferences/staff_case_preferences_schemas.ts`
  - `ui_react/src/pages/StaffPage.tsx`

## Invariants
- Query is read-only and returns a six-relation snapshot fingerprint.
- Preview is zero-write and binds before/after plus snapshot fingerprint.
- Apply locks the staff parent first, then relation tables in sorted table order; it fresh-reads and rejects stale snapshot or preview fingerprints.
- Apply uses command family staff_case_preference_manual/v1 and existing admin_command_receipts; numeric matching-profile QPA remains a separate owner.
- Apply 的 `reason` 為本次修改的選填備註，省略預設空字串；仍納入 command fingerprint 與 receipt，不開放 relation detail 編輯。
- Staff-owned RELATION_OPTIONS backs authenticated `/options`; the roster preference editor exposes only regions and weekly service. The other four imported relations and details are read-only under professional/service information. The existing six-relation QPA payload preserves those untouched facts; no storage or writer retirement.
- Existing Domain clock-window validation and canonical decoding remain available to their owner API; the roster no longer exposes clock, cooking, holiday or baby-type preference controls.

## Verification

Contract: `document/架構重整/01_規格基線/24_Staff_Matching_Preferences與不可服務期間正式規格.md` — PREF-21-01～05；兩項服務偏好與其餘匯入資料保留。
- layout_status: `custom_current`
- layout_basis: `.arch-map/tests/index.md` permits documented frontend test exceptions; the canonical Staff component oracle remains under `ui_react/src/tests/` and the owner Python oracles remain under the Staff module test root.
- test_root: `tests/domains/staff/subsystems/staff/modules/case-preference-manual/`
- test_root: `ui_react/src/tests/domains/staff/subsystems/staff/modules/case-preference-manual/`
- test_root: `ui_react/src/tests/staff_preferences_flow.test.tsx`
