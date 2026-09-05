# Issue 驗收結果（重新驗收）

> 本報告完全取代先前版本。判定只採用本次重新啟動的 backend/frontend、目前 `union_db`、真實 HTTP、DB readback 與 Chrome 畫面；舊報告結論不沿用。

## Acceptance Summary

* Checkout commit: `b235ea95c9e4ea6d02c4d9be63da91333f6e3810`
* Backend: `http://127.0.0.1:8010`，development/local developer session；完成檢查時該 port 已不再 listen
* Frontend: `http://127.0.0.1:5175/admin/`，正式 React/Vite UI；完成檢查時該 port 已不再 listen
* Database: 既有測試資料庫 `union_db`；依使用者指示直接建立合成驗收資料，未另建資料庫、未 reset、未碰 production
* Browser: 本機 Google Chrome，獨立 Playwright context，單一 desktop viewport
* Started at: 2026-09-03 15:28 +08:00
* Completed at: 2026-09-03 16:20 +08:00
* Overall: **FAIL**
* Final decision: **REJECTED**

本次使用合成識別碼 `RERUN-*`，不記錄密碼、token、cookie、身分證或銀行資料。證據根目錄：

`C:\Users\chris\.codex\visualizations\2026\09\03\01a065ca-0a61-7352-8b1e-db49d3b144d8\rerun-20260903-152814`

工作樹在驗收期間已有大量使用者修改；本報告描述的是上述 commit checkout 加上當時工作樹的實際 runtime snapshot。本次沒有修改 repository source code，也沒有修正任何驗收失敗。

## Issue Results

