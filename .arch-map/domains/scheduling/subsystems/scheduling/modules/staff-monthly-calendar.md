# Module: staff-monthly-calendar

## Parent
- domain: `scheduling`
- subsystem: `scheduling`

## Responsibility
提供月嫂月份檔期的 bounded typed Query 與前端月曆投影；正式排班／占用維持主要呈現，completed legacy assignment 只形成不可操作的歷史區段。

## Implementation
- primary:
  - `subsystems/scheduling/staff_monthly_calendar_query.py`
  - `api/routes/staff_monthly_schedule.py`
  - `api/schemas/staff_monthly_schedule.py`
  - `ui_react/src/api/scheduling/staff_monthly_schedule_client.ts`
  - `ui_react/src/adapters/scheduling/historical_assignment_overlay_adapter.ts`
  - `line/static/service-date-calendar.js`、`line/static/service-date-calendar.d.ts`、`line/static/service-date-calendar.css` — 訂單工作台與合意延期 LIFF 共用的月份格線、檔期標示投影及樣式。
- entrypoints:
  - `ui_react/src/pages/SchedulingPage.tsx`
  - `ui_react/src/pages/SchedulingPage.css`

## Dependencies
- outbound: `scheduling/staff-availability` — React 訂閱成功異動通知，只失效受影響日曆列並重查當前案件資格；中斷中的批次列不得留下已載入快取。
- outbound: `scheduling/current-service-projection` — 正式 assignment 與 daily schedule 是 current service 的主要投影。
- outbound: `orders/operational-stage-projection` — 排查案件選項依十三核心階段的正式 current ordinal 限定在第 8「訂金」之前。
- outbound: `orders/historical-precision-restart` — 重啟使舊歷史指派區段失效。歷史未服務案的唯讀預定沿目前有效的重啟世代保留，待正式班表接手。
- inbound: Scheduling UI — 消費 Scheduling 的兩個 typed 查詢及必要的 Orders 案件明細；不直接讀 persistence facts。
- inbound: `orders/service-date-confirmation`、`scheduling/leave-substitution` — 共用月曆呈現，各自透過既有查詢取得檔期資料。

