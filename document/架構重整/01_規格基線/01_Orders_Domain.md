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

### 3.1.1 Order Operational Timeline／11 步 SOP

- 七階段與 11 步 SOP 都是後端唯讀 typed projection；React 只能依 server status 呈現，
  不得由 `orders.status`、日期字串或畫面所在欄位重算完成、進行中或目前階段。
- 每一步固定回 `not_started | in_progress | blocked | completed | unavailable`。`completed`
  必須有完成標記，`in_progress` 必須有明確的目前執行強調，`blocked` 與 `unavailable` 必須
  分開顯示；不得把讀取失敗或缺根事實偽裝為尚未完成。
- 媒合聯繫、月嫂意願、客戶履歷推薦、月嫂簽回、訂金核銷、客戶簽回各讀取自己的
  immutable owner fact；不得用同一 Contract Completion event 代替月嫂與客戶兩種簽回。
- Step 2「媒合月嫂候選人加入意願池」只依 Assignments／Scheduling 的候選池／聯繫根事實完成；
  不得等待客戶接受正式方案。七階段的 Stage 2 仍依其完整媒合狀態投影，兩者不可互相覆寫。
- 正式服務履約只依 effective assignment-owned official service dates、完整 service-time tuple 與
  `BusinessClock` 投影 `not_started／in_progress／completed`；不得依可過期的 assignment status count。
- 正式服務完成後，current stage 必須前進至完工結案與請款，即使其中某個 settlement owner
  projection 仍為 `unavailable`；不得繼續把案件留在「正式服務履約／進行中」。
- Staff Payables 結清只讀 `staff_payable_projections` 的 current status／version／updated time；
  `staff_obligations` 是不可變義務來源，原始 `open` 不得被 Orders 誤判為付款仍未完成。

#### 作業步驟回退與 aggregate version（2026-08-27 人工裁決）

- append-only lineage 與 current aggregate version 不倒退，不代表 SOP step ordinal 只能往前。
  typed owner event 可使 current operational step 回到較早步驟，但新 event／projection version
  必須大於舊版，既有歷史 event不得刪除、改寫或改小 version。
- 服務前已配對月嫂因車禍、健康或其他正式不可服務事實必須整案換人時，由
  Scheduling owner 的 replacement Query／Preview／Apply 追加具名 event，並以 immutable
  successor lineage 使舊 caregiver-bound matching plan、recipient confirmation、commitment、簽回與
  assignment 轉為 superseded／不再滿足 current round。不得原地改 staff id。
- 整案重新媒合默認從 Step 2 `matching_pool` 開始；若 current owner readback 證明同一
  replacement round 已有可沿用的合法候選池，可由 server 計算為 Step 3／4。
  `resume_step` 必須是最早失效 owner root 的後端投影，不是人員任意輸入 status。
- 上述整案回到媒合只適用於 owner readback 證明尚未有任何 assignment-owned actual
  service fact。只要已提供服務，不得回 Step 2 也不新建另一套整案換人；必須使用
  Scheduling 既有 leave／substitution Query／Preview／Apply，只重建受影響日期，並沿用
  current Payroll impact／obligation lineage 計算原月嫂與代班月嫂薪資。
- 回退後 Step 1 與無關 caregiver identity 的合法 Orders／Client Finance 根事實保留；
  定金不因換人自動退款或重建。舊月嫂簽回、客戶對特定月嫂的承諾、
  日期確認與正式排班依 binding 失效範圍逐項重做。若日期／金額／條款未變，
  Finance 不得伪造新義務；若改變，仍走各 owner 正式 impact／adjustment 契約。

### 3.1.2 未完成訂單代辦看板（2026-08-25 人工裁決）

- 代辦看板的候選集合固定為所有尚未完成的訂單；canonical lifecycle 已為「訂單完成」的案件不得顯示。
- 「所有」是 server-authoritative 完整集合，不是第一頁或任意上限。若 public Query 採 cursor／continuation，
  React 必須自動續讀至 terminal page，合併時依 order identity 去重並維持 deterministic ordering；不得要求
  操作者按「下一頁」才發現其他待辦。
- 任一 continuation 失敗、timeout、abort、cursor 重複或 schema mismatch 時，頁面不得把 partial rows
  宣稱為完整看板；必須顯示載入未完成與 retry，並取消 stale request。
- 本看板是唯讀 Query projection，不得為了排除完成訂單而修改 Orders status、隱藏 blocked／unavailable
  案件或在瀏覽器重算 lifecycle。

### 3.1.3 訂單管理未完成清單（2026-08-25 人工裁決）

- 訂單管理主清單採與代辦看板相同的候選集合、完整 continuation、identity 去重、deterministic ordering
  與 partial-failure 規則：同頁顯示所有未完成訂單，完成訂單固定排除。
