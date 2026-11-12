# Assignments／Scheduling Domain

## 1. 文件邊界與所有權

- 狀態：`current-spec`
- Owner：Assignments／Scheduling Domain（`domains/scheduling/`、`subsystems/scheduling/`）
- 單一負責範圍：`generation + effective` 排班世代模型、同日分時班次占用（`SHIFT-01～05`）、`waiting-deposit` 檔期鎖、正式指派（`case_staff_assignments`）與逐日服務事實（`staff_schedule.assignment_id`）、七日緩衝提醒、服務開始／代班流程（`SSTART-01～08`）、請假／順延／局部代班／服務中換人（`handover-v1`／`leave-v1`）及其批次重播與 AutoComplete 鎖定競爭、甘特月曆與歷史指派投影、統一六層確定性加鎖順序，以及 `SCHEDULE-002／003／006` 異常決策矩陣。
- 關聯引用：見 [Global 共同契約](00_Global_共同契約.md)、[Orders Domain](01_Orders_Domain.md)、[媒合候選池與客戶決定及通勤](02A_媒合候選池與客戶決定及通勤規格.md)、[Payroll Domain](03_Payroll_Domain.md)、[Client Finance Domain](04_Client_Finance_Domain.md)、[LINE 客服與月嫂自助服務](20_LINE客服與月嫂自助服務正式規格.md)、[Contract Signing 正式規格](21_Contract_Signing_Commitment與正常驗收資料鏈正式規格.md)、[Staff Matching Preferences](24_Staff_Matching_Preferences與不可服務期間正式規格.md)、[歷史訂單生命週期與服務天數帳務](27_歷史訂單生命週期與服務天數帳務正式規格.md)。

## 2. 核心不變量與資料模型（SSOT）

| 事實 | 唯一權威 |
|---|---|
| 指派歸屬與區段歷史 | `case_staff_assignments`（`generation + effective` 版本模型） |
| 每日正式服務 owner | effective `staff_schedule.assignment_id` |
| 已完成案歷史指派 | `case_staff_assignments.status=completed` 及其正式起訖／時段（無日排班亦唯讀可視） |
| 檔期占用 | 有效逐日服務班次的實際起訖時刻（Taipei `[start, end)`） |
| actual hours | `有效正式服務日數 × Orders 每日服務時數` |
| assignment status | 首／末正式服務時刻與 Business Clock 推導（`planned | active | completed`） |
| leave／substitution lineage | `batch_key` header ＋ append-only `(batch_key, batch_item_index)` events |
| waiting-deposit lock | lock header、服務班次日與 events（自動於接受配對＋確認日期齊備時取得） |
| 七日 buffer | 獨立緩衝事實（只作協調提醒，全案開工時同交易解除，絕不擋正式寫入） |
| 長假／不可服務期間 | 版本化不可服務期間與取消事件（[Staff Matching Preferences](24_Staff_Matching_Preferences與不可服務期間正式規格.md)） |

- **嚴格禁止依賴**：`orders.staff_id`、`planned_hours`、`actual_hours_adjustments`、`replaced_assignment_id` 與 `original_assigned_*`。
- **Generation 模型不變量**：同案同一時刻至多存在一個 `effective` generation；任何正式更動採 Preview → Apply `cancel-old / create-new`（僅改費用／計薪時數／下廚且排班形狀不變者沿用現行 generation）；取消或替換後保留不可變歷史並自目前投影排除；歷史訂單未重啟精算前不占現行排班資源。

## 3. 公開契約與流程

### 3.1 同日分時占用與甘特月曆（`SHIFT-01～05`）

- **`SHIFT-01／02`（班次與可用性）**：以 Orders 每日起訖時間與跨日標記（`0 | 1`）比較「含開始、不含結束」時間區間（首尾相接可排；跨午夜班次占兩曆日而班次與工時歸開始日一次；代班占用實際承接者；月嫂全日不可服務仍阻擋相交；缺時段且可能相交回「時段待確認」）。
- **`SHIFT-03／04`**：候選排查、等待鎖、正式排班、開工、改期、請假／代班／換人共用同一判定；轉換或重建僅排除本次實際被替換來源；兩案各計服務量與工時（不可依人日去重）。
- **`SHIFT-05` & Calendar Read（甘特圖）**：
  - 逐月逐人顯示現役班次、等待訂金保留（非工作日）、七日緩衝（非工作日／非服務中）、不可服務與唯讀 `historical_assignment`（不Render無事件的空白灰塊）；連續日僅於同來源、時段與狀態一致時合併；同日多班上下並列並於跨日續班標示。
  - Calendar「可進行出勤精算案件」下拉選單採單一批次 `GET .../staff/{staff_id}/assignment-schedules` 交集 Orders 摘要（禁止 N+1 或 `orders.staff_id` fallback）。
  - 開案主責唯讀投影（`resolve_opening_primary_staff`）：取第一有效 segment 人員（追溯同人 generation 與首日代班原主責；服務前整案替換轉由新人，服務中換人保留原開案主責）。

