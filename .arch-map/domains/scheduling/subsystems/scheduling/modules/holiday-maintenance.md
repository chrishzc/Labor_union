# Module: holiday-maintenance

## Parent
- domain: scheduling
- subsystem: scheduling

## Responsibility
將官方單一年度國定假日 CSV 轉成 typed rows，經既有 Scheduling owner 的逐筆 Query／Preview／Apply 維護 holiday facts；Preview 必須零寫入，Apply 必須以每筆 fresh calendar version 並保留既有 owner facts。

## Implementation
- primary owner: `subsystems/scheduling/holiday_maintenance.py`
- read-only projection cache: `subsystems/scheduling/holiday_query_cache.py` — 支援選用外部 Redis＋L1 TTL 唯讀快取，僅於 `POST /api/v1/holidays/apply` 成功提交後以命名前綴失效。
- HTTP boundary & lazy query wiring: `api/dependencies/holidays.py`、`api/routes/holidays.py`、`api/schemas/holidays.py`
- holiday command adapter: `infrastructure/mysql/admin_command_repository.py` — 共用 adapter 檔案中的 holiday mutation，由 owner UoW 呼叫固定用途刪除程序。
- holiday query adapter: `infrastructure/mysql/scheduling_holiday_query.py`
- typed client: ui_react/src/api/scheduling/holiday_client.ts
- presentation: ui_react/src/pages/SchedulingPage.tsx
- CSV presentation: ui_react/src/components/scheduling/OfficialHolidayCsvImport.tsx
- CSV import adapter: ui_react/src/adapters/scheduling/official_holiday_csv.ts

## Contracts
- GET /api/v1/holidays
- POST /api/v1/holidays/preview
- POST /api/v1/holidays/apply
- official CSV fields: 西元日期、星期、是否放假、備註；0 表示上班，2 表示放假。

## Verification
- layout_status: custom_current
- tests: see the holiday-maintenance test module leaf.
- integration_root: `tests/domains/scheduling/subsystems/scheduling/integration/test_holiday_router.py`
- test_root: `ui_react/src/tests/domains/scheduling/subsystems/scheduling/modules/holiday-maintenance/`
- test_root: `ui_react/src/tests/scheduling_holiday_flow.test.tsx` — 既有管理工作台的自動查詢、版本化儲存與結果回讀；保留 current legacy UI 路徑。
- boundary: Subsystem
- oracles: actual parser, transport call order, zero-write Preview, fresh per-date Apply version, preserve/skip/partial failure, awaited UI readback failure, and adapter state/retry transitions.

## Provenance
- owner and workflow: source_observed from subsystems/scheduling/holiday_maintenance.py and current typed client.
- frontend presentation: source_observed from SchedulingPage.tsx and its OfficialHolidayCsvImport component.
- canonical test placement: architecture_declared by the existing Scheduling Holiday module test root and current test routing.

- test_root: `ui_react/src/tests/scheduling_no_fake_mutation.test.tsx` — 既有 SchedulingPage 假日入口的查詢與零自動 mutation 保護。

## 國定假日計價接線 ^holiday-maintenance-holiday-pricing

```yaml archmap-impact
- kind: implements_requirement
  source: holiday-maintenance-holiday-pricing
  target: ".arch-map/requirements/02_Assignments_Scheduling_Domain.md#^holiday-annual-settings"
```
- 年度設定沿既有 Query／Preview／Apply 接線。`SchedulingPage.tsx` 以年度起訖呼叫既有 GET。年度列直接顯示雙倍狀態及啟用／取消按鈕，逐列走既有 typed client Query／Preview／Apply／readback，不開抽屜或確認視窗。每列保存送出鎖、錯誤及原命令重送鍵，讀回失敗只重讀，未明 Apply 以同鍵重送；版本衝突重新查詢預覽。成功只更新該列，失敗保留原顯示並提供列內重試。新增、改名及日期修改沿原抽屜入口，與雙倍按鈕分開。CSV 入口沿現有逐筆預覽／套用及全年讀回。`SchedulingHolidayQuery` 提供版本化日期及雙倍旗標；`holiday_maintenance.py` 的 Apply 為假日異動協調入口，沿 caller UoW 串接受影響案件的兩方 owner。正式收付保護由各帳務 owner 提供 fresh facts，不由 UI 判斷。API 應回正式收據及重算／保留／待決策的案件結果，前端回讀後端結果，不自行乘二。

- `MySqlHolidayRepricing` 沿假日 Apply 同一 UoW 先保存受保護原定價、再處理未收付案件；收據 `case_results` 回傳逐案重算、保留、歷史排除或資金待決策。Preview 的 `payroll_impact` 區分無異動與 `reprice_unpaid_cases`。

- 逐案結果契約引用22A的雙邊保護與回執條款。設定入口保存 `case_results` 及可追溯原因，前端與既有案件／對帳入口讀取同一結果，不以假日旗標回讀代替帳務完成，也不新增全額免自備操作提醒。

- 帳務結果唯讀入口：`GET /api/v1/holidays/accounting-results?from_date&to_date`，沿原管理員權限由 `holiday_accounting_results.py` 從既有假日 receipt JSON 查區間內各日期最新逐案結果，不建立新帳務事實。型別由 `subsystems/scheduling/holiday_accounting_results.py` 提供，列表與日期卡共用 `HolidayRepricingResults.tsx`；沒有紀錄或讀取失敗不等於已完成。
