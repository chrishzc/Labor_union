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
  - `ui_react/src/api/staff_availability/staff_availability_changes.ts` — 成功 Apply 收據後通知同頁及同源分頁的排班／媒合 current Query；只交換 staff identity，不持久化業務資料。
- entrypoints:
  - `api/dependencies/staff_availability.py`
  - `api/routes/staff_availability.py`
  - `api/schemas/staff_availability.py`
  - `ui_react/src/api/staff_availability/`

## Contracts
- `document/架構重整/01_規格基線/24_Staff_Matching_Preferences與不可服務期間正式規格.md`
- 同一 authenticated GET 省略日期時以 `after_id`／`limit`（最多 200）分頁讀取所有紀錄；既有 366 天日期查詢保留。抽屜自動載入完整紀錄，新增日期獨立；有限期／無期限暫停共用既有 writer，新增與恢復設定按操作展開。

## Verification
- layout_status: `custom_current`
- test_root: `ui_react/src/tests/domains/scheduling/subsystems/scheduling/modules/staff-availability/`
- test_root: `tests/domains/scheduling/subsystems/scheduling/modules/staff-availability/`