| Issue | Backend | UI | DB/readback | Result | Evidence | Note |
| ----- | ------- | -- | ----------- | ------ | -------- | ---- |
| #99 月嫂歷史匯入 | 正式 preview/apply 成功；同 key 重送為 replay | 名冊 reload 顯示匯入後 education | 六組其它各 2、certification 3；來源欄位未入 schema；無重複 | **PASS** | `staff-historical-rerun.xlsx`、`staff_import_readback.py`、`detail-staff-search.png` | 使用既有 Staff 做更新驗證。 |
| #101 內部頁面解除遮罩 | 管理員 roster/orders canonical read 成功 | 列表、訂單卡與 Drawer 顯示未遮罩值，reload/切案件正常 | N/A | **BLOCKED** | `ui-staff.png`、`detail-orders-branches.png`、`detail-orders-normal-terms.png` | 未建立非管理員 authenticated session，不能證明同一敏感 read boundary 的拒絕。 |
| #102 月嫂名冊 API | roster API 成功，3 筆；nullable 欄位未造成 500 | 完整/缺值卡片可顯示 | response 不含 identity card、bank、emergency contact、admin notes | **PASS** | roster HTTP response、`ui-staff.png` | 禁止欄位檢查通過。 |
| #103 月嫂名冊 UI | 正常及強制 500 都有實跑 | 開啟、搜尋、reload 正常；500 顯示錯誤且卡片歸零 | N/A | **PASS_WITH_NOTE** | `detail-staff-search.png`、`detail-staff-forced-failure.png` | 未另做慢 response 時序；其餘核心 UI 行為通過。 |
| #104 接案偏好 ownership | focused contract/projection tests 14 passed | N/A | 六母題、一般欄位與來源欄位 ownership 分離 | **PASS** | focused test output、#99 DB readback | contract/runtime projection inspection。 |
| #111 自選期間營運報表 | 跨月與單日 inclusive；反向 400、缺日期 422；匯出成功 | default Thu→Wed 正常，匯出檔名一致；完全無資料區間仍顯示一筆資料 | N/A | **FAIL** | `operations-report-2026-08-30_2026-09-03.xlsx`、`detail-reports-empty-range.png`、`detail-reports-forced-failure.png` | 2035-01-01～01-07 仍出現 `115000001`。強制 failure 本身正確清空舊結果。 |
| #112 歷史月曆健檢 | 找不到可執行的正式 health-check API/command；近似 adapter tests 31 passed/1 failed | N/A | 未能由正式 health-check 證明零寫入 | **FAIL** | focused health/adaptor test output | 代表測試因 SQL shape/fixture drift 失敗；正式驗收入口缺失。 |
| #113 歷史月曆占用防漏 | 歷史 stage import、assignment projection 可查 | completed 與 in-service 顯示占用；unserved 不占月曆 | completed/in-service 各 1 assignment；unserved 0 | **PASS** | `detail-scheduling-july-completed.png`、`ui-scheduling.png`、`detail-scheduling-october-unserved.png`、DB readback | 未偽造未服務案 assignment。 |
| #114 歷史服務天數入口搬移 | Finance 路由存在，但代表歷史單查詢回 404 `historical_order_not_found` | 舊資料中心入口已移除；新頁顯示「歷史服務帳務資料未通過驗證」 | 匯入案缺 finance/payroll/payment terms/rate snapshot rows | **FAIL** | `detail-historical-accounting-query.png`、HTTP response、DB readback | 入口搬移完成，但核心服務天數功能不可用。 |
| #115 每週服務工時報表 | 期間 query 可執行 | 月曆有歷史服務中占用，但同期間工時頁顯示「此期間服務工時無資料」 | assignment 存在 | **FAIL** | `ui-scheduling.png`、`detail-reports-service-hours.png`、DB readback | UI 與正式排班資料不一致。 |
| #116 完全結案未完成元件 | current stage projection 可查，但無 exact `fully_closed` aggregate | 部分卡片存在 | 未形成全完成/缺單一 component 的完整 readback | **FAIL** | focused stage projection tests | 目前 checkout 不足以執行矩陣核心條件。 |
| #117 補助狀態顯示 | 找不到 per-order subsidy status/source/gap contract | 未能驗證三種代表狀態 | 無正式 owner readback | **FAIL** | current source/route inspection | 期待功能在目前版本缺失。 |
| #118 完全結案匯總 | current stage projection 有部分條件，缺 exact terminal aggregate | 未能逐步完成並 reload | 無全條件完成 readback | **FAIL** | focused stage projection tests | 不能證明只在全部 component 完成後結案。 |
| #119 補助篩選與清單 | 找不到 server-side subsidy count/filter/list contract | 無法做跨頁篩選/reload | 無混合 subsidy fixture readback | **FAIL** | current source/route inspection | 期待功能在目前版本缺失。 |
| #120 歷史／取消訂單完全結案 | Orders query 回傳 normal/historical/cancelled | 三類分支正確；filter 隔離；歷史/取消未顯示成正常主線 | 分類與 DB 狀態一致 | **PASS** | `detail-orders-branches.png`、`detail-orders-normal-filter.png`、`detail-orders-normal-terms.png` | 三張畫面已逐張人工判讀。 |
| #121 補助投影輸出 | 找不到 status/source/gap 正式 projection endpoint | N/A | 無 owner-source 對讀 | **FAIL** | current source/route inspection | 目前 checkout 無法執行要求的直接 GET。 |
| #122 人工意願記錄 | focused tests 支援 contract，但未跑正式持久化寫入 | 未做 reload | 無跨重送 DB readback | **BLOCKED** | focused candidate/willingness tests | `union_db` 缺完整 Beta 前置鏈；既有 seed 強制 `lu_test_dataset_*`，與不得另建 DB 衝突。 |
| #123 進件條款缺口與查詢 | 完整/缺件/locked focused contract tests 通過 | Drawer 可顯示缺口/待補正 | read-only projection 一致 | **PASS_WITH_NOTE** | focused terms tests、`detail-orders-normal-terms.png` | 未在本次 DB 建立完整三案；正式 read path 與 blocker 顯示可確認。 |
| #124 建立媒合方案 | focused tests 41 passed/1 message drift；未跑正式 Apply | 未做成功後 reload | 無方案 identity/防重 readback | **BLOCKED** | focused matching-plan output | 缺可安全延續的 Beta persisted prerequisite fixture。 |
| #125 查詢正式候選 | focused candidate contract tests 通過 | 未跑代表三類 Staff UI | 無 current persisted source readback | **BLOCKED** | focused candidate tests | 同上。 |
| #126 加入候選池 | contract tests 通過；未跑正式寫入 | 未 reload | 未驗證 pool row、重送與 outbox | **BLOCKED** | focused candidate-pool tests | 同上；未觸發真實通知。 |
| #127 候選池回讀 | contract tests通過；未完成跨 session persisted change | 未 reload/re-enter | 無跨 session readback | **BLOCKED** | focused candidate-pool tests | 同上。 |
| #128 進件條款回讀與錯誤 | contract tests通過；未跑真實 Apply/stale | 未驗證成功/失敗 UI | 無 version/confirmation readback | **BLOCKED** | focused terms tests | 同上。 |
| #129 意願回讀與防重複 | contract tests通過；未跑同操作重送 | 未驗證 | 無 effective-record count readback | **BLOCKED** | focused willingness tests | 同上。 |
| #130 進件條款 Preview/Apply | contract tests通過；未跑正式 Preview→Apply→stale→replay | 未驗證 | 無正式 terms/version readback | **BLOCKED** | focused terms tests | 同上。 |
| #131 候選聯絡狀態 | read projection focused tests 通過 | 未執行三狀態操作、reload、切案件 | 無 persisted state readback | **BLOCKED** | focused contact-state tests | 同上。 |
| #132 履歷推薦狀態 | delivery contract focused tests 通過 | 未執行狀態轉換/reload | 無重送 count readback | **BLOCKED** | focused delivery tests | 同上；未送外部訊息。 |
| #135 客戶決定 | decision contract focused tests 通過 | 未執行接受/拒絕/reload | 無 decision/reason persisted readback | **BLOCKED** | focused customer-decision tests | 同上。 |
| #138 月嫂契約入口 | contract-state focused tests 通過 | 未執行安全狀態轉換/reload | 無 persisted transition readback | **BLOCKED** | focused contract tests | 同上。 |
| #140 建立訂金鎖 | lock contract focused tests 通過 | 未跑正式 Preview/Apply | 無 lock identity/重送/stale readback | **BLOCKED** | focused lock tests | 同上。 |
| #151 異常中心掛載 | anomalies GET 連續回 500 | 直接 URL、側欄、reload、retry 都顯示「異常資料暫時無法取得」 | N/A | **FAIL** | `detail-anomalies-sidebar.png`、`detail-anomalies-reload.png`、`detail-anomalies-retry.png`、network log | 畫面有掛載但功能未成功。直接原因是 runtime 缺 anomaly cursor signing key。 |
| #152 LINE 欄位規則盤點 | current form/API/schema/runtime config 可追溯 | N/A | N/A | **PASS** | focused read-only inspection | 未把未決業務限制升格。 |
| #153 訂單缺件辨識與補件 | 缺件資料可辨識 | 代表案顯示「目前不可完成補件」、「案件已不在待補件狀態」 | 未寫入 | **FAIL** | `detail-orders-branches.png` | 缺 start_date/service_days 的歷史未服務案不能由正式入口補齊。 |
| #154 放寬自由輸入限制 | focused form/API contract tests 30 passed | 代表欄位規則由 current form 驗證 | N/A | **PASS_WITH_NOTE** | focused validation tests | 未另做完整手動提交；required/maxlength 與自由輸入規則測試通過。 |
| #155 canonical 固定格式驗證 | Preview/Apply schema focused tests 30 passed | N/A | N/A | **PASS_WITH_NOTE** | focused validation tests | 正式 schema/field-level contract 通過。 |
| #156 業務型驗證決策 | 找不到七類完整 business-owner decision evidence | N/A | N/A | **BLOCKED** | current canonical/source inspection | 依矩陣標 BLOCKED/NOT_VERIFIABLE；未替業務決策。 |
| #162 completed assignment 修復 | reuse、create、replay、stale 409 均以正式 preview/apply 實跑 | 月曆顯示 repaired/completed assignment | 只建立/重用 completed assignment；Orders 欄位、Payroll、Client Finance 不變；無重複 | **PASS** | `historical-162-repair.xlsx`、HTTP responses、DB readback、`detail-scheduling-july-completed.png` | stale preview 回 `historical_calendar_assignment_stale_preview`。 |

