# Module: service-date-confirmation

## Parent
- domain: `orders`
- subsystem: `orders`

## Responsibility
以 Query／Preview／fresh-lock Apply 保存人工確認的事前服務日期。一般案件與完成 Precision Restart、current Scheduling generation 仍是空 tombstone 的歷史案件都只建立 confirmed-date root；歷史 Query 仍回傳 pairing evidence 中的既定服務人員，後續由明確的正式安排 Preview／Apply 建立 canonical schedule。日期保存本身不得建立 assignment、staff schedule、buffer、rate snapshot 或增加 Scheduling version。

## Implementation
- primary:
  - `domains/orders/service_date_confirmation.py`
  - `subsystems/orders/service_date_confirmation_workflow.py`
  - `subsystems/orders/historical_restart_arrangement.py` — confirmed dates 後獨立的正式安排 Preview／Apply coordinator。
  - `subsystems/orders/calendar_detail_query.py`
  - `infrastructure/mysql/service_date_confirmation_repository.py`
  - `api/schemas/service_date_confirmation.py`
- entrypoints:
  - `api/routes/service_date_confirmation.py`
  - `api/dependencies/service_date_confirmation.py`
  - `api/schemas/order_calendar_detail.py`
  - `ui_react/src/adapters/orders/order_mutation_adapter.ts`
  - `ui_react/src/adapters/orders/service_date_start_flow.ts` — 將未保存開始日的建議範圍投影到 UI；人工確認後串接既有 Actual Start 與服務日期 writer，保留第一步結果及第二步恢復狀態。
  - `ui_react/src/components/OrderServiceDatesPanel.tsx`
  - `ui_react/src/components/HistoricalRestartArrangementPanel.tsx`
  - `ui_react/src/api/orders/order_mutation_client.ts`

## Dependencies
- outbound: `orders/actual-start` — 輸入改變時零寫入 Preview；最後確認才 Apply／readback，取得新 owner versions 後再 Preview／Apply 服務日期。正式或歷史重排候選須與核對集合一致。
- outbound: `scheduling/scheduling` — 日期保存不再重建 restart tombstone；後續明確正式安排才呼叫 canonical generation replacement writer。
- outbound: `staff-payables/payroll` — 日期保存不寫 rate snapshot；後續真正建立安排時才沿 source frozen rate，或在歷史 pairing 無 source snapshot 時使用既有 case payroll policy。
- inbound: `orders/historical-precision-restart` — completed restart、空 effective generation 與 immutable historical pairing evidence；source assignment identity 可不存在。

## Contracts
- `GET／POST /api/v1/orders/{case_no}/service-dates` — confirmed-date Query／Preview／Apply。
- `POST /api/v1/orders/{case_no}/service-dates/arrangement/{preview,apply}` — 歷史重啟待安排案件的明確分段、fresh-lock、冪等 canonical Scheduling handoff；Query 的 `arrangement_pending` 只投影 current restart tombstone 與 confirmed-date 版本。
- `document/架構重整/01_規格基線/01_Orders_Domain.md` §3.4.1 — 一般日期確認與 restart-specific canonical Scheduling handoff。

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
- Orders owns confirmed-date Q/P/A — `architecture_declared` — `document/架構重整/01_規格基線/01_Orders_Domain.md` §3.4.1。
- Scheduling owns generation replacement and `staff_schedule` — `source_observed` — `infrastructure/mysql/scheduling_replacement_writer.py`。
- Restart-specific handoff separation — `source_observed` — `subsystems/orders/historical_restart_arrangement.py` 與 `document/架構重整/01_規格基線/01_Orders_Domain.md` §3.4.1。

## Change triggers
- Reconcile when confirmed-date API, restart-pending detection, historical assignment lineage, Scheduling replacement contract, server read-back, or canonical test roots change.
