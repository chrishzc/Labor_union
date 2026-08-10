# Global 效能與 UX 體感架構

## 1. 定位

本文件在不破壞業務正確性、Preview／Apply、append-only、idempotency 與交易原子性的
前提下，從「前端體感」、「網路傳輸」與「後端計算」三個關卡改善使用者體驗。

效能不是繞過 Domain 規則的理由。任何快取、樂觀顯示、背景工作或 transport optimization
都只能加速既有 typed contract，不能形成第二套 SSOT、第二套計算或隱藏 fallback。

## 2. 效能根事實與量測

效能判斷只使用可量測 evidence：

- browser／Streamlit interaction timing；
- API server timing、status、payload bytes 與 correlation id；
- DB query count、duration、rows examined 與 lock wait；
- cache hit／miss／age／invalidation reason；
- background job queued／started／completed time；
- projector／outbox lag；
- compression response behavior 與 payload evidence；部署協定由部署者在系統外自行處理。

「感覺很快」、開發機單次測量、mock timing 或 console print 不是 release evidence。
正式效能 budget 必須按可重跑的本機隔離環境保存；不得用單次開發機測量冒充 Global
invariant。target-host／edge latency 不屬產品設定或 release gate。

效能量測不得建立逐請求 telemetry 資料表、不得把 request／response payload 或逐筆 timing
寫入資料庫，也不得輸出無上限的 slow-request console log。API 僅在當次回應附
`Server-Timing` 與 `X-Response-Time-Ms`；cache telemetry 僅為程序記憶體中的固定計數，
程序重啟即歸零。可重跑 benchmark 的彙總結果以有限 evidence artifact 保存，不是長期
operation log；工作單、receipt、outbox 等業務稽核資料不屬效能 telemetry，仍依各自資料
生命週期保存。

效能 budget 採 record-only：只供人工在效能快照檢視與比較，不顯示即時警告、不建立 anomaly、
不影響 command 結果，也不阻擋 release。每一筆彙總仍標示量測層級（UI、API、DB、cache 或
job），使人工需要改善時可辨識方向。

### 2.1 管理端查看入口

系統管理員在 Streamlit 導覽列開啟「🩺 系統狀態」，由
`GET /api/v1/system/status/performance-snapshot` 讀取記憶體快照。此 read-only endpoint 使用
既有 `system.administration` capability，不要求 `admin.audit.read`。目前畫面顯示 API service
本次啟動後的樣本數、平均、p50／p95 的固定 latency-bucket 上限及最大值；它不顯示 URL、
案件、人員、request／response payload 或逐筆 timestamp。服務重啟後快照歸零，因此它不是
歷史趨勢報表；cache、DB 與 job 的可重跑彙總則隨各 benchmark evidence artifact 人工比較。

## 3. 前端關卡：先回應，再取得權威結果

### 3.1 UI 狀態模型

每個 Query／Preview／Apply 元件使用明確 typed UI state：

```text
idle
→ loading
→ success | empty | warning | error
success --背景 refresh→ refreshing
success --版本落後→ stale
```

- route shell、標題、篩選器與已知 layout 先 render，資料區使用 skeleton／placeholder。
- 點擊後的 loading／pending feedback 必須在等待 network response 前先進入前端 render
  state；不得等 API 完成後才第一次改變畫面。
- 不以空 list 冒充 loading，不以 spinner 覆蓋可繼續閱讀的既有資料。
- refresh 時保留上一份標示為 stale 的 view，收到新版本後原子替換。
- typed error 保留使用者草稿、correlation id、可否 retry 與合法下一步。

### 3.2 Optimistic UI 邊界

可以立即更新：

- 分頁、展開／收合、排序、篩選、local draft、尚未送出的勾選與欄位內容；
- skeleton、pending badge、按鈕 single-flight 狀態；
- 可由 server receipt 完整還原、且不代表業務完成的純顯示偏好。

不得先顯示成功：

- Orders Terms／Actual Start／Cancellation／Reopen Apply；
- assignment、leave／substitution、waiting lock 或 buffer Apply；
- 收款、付款、退款、adjustment、reversal、帳務修正與核銷；
- Alert claim／resolve；
- Accounts Payable archive、正式匯入或 database cutover。

上述權威命令按下後可立即顯示「處理中」，但只有收到成功 receipt 才能顯示已完成。
timeout 不等於失敗；前端以相同 idempotency key Query receipt／retry，不得產生第二個命令。

### 3.3 防連點與過量請求

- Submit 使用 single-flight：同一 command identity 在完成前只能有一個 in-flight request。
- 按鈕 loading 時停用重複 submit，但保留取消尚未送出的 local draft 能力。
- Search／filter 使用 debounce；scroll、resize、calendar hover 等高頻事件使用 throttle。
- debounce／throttle interval 是前端 performance policy，不得硬編碼散落各頁；由集中設定、
  使用者測試與 production telemetry 調整。