## Historical Workbook E2E

| Scenario | Result | Writes | Cancels | MySQL errno | Lock wait | Rollback | Evidence |
| -------- | ------ | -----: | ------: | ----------- | --------- | -------- | -------- |
| Current `union_db` stage matrix（補充） | **PASS_WITH_NOTE** | 預計/實際 adoption 4；assignment 2 | 預計/實際 0 | none | 未觀察到異常等待 | 否；同 key replay 無重複 | `historical-stage-matrix.xlsx`、preview/apply/replay、DB readback；建立 completed/in-service/unserved 多階段資料。 |
| A：空資料庫 | **NOT_RUN** | 0 | 0 | none | N/A | N/A | 使用者要求只用既有 `union_db`、不得另建 DB；目前 DB 非空。 |
| B：已有資料 | **FAIL** | 預計 4，實際 0（安全停止） | 預計 1，實際 0 | none | N/A | 未進 Apply | workbook 外 normal/cancelled/historical 存在時，preview 對外部正常單產生取消計畫；依 stop condition 未 Apply。 |
| C：Preview 後版本變動 | **PASS** | 預計/實際 0 | 預計/實際 0 | none | 代表性 request 414 ms | 是；HTTP 409 拒絕且狀態一致 | `historical-stale-matrix.xlsx`；另一 session version 1→2；舊 Apply 回 `historical_order_preview_stale`，receipt/assignment 0。 |
| D：工作簿外訂單取消範圍 | **FAIL** | 0 | 預計 1，實際 0 | none | N/A | 未進 Apply | code 對所有未出現在 workbook 的 non-cancelled order 規劃取消；找不到正式 contract 證明允許，已停止。 |