- 分頁 cursor 可作 transport 細節，但不得成為操作者工作步驟；React 必須自動續讀至 terminal page，
  不顯示「下一頁」按鈕，也不得只因預設 page size 而漏掉未完成案件。

驗收狀態（2026-08-25）：`completed`。代辦看板與訂單管理已共用 server-owned `unfinished`
lifecycle scope，自動讀完 continuation；Chrome 回讀兩頁皆為 94 筆、完成訂單 0 筆且無人工下一頁入口。
React adapter 不再自行解讀中文狀態縮減集合；focused tests 與 production build 已通過。
- 代辦看板與訂單管理可採不同 presentation，但必須消費同一 server lifecycle predicate；兩頁不得各自
  以中文 status、日期、card lane 或 local cache 判斷是否完成。

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
- 此一唯一來源補正只改料理條款；即使歷史 root 已有 `actual_start_date`、但尚無正式 Scheduling
  segment，仍可補入。不得藉此變更服務日期、時段、工時、費用或其他服務形狀；服務資料鎖仍為硬性 blocker；
- 原始 `survey_details` 保留為來源 evidence，但 Matching 只讀 Orders root；
- 服務資料鎖形成後不得修改。

### 歷史訂單待確認與警示投影（2026-08-14，已人工確認）

2026-08-28 人工裁決將歷史訂單 canonical workbook 固定為六欄：`client_name`、`case_no`、
`start_date`、`end_date`、`status`、`staff_name`（標準中文標頭為「客戶姓名、案件編號、開始日期、
結束日期、狀態、月嫂姓名」）。第七欄起包含「月嫂姓名2」不採納，不得建立第二月嫂
pairing evidence或 assignment candidate；原檔 bytes 仍參與 content digest。前六欄的單一月嫂可使用訂單開始／
結束日期作為其服務區間。

歷史訂單採納列若已唯一匹配既有 Order、但 status、月嫂或其他來源欄位仍有 issue，安全可採納欄位
照既有規則保存，同時建立 immutable review evidence；不因 review 回滾同列合法 status／日期或配對
evidence。Orders outbox 將 review 投影為 `HISTORICAL-ORDER-001`，identity 為 review identity，僅顯示
遮罩案件識別與 issue codes。`case_no + client_name` 未匹配列固定不寫 Orders、review、outbox 或 anomaly。

### 歷史 review 更正來源重新匯入（2026-08-26，已人工確認）

`HISTORICAL-ORDER-001` 不得因只能查看或追蹤而永久懸置。Orders 必須提供以單一 immutable
`review_identity` 為根的人工 remediation；Anomalies 只可組合受控入口，不能直接修改 Orders root、
review 或 alert status。首版只接受一份僅含該 review 對應列的更正 `.xlsx`，不得接受任意
`corrected_fields` 或以多列檔案猜測對應關係。

1. Context Query 以 server-owned `review_identity` 讀取 immutable review、原 adoption receipt 與
   Orders root，僅回傳去敏案件識別、每個衝突的 `field_path`、來源值／既有 Orders 值（依權限遮罩）、
   檢核規則與可採用值、造成的流程阻擋、必要 workbook contract、review／disposition version，及
   reason／evidence 要求；不得回傳原始工作簿或未遮罩個資。只回傳 `issue_codes`、顯示「欄位衝突」
   或空白判斷依據不符合此 Query 契約。
2. Preview 零寫入，必須重新讀取並鎖定 prior review、原 receipt 與目標 Orders root，驗證 actor
   capability `orders.historical_review.remediate`、prior review／disposition version、唯一來源列對應、新檔 digest、根事實與既有
   disposition。它產生只能用於該 prior review 的 fingerprint，並明示可採納或仍須建立 successor
   review 的 blocker。
3. Apply 必須帶 `prior_review_identity`、expected review／disposition version、preview fingerprint、
   idempotency key、reason 與 evidence；在一個 Orders outer Unit of Work fresh-read 後重驗全部
   binding。它可委派既有歷史採納 typed command，但不得重複 lifecycle event、assignment 或既有
   adoption receipt。
4. 原 `historical_order_adoption_reviews` 永遠 immutable。更正結果必須另以 append-only
   remediation disposition／receipt／outbox 表示 `prior_review_identity → replacement adoption receipt`
   的唯一關係，保存 actor、reason、evidence、source digest、版本、時間與可重播 identity。
5. 更正列合法採納且沒有 issue 時，寫入 `corrected_source_adopted` disposition，由 Orders outbox
   令 prior alert 與其 field warnings 依 predicate auto-resolve。若更正列仍有 issue，必須先建立
   successor review／warning，再以 `superseded_by_replacement_review` disposition 關閉 prior task；
   不得靜默刪除或把 successor 當成功。
