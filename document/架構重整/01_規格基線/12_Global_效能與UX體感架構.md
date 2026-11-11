# Global 效能與 UX 體感架構

## 1. 文件邊界與所有權

- 狀態：`current-spec`
- Owner：Global UX / Performance Architecture
- 單一負責範圍：管理端前端互動體感（UI state、防連點、離頁與草稿保護、資訊層級降噪）、網路 payload／快取契約與 202 長任務架構；不擁有個別業務頁欄位或 Domain 規則。
- 關聯引用：見 [Global 共同契約](00_Global_共同契約.md)、[Global Entry Point Governance](19_Global_Entry_Point_Governance.md)、[案件與月嫂整合名冊正式規格](33_案件與月嫂整合名冊正式規格.md)

效能不是繞過 Domain 規則的理由。任何快取、樂觀顯示、背景工作或 transport optimization 都只能加速既有 typed contract，不能形成第二套 SSOT、第二套計算或隱藏 fallback。

## 2. 效能根事實與量測

效能判斷只使用可量測 evidence：browser／React interaction timing、API server timing／payload bytes／correlation id、DB query count／duration／rows examined／lock wait、cache hit／miss／age／invalidation reason、background job queued／started／completed time、projector／outbox lag 與 compression response behavior。

- 效能量測不得建立逐請求 telemetry 資料表、不得把 request／response payload 或逐筆 timing 寫入資料庫，也不得輸出無上限的 slow-request console log。
- API 僅在當次回應附 `Server-Timing` 與 `X-Response-Time-Ms`；cache telemetry 僅為程序記憶體中的固定計數，程序重啟即歸零。
- 效能 budget 採 record-only：只供人工於本機可重跑快照檢視與比較，不顯示即時警告、不建立 anomaly、不影響 command 結果，也不阻擋 release。

### 2.1 系統效能快照查詢入口

獨立 `system-status` 頁面已不在正式導航內，但 `GET /api/v1/system/status/performance-snapshot` 與右上角狀態指示器仍保留。API 快照只包含本次啟動後的樣本數、平均、p50／p95 的固定 latency-bucket 上限及最大值；不包含 URL、案件、人員、request／response payload 或逐筆 timestamp。

## 3. 前端關卡：先回應，再取得權威結果

### 3.1 UI 狀態模型

每個 Query／Preview／Apply 元件使用明確 typed UI state：

```text
idle → loading → success | empty | warning | error
success --背景 refresh→ refreshing
success --版本落後→ stale
```

- route shell、標題、篩選器與已知 layout 先 render，資料區使用 skeleton／placeholder。
- 點擊後的 loading／pending feedback 必須在等待 network response 前進入前端 render state，不以空 list 冒充 loading，不以 spinner 覆蓋可閱讀的既有資料。
- refresh 時保留上一份標示為 stale 的 view，收到新版本後原子替換；typed error 保留使用者草稿、correlation id、可否 retry 與合法下一步。

### 3.2 Optimistic UI 邊界

可以立即更新：分頁、展開／收合、排序、篩選、local draft、尚未送出的欄位內容、skeleton、pending badge、按鈕 single-flight 狀態，以及可由 server receipt 還原的純顯示偏好。

不得先顯示成功（按下後僅可顯示「處理中」，收到成功 receipt 才顯示完成）：

- Orders Terms／Actual Start／Cancellation／Reopen Apply；
- assignment、leave／substitution、waiting lock 或 buffer Apply；
- 收款、付款、退款、adjustment、reversal、帳務修正與核銷；
- Accounts Payable archive、正式匯入或 database cutover。

timeout 不等於失敗；前端以相同 idempotency key 查詢 receipt／retry，不得產生第二個命令。

### 3.3 防連點與過量請求

- Submit 使用 single-flight：同一 command identity 在完成前只能有一個 in-flight request，loading 時停用重複 submit。
- Search／filter 使用 debounce；scroll、resize、calendar hover 等高頻事件使用 throttle，區間由集中 performance policy 管理。
- request 被新 Query 取代時應取消或忽略舊 response；React 元件以 local draft 與 stable idempotency identity 搭配 typed API client 運作。

