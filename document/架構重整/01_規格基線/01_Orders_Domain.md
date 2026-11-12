# Orders Domain

## 1. 文件邊界與所有權

- 狀態：`current-spec`
- Owner：Orders Domain（`domains/orders/`、`subsystems/orders/`）
- 單一負責範圍：訂單識別（`case_no`）、Order Terms（`start_date`、`service_days`、`service_hours_per_day`、`requires_cooking`、`floor_fee` 與每日服務時段三欄 `service_start_time`/`service_end_time`/`service_end_day_offset`）、`actual_start_date` 確認與更正、具跨 Domain 影響之不可變 Terms 事件、Cancellation 與 Controlled Reopen 事件、Lifecycle 狀態機與 `order_service_data_locks`、完工時刻（`AutoCompleteOrderService`）與完工後日期更正（`official-service-dates`）、Contract Completion 交易協調，以及訂單終結切換（`case_terminal_closure`）outbox 發布。
- 關聯引用：見 [Global 共同契約](00_Global_共同契約.md)、[訂單看板、事前日期與歷史採納](01A_訂單看板與事前日期及歷史採納規格.md)、[Assignments / Scheduling Domain](02_Assignments_Scheduling_Domain.md)、[Payroll Domain](03_Payroll_Domain.md)、[Client Finance Domain](04_Client_Finance_Domain.md)、[External Integration / Access Control](17_External_Integration_LINE_Access正式規格.md)、[LINE Gateway 與通知投遞](17A_LINE_Gateway_Inbox與通知投遞正式規格.md)、[Case Import 與非市民待審](17B_Case_Import與非市民Redis待審正式規格.md)、[LINE 客服與月嫂自助服務](20_LINE客服與月嫂自助服務正式規格.md)、[Contract Signing 正式規格](21_Contract_Signing_Commitment與正常驗收資料鏈正式規格.md)、[LINE 身分管理與解除](23_LINE身分管理與解除正式規格.md)、[歷史訂單生命週期與服務天數帳務](27_歷史訂單生命週期與服務天數帳務正式規格.md)。

## 2. 核心不變量與資料模型（SSOT）

| 資料 | 類型 | 唯一權威 |
|---|---|---|
| Order Terms | root_fact | Orders aggregate；具跨域／lifecycle 影響異動另存有效 Terms event |
| 下廚需求（`requires_cooking`） | root_fact | Case Import 正規化結果或 Orders Terms event（未綁定 Client BeClass 時存 `NULL`，禁預設否） |
| 每日服務時間 | root_fact | `service_start_time`、`service_end_time`、`service_end_day_offset`（`0 \| 1`，禁止由時刻大小猜測跨日） |
| actual start | root_fact | 無正式 Scheduling 時存於 Orders aggregate；已有正式安排或延遲訂金重認存為 Actual Start event |
| planned end | derived_projection | 凍結 `planned start`、目前 Terms 與規劃服務日 |
| actual end | derived_projection | 有效 assignment-owned 正式服務日最大日期 |
| lifecycle status | derived_projection | Lifecycle evaluator（嚴禁 caller 傳入 `target_status`） |
| cancellation／controlled reopen | immutable_event | Cancellation／Reopen event（重開不刪取消歷史） |
| service-data lock | 不可逆 derived fact | `order_service_data_locks`（`completed` 或完工確認成立，永不回退或因退款解鎖） |
| lifecycle version | concurrency projection | 每個成功非重播命令遞增 1 |
| `orders.staff_id`／`orders.deposit_date` | compatibility_projection | 嚴禁作為排班／薪資／訂金到期日 fallback（正式訂金日由 Client Finance 擁有） |

- Orders 不擁有：`client_name`、訂金／收退款明細、assignments／正式服務日／檔期鎖／`actual_hours`、月嫂薪資或 Alert workflow。
- **政策與費率版本保護**：案件於系統建立當下綁定費率政策及個案調整；補件、日期更正與重排維持原適用政策版本。

