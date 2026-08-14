# Orders Domain

## 1. Domain 責任

Orders 擁有：

- `case_no` 訂單識別；
- Order Terms：`start_date`、`service_days`、`service_hours_per_day`、`requires_cooking`、`floor_fee`、統一服務時段三欄；
- `actual_start_date` 的首次確認與更正事件；
- Terms change、cancellation、controlled reopen、lifecycle transition 等不可變事件；
- aggregate version、命令冪等 receipt；
- `status`、`end_date`、`actual_end_date` 與服務資料鎖的目前投影。

Orders 不擁有：

- `client_name`；
- 訂金到期日、訂金服務天數、收款、退款及其他 Client Finance 事實；
- assignments、正式服務日、檔期鎖及 `actual_hours`；
- 月嫂薪資與應付款；
- Alert 的 open／claimed／resolved；

## 2. Orders SSOT

| 資料 | 類型 | 唯一權威 |
|---|---|---|
| Order Terms | root_fact | 最新有效 Terms event 及 Orders aggregate |
| 下廚需求 | root_fact | Case Import 明確正規化結果或後續 Orders Terms event；不得於 Matching 重新解析問卷 |
| 每日服務時間 | root_fact | `service_start_time`、`service_end_time`、`service_end_day_offset` 三欄完整 tuple |
| actual start | root_fact | Confirm／Correct Actual Start event |
| planned end | derived_projection | 凍結的 planned start、目前 Terms 與規劃服務日 |
| actual end | derived_projection | 有效 assignment-owned 正式服務日最大日期 |
| lifecycle status | derived_projection | Lifecycle evaluator |
| cancellation | immutable_event | Cancellation event |
| controlled reopen | immutable_event | Reopen event；不刪除 cancellation history |
| service-data lock | 不可逆 derived fact | completed 且客戶正式義務結清 predicate 首次成立 |
| lifecycle version | concurrency projection | 每個成功非 replay aggregate command 加一 |
| `orders.staff_id` | compatibility_projection | 禁止作人力、排班或薪資 fallback |
| `orders.deposit_date` | compatibility_projection | Client Finance 的 deposit due date 才是正式權威 |

## 3. Subsystems

### 3.1 Order Query

責任：

- 組合 Orders roots、目前投影及其他 Domain 的 ViewModel。
- 分開回傳 `domain_blockers` 與 `alerts`。

禁止：

- 修資料、觸發狀態機、持久化重算或以 fallback 補造根事實。

### 3.2 Terms Preview／Apply

Preview 輸入只接受 Terms 根事實意圖；輸出：

- before／after；
- assignment 與 schedule 重建候選；
- planned／actual end、hours、樓層費及兩端未核銷投影差異；
- blockers、aggregate version、fingerprint。

Apply：

1. 驗證 actor、reason、idempotency key、expected version。
2. 鎖定並讀取 fresh Orders、Scheduling 與 Finance facts。
3. 以相同 candidate builder 重建 Preview。
4. 驗證 fingerprint。
5. 追加 Terms event。
6. 委派 Scheduling 取消全部舊有效 assignments 並建立新資料。
7. 委派兩端 Finance 重算未核銷投影。
8. 重評 lifecycle，寫 audit、outbox 與 receipt。
9. 單一 commit。

每日服務時間 tuple 契約：

- `service_start_time`、`service_end_time`、`service_end_day_offset` 必須全空或全有；新匯入
  訂單進入契約完成、waiting-deposit lock 或訂金核銷前必須全有。
- `service_end_day_offset` 只允許 `0 | 1`，必須由契約明確提供；不得依結束時間小於開始
  時間自行猜測跨日。
- legacy 三欄全空可唯讀載入，但立即形成資料異常，且阻擋契約完成、收訂金、進入服務與
  自動完成；不得以預設上下班時間補值。
- legacy 案件可先建立空的 Client Finance／Payroll account、付款政策與 Scheduling
  aggregate，讓正式 Terms Preview／Apply 得以補登時段；此架構初始化本身不建立訂金
  或其他帳務義務，因此不得把它誤判為簽約或收款。
