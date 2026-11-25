# Module: service-date-confirmation

## Parent
- domain: `orders`
- subsystem: `orders`

## Responsibility
以 Query／Preview／fresh-lock Apply 保存一般案件的事前服務日期。歷史 Precision Restart 工作台共讀目前重啟綁定的既定人員，並以一次儲存班表提交實際開始日、確認日期與正式排班。資料分別由既有 Orders、Scheduling、Payroll writer 保存。

## Implementation
- primary:
  - `domains/orders/service_date_confirmation.py`
  - `subsystems/orders/service_date_confirmation_workflow.py`
  - `subsystems/orders/historical_restart_arrangement.py` — 一次儲存班表的 outer UoW，協調既有 Actual Start、確認日期、Scheduling、Payroll 與 Orders lifecycle writer，另承接既有獨立正式安排 API。
  - `domains/orders/lifecycle.py` — 重啟正式安排沿用 Orders 服務中判定，不補造訂金或契約事實。
  - `subsystems/orders/calendar_detail_query.py`
  - `infrastructure/mysql/order_calendar_detail_query_repository.py` — 唯讀投影 current 服務方式與 immutable Case Import 原始文字，供當次人工排休試算對照。
  - `infrastructure/mysql/service_date_confirmation_repository.py`
  - `api/schemas/service_date_confirmation.py`
- entrypoints:
  - `api/routes/service_date_confirmation.py`
  - `api/dependencies/service_date_confirmation.py`
  - `api/schemas/order_calendar_detail.py`
  - `ui_react/src/adapters/orders/order_mutation_adapter.ts`
  - `ui_react/src/adapters/orders/service_date_start_flow.ts` — 將未保存開始日的建議範圍投影到 UI；人工確認後串接既有 Actual Start 與服務日期 writer，保留第一步結果及第二步恢復狀態。
  - `ui_react/src/components/OrderServiceDatesPanel.tsx`
  - `ui_react/src/components/OrderServiceDateAdjustment.tsx` — 純日期合併、分裂、精確復原與回執後讀回；不編輯帳務。
    - 顯示 Case Import 原始服務方式；人工休假星期僅作當次 server 精算參數，即時更新建議。歷史重啟在同一表單選日期、分配月嫂並儲存班表，成功後回讀正式排班。
  - `ui_react/src/components/OrderServiceDateAdjustment.css`
  - `ui_react/src/components/OrderServiceDateCalendar.tsx` — 案件內既有月曆，事前日期確認與完工後日期更正共用呈現；不擁有日期寫入規則。
  - `ui_react/src/components/OrderCaregiverScheduleCalendars.tsx` — 首排與正式排班調整共用的逐人月曆區塊，分配結果委派各自的既有寫入流程。
  - `ui_react/src/components/CandidatePlannedServiceDates.tsx` — 初步候選每週說明的單一保存預計日期操作，重用 Service Dates flow；不串接 Actual Start，星期僅為當次試算。
  - `ui_react/src/components/HistoricalRestartArrangementPanel.tsx` — 歷史重啟及一般首排的基本「月嫂分配」版型。
  - `ui_react/src/api/orders/order_mutation_client.ts`

## Dependencies

- outbound: `scheduling/staff-monthly-calendar` — 訂單工作台重用月份格線與檔期標示，取各月嫂的現行排班投影供選日參考。
- outbound: `scheduling/waiting-deposit-lock` — Apply 先借用 occupancy mutex，保存日期及失效日期表後，在同一 outer UoW 自動保留已確認配對；只有條件齊備才鎖，衝突整筆 rollback。Query／Preview 不上鎖，不建立 assignment 或增加 Scheduling version。
- outbound: `case-import/hcm-current-workbook-import` — 原始服務方式只讀 Case Import immutable source snapshot，排班試算不改寫來源。
- outbound: `orders/actual-start` — 輸入改變時零寫入 Preview；一般流程最後確認才 Apply／readback，取得新 owner versions 後再 Preview／Apply 服務日期。已有合併／分裂結果的開始日變更，使用 Actual Start 單一原子取消重排及正常日期保存，前端不再追加第二筆服務日期 Apply。正式或歷史重排候選須與核對集合一致。
- outbound: `orders/lifecycle-authoritative-facts` — 歷史正式安排以 typed lifecycle candidate 委派現有 Orders writer 保存事件、projection 與 outbox；尚未確認或未來開始日維持訂單成立。
- outbound: `scheduling/scheduling` — 歷史儲存班表 Apply 使用 canonical generation replacement writer 建立有效班表。
- outbound: `staff-payables/payroll` — 日期保存不寫 rate snapshot；後續真正建立安排時才沿 source frozen rate，或在歷史 pairing 無 source snapshot 時使用既有 case payroll policy。
- outbound: `contract-signing/external-signing-presentation` — 一般首排借用 `ArchivedCommitmentPort` 以現行直接歸檔、已接受方案及確認日期投影缺少的精確承諾；Apply 經同一 outer UoW 的公開 borrowed writer 建立，Preview 不寫入，既有承諾不覆寫。
- inbound: `orders/historical-precision-restart` — 空 effective generation 與重啟事件中的媒合方案、分段及歷史來源。舊版重啟事件沿用原歷史配對證據。