## Failed / Blocked Items

以下只列真正的 `FAIL` / `BLOCKED`；`PASS_WITH_NOTE` 不列入。

### #101 — BLOCKED

* 操作：管理員列表、Drawer、歷史/訂單代表頁與 reload 已實跑。
* Expected：非管理員不能取得同一敏感 read boundary 的未遮罩值。
* Observed：沒有非管理員 authenticated fixture/session，故此邊界未能可信驗證。
* 最直接 evidence：`ui-staff.png`、`detail-orders-normal-terms.png`。
* 資料副作用：無。
* Stop condition：否；必要權限 fixture 缺失。

### #111 — FAIL

* 操作：查詢 2035-01-01～2035-01-07 的完全無資料區間。
* Expected：明確 empty state。
* Observed：頁面仍顯示 legacy 歷史列 `115000001`。
* 最直接 evidence：`detail-reports-empty-range.png`。
* 資料副作用：無。
* Stop condition：否。

### #112 — FAIL

* 操作：尋找並執行正式只讀歷史月曆 health check。
* Expected：正式 entry point 可分類代表 fixture，且 before/after 零寫入。
* Observed：目前 checkout 無正式 API/command；最近似 adapter 驗證有 1 個 SQL shape/fixture drift failure。
* 最直接 evidence：focused health/adaptor test output。
* 資料副作用：無。
* Stop condition：否。

### #114 — FAIL

* 操作：由 Finance 入口查詢新匯入 completed 歷史單。
* Expected：原服務天數功能可用並可 readback。
* Observed：UI 顯示驗證失敗；API 404 `historical_order_not_found`；必要帳務 rows 不存在。
* 最直接 evidence：`detail-historical-accounting-query.png`、HTTP/DB readback。
* 資料副作用：無；未 Apply。
* Stop condition：否。

### #115 — FAIL

* 操作：查詢涵蓋 `RERUN-HIST-IN-SERVICE` 的每週服務工時。
* Expected：顯示與 assignment 相符的合理工時。
* Observed：排班月曆有占用，但報表顯示「此期間服務工時無資料」。
* 最直接 evidence：`ui-scheduling.png`、`detail-reports-service-hours.png`。
* 資料副作用：無。
* Stop condition：否。

### #116、#118 — FAIL

* 操作：定位 current terminal-close aggregate 並嘗試建立全完成/缺 component 驗證。
* Expected：缺項顯示 blocker，全部完成後才完全結案。
* Observed：目前 checkout 只有部分 stage projection，沒有可執行 exact `fully_closed` 條件的正式匯總輸出。
* 最直接 evidence：current source inspection、focused stage projection tests。
* 資料副作用：無。
* Stop condition：否。

### #117、#119、#121 — FAIL

