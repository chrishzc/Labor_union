# Module: weekly-operations-report

## Parent
- domain: `global`
- subsystem: `reporting`

## Responsibility
以 canonical `start_date`／`end_date` 協調自選期間內案件與 Scheduling 正式工作日，按實際星期一至星期日分週；「補助案件統計表」則固定取得 `end_date` 所屬完整年度的 Government Subsidy owner rows，並依民國申請年度與身分類別組成頂端筆數／金額摘要，以既有專用欄位格式提供 strict JSON 及同 candidate XLSX，不得改套獨立「年度補助」報表格式。
案件年度累計自 1 月 1 日起算；正常與歷史訂單依相同業務狀態合併計數，JSON／XLSX 共用 Reporting classification。待辦看板另使用同一 owner 的獨立唯讀案件統計 GET，按匯入曆年／季度／月份計數，維持全年度累計，不查服務、補助或 weekly metrics；計數 adapter 不讀取姓名、地址或原始拒絕原因。

## Implementation
- primary:
  - `subsystems/reporting/weekly_operations_report_query.py`
  - `subsystems/reporting/weekly_operations_report_export.py`
  - `subsystems/reporting/weekly_report_metrics_service.py`
  - `infrastructure/mysql/weekly_operations_report_query_adapter.py`
  - `api/dependencies/operations_reports.py`
  - `api/schemas/operations_reports.py`
  - `db/schema_parts/218_weekly_report_metrics.sql`
  - `db/schema_parts/1035_weekly_report_metrics.sql`
  - `ui_react/src/pages/ReportsPage.tsx` — 營運案件／工時與原完整 workbook，補助連結導向 Finance。
  - `ui_react/src/components/reports/OperationsReportsWorkspace.tsx` — 共用既有報表欄位與 Query／XLSX；帳務端唯一補助畫面（週報補助統計／季度／年度），案件編號使用原案件抽屜 callback。
  - `ui_react/src/components/FinanceGovernmentSubsidyList.tsx` — Finance presentation 接線，無第二套報表或 CSV。
- entrypoints:
  - `api/routes/operations_reports.py`
  - `ui_react/src/api/reports/weekly_operations_report_query_client.ts`
  - `ui_react/src/api/reports/weekly_operations_report_schemas.ts`
  - `ui_react/src/api/reports/weekly_operations_report_export_client.ts`
  - `ui_react/src/api/reports/weekly_report_metrics_client.ts`

## Dependencies
- outbound: `case-import/hcm-current-workbook-import` — 依獨立保存的 HCM 審核狀態分類，拒絕原因不參與統計。
- outbound: `case-import/provisional-registration` — 依 LIFF 核准配號紀錄，或後台手動建案的 `case_import_events` 不可變來源快照，取得正式建案時間。
- outbound: `government-subsidy/reconciliation-register-query` — 以 owner formula 取得 `end_date` 所屬年度的正常／歷史已付訂金訂單補助統計 rows（區分為 `general`、`subsidized`、`indigenous` 三軌），不要求 claim batch。
- outbound: `orders | client | scheduling` — selected-week案件與正式服務facts。
- inbound: authenticated React Reports page、Finance 政府補助唯一入口、Orders 待辦看板統計列。
- storage: current `weekly_report_metrics` uses Monday `week_start_date` as its key and nullable promotion／inquiry counts; fresh `218` and preserve `1035` provide the table. Released `1031` batch objects are historical compatibility only and have no current runtime reader／writer.