### 3.2 Waiting Deposit Lock、Assignment Plan 與 Actual Start 重算

- **Waiting Deposit Lock**：支持 Acquire（接受配對＋確認日期齊備時最後條件 Apply 自動執行）、Release-to-unbound、Cancel 與 Convert（首次正式排班必須轉換有效 waiting lock，缺鎖回 `assignment_plan_bootstrap.waiting_lock_required`；訂金逾期不自動釋放）；保留各服務日實際班次（不含週休，buffer 獨立）；同月嫂可同日保留多筆非重疊班次。
- **Assignment Plan Query**：唯讀回傳現行版本與各 owner version（Finance／Payroll 未建立時回 `NULL`，禁止填 0）。
- **Actual Start 已有有效排班重算**：以現行 effective assignments 之順序、月嫂與每段既有 `official-service-day count` 為不變輸入（禁止平移舊日或重分配天數），依序由新 `actual_start_date` 逐日重算各段（保留已核准之請假占用／代班 outcome 與假日事實，任一衝突或 lineage 無法承接回 typed conflict 零寫入，並交 Payroll 搬移 1-to-1 `source_assignment_id` 費率快照）。
- **Holiday facts**：`SchedulingHolidayQuery` 作為版本化唯讀 port，納入 Preview fingerprint 並在 Apply 重鎖重讀（無法讀取回 `holiday_calendar_unavailable`）。

<a id="service-start-and-substitution"></a>

### 3.3 服務開始、排班與代班流程（`SSTART-01～08`）

```text
客戶於原群組提議日期（雙方自行協調；客戶 LIFF 移除日期/天數修改入口）
→ 月嫂於 Staff LIFF 點「接受，填開始日」或「無法配合，請工會代班」
  ├─ 接受且無衝突＋契約／訂金／時段齊全 → 共同 coordinator 單一 UoW 更新 Orders/Scheduling/Finance/Payroll
  │   → 發送無確認按鈕之群組結果日期表（不另經工會確認）
  └─ 不接受／檔期衝突 → 建立工會代班待辦（僅洽談中／成立／服務中）
      → 工會確認替代區段並選定月嫂詢問意願 →（願意）→ 寄送單人本案群組邀請 →（取得真實入群證據）
      → 工會人員直接填寫實際服務日期 → 同一共同 Apply 正式生效並發送群組結果表
```

- **核心條款（`SSTART-01～08`）**：
  - **工會首次儲存班表**：一般案件已選定月嫂、簽約完成、符合訂金條件且尚無正式班表時，授權工會人員在「設定服務日期」核對實際開始日與服務日。單一月嫂承接全部選定日；多位月嫂在各人名下分配服務日，維持有效簽約方案的人員與各段服務量。工會提交明確記錄為工會確認，由共同 Apply 在同一交易保存日期、正式指派／逐日班次與相關業務結果。若已有同方案人員的有效指派但完全沒有正式逐日班次，須核對該指派並接續建立班次，避免產生重複的有效指派。檔期、版本或承諾不符時整筆阻擋。同一工作區回讀現行服務日期與月嫂排班明細，下方集中顯示本案的服務開始、請假與代班待辦。
  - **班表成立判定**：已確認日期以 Orders 日期版本表示。現行正式排班以有效指派及其有效逐日工作班次為準；存在有效指派且缺逐日工作班次時，顯示待處理並回傳可辨識的擋關原因。
  - 停用客戶 LIFF 「服務日期／天數」申請及結構化日期 payload（保留其他異動與歷史查閱），並停用雙方「確認日期表／拒絕日期表」卡按鈕（舊確認路由固定回 `410`）。
  - 服務中局部代班保持全案原 `actual_start_date` 與第一期款到期日；只有全案實際開工日改變時同交易同步第一、二期到期日。未來開工日之排班先保存正式結果，到期由背景 canonical lifecycle worker 轉為 `服務中`。
  - **共用入口**：`POST /api/v1/line/staff-self-service/service-start/*`、工會 `POST /api/v1/line/mobile-admin/service-start/*` 及 `GET/POST /api/v1/scheduling/service-start/*`；一般具備權限工會人員皆可操作（不限 `system_admin`）。

### 3.4 請假／順延／局部代班與服務中換人（`leave-v1`、`handover-v1`）