* 操作：定位並呼叫補助狀態、server filter/list/count、projection source/gap。
* Expected：三個 current server-owned contract 可供 runtime 驗收。
* Observed：目前 checkout 找不到對應正式 route/contract；無法執行核心功能。
* 最直接 evidence：current source/route inspection。
* 資料副作用：無。
* Stop condition：否。

### #122、#124–#132、#135、#138、#140 — BLOCKED

* 操作：已執行對應 focused contract tests，並檢查正式 seed/fixture 路徑。
* Expected：正式 API + persisted DB 跑成功、重送、reload/readback；適用者另跑 stale/version。
* Observed：`union_db` 缺可安全延續的完整 Beta 前置鏈；正式 seed 限制 DB 名稱為 `lu_test_dataset_*`，但使用者禁止另建 DB。僅有 focused tests，不足以升格為實機 PASS。
* 最直接 evidence：candidate/willingness/terms/matching/contract/lock focused outputs；seed guard inspection。
* 資料副作用：無；未送外部通知。
* Stop condition：否；必要 fixture/environment blocker。

### #151 — FAIL

* 操作：直接 URL、側欄、reload、retry。
* Expected：同一功能頁成功取得資料；只有強制 API failure 才顯示 error state。
* Observed：所有正常入口都顯示「異常資料暫時無法取得」；GET 連續 500。runtime 缺 anomaly cursor signing key。
* 最直接 evidence：`detail-anomalies-sidebar.png`、`detail-anomalies-reload.png`、`detail-anomalies-retry.png`。
* 資料副作用：無。
* Stop condition：否。

### #153 — FAIL

* 操作：開啟缺 `start_date` / `service_days` 的歷史未服務代表案。
* Expected：由正式入口完成補件；成功後 reload 更新。
* Observed：UI 顯示「目前不可完成補件」、「正式排班或指派資料已形成」、「案件已不在待補件狀態」。
* 最直接 evidence：`detail-orders-branches.png`。
* 資料副作用：無；按鈕不可用。
* Stop condition：否。

### #156 — BLOCKED

* 操作：追查 O 字頭、phone、日期區間、60 天、zip、gender、中藥互斥七類 decision/source。
* Expected：已決項有 business-owner evidence，未決項維持未決。
* Observed：本環境找不到完整 business-owner decision evidence。
* 最直接 evidence：current canonical/source inspection。
* 資料副作用：無。
* Stop condition：否；不得由 Agent 代替業務決策。

### Historical Scenario A — NOT_RUN

* 操作：fresh empty DB bootstrap/import。
* Expected：空 DB 完整 E2E。
* Observed：使用者明確要求不得另建 DB，而既有 `union_db` 非空。
* 最直接 evidence：目前 DB 狀態與使用者指示。
* 資料副作用：無。
* Stop condition：是；環境限制。

### Historical Scenario B / D — FAIL

* 操作：在 workbook 外保留一筆 normal 與一筆 cancelled，再 preview historical import。
* Expected：workbook 外 normal 不會只因缺席就被取消，除非正式 contract 明確授權。
* Observed：preview 規劃取消 1 筆 workbook 外 normal；current code 選取所有缺席的 non-cancelled orders，找不到正式 contract 支持。
* 最直接 evidence：outside-order DB readback、preview response、current cancellation query inspection。
* 資料副作用：實際 writes 0、cancels 0；外部訂單維持原狀。
* Stop condition：是；停止 Apply，未 retry、未改 fixture、未加 flag。

## Final Decision

**REJECTED**

至少有以下可重現的 current runtime/data/UI defects：

* #151 異常中心正常載入即 HTTP 500，畫面顯示無法取得資料。
* #114 歷史服務帳務入口雖搬移，但代表歷史單查詢 404，功能不可用。
* #115 歷史服務中案件在月曆有占用，營運報表卻顯示無服務工時。
* #111 所謂完全無資料期間仍出現 legacy row。
* #153 代表歷史缺件案能被辨識，卻無法從正式入口完成補件。
* Historical Scenario B/D 會規劃取消 workbook 外正常訂單；因缺正式允許集合證據，已中止 Apply。

因此不能以「掛載成功」、「focused tests 通過」或「畫面不是白頁」替代核心成功路徑。#99、#102、#113、#120、#152、#162 等已取得充分 runtime/DB/UI 證據的項目仍維持通過，但不足以改變整體拒收結論。
