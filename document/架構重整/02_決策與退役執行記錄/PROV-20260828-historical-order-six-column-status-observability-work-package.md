# Historical Orders 六欄狀態判定修正任務包

- `package_id`: `PKG-HISTORICAL-ORDER-SIX-COLUMN-STATUS`
- `package_status`: `completed`
- `specification`: `PROV-20260828-historical-order-six-column-status-observability-spec-gap.md`
- `owner`: Orders
- `scope`: `HOS-R1`～`HOS-R6`；`HOS-A1`～`HOS-A5`

## 1. Work units

1. `status-source-integrity`
   - 修正row fingerprint的status token，補`0`／blank collision regression。
   - 補六欄`0／1／2` parser與row conservation tests。
2. `typed-status-counts`
   - Subsystem Preview／receipt加入strict status counts與守恆。
   - API Pydantic、React Zod／adapter同步；Apply replay保留相同counts。
3. `operator-observation`
   - Data Import卡顯示取消0／完成1／洽談2／無法辨識數量。
   - 不新增可編輯status控制。
4. `verification`
   - Python Module→Subsystem→API focused tests。
   - React focused＋production build。
   - disposable／allowlisted `lu_test_*`三狀態Apply、receipt、event、replay readback。
   - true no-auth Browser Preview counts。

## 2. Write set

- `subsystems/orders/historical_order_workbook.py`
- `subsystems/orders/historical_order_workbook_import.py`
- `api/schemas/historical_order_adoption.py`
- `ui_react/src/api/orders/historical_order_workbook/`
- `ui_react/src/adapters/orders/historical_order_workbook_adapter.ts`
- `ui_react/src/pages/DataImportPage.tsx`
- 直接對應tests、正式規格與final receipt

DB schema、migration、HPROJ、RPRE、Matching及其他dirty paths不在write set。

## 3. Completion

只有`HOS-A1`～`HOS-A5`全部`passed`，並完成fresh獨立複驗、文件狀態同步及精確
commit／push後，本包才可標`completed`。

## 4. Current evidence（2026-08-28）

- Module／Subsystem／API focused：`25 passed`。
- React focused：`3 files／15 tests passed`；production build `passed`。
- 真 `lu_test_task96_rpre_browser_r3_20260828` MySQL：三列 `0／1／2` Apply、event、receipt、
  replay readback `passed`。
- no-auth Browser：四列 Preview與Apply均顯示 `0／1／2／invalid` 各 `1`；receipt readback
  為unmatched `4`且相符case Orders `0`，`passed`。
- fresh Luna/high 獨立複驗：source／Python／React／build `passed`；DB／Browser由主lane final receipt覆蓋。