## Contracts
- HCM 審核不符合優先於訂單狀況，六項資格欄位每筆至多一個；資格來源缺漏保留待確認。確認符合並歸一般市民的案件只計一般市民符合；原住民及其來源別名（`原民`、`原住民市民`）依審查結果計入原住民符合或原住民不符合；實為非市民誤報、原 HCM 作廢者依 `QUAL-STAT-03` 維持計入一般市民不符合且不轉換成 `A` 案。週報畫面、同候選 Excel 與待辦看板共用分類。
- 2026-11-04 核准搬移：營運畫面只留案件／工時兩分頁，補助統計及季度／年度移至 Finance 唯一入口；原三 worksheet、typed API／owner formula／XLSX 不變。案件操作仍使用 Finance 原抽屜，原查詢條件與來源位置保留；不維護第二套 CSV。
- 週報 React／XLSX 案件受理總表使用 A:Z 26 欄雙層表頭，取消原因讀取 Orders 生效的取消事件或歷史訂單資料。`補助案件統計表` 支援三軌獨立分區（`general`、`subsidized`、`indigenous`）與頂端六列兩年度統計。看板 summary 與 `WorkbenchCaseStatistics` 同步呈現在三大資格群組共六欄與模板四欄計數，非市民區塊獨立呈現。正式欄位裁決：`.arch-map/requirements/34_營運報表與統計口徑正式規格.md` §2–§5。
- 非市民依正式身分／綁定費率規則分類，排除於原受理統計及同 candidate XLSX；獨立 `case_category=non_citizen` 統計以臺灣時間的正式建案日歸屬月／季／年，提供完整年度累計。LIFF 採核准時間，後台手動案採建案快照。未核准待審案與無可追溯建案時間的舊案不計入。
- Reporting adapter 借用 `infrastructure/mysql/case_category_query.py` 的唯讀分類 SQL；身分根值與費率規則仍屬原 owner。Reports／看板共用 `ui_react/src/components/WorkbenchCaseStatistics.tsx` 與其 CSS（Orders presentation owner）。
- 服務工時及補助列保留原姓名，另借用同一 Staff join 的 nullable `staff_union_no`，供管理端顯示「公會編號 姓名」；報表金額、工作日、週序及既有 XLSX 欄位不變。
- `operations-report.v5` 提供取消原因（相容 `v3`、`v4`）、canonical `start_date`／`end_date`與Monday-keyed weekly metrics — `.arch-map/requirements/34_營運報表與統計口徑正式規格.md` §2。
- `GET /api/v1/operations-reports/case-statistics`、曆年計數與歷史狀態合併 — `.arch-map/requirements/34_營運報表與統計口徑正式規格.md` §4。

### 營運案件分類與帳務合計 ^reporting-case-category-boundary

