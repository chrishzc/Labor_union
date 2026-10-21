module: staff-availability
parent_subsystem: scheduling
architecture: ../../../../../../../domains/scheduling/subsystems/scheduling/modules/staff-availability.md
layout_status: custom_current
test_root: ui_react/src/tests/domains/scheduling/subsystems/scheduling/modules/staff-availability/
test_root: tests/domains/scheduling/subsystems/scheduling/modules/staff-availability/

# Owned verification
- `staff_availability_changes.test.ts` — 四種 Apply 成功才通知、失敗不通知、跨分頁訊息及訂閱釋放。
- `staff_availability_flow.test.tsx` — StaffPage 的不可服務期間查詢、Preview／Apply、readback 與不過度推論空清單。
- `staff_availability_records_client.test.ts` — 分頁讀完全部紀錄、同人限制與游標前進。
- `test_staff_availability_records.py` — 全紀錄分頁、舊日期查詢與只讀 repository 邊界。
