# Module: weekly-operations-report

## Parent
- domain: `global`
- subsystem: `reporting`

## Responsibility
以 canonical `start_date`／`end_date` 協調自選期間內案件與 Scheduling 正式工作日，按實際星期一至星期日分週；「補助案件統計表」則固定取得 `end_date` 所屬完整年度的 Government Subsidy owner rows，並依民國申請年度與身分類別組成頂端筆數／金額摘要，以既有專用欄位格式提供 strict JSON 及同 candidate XLSX，不得改套獨立「年度補助」報表格式。
案件年度累計自 1 月 1 日起算；正常與歷史訂單依相同業務狀態合併計數，JSON／XLSX 共用 Reporting classification。待辦看板另使用同一 owner 的獨立唯讀案件統計 GET，按匯入曆年／季度／月份計數，維持全年度累計，不查服務、補助或 weekly metrics；計數 adapter 不讀取姓名、地址或原始拒絕原因。

<a id="reporting-established-design"></a>

## 曾成立統計的實作邊界 ^reporting-established-design

- 分類契約見 [曾成立案件統計](../../../../../requirements/34_營運報表與統計口徑正式規格.md#established-case-count)。`WeeklyOperationsReportQuery._case_row` 消費正式成立證據，沿用同一 classification 與同候選 XLSX；「成立後未服務」明細的服務天數為零，現有受理總表欄位不變。
- MySQL read adapter 透過 bounded typed projection 提供 Orders 的正式成立證據、目前狀態及已確認零服務量；Reporting 應用層在同一分類結果產生模板四欄與明細。成立認列與目前生命週期分布分開，UI／XLSX 只格式化正式查詢結果，不自行判斷、增減或累加款項。
- 取消案更正後的數量變化由重查正式 owner facts 自然得到，不執行「取消 counter 減一、成立 counter 加一」寫入，避免重送重複增減；日期、身分與案件類別沿原查詢邊界。
- `weekly_operations_report_query_adapter.py` 借用 `order_establishment_read_model.py` 的共用成立證據 SQL；歷史零服務更正原因來自已提交 lifecycle event 的更正意圖，普通零服務終止原因來自生效的 cancellation control。UI 與 XLSX 不從原工作簿猜測目前分類。
- 驗證入口對應 `REPORT-ESTABLISHED-01/02/03`：正常／歷史、前後重讀、同候選 XLSX 與零服務原因的正反案例分別在 Reporting owner tests 及歷史更正 MySQL integration。來源 mappings 與本節文字不表示真實 DB 已驗收。

```yaml archmap-impact
- kind: implements_requirement
  source: reporting-established-design
  target: '.arch-map/requirements/34_營運報表與統計口徑正式規格.md#^established-case-count'
```

## Implementation
- primary:
  - `subsystems/reporting/weekly_operations_report_query.py`
  - `subsystems/reporting/weekly_operations_report_export.py`
  - `subsystems/reporting/weekly_report_metrics_service.py`
  - `infrastructure/mysql/weekly_operations_report_query_adapter.py`
  - `infrastructure/mysql/order_establishment_read_model.py` — 借用 Orders 正式成立事件／歷史採納證據的唯讀 SQL，不在 Reporting 重定義成立。
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

例如管理員呼叫 `PUT /api/v1/operations-reports/weekly/metrics/2026-08-24`，主體為 `{"promotion_count":0,"inquiry_count":null}`：兩個鍵都必填，`0` 儲存實際零，明傳 `null` 會清除該週欄位的舊值。成功回應的 `data` 是整列，含 `week_start_date`、`week_end_date`、兩個計數及 `updated_at`，沒有版本欄位。省略任一鍵回 422；兩鍵合法但把週起日改為 2026-08-25（週二），回 400 `weekly_report_metric_invalid`。兩例都不變更已存資料。

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

[需求書 §2.2「案件受理總表的取消原因」](../../../../../requirements/34_營運報表與統計口徑正式規格.md#weekly-case-cancel-reason) 定義顯示條件。`weekly_operations_report_query_adapter.py` 對「訂單取消」依生效 cancellation control 的原因回退 Orders `cancel_reason`；對「成立後未服務」先讀已提交更正 lifecycle event 的 `historical_unserved_correction.reason`，沒有更正原因時使用生效的取消原因。`WeeklyOperationsReportQuery._case_row` 在這兩種狀態保留原因，其他返回 `None`。這是週報明細投影，不是待辦看板的統計欄位。

`api/routes/operations_reports.py` 僅在 `operations-report.v5` 的案件明細輸出 `cancel_reason`（字串或 `null`），`v3`／`v4` 省略欄位。`OperationsReportsWorkspace.tsx` 對 `null` 留空；`weekly_operations_report_export.py` 同樣消費該明細值，寫入案件受理總表第 25 欄，原因存為純文字，不求值為 Excel 公式。

驗證定位：`tests/test_weekly_operations_report_contract.py::test_weekly_report_projects_order_cancellation_reasons_in_v5_and_excel` 檢查合成明細的 v5 文本／null、v3/v4 省略及 XLSX 文本／空白。它替代資料來源，不能證明 MySQL 查找或歷史回退已測。

```yaml archmap-impact
- kind: implements_requirement
  source: reporting-weekly-cancel-reason
  target: '.arch-map/requirements/34_營運報表與統計口徑正式規格.md#^weekly-case-cancel-reason'
```

### 每週服務工時的來源與輸出 ^reporting-weekly-daily-hours

[需求書 §2.2「每週服務中與工時的逐日時數」](../../../../../requirements/34_營運報表與統計口徑正式規格.md#weekly-service-daily-hours) 定義日班認列與週工時。報表只讀，不修改合約、排班或帳務。

| 負責角色 | 正式約定與接線 | 去哪查 |
| --- | --- | --- |
| Scheduling／資料來源 | 生效班表提供實際工作日、當日人員及逐日時數覆寫。Reporting 以唯讀 SQL 選有效工作日，排除取消或已替換指派。逐日覆寫為 `NULL` 才沿用案件原訂時數。 | `infrastructure/mysql/weekly_operations_report_query_adapter.py` 的 `_SERVICE_FACTS_SQL` |
| Reporting／後端 | 依人員、案件及實際服務日期所在的星期一分組。SQL 計有效日期數，工時齊全時加總逐日時數；同組含不同日工時時不回傳單一每日時數。Query 優先使用回讀的 `weekly_hours`；XLSX 使用查詢列的週天數及週工時，不另算。 | `WeeklyOperationsReportQuery._service_row`、`weekly_operations_report_export.py` |
| 前端 | 讀取查詢結果的 `weekly_work_days` 與 `weekly_hours`。每日時數為 `null` 時留空，不把原訂時數或自行計算的平均值填上。 | `OperationsReportsWorkspace.tsx`、`ui_react/src/tests/reports_weekly_service_display.test.tsx` |

[驗證定位](../../../../../tests/domains/global/subsystems/reporting/modules/weekly-operations-report.md) 區分替身資料的畫面檢查與資料來源檢查。需求書的跨週合併／分裂情境仍須核對 Scheduling 到週報 JSON、畫面與 XLSX 的完整鏈路；本節不宣稱已執行。

```yaml archmap-impact
- kind: implements_requirement
  source: reporting-weekly-daily-hours
  target: '.arch-map/requirements/34_營運報表與統計口徑正式規格.md#^weekly-service-daily-hours'
```

### 補助資格分類與報表輸出 ^reporting-qualification-stats

[需求書 §3](../../../../../requirements/34_營運報表與統計口徑正式規格.md#qualification-and-aboriginal-stats) 定義三軌資格、HCM 作廢與新 `A` 案隔離。Reporting 只讀分類，不更正原案或重新計價。

| 負責角色 | 正式約定與現行接線 | 去哪查 |
| --- | --- | --- |
| 案件來源／資料 | 讀取正式 `identity_status`、`hcm_review_status` 與案件識別。整案審核不符合的原 HCM 紀錄留在週報候選；另立的 `A` 案仍依 §5 分流，不把新案回灌到原 HCM 計數。 | `infrastructure/mysql/weekly_operations_report_query_adapter.py` 的 `_REPORT_CASE_CATEGORY_SQL` |
| Reporting／後端 | `review_result` 每案一個；六項資格旗標與四項案件狀況分開，不相加作總件數。確認為零時保留數值 `0`；有未能歸類的拒絕且該拒絕欄沒有已知計數時，該欄回 `null`，不補零。相同日期範圍才比較週報與待辦看板；年度補助統計的範圍另算。 | `WeeklyOperationsReportQuery._case_row`、`_qualification_summary`、`weekly_report_metrics_service.py` |
| 前端／匯出 | 待辦看板把未知的資格彙總顯示為 `—`。週報 XLSX 彙總保留真實數字 `0`，未知留空；明細的 `0/1` 旗標則是 `0` 留空、`1` 顯示，不改 JSON 的數值。 | `WorkbenchCaseStatistics.tsx`、`weekly_operations_report_export.py` |

未證實的邊界：若實為非市民的誤報案作廢後仍保留原住民 `identity_status`，週報分類器會把該筆判為原住民不符合。尚未確認作廢上游是否在投影前提供更正後的身分，因此不能把 `QUAL-STAT-03` 視為已驗收，也不更動該條規格。

驗證定位：`tests/test_weekly_operations_report_contract.py::test_workbench_and_weekly_have_identical_known_counts_for_same_calendar_period` 核對替身資料的相同期間、已知零與未知值。它不證明原住民誤報作廢的正式資料鏈、實際畫面或 XLSX 資格儲存格已驗收。

```yaml archmap-impact
- kind: implements_requirement
  source: reporting-qualification-stats
  target: '.arch-map/requirements/34_營運報表與統計口徑正式規格.md#^qualification-and-aboriginal-stats'
```

## Verification
- layout_status: `custom_current`
- test_root: `tests/domains/global/subsystems/reporting/modules/weekly-operations-report/`
- test_root: `tests/test_weekly_operations_report_contract.py`
- test_root: `tests/test_weekly_operations_report_api_versions.py`
- integration_root: `tests/test_weekly_operations_report_mysql.py`
- higher_boundary: [Orders historical-adoption 的整合測試](../../../../../../tests/domains/orders/subsystems/orders/modules/historical-adoption/integration/test_wp80_disposable_mysql_e2e.py) — 引用該 owner 的歷史零服務更正前後真實 Query／JSON／XLSX、分類重播與重匯一致性。
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