- request 被新 Query 取代時應取消或忽略舊 response；不得讓較舊 response 覆蓋新 view。

Streamlit 先使用 placeholder、`session_state` 的 local draft／stable idempotency identity、
集中 API client 與明確 loading state；未來替換前端沿用同一 server contract。

## 4. 網路關卡：傳最少且可快取的 typed data

### 4.1 Payload contract

- Summary、list、detail、Preview 與 Apply receipt 使用不同 ViewModel；不得以一個巨大
  response 滿足所有頁面。
- List 預設 cursor pagination、穩定排序與 bounded page size；不得一次傳回整表。
- 大型 timeline、audit、Excel report 明細使用獨立 endpoint／export，不嵌入 summary。
- API 只回 UI 需要的 typed fields；不得傳 raw bank payload、完整帳號、secret 或 UI 不使用
  的 legacy columns。
- response 支援壓縮；payload bytes、serialization time 與 DB query count 納入 telemetry。
- 不提供任意 client-selected SQL fields；欄位集合由 versioned response contract 控制。

### 4.2 Connection／protocol

- HTTP/1.1 request／response 與 compression negotiation 必須正確；應用程式業務語意不得
  依部署協定改變。
- reverse proxy、keep-alive、HTTP/2、HTTP/3、TLS、UDP 與 connection reuse 是部署者可選的
  外部基礎設施優化，不保存為 deployment profile，也不是產品 release gate。

### 4.3 Conditional query

- 可重建 Query ViewModel 可使用 `ETag`／version token 與 `If-None-Match`。
- `304 Not Modified` 只節省 payload，不取代 Domain version 檢查。
- Preview／Apply request、typed errors、receipts 與財務明細不得被 shared proxy cache。

## 5. 後端關卡：Query read model、受控快取與索引

### 5.1 Query path

- Query 使用專用 read model／projection，不在 request path 觸發狀態轉移或全域 rescan。
- 所有 list／search query 都必須 bounded、可分頁，並以真實 MySQL `EXPLAIN`／實測驗證索引。
- 避免 N+1；跨 Domain 顯示由 Query assembler 批次載入 typed views。
- 高成本但可重建的 summary 由 outbox projector 增量更新，不在每次頁面載入時計算全歷史。

### 5.2 Cache policy

可以快取：

- immutable static assets；
- 已遮蔽、具授權範圍的 Query ViewModel；
- 由完整 facts version、contract version、actor permission scope 與 canonical input
  組成 key 的 pure Preview 計算結果；
- bounded reference data。

禁止快取成正式依據：

- Apply authorization、row lock result、current balance、可接案結果、可付款結果；
- idempotency receipt 的唯一權威；
- Alert blocker predicate；
- database cutover identity／freshness；
- 任何 canonical bank fact、ledger 或 assignment root fact 的可寫副本。

Apply 永遠鎖定 fresh facts，使用相同 candidate builder 重算並驗證 version／fingerprint；
即使 Preview 命中 cache 也相同。Cache miss、eviction 或 Redis unavailable 只能降低速度，
不得改變結果或阻擋核心正確流程。

Cache key 必須包含 identity、授權範圍、facts／aggregate version、contract version 與
locale／timezone 等會改變輸出的欄位。採 cache-aside、bounded TTL、Domain event
invalidation、single-flight／request coalescing 防止 cache stampede。財務、排班與權限
敏感 view 不使用未標示的 stale-while-revalidate；若顯示舊 view，UI 必須明確標示 stale。

Redis 是可選 infrastructure adapter，不是初始必要依賴。先以測量證明重複高成本 Query
值得快取，再引入外部服務；單機 in-process cache 也必須遵守相同 key／invalidation contract。

## 6. 長任務：202 Accepted 與 durable job

適合背景化：

- PDF／XLSX／大型 report 產生與 archive；
- Email、LINE 或外部通知；
- historical scan／reprocess report；
- anomaly bounded rescan；
- projector catch-up；
- 不要求使用者同步等待的外部整合。

核心 Apply 不因「可能較慢」就拆成多個非原子背景步驟。若完整 Finance Import Apply、
Accounts Payable Export 或其他單一原子 command 經量測確實超過互動 request budget，
API 可先建立 durable command job 並回：

```text
202 Accepted
job_id
command_identity
status_url
retry_after
correlation_id
```

Worker 仍必須執行原本同一個 application command／outer Unit of Work；不能把 ledger、
allocation、lifecycle 或 receipt 拆成多次 commit。

Job lifecycle：

```text
queued → running → succeeded | failed
queued → cancelled
```

- `succeeded` 必須連結正式 command receipt；`failed` 保存 typed error，不偽造業務成功。
- queued job 可取消；running job 只有在 application command 尚未進入不可中斷交易且能
  證明零副作用時才可取消。