6. duplicate Apply 只回同一 receipt；payload mismatch、stale version、未授權 actor、非唯一對應、
   preview stale、worker timeout 或 projector readback 未達 predicate 均回 typed error／pending，保留
   可見 blocker。Apply 結果必須可從 Orders receipt、disposition 與 anomaly current projection
   readback 驗證。predicate 已解除的 prior alert 必須從 active 異常頁移除，僅在 audit history 保留；
   successor 存在時必須顯示 successor 的具體欄位衝突與新修正入口，不能留 prior review 作為唯一待辦。
7. 更正來源若通過 Orders 完整規則、但採納後 status、日期與 assignment 均與現行 root
   相同，這是合法 no-op adoption：必須可寫入 remediation disposition，但不得建立
   lifecycle event 或增加 lifecycle version。schema constraint 也必須同時允許此形狀，並繼續對
   真實狀態轉換強制 event 與 `resulting_lifecycle_version = expected_lifecycle_version + 1`。

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

#### 3.4.1 事前服務日期精算與排休覆寫

- 在尚未形成正式 assignment 前，服務日期確認 UI 必須由 server 精算：`週休1日` 預設週日、
  `週休2日` 預設週六與週日；國定假日預設休假，事前請假由人工明示。
- 固定週休可由人工覆寫為服務日，並以 `custom_work_dates` 重跑 server 精算；此欄位只覆寫
  固定週休，不能覆寫國定假日休假或事前請假。取消覆寫後必須恢復該固定週休。
- UI 不得自行加減、重排或提交服務日；每次覆寫都必須重新取得目標合約天數完全守恆、且全數位於
  server `selectable_dates` 的結果，才可進入既有服務日期 Preview／Apply。
- 本節只確認 Orders 的事前服務日期，不得直接切換 `staff_schedule.is_work_day`、建立 assignment
  或替代正式請假／代班流程；正式排班後的請假與代班仍由 Scheduling 擁有。

### 3.5 Cancellation

- 只適用於全部約定服務完成前。
- 已開始服務時，Preview 由使用者確認逐日「實際服務日期＋實際月嫂」；現有事實預填，新增或改派必須指定月嫂與原因。
- Apply 取消舊 assignments、未來 schedule 與 buffer，依確認後服務日建立新 assignments，重算 hours、整數樓層費、Client Finance 與 Staff Finance。
- 取消結果若包含 Client Finance impact，Orders 只轉送 owning Domain 的 typed 結果；每筆必須帶
  `direction`（`refund_due`／`additional_charge_due`／`no_finance_change`）與
  `direction_amount_ntd`。Orders、API 與 UI 不得由 action kind、obligation amount 或金額正負自行推定。
- 完整履約後取消回 `order_cancellation_after_full_service` blocker 並零寫入；狀態、薪資與服務結算維持完整履約。

#### 3.5.1 服務中代班的契約邊界（2026-08-27 人工裁決）

服務中已有至少一筆 assignment-owned actual service fact 時，代班是 Scheduling 對受影響日期
的 substitution，不是 Orders 的整案換人或契約重建：

- 正常代班不要求代班月嫂另簽獨立服務契約／簽回，也不要求客戶追加確認或簽署變更文件；既有
  commitment、客戶契約、已服務日期與原月嫂的合法薪資根事實保留。
- 代班月嫂 identity、受影響日期、原／新 assignment 與 Payroll impact 由 Scheduling／Payroll
  的 typed substitution lineage 擁有；缺少新契約、簽回、客戶確認或變更文件，不得阻擋代班
  Apply、排班 lineage、actual-service readback 或薪資。
- 人員可另走人工受控的 optional `substitution_supplement` 文件／證據入口。附件只形成可稽核
  supplemental evidence，不自動形成 signed／customer-accepted 事件；無附件或 archive 失敗
  不影響代班合法性。若內容要改變日期、條款或金額，須另依 Terms／Finance impact／adjustment
  owner command 處理，不得由附件直接改寫 Orders root。
- substitute identity 不存在、occupancy conflict、fresh version stale 或 owner readback 失敗等
  真實 blocker 仍須 fail closed；以「沒有追加契約」作為 blocker 則不符合本契約。已有 actual
  service 卻嘗試整案回 Step 2，仍固定拒絕且零寫入。

### 3.6 Controlled Reopen

- 只有尚未產生取消相關正式退款、reversal 或 settlement 才可受理。
- 追加 reopen event，不刪除 cancellation history。
- 不恢復舊 assignment、schedule、lock 或 payment stage。
- 受理後必須 fresh Preview；已有正式退款或結算時另建新訂單。