- Terms Apply 改變任一時間欄時，與其他 Terms 一樣重建 Scheduling candidate、完成時刻、
  未核銷帳務／薪資日期與 lifecycle impact；服務資料鎖形成後不得修改。

下廚需求契約：

- `requires_cooking` 是可為 unknown 的 Orders root；HCM 獨立匯入時若尚未唯一綁定 Client
  BeClass，固定保存 `NULL`，不得預設為否，也不得因此阻擋 Client／Order 建立；
- HCM 與 Client BeClass 唯一配對後，Case Import reconciliation 才可從明確 yes／no source
  經 typed Orders command 補入 `requires_cooking`；問卷空白、矛盾或自由文字無法唯一判定時保留
  `case_import_cooking_requirement_ambiguous` review，但不得回滾或刪除已匯入的 HCM roots；
- 原始 `survey_details` 保留為來源 evidence，但 Matching 只讀 Orders root；
- 服務資料鎖形成後不得修改。

### 歷史訂單待確認與警示投影（2026-08-14，已人工確認）

歷史訂單採納列若已唯一匹配既有 Order、但 status、月嫂或其他來源欄位仍有 issue，安全可採納欄位
照既有規則保存，同時建立 immutable review evidence；不因 review 回滾同列合法 status／日期或配對
evidence。Orders outbox 將 review 投影為 `HISTORICAL-ORDER-001`，identity 為 review identity，僅顯示
遮罩案件識別與 issue codes。`case_no + client_name` 未匹配列固定不寫 Orders、review、outbox 或 anomaly。

### 3.2.1 Contract Completion Preview／Apply

正式契約完成是 Orders 根事實，但客戶應收義務由 Client Finance 擁有。依第 `21` 份正式
規格，最後一位月嫂簽回並形成有效 commitment 時可先建立唯一 deposit obligation；客戶
簽回時的 Contract Completion 必須保留該 deposit，只補足尚未建立的剩餘期款。客戶簽回、
Orders contract event 與 Client Finance 補足義務必須使用同一 outer Unit of Work：

1. Preview 讀取客戶簽回證據、有效 commitment 的精確服務日、完整服務時段、Client Finance
   付款條款、既有 deposit／剩餘義務與兩個 aggregate versions。
2. commitment 精確服務日數必須等於訂單服務天數；不得由起訖日猜測休假日。缺漏時仍回
   stable error `official_service_dates_incomplete` 且零寫入；不得為滿足此 blocker 先建立
   execution schedule。
3. 舊資料若已有客戶義務、卻沒有正式契約完成事件，回
   `client_obligation_history_conflict` 交異常中心人工確認；不得反推補造事件。
4. Preview 顯示既有 deposit 與預計補足義務的筆數、服務日數、整數金額與到期日，並證明
   deposit 金額與 identity 不會被重建或重複計入。
5. Apply fresh-read 並驗證 Contract Signing status、Orders 與 Client Finance expected version、
   Preview fingerprint 及 idempotency key；先追加契約完成事件，再委派 Client Finance 補足
   尚未建立的正式期款，最後
   重評 lifecycle、寫 outbox 與 receipt，單一 commit。
6. 任一步失敗時，簽回事件、契約事件、新義務、兩端 outbox、versions 與 receipt 全部回滾；
   相同命令 replay 回傳原 receipt，不得重複建立義務。

### 3.3 Lifecycle Projection

輸入只接受：

- 有效取消事件；
- 正式契約流程完成事實；
- 訂金有效核銷；
- actual start confirmation／reconfirmation；
- assignment-owned 最後服務結束時刻；
- Domain 根事實 blockers；
- 客戶正式義務結清；
- 不可逆服務資料鎖。

優先序：

1. 全部約定服務尚未完成且有有效取消事件：訂單取消。
2. 全部約定服務已完成：訂單完成；拒絕後續取消。
3. 契約完成、訂金有效、execution schedule 有效、actual start 已到且無 reconfirm blocker：服務中。
4. 訂金有效：訂單成立；此狀態不代表客戶已簽回，也不授權 execution conversion。
5. 其他：洽談中。

