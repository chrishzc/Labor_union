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

### 3.4 資料中心資訊架構（2026-08-25 人工裁決）

管理端以單一「資料中心」作為營運區入口，取代側邊欄分離的「資料匯入」與「數據瀏覽」。
入口內固定提供三個同層分頁：

1. `NAS 檔案`：以接近檔案總管的簡單投影顯示資料夾與其中的檔案；
2. `資料匯入`：完整保留既有 HCM、Client BeClass、Staff historical、Historical Orders 與其他
   owner-specific typed Preview／Apply 匯入流程；
3. `數據瀏覽`：完整保留既有六來源去敏、唯讀 Query 與明細抽屜。

2026-08-27 人工已將「工會內部管理 UI 的一般業務資料去敏」改為完整值顯示；上列「去敏」是施工前
現況描述，不再是目標契約。後續由
`PROV-20260827-internal-admin-ui-unmasked-display-spec-gap.md` 逐 surface 固定 permission、完整值欄位與
負向驗收後分批替換。未完成該 package 前不得以臨時前端反遮罩、raw payload 或擴大 Query 欄位繞過
typed owner contract。

分頁切換屬 local navigation，不得重送 mutation、清空尚未送出的合法草稿或讓舊 response 覆蓋新分頁。
每個分頁使用可程式判讀的 tab／tabpanel 關聯、鍵盤焦點與明確 selected state。NAS 分頁目前只規劃
資料夾與檔案名稱的檔案總管式投影；不在畫面另列資料夾層級、用途、所屬案件／人員、版本、大小、
更新時間或異常狀態等管理欄位。後端為安全讀取、對帳與版本治理所需的 metadata 仍由正式 storage
契約管理，但不因此成為 UI 顯示需求。版型、互動與視覺細節等待使用者另行提供介面設計；本次只
固定資料中心入口、三分頁與資料夾／檔案投影概念，不授權先行實作。一般畫面不得顯示實體 NAS path、
digest 全值、Preview fingerprint、raw cursor 或其他非業務必要雜訊。

## 4. 網路關卡：傳最少且可快取的 typed data

### 4.0 內部完整值與外部安全邊界（2026-08-27 人工裁決）

- 已認證、enabled 且具對應 owner permission 的工會內部管理 UI，對畫面實際需要的一般業務資料使用
  canonical 完整值，不再以遮罩防止內部人員查看。
- 完整值顯示不等於 unrestricted dump：API 仍只回該 ViewModel 需要的 typed fields，維持 cursor
  pagination、bounded page size、rate limit、audit、download/export capability 與 server-side filtering。
- LINE 對客／群組訊息、Client／Staff LIFF、自助／公開頁面仍依各自 recipient 與 privacy 契約，不受本
  裁決自動改成完整值。
- credential、secret、完整銀行驗證資料、raw provider payload、NAS 實體 locator、raw error／log／receipt／
  evidence 與純技術 identity 不是「一般 UI 去敏」範圍，仍禁止顯示。
- 每個既有 masked surface 必須先盤點 API owner、permission、欄位、copy/export/download、cache 與測試，
  再由 bounded package 修改；不得以 browser-side unmask、額外 raw endpoint 或 client-selected fields 實作。

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

- 2026-08-25 人工裁決：日常業務頁的預設資訊層級只呈現操作者需要的根事實、業務狀態、
  阻擋原因、影響範圍與下一步。Preview 應以可理解的變更前後內容與業務影響呈現；不得把
  `preview_fingerprint`、receipt identity／key、correlation／idempotency key、job UUID、內部
  aggregate／domain version、source identity、raw enum／JSON 或 replay 旗標直接顯示為一般
  成功訊息、摘要、卡片或確認條件。
- 上述技術欄位仍必須保留在 typed contract、Apply fresh-fact 驗證、receipt／readback、稽核
  或明確標示且受權限控管的「技術詳情／系統狀態」中；隱藏一般畫面雜訊不得刪除安全檢查、
  交易證據或人工 recovery 能力。法律文件版本、案件編號、可供業務辨識的申請／待辦編號，
  只有在辨識、下載、追蹤或客服溝通確實需要時才可保留。
