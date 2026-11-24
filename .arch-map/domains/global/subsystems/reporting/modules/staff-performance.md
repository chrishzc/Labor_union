# Module: staff-performance

## Parent
- domain: `global`
- subsystem: `reporting`

## Responsibility
Compose monthly, quarterly and annual read-only staff performance. Credit each case and its full price once to its opening month/principal; retain each worker's own service-month hours. All trends are monthly and reconcile to period totals. Preserve unknown opening dates and prices.

## Implementation
- `subsystems/reporting/staff_performance_query.py`
- `subsystems/reporting/staff_performance_export.py`
- `infrastructure/mysql/staff_performance_query_repository.py`
- `api/schemas/staff_performance.py`
- `api/dependencies/operations_reports.py`
- `api/routes/operations_reports.py` — authenticated GET `/api/v1/operations-reports/staff-performance` and `/staff-performance/export`.
- `ui_react/src/api/reports/staff_performance_client.ts`
- `ui_react/src/components/reports/StaffPerformancePanel.tsx`
- `ui_react/src/components/reports/StaffPerformancePanel.css`
- `ui_react/src/pages/ReportsPage.tsx` — report workspace composition; existing reports remain separate.

## Dependencies
- outbound: `scheduling/schedule-generation` — effective work days and exact opening principal through rebuild/substitution lineage; no inferred actual start date or new persistence root.
- outbound: `orders/actual-start` — official actual start date and shared weekday rules for estimating historical report hours.
- outbound: `orders/historical-adoption` — adopted pairing evidence and its assignment identify the opening principal when historical orders have no effective formal work days.
- outbound: `orders/historical-service-accounting` — current confirmed service days per historical assignment.
- outbound: `orders/order-terms` — normalize registered historical service mode for the report estimate.
- outbound: `staff/staff-roster-profile` — canonical id, name and custom union number.
- outbound: `client-finance/pricing-configuration` — `case_total_amount` from complete owner pricing facts; no report-owned pricing rule.
- inbound: `staff/staff-roster-profile` — named staff performance shortcut.

## Contracts
- `.arch-map/requirements/34_營運報表與統計口徑正式規格.md` §6 STAFF-PERF-01..05, `staff-performance.v2`; XLSX includes period/ranking metadata, full-case and recognized amounts separately.
- No transaction ownership, DB writes, schema changes or external provider effects.


### 正式逐日工時與開案認列

[需求書 §6.1](../../../../../requirements/34_營運報表與統計口徑正式規格.md#61-口徑與認列規則) 定義月嫂表現的工時：只看各月嫂於期間內的有效工作日；`staff_performance_query_repository.py::list_service_days` 每日取 `Orders.service_hours_per_day`，不讀逐日覆寫。相對地，[週報逐日時數](../../../../../requirements/34_營運報表與統計口徑正式規格.md#weekly-service-daily-hours) 的 SQL 優先取 Scheduling 的 `service_hours_override`。同一正式班次兩份報表可以有不同數字，不能把其中一份當成另一份的驗收基準。

`StaffPerformanceQuery` 另使用實際開案日與開案主責做一次性認列，`total_amount_ntd`（明細整案金額）和 `recognized_amount_ntd`（本期認列額）不可互代。已知開案且主責是另一人時，接手者可有工時，接案件數與認列金額為零；有已知工時但實際開案日未知時，受影響的認列保留 `null`，XLSX 顯示「待確認」。JSON 和 XLSX 分別查詢，`staff-performance.v2` 是格式版本，不是兩次請求共用的資料快照。

交接驗證（尚未實跑）：以固定資料核對兩份查詢及各自 XLSX。例：A 於 10/26 開案，原訂每日 4 小時、整案 NT$12,000；B 接手後，11/02、11/09 兩個 4 小時班次合為 11/02 一個 8 小時正式班次。依現行兩項口徑，該案 B 的週報工時為 8，11 月月嫂表現為 4，B 的 11 月認列為零；A 只在 10 月認列 1 件、NT$12,000。若任一角色要求兩報表工時一致，先確認業務口徑再改需求或程式。既有 `test_handover_has_hours_but_never_takes_the_opening_credit` 與 `test_missing_actual_start_keeps_hours_and_marks_credit_unknown` 使用合成資料，不涵蓋兩份 SQL 的合併班次對照。

## Verification
- layout_status: `custom_current`
- layout_basis: Reporting tests use module roots; React mirrors the same owner in the existing Vitest runtime.
- test_root: `tests/domains/global/subsystems/reporting/modules/staff-performance/` — 既有合成案例核對缺正式開工日仍保留服務時數，案件數與金額標待確認。
- test_root: `ui_react/src/tests/domains/global/subsystems/reporting/modules/staff-performance/`
- routing: `.arch-map/tests/domains/global/subsystems/reporting/modules/staff-performance.md`

## Change triggers
Reconcile when performance metrics, period, identity/price sources, read API/export, UI entry or tests change.