Lifecycle Application 是 status、history 與服務資料鎖投影的唯一 writer。任何 caller 都不得傳入 target status。

### 3.3.1 服務完成時刻與 AutoComplete

`AutoCompleteOrderService` 是 Orders 唯一可將服務完成結果持久化的 command。它必須在同一
Orders outer Unit of Work 中鎖定 lifecycle aggregate、effective Scheduling generation、
assignment-owned official service days、`actual_end_date`、完整 service time tuple 與 active
lifecycle controls，再以 Asia/Taipei business clock 評估：

```text
completion_instant
= actual_end_date + service_end_day_offset + service_end_time
```

只有 `evaluation_at >= completion_instant`、正式服務日完整一致、沒有 `auto_complete` blocker，
且訂單未取消／未完成時，才可由 `服務中` 轉為 `訂單完成`。Apply 必須追加 immutable lifecycle
event、以 expected lifecycle version 更新 projection、保存 idempotency receipt 及 post-commit Orders
source outbox，最後單次 commit；不得重建或結清 Client Finance、Payroll、退款或補助義務。

相同 idempotency key 與 command fingerprint replay 回原 receipt；payload mismatch、expected version
或 authoritative facts 漂移固定回 typed conflict。時刻未到、服務日不完整、effective generation
矛盾、human hold 或取消固定為 typed `domain_blocked` 且零寫入。automatic discovery 只可將 due
candidate 放入 durable command queue；worker 仍只能呼叫此 command，不得直接更新 `orders.status`。

AutoComplete 與 Scheduling leave-substitution Apply 必須序列化於同一 Orders lifecycle aggregate。
任一方先提交都會使另一方持有的 Orders expected version 失效；舊 command 不得以舊服務日完成，
也不得在完成後補寫請假。人工後續更正必須使用獨立、可稽核的 correction command。

訂金 receipt／reversal 與 actual-start reconfirm 綁定：

- 訂金有效性只由 Client Finance 的正式 deposit obligation、succeeded receipt、合法 reversal
  與 allocation reducer 推導；`deposit_reconciled` 不是可寫入欄位。
- 每次 deposit ledger Apply 都以同一 outer Unit of Work 送出
  `deposit_reconciled | deposit_reversed` lifecycle intent，並綁定不可變
  `deposit_settlement_identity` 與有效結算日期。
- 尚未開始服務時，reversal 使 `deposit_reconciled = false`，阻擋進入服務；不得刪除原
  receipt、reconfirmation 或 lifecycle history。
- 已開始或已完成服務後，deposit reversal 只重開 Client Finance 義務並形成帳務異常，
  不倒退服務狀態、不取消 assignment，也不解除服務資料鎖。
- reversal 後再次有效核銷若發生於原 `actual_start_date` 之後，既有 reconfirmation 因
  settlement identity 不同而失效，必須重新確認 actual start；reversal 本身不猜測新的
  actual start。

### 3.4 Actual Start Preview／Apply

- 首次確認與更正都必須 Preview／Apply。
- 不得以 planned start、訂金日期、第一個 schedule 或 UI default fallback。
- 延遲訂金核銷後仍須人工重新確認真正開始日。
- Apply 同交易重建 assignments、正式服務日、actual end、未核銷薪資／帳務日期及 lifecycle。
- 原過期日期到新確認日期之間不得補造服務日。

### 3.5 Cancellation

- 只適用於全部約定服務完成前。
- 已開始服務時，Preview 由使用者確認逐日「實際服務日期＋實際月嫂」；現有事實預填，新增或改派必須指定月嫂與原因。
- Apply 取消舊 assignments、未來 schedule 與 buffer，依確認後服務日建立新 assignments，重算 hours、整數樓層費、Client Finance 與 Staff Finance。
- 完整履約後取消回 `order_cancellation_after_full_service` blocker 並零寫入；狀態、薪資與服務結算維持完整履約。