## 3. 公開契約與流程

### 3.1 Lifecycle 狀態機與 `case_terminal_closure`

輸入僅接受：有效取消事件、契約完成事實、訂金有效核銷、Client Finance 有效一般市民訂金未付人工放行、actual start 確認、最後正式服務時刻、Domain blockers、客戶義務結清與不可逆服務資料鎖。評估優先序：

1. 未履約完成且存在有效取消事件 → **訂單取消**
2. 全部約定服務已完成 → **訂單完成**（此後一律拒絕取消，回 `order_cancellation_after_full_service`）
3. 契約完成 ∧（訂金有效核銷 ∨ 有效訂金未付人工放行）∧ execution schedule 有效 ∧ actual start 已到且無重認阻擋 → **服務中**
4. 訂金有效核銷 ∨ 有效訂金未付人工放行 → **訂單成立**（不代表已簽回，亦不單獨授權 execution conversion）
5. 其餘 → **洽談中**（缺進件欄位則維持 `待補件`）

- **`case_terminal_closure` 交接**：案件進入終局閉環時，Orders 在同一 outer UoW 寫入 `case_terminal_closure` event（含 `case_no`、`terminal_kind`、resulting version、nullable `source_subject` 與 idempotency identity）並發布 outbox；由 [LINE 身分管理 §7.2](23_LINE身分管理與解除正式規格.md#72-orders-terminal-closure-auto-restore) 檢查該人員全部案件是否皆已終局以觸發預設選單恢復（未綁定客戶依 skip receipt 略過）。

### 3.2 `AutoCompleteOrderService` 與完工後日期更正

- **完工時刻與鎖定**：
  ```text
  completion_instant = actual_end_date + service_end_day_offset + service_end_time  # Asia/Taipei
  ```
- **唯一正式持久化入口**：`AutoCompleteOrderService` 於單一 outer UoW 鎖定 lifecycle aggregate、effective Scheduling generation、assignment-owned 正式服務日、`actual_end_date`、完整時段 tuple 與 active controls，當 `evaluation_at >= completion_instant` 且無 `auto_complete` blocker（與 Scheduling 請假代班原子序列化 CAS Orders version），轉為 `訂單完成` 並立即建立 `order_service_data_locks` 凍結服務日期、時數、服務單價與樓層費（非財務聯絡個資仍可獨立更正）；同時寫出 `line_service_completion_notification=true` outbox 觸發原案件群組單次完工滿意度問卷通知（見 [LINE 客服與月嫂自助服務 §4.4](20_LINE客服與月嫂自助服務正式規格.md)）。
- **唯讀狀態查詢**：`GET /api/v1/orders/{case_no}/service-completion` 回報權威完成時刻與目前進度，不設一般工作台人工「辦理完工確認」步驟（由背景 durable discovery 委派 canonical handler 自動評估）。
- **完工後服務日更正（`official-service-dates`）**：僅限已完成案件，在不涉及調整、補助退還等價格變動前提下，依守恆天數經 Scheduling replacement 更新各 assignment 服務日並推進 `actual_end_date`（保留原 completion event 與 `order_service_data_locks`，零新建金融義務）。

### 3.3 訂金 Reversal 與開工重認

- 訂金有效性唯一衍生自 Client Finance（每次核銷或沖正於同一 UoW 送出 `deposit_reconciled | deposit_reversed` 並附 `deposit_settlement_identity`）：尚未開始服務時沖正阻擋進入服務；已服務／已完工後沖正僅重開帳務義務與異常，不倒退狀態或解鎖服務資料；若於原 `actual_start_date` 後補繳且 identity 不同，須重新確認 actual start。

### 3.4 Order Terms Preview／Apply 與時段／下廚契約

- **Query vs Mutation 分離**：Query 僅組合唯讀 ViewModel（分開回傳 `domain_blockers` 與 `alerts`），不拒絕對「已存在客戶義務但尚無排班」之合法案號查詢。
- **Pre-assignment vs Formal Apply**：
  - Preview 輸出 before/after、排班重建形狀是否變動、`planned/actual end`、hours、樓層費、實際受影響未核銷帳務差額、`requires_formal_apply`、`fingerprint` 與版本（Terms 畫面計算每日時數時 `4h` 班不扣休息、`8.5h` 班如 `08:30～17:00` 扣 30 分鐘休息計 `service_hours_per_day = 8`）。
  - **普通保存（`requires_formal_apply=false`）**：不影響 Scheduling／confirmed dates／Finance／Payroll／lifecycle 時，僅更新 Orders Terms 與 version（無須 reason／idempotency key 或永久 receipt；結果未明由 Query 比對版本）。
  - **正式 Apply（`requires_formal_apply=true`）**：強制要求 reason／idempotency key，依實際影響委派 Client Finance／Payroll／Scheduling（僅金額／計薪時數／下廚等不改排班形狀時保留現行 generation、`scheduling_command_receipt_id = NULL`，不建立無意義空 generation）。尚未開始且已有排班而改 `service_days` 時，須於同一 Apply 附上精算之完整 `replacement_service_dates` 與逐段 `replacement_allocations.service_days`（已開始服務則禁止全案天數重排）。
- **已結案漏填樓層費更正**。具 `order_service_data_locks` 或符合 [規格 27 §6.3](27_歷史訂單生命週期與服務天數帳務正式規格.md#63-人工發起服務天數更正與已結案樓層費個案計價更正) 的已完成案件，以 `floor_fee_correction=true` 發起更正。Query 回報 `floor_fee_correction_available`。Apply 保留服務鎖、日期與排班 generation。歷史已完成補助市民案件的訂金更正由 Orders 與 Client Finance 同交易完成。其他已結案樓層費更正由 Finance 與 Payroll 在同一交易承接各自差額。
- **每日服務時間與下廚需求**：三欄必須「全空或全有」（新案於契約完成、waiting lock 或訂金核銷前必須完整；修改時段須一次完整傳遞）。HCM 與 BeClass 唯一配對後可經 typed command 補寫 `requires_cooking`（即使已有 `actual_start_date` 但無正式排班時亦同）；問卷模糊維持 `case_import_cooking_requirement_ambiguous` review 而不回滾 HCM 匯入。
- **Contract Completion 協調（`Orders` ＋ `Client Finance`）**：Preview 驗證簽回證據、commitment 服務日數守恆（缺日回 `official_service_dates_incomplete`）、完整時段與雙方版本；Apply 於單一 outer UoW 寫入 `contract_completed` 並委派 Client Finance 保留既成訂金後補建其餘期款（若有舊義務卻缺完成事件回 `client_obligation_history_conflict`）。

### 3.5 Actual Start Preview／Apply

- 首次確認與更正皆須 Preview／Apply（正常案件開工與代班流程依 [Scheduling §3.3 SSTART-01～08](02_Assignments_Scheduling_Domain.md#service-start-and-substitution) 自動同步並保存群組結果日曆；禁止以 `planned_start` 或預設日 fallback）。
- **尚無有效正式 assignment（日期-only 路徑）**：僅更新 `actual_start_date` 與 `lifecycle_version`（Finance／Payroll／Scheduling 不存在時傳 `NULL`，不建空事件或假排班；此狀態不代表已開始服務）；若 Preview 後已有有效排班則回 typed conflict 關閉重取。
- **已有有效正式 assignment**：須顯示逐段重建預覽，單一 Apply 同交易重建 assignments、正式服務日、`actual_end_date` 與 lifecycle，並由 Payroll adapter 一對一原值搬移 source assignment rate snapshot（source 缺漏回 integrity blocker）；過期日期與新確認日間不補造服務日；歷史重啟案依 [規格 27 §8](27_歷史訂單生命週期與服務天數帳務正式規格.md#8-重啟正常流程) 免除訂金／簽約前置直接進入服務中。

### 3.6 Cancellation 與 Controlled Reopen

- **Cancellation（未完整履約前適用）**：
  - Preview 鎖定 Taipei 業務日，對已開始服務者預填截至當日之實際排定日＋月嫂（供確認增減並允許 0 日完全未履約取消），並由具權限工會人員逐案輸入取消違約金（不收為 `0`，收取輸入正整數 NTD＋必填原因；一般取消原因選填）。
  - Preview 明確列示服務應付 `S`、違約金 `F`、淨實收 `R`、應退／應補收與 Client Finance 必填 `direction`（`refund_due | additional_charge_due | no_finance_change`）＋ `direction_amount_ntd`。
  - Apply 在單一 outer transaction 保存取消事件、解除等待鎖、更新實際服務 assignments 與雙邊義務，正式提交與全額結清後依 [LINE 客服與月嫂自助服務 §4.5](20_LINE客服與月嫂自助服務正式規格.md) 提供 LINE 私訊通知客戶按鈕。
- **Controlled Reopen**：管理端入口位於客戶名冊的「訂單取消」案件詳情上方。僅受理尚未發生取消正式退款、沖正或結算之取消案；備註選填（空白則系統稽核補記「系統記錄受控重開訂單」）；追加 reopen event、不刪取消歷史、不恢復舊排班／等待鎖／分期（已有退款、沖正或結算須另建新案）。

### 3.7 Typed Endpoints、Errors、純函式 Modules 與 Writer Exit

- **API Endpoints**：`GET /orders/{case_no}`、`POST /orders/{case_no}/terms/{preview,apply}`、`POST .../actual-start/{preview,apply}`、`POST .../cancellation/{preview,apply}`、`POST .../reopen/{preview,apply}`。Apply 禁止接收前端傳入之 `status`、`actual_end`、`actual_hours` 或金額結果。
- **Stable Errors**：`order_not_found`、`invalid_order_terms`、`service_time_terms_incomplete`、`service_time_terms_invalid`、`service_data_locked`、`actual_start_reconfirmation_required`、`order_cancellation_after_full_service`、`order_reopen_financial_history_exists`、`order_version_conflict`、`stale_preview`、`idempotency_conflict`、`cross_domain_candidate_rejected`、`transaction_failed`。
- **純函式 Modules**：`TermsValidator`、`ServiceTimeTermsValidator`、`PlannedEndCalculator`、`ActualEndCalculator`、`CompletionInstant`、`LifecycleEvaluator`、`ServiceDataLockPredicate`、`TermsDiff`、`PreviewFingerprint`、`CancellationServiceDayValidator`、`FloorFeeProration`（`ROUND_HALF_UP`）、`LargestRemainderAllocator`、`ReopenEligibility`、`DepositSettlementIdentity`（無 DB／時間／UI 相依）。
- **Writer Exit**：僅 Orders Lifecycle Application／persistence 可寫 `orders.status`、`actual_start_date`、`actual_end_date`、服務時間三欄與 lifecycle version；`services/order_lifecycle_persistence.py` 僅受 Orders 呼叫，`client_payment_writer.py`、`caregiver_availability_lock_*`、`order_assignment_synchronization.py`、`db_service.py`、`import_client_hcm.py` 與 `line_review_service.py` 均不得直接推進或改寫 lifecycle。

## 4. 驗收標準

1. 涵蓋全生命週期狀態轉移、`service_time_terms` 三欄缺漏 fail closed、跨日 offset 拒絕猜測、訂金於開工前後沖正之差異行為、已鎖定案退款不解鎖，以及完工後 `floor_fee_correction` 與 `official-service-dates` 守恆。
2. 驗證 `AutoCompleteOrderService` 與 `leave-substitution` 搶鎖 CAS 衝突零部分寫入、取消與違約金全案結算及 `direction` enum 一致、代班不重開簽約與不影響原月嫂合法薪資。