- Queue 採 at-least-once delivery；worker 以 command idempotency identity 防重。
- 前端以 bounded polling＋backoff／jitter 為基準；SSE／WebSocket 只是完成通知優化，
  job repository 才是狀態 SSOT。
- worker crash、duplicate delivery、notification loss 或 WebSocket disconnect 不得重複
  正式交易，也不得讓 job 永遠顯示假成功。

Accounts Payable async export 仍須先產生一次 XLSX bytes、完成 archive 與 hash 驗證，
再把同一 bytes 提供下載；202 不改變既有 archive invariant。

## 7. Modules／Ports

Modules：

- `UiOperationPolicy`
- `OptimisticDisplayEligibility`
- `SingleFlightCommandIdentity`
- `RequestSupersessionPolicy`
- `ApiViewModelProjection`
- `CursorPaginationPolicy`
- `PayloadBudgetPolicy`
- `ConditionalQueryVersion`
- `CacheKeyBuilder`
- `CacheEligibilityPolicy`
- `CacheFreshnessPolicy`
- `CacheInvalidationIntent`
- `BackgroundJobLifecycle`
- `BackgroundJobReplayPolicy`
- `PerformanceBudgetEvaluator`

Ports：

- `QueryCachePort`
- `PerformanceTelemetryPort`
- `BackgroundJobRepository`
- `BackgroundJobQueuePort`
- `JobCompletionNotificationPort`
- `DomainProjectionFreshnessPort`

## 8. Typed results／errors

Async accepted result：

- `job_id`
- `command_identity`
- `status`
- `status_url`
- `retry_after`
- `correlation_id`

Stable errors：

- `payload_too_large`
- `page_size_invalid`
- `query_budget_exceeded`
- `cache_contract_violation`
- `job_not_found`
- `job_identity_conflict`
- `job_state_conflict`
- `job_queue_unavailable`
- `job_result_unavailable`
- `request_superseded`
- `performance_dependency_unavailable`

Cache unavailable 對核心 Query 應 fallback 至正確 bounded source query；DB、queue 或必要
worker unavailable 才回 typed unavailable。UI 不得依 error message 字串決定 retry。

## 9. 驗收

### Module

- optimistic eligibility 不允許任何正式 Apply 先顯示成功。
- cache key 對 actor scope、facts version、contract version 或 timezone 任一變更都不同。
- cursor、payload projection、job transition 與 retry/backoff deterministic。

### Subsystem

- skeleton／loading／stale／error 不互相冒充。
- click handler 在 await network 前先產生 loading／pending state。
- 連點十次只送一個 command identity；timeout retry 沿用同一 idempotency key。
- 舊 Query response 晚到不覆蓋新 Query。
- cache hit／miss／eviction／invalidation 回傳相同業務結果。
- Redis unavailable 時 bounded Query 正確 fallback。
- job duplicate delivery、worker crash 與 notification loss 不重複正式 command。
- Accounts Payable async archive bytes 與下載 bytes 完全相同。

### Domain

- Orders、Scheduling、Finance、Payroll、Payables 的 Apply 在所有 cache 狀態下都 fresh
  rebuild，stale Preview 固定 conflict。
- Query read model／cache lag 不改變 Domain blocker。
- 202 job 最終 receipt 與同步執行同一 command 的結果一致。

### Global／UX

- 實際頁面驗證 first feedback、skeleton、loading、empty、stale、success、typed error。
- 真實 MySQL 與真實格式 Excel 下量測 Query、Preview、Apply、export、projector lag、
  payload bytes、query count、lock wait 與 job latency。
- 不要求 HTTP/2／HTTP/3 或 target-host 協定 evidence；部署者可在系統外量測其選用的
  基礎設施。
- 建立可重跑本機隔離環境的 baseline 與 record-only budget；彙總結果標示 frontend、
  backend、DB lock 或 background queue 的量測層級，供人工檢視，不以取消正確性檢查換取
  通過。

## 10. 實作順序

1. Slice 0 建立 telemetry、payload projection、pagination、single-flight、cache／job ports；
   Redis、WebSocket、SSE 與 HTTP/3 不作初始強制依賴。
2. 各 Domain Query 建立 bounded read models、version token、必要 indexes 與 query budgets。
3. Streamlit 先完成 skeleton／placeholder、loading state、draft preservation、single-flight
   與 request supersession。
4. 以實測選出高成本重複 Query，再逐一加入 cache；每一項都要有 invalidation test。
5. 以實測選出超過互動 budget 的 report／export／scan，再導入 durable job。
6. API 維持 compression negotiation 與 HTTP/1.1 相容；proxy／HTTP/2／HTTP/3 由部署者
   在系統外自行評估，不能阻擋產品 release。

不得在缺少 baseline 時先部署 Redis、queue 或 WebSocket，避免把基礎設施複雜度當成效能
成果。