### 3.6 Controlled Reopen

- 只有尚未產生取消相關正式退款、reversal 或 settlement 才可受理。
- 追加 reopen event，不刪除 cancellation history。
- 不恢復舊 assignment、schedule、lock 或 payment stage。
- 受理後必須 fresh Preview；已有正式退款或結算時另建新訂單。

### 3.7 Historical Order Adoption

restricted historical source 只能補登既有 Order，不建立 Client／Order。唯一匹配鍵為
`case_no + client_name` 精確相符；找不到固定為 `unmatched_case`，零 Domain mutation且不建立警示。
source profile v1 只接受 0→取消、1→完成、2→洽談中；空白／其他值保存 review evidence。

`actual_start_date`、`actual_end_date` 永遠允許 `NULL`。有效來源值只補目前空值，既有非空衝突
保留 current fact並 review。來源 terminal assertion 可在缺日期、取消原因、排班或付款時成立，
但不得觸發現行通知、訂金、收付款或自動帳務；immutable lifecycle event／receipt 必須標示
historical origin。既有非洽談狀態與來源不同時不得覆寫。Preview 零寫入，Apply 每列鎖定 fresh
Order、驗證 version／fingerprint，並以單一 UoW 保存 projection、event、receipt、outbox及跨域 evidence。

## 4. Module

### Confirmed Service Dates (2026-08-12)

Orders owns the `Confirm Service Dates` Preview/Apply command. The candidate must contain
exactly the contracted service-day count, be unique and sorted, and every date must be within
the server-provided selectable range. Apply locks current Orders/Scheduling facts, validates the
Preview fingerprint, creates one immutable version and receipt, and invalidates the current
matching schedule snapshot. It never creates an assignment, staff schedule, Payroll impact, or
outbound LINE task.

Calendar-week views use Sunday through Saturday. A modification never overwrites historical
confirmed versions or prior schedule-confirmation events; it creates a new current lineage which
must be previewed, sent, and confirmed again before formal assignment can proceed.

### Confirmed Service Dates (2026-08-12)

Orders owns the `Confirm Service Dates` Preview/Apply command. The candidate must contain
exactly the contracted service-day count, be unique and sorted, and every date must be within
the server-provided selectable range. Apply locks current Orders/Scheduling facts, validates the
Preview fingerprint, creates one immutable version and receipt, and invalidates the current
matching schedule snapshot. It never creates an assignment, staff schedule, Payroll impact, or
outbound LINE task.

Calendar-week views use Sunday through Saturday. A modification never overwrites historical
confirmed versions or prior schedule-confirmation events; it creates a new current lineage which
must be previewed, sent, and confirmed again before formal assignment can proceed.

| Module | Input | Output | SSOT／限制 |
|---|---|---|---|
| TermsValidator | candidate terms | typed validation | 三個服務時段欄位全空或全有；正式流程前必須完整 |
| ServiceTimeTermsValidator | start、end、day offset | canonical tuple／typed blocker | offset 僅 0/1；不推測跨日 |
| PlannedEndCalculator | planned start、terms、規劃服務日 | end date | 不讀 actual facts |
| ActualEndCalculator | 有效正式服務日 | actual end | 忽略 cancelled、休假與 buffer |
| CompletionInstant | actual end、服務結束時間、day offset | Taipei instant | 不使用午夜或伺服器時區 |
| LifecycleEvaluator | typed roots | status decision | 不讀 Alert 或 target status |
| ServiceDataLockPredicate | completion、客戶結清、既有鎖 | lock decision | 一旦 true 永不回 false |
| TermsDiff | before／after roots | canonical diff | 不含 client name 或 Finance-owned 欄位 |
| PreviewFingerprint | relevant roots、candidate、contract version | deterministic hash | 顯示欄位改變不得誤判 stale |
| CancellationServiceDayValidator | 合約服務量、逐日 owner | validated actual service facts | 完整履約後禁止取消 |
| FloorFeeProration | 原費用、合約日、實際日 | 整數總額 | `ROUND_HALF_UP` |
| LargestRemainderAllocator | 整數總額、各 assignment 日數 | 整數 allocations | 固定 assignment 順序；總和守恆 |
| ReopenEligibility | cancellation 及財務事件 | allow／blocker | 不恢復舊資料 |
| DepositSettlementIdentity | obligation、receipt、reversal、allocation | deterministic identity | reconfirmation 必須綁定目前 identity |