### 3.4 資料中心資訊架構

資料中心包含 `資料匯入` 與 `NAS 檔案` 等分頁，日常個案與人員資料維護收斂於以 `case_no` 為中心的客戶名冊與以 `staff_id` 為中心的月嫂名冊，並可經 [Entry Point Governance](19_Global_Entry_Point_Governance.md) 定義之路由與 alias 進入。

- 分頁切換屬 local navigation，不得重送 mutation、清空未送出草稿或讓舊 response 覆蓋新分頁；tab／tabpanel 需具可程式判讀之焦點與 selected state。
- NAS 介面僅維持資料夾與檔案名稱的檔案總管式投影，不在畫面另列層級、用途、所屬案件／人員、版本、大小、更新時間、實體 NAS path、digest 全值、Preview fingerprint 或 raw cursor。

### 3.5 管理端未儲存變更與離頁

主選單、分區、Hash／歷史導航、登出、會卸載編輯內容的分頁、切換資料對象及關閉抽屜前，若存在未儲存草稿差異（不含搜尋、篩選、純預覽選項及已還原為原值的欄位），須顯示欄位名稱與變更前後內容，提供儲存、明確捨棄或繼續編輯。

- 帳務相關儲存頁採單擊儲存、原因選填；離開提示的儲存按鈕須呼叫同一正式儲存流程並確認回讀後才離開。多份未儲存表單由人員回原表單分別完成，不批次提交不同 owner。
- 實際 in-flight 與請求結束後的 outcome unknown／readback failed 必須分開：後兩者於同一 React session 站內切頁不鎖死整頁；既有操作 store 保留案件、方案、actor、原命令 key、payload、收據及錯誤。「捨棄輸入並離開」只捨棄未提交草稿，不取消或重送待核對命令。
- 切頁後抵達的結果仍更新原案件 store，不污染其他案件或帳號。重新整理、關頁與離站使用瀏覽器原生離頁警告；敏感欄位僅提示已修改，不複製明文進警告內容。草稿僅存於當次 React 記憶體。

## 4. 網路關卡與資料可見邊界

### 4.0 內部完整值與外部安全邊界

- 已認證、enabled 且具對應 owner permission 的工會內部管理 UI，對畫面實際需要的一般業務資料（以及 verified applicant 查看自己 owner scope 的自助 readback）直接呈現 owner typed Query 提供的完整一般業務值，不使用局部姓名／電話／地址遮罩。
- 完整值顯示仍受 bounded ViewModel、cursor pagination、rate limit、audit、capability 與 server-side filtering 約束。
- credential、secret、完整銀行帳號驗證輸入以外的一般查詢投影（依各 owner 規範）、raw provider payload、NAS 實體 locator 與 raw error／log／receipt／evidence 仍嚴禁穿透 UI。

### 4.1 Payload、協定與條件查詢

- Summary、list、detail、Preview 與 Apply receipt 使用不同 ViewModel；List 預設 cursor pagination、穩定排序與 bounded page size。
- 大型 timeline、audit、Excel report 明細使用獨立 endpoint／export；API 僅回 UI 需要的 typed fields，不支援 client-selected SQL fields。
- 應用程式業務語意不依 HTTP/1.1、HTTP/2、HTTP/3、reverse proxy 或 TLS 設定改變；部署架構細節由部署者自行處理。
- 可重建 Query ViewModel 可用 `ETag`／`If-None-Match` 搭配 `304 Not Modified` 節省傳輸，但不取代 Domain version 檢查；Preview／Apply、typed errors、receipts 與財務明細禁止 shared proxy cache。

## 5. 後端關卡：Query read model 與受控快取