## Contracts
### 合併、分裂與精確復原 ^service-date-adjustment

- `source_observed`：依 [Scheduling §3.4.2](../../../../../requirements/02_Assignments_Scheduling_Domain.md#service-date-merge-split) 與 [Admin UI §2.4](../../../../../requirements/31_MultiCaregiver_Admin_UI正式規格.md#service-date-merge-split-ui) 實作；執行結果另見本次功能驗證紀錄。
- 規則型別與純轉換放在 `domains/scheduling/service_date_adjustment.py`；`subsystems/scheduling/service_date_adjustment.py` 協調 Query／Preview／Apply，`infrastructure/mysql/service_date_adjustment_repository.py` 實作保存埠。既有服務日期 route／dependency／schema 與 `OrderServiceDatesPanel.tsx` 接入同一命令，不經會更正金額的服務歸屬流程。
- 事前日期仍由 Orders immutable confirmed version 保存。逐日記錄 nullable `staff_id` 及 `service_hours_override`，正式首排完整承接；沒有正式 generation 時也可合併、分裂及復原，不先製造正式指派。
- `service_date_adjustment_receipts` 是本功能的不可變操作紀錄，保存精確 request identity、來源／結果日班及被復原操作，供事前與正式階段共同辨認配對。既有 Scheduling receipt 要求非空 rebuild／generation，不能用來假裝保存沒有世代重建的異動。復原只還原該次結果的來源原值，NULL 亦精確恢復，不回退整案後續變更。
- 實作沿用下方 test roots；純轉換測試為 `tests/domains/scheduling/subsystems/scheduling/modules/schedule-generation/test_service_date_adjustment.py`，來源選取及復原互動為同一前端 test root 的 `service_date_adjustment_selection.test.tsx`。

- `GET／POST /api/v1/orders/{case_no}/service-dates` — confirmed-date Query／Preview／Apply。
- `POST /api/v1/orders/{case_no}/service-dates/schedule/apply` — 歷史重啟一次儲存班表。Query 的 `historical_schedule_pending` 投影有效空重啟世代。
- `POST /api/v1/orders/{case_no}/service-dates/office-schedule/apply` — 一般案件從「多月嫂排班」直接儲存首份正式班表。允許交錯日期，委派 `scheduling/service-start` 共用正式排班 writer。既有 `office-schedule/preview` API 可獨立查閱，不是該畫面的儲存前置。
- `POST /api/v1/orders/{case_no}/service-dates/arrangement/{preview,apply}` — 既有獨立正式安排 API。`arrangement_pending` 投影有效空重啟世代與已確認日期版本。
- `.arch-map/requirements/01A_訂單看板與事前日期及歷史採納規格.md` §3.2 — 日期確認與歷史重啟儲存班表。

## Verification
- layout_status: custom_current
- test_root: `ui_react/src/tests/domains/orders/subsystems/orders/modules/service-date-confirmation/` — 既有模擬案例核對正式讀回案件不符時，不試算、不預覽，也不套用。
- static:
  - `git diff --check`
- test_root: `tests/domains/orders/subsystems/orders/modules/service-date-confirmation/`
- test_root: `ui_react/src/tests/fixtures/orders/order_mutation_contract_fixtures.ts`
- higher_boundary:
  - `ui_react/src/tests/domains/orders/subsystems/orders/modules/service-date-confirmation/order_workbench_v2_service_dates.test.tsx`

## Provenance
- Orders owns confirmed-date Q/P/A — `architecture_declared` — `.arch-map/requirements/01A_訂單看板與事前日期及歷史採納規格.md` §3.2。
- Scheduling owns generation replacement and `staff_schedule` — `source_observed` — `infrastructure/mysql/scheduling_replacement_writer.py`。
- 歷史重啟班表 outer UoW — `source_observed` — `subsystems/orders/historical_restart_arrangement.py`。

## Change triggers
- Reconcile when confirmed-date API, restart-pending detection, historical assignment lineage, Scheduling replacement contract, server read-back, or canonical test roots change.

## 國定假日計價接線 ^service-date-confirmation-holiday-pricing

```yaml archmap-impact
- kind: implements_requirement
  source: service-date-confirmation-holiday-pricing
  target: ".arch-map/requirements/02_Assignments_Scheduling_Domain.md#^service-date-merge-split"
```
- 假日計價接線設計，待實作驗證。`service_date_adjustment_repository.py` 提供 current effective generation 的有效服務日及 `service_hours_override`，供兩方帳務 owner 取得實際日期與當日時數；原財務日期仍供既有非假日計算、受款人及付款日政策使用。日期調整沿同一 caller UoW 接續計價，不另建帳務 writer。