### 3.7 Historical Order Adoption

restricted historical source 只能補登既有 Order，不建立 Client／Order。唯一匹配鍵為
`case_no + client_name` 精確相符；找不到固定為 `unmatched_case`，零 Domain mutation且不建立警示。
source profile v1 只接受 0→取消、1→完成、2→洽談中；空白／其他值保存 review evidence。

2026-08-28 狀態判定補充裁決：numeric `0`不得因falsy正規化而與空白共用row fingerprint；
Preview與Apply receipt必須由Orders回傳`0／1／2／invalid`守恆數量，管理端只顯示該typed結果，
不得由前端重算或提供target status editor。完整契約與驗收位於
`PROV-20260828-historical-order-six-column-status-observability-spec-gap.md`。

`actual_start_date`、`actual_end_date` 永遠允許 `NULL`。精確配對且可解析的有效歷史來源值直接寫入，
不比較 current value 或 source time，也不產生 `current_conflict`。來源 terminal assertion 可在缺日期、取消原因、排班或付款時成立，
但不得觸發現行通知、訂金、收付款或自動帳務；immutable lifecycle event／receipt 必須標示
historical origin。無法精確配對、欄位不可解析或違反 Orders invariant 時建立 typed warning 並 fail closed。
此受限斷言只授權 Orders-owned historical adoption command，不授權一般 adapter 或 UI 寫入。Preview 零寫入，Apply 每列鎖定 fresh
Order、驗證 version／fingerprint，並以單一 UoW 保存 projection、event、receipt、outbox及跨域 evidence。

2026-08-23人工進一步裁決Historical Orders workbook採`ROW_ATOMIC_RESUMABLE + archive_required`。
workbook command必須有durable `running → row_committed* → terminal_receipt`、resume cursor、每列fresh
Order version與`retryable_interrupted | terminal_failed`；same key＋same canonical workbook只續跑未terminal
rows或replay terminal receipt，same key＋different workbook固定conflict。`assignment_candidate`與
`evidence_only_pairing`是`adopted`子分類，不得重複計入source-row aggregate。

HCM Current仍由Case Import編排whole-workbook outer UoW。若HCM來源`exact IP + exact normalized name`
命中既有Client，Orders端固定0 mutation並接受`review_only`結果，不得建立partial Order；只有未命中duplicate
identity、但尚無唯一Client BeClass對方的合法案件，才可依既有條款建立Order並讓
`requires_cooking = NULL`。archive成功不等於Orders commit，rollback後的archive compensation由Case Import擁有。

### 3.8 Historical Operational Baseline（2026-08-27 人工裁決）

只有 Historical Orders 可由具權限人員以 append-only Preview／Apply 設定目前 11 步作業基準。選定
第 `N` 步後，第 `1..N-1` 步投影為 `historical_baseline_completed`，第 `N` 步為 current／in-progress；
一般新案件不得使用此狀態。baseline event 必須保存 case/order identity、selected step、actor、reason、
evidence、current owner versions／fingerprints、idempotency 與 receipt，且不得建立不存在的 LINE delivery、
簽章、付款、allocation、assignment 或 lifecycle event。

歷史案件可免除重建已不可得的過去操作軌跡，但從 current step 繼續執行所需的 canonical root 仍必須存在。
缺少 matched caregiver、有效 commitment、confirmed official dates、effective assignment、actual start、
service-time tuple 或 owner financial root 時，必須建立具體、可由 owning Domain Q/P/A 補齊的異常；補正後
fresh readback 使該 occurrence 消失並允許後續推進。歷史簽回或傳遞證據確實不可取得時，可追加具
actor／reason／獨立 evidence 的 `historical_evidence_unavailable_accepted` disposition；它只結束補找舊文件的
operational blocker，不得偽造成 signed／delivered／paid，也不得繞過 current/future command 的必要 root。

Orders service completion 與 Client Finance、Staff Payables、Government Subsidy settlement 分開投影：
服務根事實完整可使 Orders 完成；未結清金流仍各自保持 actionable alert，不得把 Orders 倒退為服務中。
取消則依 §3.5 分流，沒有額外解約違約金；服務前無正式金流不要求付款紀錄，已有收款或服務中取消所形成的
退款、補收、月嫂應付／追回仍由各 owner 結清後才解除。

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
- 服務中代班不要求新契約／簽回或客戶變更簽署，缺少文件仍可完成 substitution、排班 lineage
  與薪資；optional supplement 只保存人工 evidence；
- 完成但未鎖時補登正確服務根事實；
- 鎖形成後退款／reversal 不解鎖；
- legacy status／assignment writers 不可達或固定 Gone。