Module 必須為純函式，不得讀 DB、取得現在時間或 import API／UI。

## 5. Typed API

```text
GET  /orders/{case_no}
POST /orders/{case_no}/terms/preview
POST /orders/{case_no}/terms/apply
POST /orders/{case_no}/actual-start/preview
POST /orders/{case_no}/actual-start/apply
POST /orders/{case_no}/cancellation/preview
POST /orders/{case_no}/cancellation/apply
POST /orders/{case_no}/reopen/preview
POST /orders/{case_no}/reopen/apply
```

Apply request 只接受原始 intent、actor、reason、expected version、preview fingerprint 及 idempotency key。不得接受 status、actual end、actual hours、金額或前端計算完成的 assignment 結果。

Stable errors：

- `order_not_found`
- `invalid_order_terms`
- `service_time_terms_incomplete`
- `service_time_terms_invalid`
- `service_data_locked`
- `actual_start_reconfirmation_required`
- `order_cancellation_after_full_service`
- `order_reopen_financial_history_exists`
- `order_version_conflict`
- `stale_preview`
- `idempotency_conflict`
- `cross_domain_candidate_rejected`
- `transaction_failed`

## 6. 現況遷移

可吸收既有 lifecycle command envelope、facts validation、pure candidate、persistence、outbox 與 typed API client 的結構，但必須：

- 補入契約完成根事實；
- 移除 target-status manual correction；
- 不讓 human hold 成為新核心依賴；
- 將 cancellation shell 擴充為完整跨 Domain transaction；
- 以 Terms Preview／Apply 取代 ownership 過寬的 assignment synchronization；
- 將 UI 日期、金額與 status 計算移回後端。

既有 dirty／untracked lifecycle 成果必須逐檔吸收，不得刪除後重建。

Live writer 退出清單：

- `services/order_lifecycle_persistence.py` 可吸收為 Orders persistence adapter，但只能由
  Lifecycle Application 呼叫。
- `services/client_payment_writer.py`、Finance Import 與 Client Finance 只能送 lifecycle
  intent，不得直接寫 `orders.status`。
- `services/caregiver_availability_lock_conversion_service.py`、
  `services/caregiver_availability_lock_cancellation_service.py`、
  `services/order_assignment_synchronization.py` 與 `services/db_service.py` 的 status／日期
  writer 必須遷移至 Orders typed port 後關閉。
- `scripts/imports/import_client_hcm.py` 與 `services/line_review_service.py` 只可建立初始
  Orders root facts，不得自行推進 lifecycle。
- final writer scan 必須證明 `orders.status`、`actual_start_date`、`actual_end_date`、
  服務時間三欄與 lifecycle version 都只有目標 owner 可寫。

## 7. Domain 驗收

至少覆蓋：

- 匯入洽談案件到成立、服務中、完成及服務資料鎖；
- 相同與衝突 Import replay；
- Terms 全案重建；
- 延遲訂金後重新確認 actual start；
- 服務時間三欄缺漏時，契約完成、waiting lock conversion、訂金核銷、進入服務與完成都
  fail closed；跨日 offset 不由時間大小推測；
- 訂金 reversal 在服務前阻擋進入服務；服務開始後只重開財務義務，不倒退服務狀態；
- reversal 後的新延遲核銷使用新 settlement identity，舊 actual-start reconfirmation
  不得重放；
- 多月嫂中途取消及雙邊重算；
- 全部服務完成後取消零寫入；
- 完成但未鎖時補登正確服務根事實；
- 鎖形成後退款／reversal 不解鎖；
- legacy status／assignment writers 不可達或固定 Gone。