[需求書 §5「非市民自費案件獨立統計」](../../../../../requirements/34_營運報表與統計口徑正式規格.md#noncitizen-statistics-20261029) 定義營運分流。待辦看板的 `WorkbenchCaseStatistics.tsx` 經 `weekly_operations_report_query_client.ts` 呼叫 `GET /api/v1/operations-reports/case-statistics`。`api/routes/operations_reports.py` 將 `case_category` 傳到 `WeeklyOperationsReportQuery.query_case_statistics`：補助區用 `subsidy`（預設），非市民區用 `non_citizen`，Query 依類別選用各自的統計來源。

API 的 `data.summary.order_status_counts` 依 `api/schemas/operations_reports.py` 定義六個狀態鍵，含「訂單完成」。`WorkbenchCaseStatistics.tsx` 的非市民區塊只依 `STATUS_LABELS` 讀取需求書 §5 指定的五個值，不把所有 API 鍵直接轉成欄位；期間件數與年度累計讀取 API 獨立欄位，不加總畫面上的狀態欄。查詢端的驗證入口是 `tests/domains/global/subsystems/reporting/modules/weekly-operations-report/test_non_citizen_statistics.py::test_non_citizen_calendar_periods_and_full_annual_count`；它不驗證 React 欄位是否顯示。

「全部案件」的跨類合計歸 Client Finance §2.3，不是上述查詢的第三種 `case_category`，也不回灌 Reporting。核對分流時，從下方 Verification 的案件統計契約測試入口追查；營運與帳務合計的正反驗收見需求書 §5。測試定位不代表已執行。

```yaml archmap-impact
- kind: implements_requirement
  source: reporting-case-category-boundary
  target: '.arch-map/requirements/34_營運報表與統計口徑正式規格.md#^noncitizen-statistics-20261029'
```

### 週報人工指標的儲存與輸出 ^reporting-weekly-metrics-null-zero

[需求書 §2.1「每週人工指標：未登錄與實際零」](../../../../../requirements/34_營運報表與統計口徑正式規格.md#weekly-metrics-null-zero) 定義畫面和匯出行為。`WeeklyMetricsEditor.tsx` 將空欄轉成 `null`，數字 `0` 則原樣經 `weekly_report_metrics_client.ts` 交給管理員的週指標 PUT 路由。`WeeklyReportMetricsService.save_metric` 在寫入前驗證星期一與非負數，再用 `week_start_date` 更新 `weekly_report_metrics` 的兩個可空欄位；非星期一由路由回傳 400，不寫入。

週報明細用 `week_start_date` 對應當週指標，不從案件列推算。React 的 `OperationsReportsWorkspace.tsx` 對該週只畫一次，經 `displayWeeklyMetric` 將 `null` 顯示為「未登錄／待補正」；XLSX 由 `weekly_operations_report_export.py` 每週各寫一次，`null` 寫為「未登錄」。兩邊的實際零都保留。

驗證定位：`tests/test_weekly_operations_report_contract.py::test_weekly_metrics_list_and_save_are_monday_keyed` 驗證 API 的週起日、`0`、`null` 和拒絕週二；同檔 `test_weekly_metric_storage_preserves_null_zero_and_rejects_non_monday_key` 使用替身連線驗證服務層。這兩例不驗證真實 MySQL 或畫面／XLSX。

```yaml archmap-impact
- kind: implements_requirement
  source: reporting-weekly-metrics-null-zero
  target: '.arch-map/requirements/34_營運報表與統計口徑正式規格.md#^weekly-metrics-null-zero'
```

### 週報日期的編輯與套用 ^reporting-weekly-date-selection

[需求書 §2.1「套用週報查詢日期」](../../../../../requirements/34_營運報表與統計口徑正式規格.md#weekly-report-date-selection) 定義畫面行為。React `OperationsReportsWorkspace.tsx` 將編輯值存在 `dateDraft`，查詢只消費已套用的 `startDate`／`endDate`。Enter 觸發欄位失焦，兩者都由 `changeDateRange` 驗證日期及起迄順序。有效的新期間會清除舊匯出狀態並切為 loading，然後呼叫 `weeklyOperationsReportQueryClient.query`；未套用或無效時停用重新載入與匯出。查詢 effect 會中止舊請求，並用請求序號忽略過期回應。

驗證定位：`ui_react/src/tests/reports_query_page.test.tsx` 的「年份未輸完時不送出跨千年查詢，離開欄位後才查詢」覆蓋起訖兩欄；「日期範圍與 reload 變更會清除 stale export success」另核對舊下載訊息。這兩個測試 mock 查詢與匯出，不驗證 API 實際資料。

```yaml archmap-impact
- kind: implements_requirement
  source: reporting-weekly-date-selection
  target: '.arch-map/requirements/34_營運報表與統計口徑正式規格.md#^weekly-report-date-selection'
```

### 案件受理總表的週資料、月小計與年度累計 ^reporting-weekly-monthly-rollup

[需求書 §2.2「案件受理總表的月小計歸屬」](../../../../../requirements/34_營運報表與統計口徑正式規格.md#weekly-monthly-rollup) 定義時間口徑與顯示順序。`WeeklyOperationsReportQuery.query` 先以起迄日取案件，再依 `week_start_date` 的年／月建立 `monthly_subtotals`；`weekly_metrics` 以相同的星期一鍵對應，週指標不依案件筆數或選取天數複製或攤分。`annual_totals` 的年度案件數另依案件實際日期查該曆年 1 月 1 日到查詢迄日（上限為該年 12 月 31 日），不從月小計回加。

`OperationsReportsWorkspace.tsx` 與 `weekly_operations_report_export.py` 消費這兩組統計，年度累計先於週資料，月小計在相同月份最後一組週資料後；畫面與 XLSX 不各自重算歸屬。

驗證定位：`tests/domains/global/subsystems/reporting/modules/weekly-operations-report/test_weekly_operations_report_totals.py` 的 `test_partial_date_selection_keeps_case_filter_but_never_splits_week_metrics` 與 `test_early_january_week_remains_in_previous_december` 覆蓋查詢與歸屬；`test_cross_year_months_follow_monday_and_annual_cases_follow_calendar_year` 另核對 XLSX 列順序。這些是合成資料的查詢與活頁簿測試，不是 React 或真實資料庫驗收。

```yaml archmap-impact
- kind: implements_requirement
  source: reporting-weekly-monthly-rollup
  target: '.arch-map/requirements/34_營運報表與統計口徑正式規格.md#^weekly-monthly-rollup'
```

### 週報取消原因的讀取與輸出 ^reporting-weekly-cancel-reason

[需求書 §2.2「案件受理總表的取消原因」](../../../../../requirements/34_營運報表與統計口徑正式規格.md#weekly-case-cancel-reason) 定義顯示條件。由 `weekly_operations_report_query_adapter.py` 依該案目前生效的 cancellation control 找到 Orders 取消事件；現行 adapter 以 `COALESCE(cancellation.reason, o.cancel_reason)` 讀取可用原因。接著 `WeeklyOperationsReportQuery._case_row` 只在訂單狀態為「訂單取消」時保留值，其他返回 `None`。這是週報明細投影，不是待辦看板的統計欄位。

`api/routes/operations_reports.py` 僅在 `operations-report.v5` 的案件明細輸出 `cancel_reason`（字串或 `null`），`v3`／`v4` 省略欄位。`OperationsReportsWorkspace.tsx` 對 `null` 留空；`weekly_operations_report_export.py` 同樣消費該明細值，寫入案件受理總表第 25 欄，原因存為純文字，不求值為 Excel 公式。

驗證定位：`tests/test_weekly_operations_report_contract.py::test_weekly_report_projects_order_cancellation_reasons_in_v5_and_excel` 檢查合成明細的 v5 文本／null、v3/v4 省略及 XLSX 文本／空白。它替代資料來源，不能證明 MySQL 查找或歷史回退已測。

```yaml archmap-impact
- kind: implements_requirement
  source: reporting-weekly-cancel-reason
  target: '.arch-map/requirements/34_營運報表與統計口徑正式規格.md#^weekly-case-cancel-reason'
```

## Verification
- layout_status: `custom_current`
- test_root: `tests/domains/global/subsystems/reporting/modules/weekly-operations-report/`
- test_root: `tests/test_weekly_operations_report_contract.py`
- test_root: `tests/test_weekly_operations_report_api_versions.py`
- integration_root: `tests/test_weekly_operations_report_mysql.py`
- integration_root: `ui_react/src/tests/reports_query_page.test.tsx`
- integration_root: `ui_react/src/tests/reports_weekly_totals.test.tsx`
- integration_root: `ui_react/src/tests/reports_weekly_api_versions.test.tsx`
- integration_root: `ui_react/src/tests/reports_weekly_service_display.test.tsx`
- integration_root: `ui_react/src/tests/weekly_operations_report_client.test.ts`
- integration_root: `ui_react/src/tests/reports_entry_cross_owner_cutover.test.tsx`
- integration_root: `ui_react/src/tests/fixtures/reports/weekly_operations_report_contract_fixtures.ts`

## Provenance
- Global Reporting擁有跨Domain營運報表composition，business formula仍由各owner提供 — `architecture_declared` — [營運報表與統計口徑正式規格](../../../../../requirements/34_營運報表與統計口徑正式規格.md) §1；現行source差異見上節。
- 週報 API／XLSX 契約的既有測試定位 — `source_observed` — [日期與篩選拒絕測試](../../../../../../tests/test_weekly_operations_report_contract.py#L116-L139) 與 [JSON／XLSX 歷史分組測試](../../../../../../tests/test_weekly_operations_report_contract.py#L142-L162)（替身資料，不是正式環境或 MySQL 結果）。

## Change triggers
Reconcile when報表期間／annual_ytd、補助期間、三分頁schema、owner fact dependency、public GET/export、批次POST／PATCH、writer／commit boundary、正式契約或Reports presentation test path改變。