- **Leave／Substitution**：桌面工作台依 server 進行中＋已有排班案納入選單（含已排班未開工）。月嫂本人提交雙方已協調結果（`execution_dates` 採 `leave-v1`；順延可指定明確補班日或依規則順延；無衝突直接單一 UoW 生效，衝突或代班立待辦）。休假同意不再經由已退役獨立 LINE 審核入口。
- **批次重播與 AutoComplete 競爭**：`batch_key` 加鎖檢查 header／item_count／連續 ordinal／snapshot／fingerprint（同鍵異內容回 `batch_key_request_identity_conflict`）；Apply 與 [Orders AutoComplete](01_Orders_Domain.md#32-autocompleteorderservice-與完工後日期更正) **皆須先鎖定同一 Orders lifecycle aggregate 驗證 expected version**，先提交者勝出、後到者以 stale 失敗零寫入。
- **服務中換人（`handover-v1`）**：針對已開工、仍有剩餘服務日且未鎖定之案件指定原 segment：選定接任月嫂詢問意願（附全部剩餘日）→ 願意後單人邀請並取得真實入群 membership → 工會填入交接日（`>= 今日` Taipei 時鐘，不得遺漏或改動已服務日與原薪資）→ 委派 `LeaveSubstitutionBatchIntent.handover_date` Preview／Apply 於單一 UoW 更新排班、原月嫂保留已付／匯出段與 Payroll handover 差額（見 [Payroll §3.5](03_Payroll_Domain.md#35-服務中換人付款承接staff-handover)）＋發送無按鈕群組結果表（維持最多 4 個有效 segments）。

<a id="multi-caregiver-service-correction"></a>

#### 3.4.1 多月嫂排班

- **工作台入口**。一般訂單成立、服務中與完工後，授權經辦從「確認服務日期與排班」或「服務完工」開啟「多月嫂排班」。尚無正式班表時帶入已確認的日期與人員，允許新增或替換月嫂、分配區段或日期，直接建立單人或多人首份正式班表。保存原契約、客戶確認及定金核銷紀錄。
- **編輯範圍**。已排班案件讀入正式班次，可調整月嫂、服務區段或服務日期，每個服務日恰分配一次。涉及約定總天數、每日時數或客戶價金變更時，沿既有改約流程。既有月嫂意願、入群及通知流程仍可使用，線下已協調者由經辦記錄原因及依據後辦理。
- **調整後續排班**。一般服務中可從交接日起由另一位月嫂承接原區段剩餘班次，或以局部代班調整指定後續服務日，分別沿本節交接與代班契約。歷史服務中依 [歷史服務歸屬與後續排班](27_歷史訂單生命週期與服務天數帳務正式規格.md#historical-service-attribution-correction) 接續。一般案件的預覽逐日顯示所選區段異動，其餘班次、已服務紀錄及原開工事實維持。
- **更正已服務紀錄**。一般服務中可依證據重新分配所選區段的已服務日，後續班表維持原安排。一般完工案可重新分配原正式服務日，每個原班次恰分配一次，保留原完工事件與服務資料鎖。歷史已服務部分依 [歷史服務歸屬與後續排班](27_歷史訂單生命週期與服務天數帳務正式規格.md#historical-service-attribution-correction) 處理。經辦保存原因及來源證據，沿用本案已確認的服務量、時數與客戶計價基準。同時需更正已服務部分與調整後續班次時，各自預覽及確認，下一次預覽讀取前一次生效結果。
- **交易契約**。Query 與 Preview 零寫入。Apply 先鎖定並驗證目前 Orders lifecycle、Scheduling、相關歷史服務量、Payroll、Staff Payables 及結清來源版本。服務歸屬有效且正式班次無檔期衝突時，Apply 儲存正式排班或歷史服務天數。區段、服務量、檔期或來源版本衝突回 typed error 並零寫入；交易錯誤整筆回滾。
- **帳務同交易承接**。預覽逐一顯示受影響月嫂及款項來源的應付差額與核銷狀態。依受影響的受款人與來源判斷，其他區段已有核銷仍可調整本次未付款、未核銷的區段。原應付有人工改額時先確認採用的計算結果。確認時重讀核銷及班表，變動則要求重新預覽。各 owner 在同一外層交易提交正式排班、[Payroll 應付更正](03_Payroll_Domain.md#service-attribution-payroll-correction)及 [Staff Payables 分來源待付與追償](16_Staff_Payables與Client_Refund正式規格.md#service-attribution-settlement)。原出款及核銷連結保留，同鍵同命令回原收據，同鍵異內容回 typed conflict。既有人工分期無法由班表推導分來源金額時，正式排班與帳務待核對事件一同提交，受影響的舊應付暫停再核銷。經辦從本案帳務或排班頁補上各區段補助金額及依據，預覽並確認後按來源處理應付與追償，保留原受款人、來源及核銷。補證只更新帳務與核對事件，沿用當時最新正式班表。歷史單的原付款證據與帳務重開依 [歷史服務歸屬與帳務完成](27_歷史訂單生命週期與服務天數帳務正式規格.md#historical-service-attribution-correction) 處理，符合重啟條件的案件重啟後沿一般流程建立與編輯正式班表。

### 3.5 確定性加鎖順序、Durable Job 與 `SCHEDULE` 異常矩陣

- **統一六層鎖順序**（所有 Scheduling command 共用，禁止局部重訂或半途加鎖；若 fresh 重算發現新增未鎖定月嫂直接回 `scheduling_lock_set_stale` 整筆回滾）：
  1. Case / Scheduling aggregate
  2. 所有受影響 `staff` mutex rows（去重後依 `staff_id` 升冪）
  3. Replay batch header / children
  4. Effective generation 與 assignments（`assignment_id` 升冪）
  5. Schedules / waiting locks / buffer facts（日期與 row id 排序）
  6. Payroll / Client Finance obligations（aggregate identity 排序）
- 複雜排班變更（如 `ApplyAssignmentPlan`、`ApplyLeaveSubstitutionBatch`）支援回傳 `202 Accepted` Durable Job 並由 worker 在單一交易完成全部鎖定與提交。
- **異常決策矩陣（`SCHEDULE-002 / 003 / 006`）**：只以 `Preview/ApplyAssignmentPlan`（尚未有實際服務日時）或 `Preview/ApplyLeaveSubstitutionBatch`（已有實際服務日時）修復 lineage 斷裂、同月嫂重疊或日數總量違規；成功後於同交易寫入 `anomaly.recheck` intent 並在 fresh authoritative readback 後刪除異常。

### 3.6 Typed Commands、Ports、Errors 與 Writer Exit

- **Commands**：`QueryStaffAvailability`、`Preview/ApplyAssignmentPlan`、`Preview/ApplyLeaveSubstitutionBatch`、`Acquire/Release/Convert/CancelWaitingDepositLock`、`QueryCaseCalendar`。
- **輸入 Ports**：`OrdersTermsFactsPort`、`OrdersActualStartFactsPort`、`ClientDepositSettlementFactsPort`、`PayrollImpactCandidatePort`、`ClientFinanceImpactCandidatePort`、`BusinessClockPort`。
- **Stable Errors**：`invalid_scheduling_intent`、`case_not_found`、`staff_not_found`、`assignment_not_found`、`coverage_incomplete`、`service_ownership_conflict`、`staff_occupancy_conflict`、`waiting_lock_conflict`、`buffer_conflict`、`scheduling_generation_conflict`、`scheduling_lock_set_stale`、`stale_preview`、`batch_key_request_identity_conflict`、`invalid_batch_replay_snapshot`、`scheduling_data_integrity_violation`、`holiday_calendar_unavailable`、`idempotency_conflict`、`transaction_failed`。
- **Writer Exit**：僅 Scheduling adapters 可寫 effective assignment、`staff_schedule`、waiting lock、buffer 與 generation；`services/assignment_schedule_rest_date_service.py`、`caregiver_availability_lock_*`、`caregiver_matching_*`、`multi_caregiver_schedule_*`、`order_assignment_synchronization.py`、`payment_service.py`、`actual_hours_adjustment_confirmation_service.py` 與 `db_service.py` 均不得直接修改核心根事實。

## 4. 驗收標準

- 已簽約且定金已核銷的單月嫂成立案件可直接保存多人首份班表，原契約與定金核銷可查。服務中可調整後續班次，保留已服務日與其人員歸屬。完工未核銷案可修改人員、區段與日期，保留原完工事件與班表版本。部分已核銷案件可調整其他未核銷區段，保存後原核銷連結不變。
- 班次重疊、服務量不守恆或預覽所用來源版本變更時，確認回 typed conflict 或驗證錯誤且零寫入。一般單驗證原款未付、部分付款、已付及人工改額已確認的更正，排班與差額同交易生效，原核銷可追溯。驗證交易回滾、同鍵重播及追償防重。
- 既有人工分期分別驗證未核銷及部分已核銷。補證前可保存與回讀最新班表，舊應付原核銷可追溯，受影響的舊餘額暫停出款。補證預覽零寫入，確認後自備及補助分開計算，一來源的超付不抵銷其他來源待付。同鍵重送沿用原結果。

1. Unit／Subsystem 驗證 `SHIFT-01..05`（非重疊雙班、首尾相接、跨午夜歸屬、不可服務與 buffer 分離）、6 層升冪防死結鎖、`scheduling_lock_set_stale` 回滾、`batch_key` 重播／錯荷拒絕，及 Leave vs AutoComplete 競爭零部分寫入。
2. `SSTART-01..08` 與 `handover-v1` 驗證客戶／月嫂／工會各工作面按鈕與 `410` 舊確認阻擋、群組單人邀請與真實入群驗證、局部代班／換人不覆寫已服務日或全案開始日，及甘特圖唯讀 `historical_assignment` 並列顯示。