## Contracts
- `architecture_declared`：合併、分裂及復原的日班呈現依 [Admin UI §2.4](../../../../../requirements/31_MultiCaregiver_Admin_UI正式規格.md#service-date-merge-split-ui)。只讀目前生效的逐日班次；逐日時數有覆寫值時顯示當日時數及協調文字，不以 Orders 時段推造起訖。復原 NULL 後恢復正常呈現。施工完成後核對 inactive 來源日班不重複出現。

- 名冊先讀完 bounded Staff summary cursor 全部頁面，再依 Staff-owned `union_no` 自然升冪排列，未設定排最後；日曆、排查與代班選單使用「公會編號 姓名」，搜尋比對公會編號，不以內部 STF 代碼代替。
- 排班主頁的可選名單使用 `/staff/summaries?lifecycle_state=active`，初頁與後續 cursor 均保留篩選。歷史案件、completed assignment 與單人月份 Query 保持唯讀可查；全域歷史人員標籤仍從未篩選摘要解析，不刪除歷史 root。
- `GET /api/v1/staff/{staff_id}/monthly-schedule` — `api/routes/staff_monthly_schedule.py` 與 `api/schemas/staff_monthly_schedule.py`。
- 多筆逐日班次及可追溯的起訖共供工會甘特與 `line/static/staff_schedule.html`；跨日續班沿用原服務日。LINE 用同案、指派及服務日定位既有請假表單。
- `historical_assignment` — completed legacy assignment 的唯讀 provenance projection；不宣稱 daily schedule ownership。
- `historical_reservation` — 工會月曆以共用檔期資料呈現歷史未服務案的唯讀預定區段，涵蓋重啟後待排班期間。
- `SchedulingPage` 對日曆、案件選項及資格投影分別最多同時查詢 3 位人員；日曆每列完成即顯示，兩個 projection 同時接收成功／失敗，避免無上限 fan-out 及未處理的 rejected Promise，不自動重送失敗列。

### 年度時間軸的唯讀邊界
- 載入由可視月份驅動，快取鍵為人員、年、月；切月不寫入。每個人員月份讀取 [正式班次與占用](current-service-projection.md)（`GET /api/v1/scheduling/staff/{staff_id}/current-calendar`，`range_start`／`range_end` 含首末日）及補充檔期與歷史（`GET /api/v1/staff/{staff_id}/monthly-schedule`，`year`／`month`），沿用最多三列並行。合法空月仍依正式契約回傳完整日期範圍，不以缺頁／失敗代替空月。
- 補充資料只有歷史指派或歷史保留含非空案號時，才按案號去重，查 `GET /api/v1/orders/{case_no}` 取得唯讀整案日期。歷史指派依各端實際日期優先，缺值才用同端預定日期；歷史保留用預定日期。起訖缺失或逆序時，只不顯示整案期間，月內資料仍可保留；讀取或解碼失敗才是可重試的補充支線錯誤。
- 兩支線均有結果（成功或失敗）後提交當月列，區分未查、載入、完整空結果、失敗與部分失敗。預設「全部」可保留成功支線的資料；歷史不能替代正式狀態來通過其他篩選。重試同人員同月份的失敗支線，補充月資料與其適用的 Orders 明細可能一併重讀；已成功且仍有效的正式支線不要求重讀。回到仍有效月份不重查，跨年與中斷請求不得寫回其他月份。
- 合併逐筆比較來源類型、指派／鎖／不可服務識別、服務日及時段。同來源同班去重，不同案件及唯讀歷史可同日並列。跨午夜的續班不增加正式服務事實。歷史整案起訖與重啟抑制仍由原查詢與 Orders 日期投影負責，不形成出勤或計薪來源。
- 成功異動依既有通知失效受影響人員的已快取月份；只有人員識別而沒有日期的通知，以該人員所有已快取月份為保守失效範圍，不清其他人。返回畫面的重新查詢讀回有效來源；不得依訂單狀態一律隱藏歷史。
- 正式日班及正式緩衝讀取須核對有效 generation 與 aggregate current pointer；取消／替換來源退出目前投影。completed 歷史指派沿既有獨立分支及重啟規則，後端逐月契約維持不變。

#### 可視月份與部分失敗驗收
- **正例**：同一月嫂八月與九月各有不同正式班，八月另有歷史指派。只水平滑動，不使用月份選單，即看到對應月份的班及歷史；回到仍有效的八月不重查。兩路皆成功且確定無班，才是完整空結果。
- **反例**：在「全部」下，八月正式成功、歷史案整案日期請求失敗。保留正式和已讀到的月內歷史，標明整案日期不可用且可重試；重試不必重讀有效的正式結果。若明細成功讀回但日期缺值，日期不可用仍成立，不能把缺值標為網路錯誤。反向讓正式查詢失敗但補充成功，仍可見歷史且不可視為完整空結果。

## Verification
- test_root: `tests/domains/scheduling/subsystems/scheduling/modules/staff-monthly-calendar/`
- layout_status: `custom_current`
- test_root: `ui_react/src/tests/staff_monthly_schedule_client.test.ts` — 既有模擬案例拒絕將歷史列標為正式工作日；同一歷史指派在缺日期處不合併區段。
- test_root: `ui_react/src/tests/scheduling_current_page.test.tsx`
- higher_boundary:
  - `tests/domains/scheduling/subsystems/scheduling/integration/`

## Provenance
- Scheduling ownership 與 typed API boundary — `architecture_declared` — repository `AGENTS.md` 與 Scheduling subsystem parent map。
- backend/API/frontend implementation paths — `source_observed` — current query、route、schema、client、adapter 與 page imports。
- 排查案件的 pre-deposit 邊界 — `source_observed` — `SchedulingPage.tsx` 讀取完整 Orders core-stage timeline，且只保留 `current_core_stage_ordinal < 8`。
- canonical Python test root — `architecture_declared` — Scheduling owner hierarchy 與 Arch Map test placement contract。
- React test paths — `source_observed` — current project colocated React test harness layout。

## Change triggers
Reconcile when monthly endpoint schema、calendar projection precedence、historical restart suppression、implementation paths或 focused test roots 改變。
