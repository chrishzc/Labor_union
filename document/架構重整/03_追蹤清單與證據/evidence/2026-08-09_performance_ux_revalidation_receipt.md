---
scope: 12_Global_效能與UX體感架構
status: verified-local-contract
verified_at: 2026-08-09
---

# Global 效能與 UX 體感重新驗證收據

## 追溯依據

- 規格基線：`01_規格基線/12_Global_效能與UX體感架構.md`
- Durable job 決策：`../../04_已完成與上線封存/superseded_specs/26_Durable_Job_Completion_Decision_Package.md`
- Worker supervision 決策：`41_Durable_Job_Worker_Supervision_Deployment_Decision.md`
- Global readiness：`../../04_已完成與上線封存/superseded_specs/46_Six_Remaining_Gaps_Completion_Architecture.md`

## 本次修復與驗證

- `ui.request_state` 現使用完整 typed read-state：`idle`、`loading`、`refreshing`、
  `success`、`empty`、`warning`、`error`、`stale`；generation 不符的舊 response 仍只記錄
  stale generation、不得覆寫新 request。
- Orders summary 在 stale cache refresh 前顯式標記 stale，新的 request 進入 `refreshing`；
  cached Query 仍只作 bounded read-view 加速，不參與正式 Apply。
- 新增 `test_performance_policies.py`，驗證只有 local display 可 optimistic success；
  cache identity 對 actor scope／facts version 改變；page size ≤200；single-flight、request
  supersession、background-job transition 與 payload budget 均 fail closed。
- Durable job 的 command identity、lease worker、typed status、at-least-once replay與 cache
  boundary 維持既有 shared-kernel／MySQL contracts；Finance Import UI job E2E 仍保留為需要
  disposable MySQL 的 gate。
- API timing 改為僅附在當次回應的 `Server-Timing`／`X-Response-Time-Ms`，不建立 telemetry
  資料表、不逐請求落庫，也不再輸出無上限 slow-request console log；cache telemetry 只保留
  程序內的固定計數，重啟即歸零。
- 效能 budget 已確認採 record-only：不顯示即時警告、不建立 anomaly、不影響 command 結果、
  不阻擋 release；僅在人工開啟效能快照時顯示彙總與量測層級。
- 系統管理員可於 Streamlit「🩺 系統狀態」查看 API memory snapshot；正式 API 使用
  `GET /api/v1/system/status/performance-snapshot` 與既有 `system.administration` capability，
  不要求 `admin.audit.read`。快照只有服務本次啟動後的 API 樣本數、平均、p50／p95 bucket
  上限與最大值，重啟即歸零，不含逐筆 request、URL、案件、人員或 payload。

## 本機驗收

```text
tests/test_performance_policies.py
tests/test_ui_request_state.py
tests/test_g15_cache_boundary_contract.py
tests/test_durable_job_worker.py
tests/test_background_job_repository_mysql.py
tests/test_assignment_plan_durable_job.py
tests/test_payroll_rebuild_durable_job.py
tests/test_staff_payout_durable_job.py
tests/test_government_subsidy_durable_job.py

31 passed, 4 skipped in 1.44s
```

另執行 UI request-state、cache-boundary 與 Finance Import UI job gate：
`6 passed, 1 skipped`；skip 均要求 explicit disposable MySQL，未使用 `.env`、`union_db`
或 target host。

本次 API timing boundary 與既有 performance policy 測試：`8 passed`。未連線資料庫，且測試
確認 GET 回應帶 timing headers、POST 維持 `no-store`、middleware 不輸出逐筆慢請求資料。

新增 bounded snapshot、system-admin route 與效能 middleware 聚焦驗證：`11 passed`。此測試只在
process memory 建立固定 latency buckets；沒有建立或查詢 telemetry 資料表。

## 外部驗收界線

本收據不把本機 unit／fixture timing 宣稱為 target-host latency evidence。HTTP/2／HTTP/3、
TLS、connection reuse 與 Task Scheduler installation 已依決策 53 退出產品設定與 release
gate；部署者可在系統外自行評估。可重跑的 payload/query/lock/job-lag 與 worker recovery
行為仍以本機隔離測試驗證。