- 成功訊息使用「已排入／處理中／已完成並回讀」等業務語意；外部 provider 工作僅能顯示
  「已排入，尚未代表送達／發布完成」，不得以 task／receipt 存在冒充外部成功。
- UX 收斂進度（2026-08-26）：LINE Rich Menu 一般畫面已移除 `typed action`、`server Preview`、
  provider request、Diff Mode、Active DB Snapshot、Before 與內部草稿 revision；Chrome 實點保留
  本機預覽、明確業務 blocker 與零發送邊界。Staff 名冊搜尋零結果改顯示可清除的明確空狀態；
  接案狀態 Drawer 對已取消紀錄明示「不可再次取消」，未填取消原因、資料已變更或操作進行中也以
  業務語意說明 disabled 原因，不以隱藏舊分頁作為驗收入口。
  Orders 媒合工作台的 delivery raw enum 改由 adapter closed label 投影，並將 reliable task、binding、
  assignment-plan、Customer Decision 與原 Key 等工程文案改為排入／身分核對／正式分段／客戶決定／
  安全重試等業務語意。營運報表已移除 server typed view 與內部資料版本；排班頁已將 Server Projection、
  backend／Official Schedule 與可靠佇列改為正式資料檢查、正式排班與 LINE 通知業務語意。Finance 案件與
  服務人員選單必須累積所有 typed 分頁，不得把前 200／20 筆當全集；收款查詢不顯示缺失結清欄位的技術
  占位，付款狀態與事件使用 closed business labels，未知值固定顯示待確認；Finance Import blocking code
  只顯示 closed 業務原因，案件、收款、人員、付款、工作簿、Preview、Apply 與結果查詢的失敗也只能依
  authentication／authorization／stale／conflict／unavailable 與本機檔案類型投影 closed 業務訊息，不得
  顯示 raw transport、schema、HTTP、correlation 或 provider detail。Anomalies 過濾技術識別後不得留下空白卡片；沒有通用 Resolve owner 時顯示
  常駐處理說明，不渲染永久 disabled 假按鈕，detail／recovery 錯誤也不得顯示 context／identity／job／
  receipt 等內部術語；timeline action、未知匯入 lane 與未知追蹤狀態固定使用 closed 業務標籤，raw enum
  只保留於 typed contract／稽核。Data Browser 只呈現六來源去敏清單、業務欄位詳情、分頁與複製；不得
  顯示 fingerprint、row／source／field identity、version、raw JSON、`loaded scope`、資料庫快照或永久 disabled
  假更正控制，並須常駐顯示資料修正應回到對應業務頁面的理由。System Status 一般畫面以服務啟動時間、
  測量次數與可理解的回應時間呈現，不顯示 server snapshot、p50／p95、`ms` 或 raw transport error；未登入
  仍須保留可操作的 closed 登入指引。Account Center 只呈現帳號、顯示名稱、啟用狀態與 root 管理權限；
  account id、access-control version、audit raw action／reason code、job UUID 與 raw command/status 只留在
  typed contract／命令安全邊界。合法 403 必須明示「僅唯一啟用 root 可管理」，不得以 generic disabled
  或任意 server message 取代。本項仍為 `in-progress`，
  不代表其他頁面已完成全站盤點。
- 實際頁面驗證 first feedback、skeleton、loading、empty、stale、success、typed error。
- Anomalies 的分類、Preview、Apply、Drawer 關閉與背景篩選若因正式 action、未填理由、尚未 Preview、
  Preview 失效、提交中或結果確認中而不可操作，必須常駐顯示 closed 業務原因並以
  `aria-describedby` 關聯控制。已進入追蹤編輯後，不保留永久 disabled 的「開啟」按鈕。
- React 人員 Session 的目前 Bearer 收到 401 時，必須清除同一 token 並立即卸載受保護 shell、返回登入頁；
  晚到舊 token 的 401、未帶 token 的登入挑戰、403、network／5xx 與不同 service token 不得誤登出。
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
