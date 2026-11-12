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
    - 顯示 Case Import 原始服務方式；人工休假星期僅作當次 server 精算參數，即時更新建議。歷史重啟在同一表單選日期、分配月嫂並儲存班表，成功後回讀正式排班。
  - `ui_react/src/components/OrderServiceDateCalendar.tsx` — 案件內既有月曆，事前日期確認與完工後日期更正共用呈現；不擁有日期寫入規則。
  - `ui_react/src/components/CandidatePlannedServiceDates.tsx` — 初步候選每週說明的單一保存預計日期操作，重用 Service Dates flow；不串接 Actual Start，星期僅為當次試算。
  - `ui_react/src/components/HistoricalRestartArrangementPanel.tsx` — 在同一日期表單按既定月嫂選取服務日。
  - `ui_react/src/api/orders/order_mutation_client.ts`

## Dependencies

- outbound: `scheduling/waiting-deposit-lock` — Apply 先借用 occupancy mutex，保存日期及失效日期表後，在同一 outer UoW 自動保留已確認配對；只有條件齊備才鎖，衝突整筆 rollback。Query／Preview 不上鎖，不建立 assignment 或增加 Scheduling version。
- outbound: `case-import/hcm-current-workbook-import` — 原始服務方式只讀 Case Import immutable source snapshot，排班試算不改寫來源。
- outbound: `orders/actual-start` — 輸入改變時零寫入 Preview；最後確認才 Apply／readback，取得新 owner versions 後再 Preview／Apply 服務日期。正式或歷史重排候選須與核對集合一致。
- outbound: `orders/lifecycle-authoritative-facts` — 歷史正式安排以 typed lifecycle candidate 委派現有 Orders writer 保存事件、projection 與 outbox；尚未確認或未來開始日維持訂單成立。
- outbound: `scheduling/scheduling` — 歷史儲存班表 Apply 使用 canonical generation replacement writer 建立有效班表。
- outbound: `staff-payables/payroll` — 日期保存不寫 rate snapshot；後續真正建立安排時才沿 source frozen rate，或在歷史 pairing 無 source snapshot 時使用既有 case payroll policy。
- inbound: `orders/historical-precision-restart` — 空 effective generation 與重啟事件中的媒合方案、分段及歷史來源。舊版重啟事件沿用原歷史配對證據。

## Contracts
- `GET／POST /api/v1/orders/{case_no}/service-dates` — confirmed-date Query／Preview／Apply。
- `POST /api/v1/orders/{case_no}/service-dates/schedule/apply` — 歷史重啟一次儲存班表。Query 的 `historical_schedule_pending` 投影有效空重啟世代。
- `POST /api/v1/orders/{case_no}/service-dates/office-schedule/apply` — 一般案件在「設定服務日期」首次儲存正式班表，委派 `scheduling/service-start` 共用正式排班 writer。
- `POST /api/v1/orders/{case_no}/service-dates/arrangement/{preview,apply}` — 既有獨立正式安排 API。`arrangement_pending` 投影有效空重啟世代與已確認日期版本。
- `document/架構重整/01_規格基線/01A_訂單看板與事前日期及歷史採納規格.md` §3.2 — 日期確認與歷史重啟儲存班表。

## Verification
- layout_status: custom_current
- test_root: `ui_react/src/tests/domains/orders/subsystems/orders/modules/service-date-confirmation/`
- static:
  - `git diff --check`
- test_root: `tests/domains/orders/subsystems/orders/modules/service-date-confirmation/`
- test_root: `ui_react/src/tests/fixtures/orders/order_mutation_contract_fixtures.ts`
- higher_boundary:
  - `ui_react/src/tests/domains/orders/subsystems/orders/modules/service-date-confirmation/order_workbench_v2_service_dates.test.tsx`

## Provenance
- Orders owns confirmed-date Q/P/A — `architecture_declared` — `document/架構重整/01_規格基線/01A_訂單看板與事前日期及歷史採納規格.md` §3.2。
- Scheduling owns generation replacement and `staff_schedule` — `source_observed` — `infrastructure/mysql/scheduling_replacement_writer.py`。
- 歷史重啟班表 outer UoW — `source_observed` — `subsystems/orders/historical_restart_arrangement.py`。

## Change triggers
- Reconcile when confirmed-date API, restart-pending detection, historical assignment lineage, Scheduling replacement contract, server read-back, or canonical test roots change.