- Query 使用專用 read model／projection，不在 request path 觸發狀態轉移或全域 rescan；list／search 均須 bounded 並經 MySQL `EXPLAIN` 驗證索引；高成本 summary 由 outbox projector 增量更新。
- 可快取：immutable static assets、具授權範圍與版本 key 的 Query ViewModel、pure Preview 計算結果與 bounded reference data。
- 禁止快取成正式依據：Apply authorization、row lock、current balance、可接案／可付款結果、idempotency receipt 權威、Cutover identity 或任何 root fact 可寫副本。Apply 永遠鎖定 fresh facts 重算。
- Cache key 必須包含 identity、授權範圍、facts／aggregate version、contract version 與 timezone；採 cache-aside、bounded TTL、Domain event invalidation 與 single-flight。Redis 為可選 adapter，cache miss／unavailable 不得阻擋核心正確性。

## 6. 長任務：202 Accepted 與 durable job

當單一原子 command 經量測超過互動 request budget（如大型報表匯出、批次匯入掃描、外部通知、projector catch-up）時，API 可建 durable command job 並回傳 `202 Accepted`（含 `job_id`、`command_identity`、`status_url`、`retry_after`、`correlation_id`）。

- Worker 仍須執行原本同一個 application command 與單一 outer Unit of Work，不得拆成多個非原子 commit。
- Job 生命週期為 `queued → running → succeeded | failed`（或 `queued → cancelled`，僅限未進入不可中斷交易時）；`succeeded` 連結正式 receipt，`failed` 保存 typed error。
- Queue 採 at-least-once delivery，以 command idempotency identity 防重；前端採 bounded polling＋backoff／jitter，job repository 為狀態 SSOT。
- Accounts Payable async export 須先產生一次 XLSX bytes、完成 archive 與 hash 驗證後再提供下載。

## 7. Modules、Ports 與 Typed errors

- Modules：`UiOperationPolicy`、`OptimisticDisplayEligibility`、`SingleFlightCommandIdentity`、`RequestSupersessionPolicy`、`ApiViewModelProjection`、`CursorPaginationPolicy`、`PayloadBudgetPolicy`、`ConditionalQueryVersion`、`CacheKeyBuilder`、`CacheEligibilityPolicy`、`CacheFreshnessPolicy`、`CacheInvalidationIntent`、`BackgroundJobLifecycle`、`BackgroundJobReplayPolicy`、`PerformanceBudgetEvaluator`。
- Ports：`QueryCachePort`、`PerformanceTelemetryPort`、`BackgroundJobRepository`、`BackgroundJobQueuePort`、`JobCompletionNotificationPort`、`DomainProjectionFreshnessPort`。
- Stable errors：`payload_too_large`、`page_size_invalid`、`query_budget_exceeded`、`cache_contract_violation`、`job_not_found`、`job_identity_conflict`、`job_state_conflict`、`job_queue_unavailable`、`job_result_unavailable`、`request_superseded`、`performance_dependency_unavailable`。Cache unavailable 應 fallback 至 bounded source query。

## 8. 預設資訊層級與 UX 驗收

1. **業務降噪原則**：日常業務頁預設只呈現操作者需要的根事實、業務狀態、阻擋原因、影響範圍與下一步。`preview_fingerprint`、receipt/correlation/idempotency key、job UUID、內部 aggregate/domain version、source identity、raw enum／JSON 與 replay 旗標，一律收斂於 typed contract、稽核或預設收合的「技術詳情與資料來源」區塊，不得暴露於一般成功訊息、卡片或操作文案。
2. **外部狀態誠實**：成功訊息採「已排入／處理中／已完成並回讀」業務語意；外部 provider 工作僅顯示「已排入，尚未代表送達／發布完成」。
3. **錯誤與權限邊界**：頁面與 provider render／lazy-load 失敗隔離於 `MasterLayout` 內容區，切換頁面可重置該內容邊界而不鎖死導覽或清除登入；唯目前人員 Bearer 收到 401 時立即清除同一 token 並返回登入頁（晚到 401、403、5xx 或不同 service token 不誤登出）。禁止展示 raw exception／stack trace／HTTP detail。
4. **效能與一致性驗證**：驗證 click 後立即進入 loading state、連點十次僅送單一 command identity、舊 Query 晚到不覆蓋新視圖、cache hit/miss/unavailable 回傳一致結果、202 job 重複投遞與 worker crash 不重複交易，以及隔離環境真實 MySQL／Excel 量測之 record-only budget。
