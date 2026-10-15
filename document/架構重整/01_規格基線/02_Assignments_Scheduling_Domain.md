# Assignments／Scheduling Domain

> Historical Orders 的 count-based 單薪帳務不建立或偽造正式服務日，也不取得 Scheduling occupancy；
> 只有工會人員執行重啟天數精算後才重新進入本 Domain 的正常 generation／assignment／service-date
> 契約。完整邊界見 `27_歷史訂單生命週期與服務天數帳務正式規格.md`。

## 1. Domain 責任

擁有 waiting-deposit 檔期鎖、正式 assignment、assignment-owned 正式服務日、請假／順延／代班、月嫂占用、七日 buffer、排班 Preview／Apply，以及日期、工時和 assignment status 投影。

不擁有 Orders Terms／lifecycle／actual start、客戶帳務、月嫂應付、Alert workflow、LINE 或契約平台流程。

## 2. SSOT

| 事實 | 唯一權威 |
|---|---|
| assignment 歸屬與區段歷史 | `case_staff_assignments` 的版本化有效紀錄 |
| 每日正式服務 owner | effective `staff_schedule.assignment_id` |
| completed assignment 的歷史區段 | `case_staff_assignments.status=completed` 與其正式起訖日 |
| assignment 檔期占用 | 有效 assignment 的完整連續區間，包含排休與請假日 |
| actual hours | 正式服務日數 × Orders 每日服務時數 |
| assignment status | 第一／最後正式服務時刻與 Global Clock |
| leave／substitution lineage | batch header＋append-only 每日 outcome events |
| waiting-deposit lock | lock header、days 與 events |
| 七日 buffer | 獨立 buffer facts；不混入服務日或薪資 |
| 可接案結果 | 上述占用事實的 Query projection |
| 長假／暫停接案 | versioned staff unavailability period 與 append-only cancel event |
| 重建原因與 old/new lineage | 通用 assignment rebuild event |

`orders.staff_id`、`planned_hours`、`actual_hours_adjustments`、`replaced_assignment_id` 及 `original_assigned_*` 不得成為新架構依賴。

## 3. Domain invariants

- assignment／schedule 改動一律 Preview，Apply 時 cancel-old／create-new，不原地截短、換人或覆寫。
- cancelled assignment 保留歷史但完全排除目前投影。
- 同案同日只有一個正式服務 owner；不支援半日或分時交接。
- 全案有效正式服務量必須等於 Orders 契約服務量。
- 全案條款變更只有在 current effective assignment 的 identity／人員／日期／區間形狀改變時才重建全部有效 assignments；費用、每日時數、下廚需求等不改變排班形狀的異動保留 current generation、assignment、schedule、buffer 與 occupancy。局部請假／代班只重建受影響 family，但仍重驗全案。
- assignment 的整段連續區間都占用月嫂，休假不能被誤判為可接其他案件。
- 一般洽談不占檔期；月嫂只表示承接意願，客戶接受推薦後仍由工會人員決定是否正式配對並以
  current confirmed service dates 建立 waiting-deposit lock。鎖定不要求月嫂先簽約或先形成
  precontract service commitment。
- 訂金逾期只形成異常，不自動釋放。
- 每個尚未開始服務的 assignment 預計結束日後七天為獨立 buffer；全案第一個正式服務開始時同交易解除全部 buffer。Current Query 亦須以全案第一個正式服務時刻排除已開始／已完成案件的 stale active buffer root，不得讓 persistence marker 覆蓋 `planned／active／completed` lifecycle。
- 七天 buffer 只作協調提醒；與其他案件 buffer 或實際服務重疊不阻擋 Query、聯繫、等待訂金鎖或正式排班。正式寫入仍須 fresh-lock 驗證完整 assignment interval／實際服務／有效 lock／不可服務事實；實際占用衝突必須零寫入，不提供強制重疊放行。buffer facts 與歷史 projection 保留，buffer 不再混入新的 hard occupancy projection。
- 國定假日不自動雙倍薪；只接受明確 special-pay event。
- 全部服務完成後不得取消訂單或縮減月嫂完整履約薪資。

## 4. Subsystems

### Availability Query

從 assignment interval、waiting lock、buffer 及其他案件占用推導可用日期。Staff holiday preference 只作排序，不是硬性淘汰；Query 不寫入。

依第 `24` 份正式規格，Availability Query 亦讀取 current `long_leave`／
`temporarily_unavailable` 期間。與服務需求日期重疊時屬 actual conflict；七日 buffer 必須獨立回傳
`buffer` 提醒，無需額外放行命令，不得與不可服務期間或正式占用混成同一 hard block。不可服務期間
由 Scheduling 的 versioned Query 同時供 Matching 與 Calendar 使用。

### Matching Segment Plan

單一月嫂完整覆蓋優先，無法覆蓋才產生 2–4 個連續分段。草稿可顯示 gap／overlap，正式聯繫、鎖定與 Apply 前必須完整合法。

### Waiting Deposit Lock

只提供 Acquire、Release-to-unbound、Cancel、Convert。訂金有效性由 Client Finance typed port 提供。服務區間與 buffer 同時查衝突，每次轉移保存事件。
lock day 只對應該分段的正式服務日；固定週休不是 lock day。七日 buffer 是獨立衍生占用，
不得被 current projection 當成正式服務日，亦不得要求固定週休有 lock day。
Preview 的 buffer conflict 是非阻擋提醒；只有 actual service／assignment／active lock conflict 阻擋 Acquire。buffer 不使用跨 assignment 的 staff/date 唯一限制；實際服務保留唯一限制。

### Assignment Plan

提供 Query、Preview、Apply；支援 bootstrap、分段增減、換人、日期調整及 Orders Terms 全案重建。Apply 取消舊紀錄並新增新集合，通用 rebuild event 保存一對多／多對一 lineage。

#### Actual Start 逐段重新精算（2026-09-23）

已有 effective assignments 的 Actual Start 更正不得整批平移舊日期，也不得以全案新服務日按陣列位置
切片後把各段區間縮成第一／最後服務日。Scheduling 必須以 current effective assignments 的順序、staff
與每段既有 official-service-day count 為不可變輸入，依下列規則建立完整 replacement candidate：

1. 第一段 `assigned_start_date` 固定為使用者確認的新 `actual_start_date`；該日可以是休息日，不要求等於
   第一個 official service date。
2. 以 current 服務方式、固定週休、版本化 Holiday facts，以及對新日期仍有效的請假／人工覆寫逐日精算，
   直到該段取得與 source segment 相同的 official-service-day count；最後一個 official service date 為該段
   `assigned_end_date`。
3. 後續每段的 `assigned_start_date` 固定為前一段 `assigned_end_date + 1 day`，再依相同規則取得該段原有
   service-day count。落在段首至第一服務日之間的休息日屬該段完整占用，不得形成未歸屬 gap。
4. replacement 必須保留 segment 順序、staff identity、逐段服務量及一對一 source assignment lineage；
   不得換人、重新媒合、跨段挪用服務量或沿用只綁舊日期的假日上班同意。
5. 全部 segments 的連續區間、每日唯一 ownership、總服務量、actual hours、人員占用、七日 buffer 與
   generation version 必須重新驗證；`actual_end_date` 取最後一段 `assigned_end_date`。任何衝突皆在
   Preview 顯示；actual conflict 使 Apply 零寫入，七天 buffer overlap 僅提醒。

Holiday／人工調整 facts 與其版本必須納入 Preview fingerprint；Apply 在同一 outer Unit of Work fresh-lock
相同 owner facts 後重算，不得由 UI 提供日曆結果，也不得以另一條 DB connection 讀取未綁定版本的假日集合。

對已有 effective assignments 的開工日更正，逐段候選須在正式寫入前供內部操作者查看與
重新確認。此 Actual Start 畫面只接受新開始日，不接受自選服務日、請假或假日上班輸入；
這些調整須先走既有受控 owner 流程，不由 UI 提交權威日曆結果或直接切換
`staff_schedule.is_work_day`。Scheduling 依目前有效的週休、Holiday、請假及人工調整 facts
重新精算／驗證，回傳可核對的完整候選。開始日或相關 owner facts 變更使既有 Preview
失效；最終確認仍由 Actual Start 單一 Apply fresh-lock 重算並同交易寫入。
取消、拒絕或 stale conflict 全部零寫入。

已核准請假／代班若在 source effective generation 仍有有效占用與對應 outcome，本次 Actual Start
重排必須一併保留並重新驗證：原月嫂的請假日期不得被排成正式服務日；既有代班／順延 outcome
的已核准人員與結果日期不得因重排被偷偷移動、重複計入或遺失；有效請假占用須隨 successor
generation 繼續有效，immutable outcome 與原有 Payroll 事實保持不變。Preview fingerprint 必須綁定
這些 current facts，Apply 在同一 Unit of Work fresh-lock；若新逐段候選無法唯一對應並保留既有
outcome，或與請假、人員占用衝突，回 typed conflict 且 Orders／Scheduling／請假占用全部零寫入，
由操作者走既有請假／代班流程調整後重新 Preview。本次畫面不另建請假／代班批准入口。

Actual Start replacement 建立 successor assignment identity 時，Scheduling candidate 必須保存每段唯一
`source_assignment_id`，供 Payroll persistence adapter 原值搬移 immutable rate snapshot。這項搬移不重算
Payroll、不改 Payroll root version／obligation／amount；source snapshot 缺失或 lineage 不唯一時 fail closed，
不得以 current case policy 取代 source snapshot。

2026-08-27 人工裁決：服務前現任月嫂因車禍或其他正式不可服務事實必須
整案換人時，不是將 Orders／Scheduling version 改小，也不是原地改舊 assignment。
必須新增 version 更大的 caregiver-replacement event，supersede 舊 active matching／assignment
lineage，建立新 matching round，並讓 Orders 11 步投影回到最早失效的 caregiver-bound
step。整案重新媒合默認為 Step 2；只有 current replacement round 的 owner root 證明可沿用
合法候選池時，server 才可投影 Step 3／4。舊候選回覆、特定月嫂簽回、recipient
confirmation、waiting lock、commitment 與排班的 immutable 歷史保留，但不得滿足
新 round 的 gate。

分流根事實固定由 Scheduling 的 assignment-owned official service facts 決定：

- 尚未提供任何服務：可建立新 matching round 並讓 Orders current SOP 回 Step 2／3／4。
- 已提供任何服務：禁止整案回媒合，固定走既有 Leave／Substitution；只重建受影響
  assignment family，保留已服務日與原月嫂薪資事實，代班日由新 assignment 及既有
  Payroll impact 計算。不新建另一套代班或薪資公式。

第一個正式 assignment 的 bootstrap 必須轉換同案仍有效的 waiting-deposit lock；
若沒有 waiting lock，回 `assignment_plan_bootstrap.waiting_lock_required`，不得直接建立
正式 assignment。轉換前仍必須驗證契約流程完成、服務時間完整，以及 Client Finance 提供的訂金已正式核銷或有效的一般市民訂金未付人工放行；放行不得把訂金投影成已核銷或零元；
legacy 缺漏只能進異常與人工修正，不得由 Assignment Plan 猜測或補造。

依第 `21` 份正式規格，存在所有月嫂簽約完成後保存的 commitment 時，第一次 bootstrap 還必須鎖定並驗證
matching plan/version、staff 與精確日期集合完全相同；實際開始日調整適用下述同日最新裁決。人選、服務量或 current 日期確認不符時回
`commitment_execution_mismatch` 且零寫入。成功時 assignments、schedules、Payroll impact、
commitment `converted` terminal event、outbox 與 receipt 同一交易提交。Calendar Read、Payroll
與 Government Subsidy 在 conversion 前不得讀取 commitment days。

#### Matching Schedule Confirmation Gate (2026-08-12)

Formal Assignment Plan Preview and Apply must fail closed unless a current schedule snapshot is
bound to the current Orders confirmed-service-date version. The customer must have confirmed the
parent schedule and every caregiver segment selected for formal conversion must have confirmed
its own child schedule from that same lineage. The gate blocks only formal assignment/scheduling;
candidate search, matching communication, willingness, and waiting-deposit lock remain available.
Any terms, confirmed-date, matching-plan, recipient-binding, or schedule-fingerprint change
invalidates the lineage. The server enforces this gate for direct API callers as well as the UI.

When confirmed service dates change, the previous snapshot, delivery task and confirmation events
remain immutable historical evidence, but the current schedule-confirmation Query projects that
lineage as `sent_outdated`. The change itself creates neither a new snapshot nor an outbound
delivery intent. The UI must show the current date table and its difference from the previous sent
table; only an explicit human resend may create a new snapshot and durable delivery task. Previous
confirmations never satisfy the new version's Assignment Plan gate.

2026-08-24 人工裁決：LINE 不是日期表確認的唯一入口。缺少 LINE identity／binding，或現場、電話、
紙本已完成確認時，內部操作者可先對 current confirmed-service-date version 與 current matching plan
執行人工快照 Preview，明確確認後 Apply 建立 immutable `draft` snapshot 與 customer／caregiver
recipient snapshots；不得建立或假造 LINE delivery task。每位 recipient 再以非空 reason、actor、
idempotency identity 記錄 `manually_confirmed`／`manually_revoked`。Assignment Plan gate 僅接受 current
lineage 中客戶與目標月嫂全數 `confirmed` 或 `manually_confirmed`；日期、方案、segment 或 fingerprint
異動仍使舊確認失效。若後續改走 LINE，必須保留人工歷史、明確 invalidated 後建立新的 `sent` snapshot。

2026-10-15 使用者裁決：正常媒合案件的服務安排介面只保留「設定服務日期／確認排班」兩步。
日期表先由既有 Orders writer 保存，可在正式指派前顯示日曆；原訂服務方式須顯示於排休選擇旁，
本次排休星期仍只作試算輸入。人工確認只收一份非空確認紀錄；儲存該紀錄即為人員確認操作，
若尚無 current snapshot，由相同操作接續既有人工快照 Preview／Apply，再確認指定 recipient。
不增加確認方式選單或重複勾選，不建立 LINE delivery intent，結果未明時沿用原 command identity 恢復。

同日後續 UI 裁決：星期選項與「無固定週休」同列。日期設定直接以「儲存服務日期」作為人員確認，
在同一操作內沿用既有日期／開始日 Preview、Apply 及正式回讀，不再顯示額外預覽確認步驟；
只有完整日期表正式回讀成功後，才切換至「確認排班」，失敗或結果未明時留在原步驟續辦。
尚無指派時，可在上方同一日期欄位下單獨「儲存實際開始日」，只呼叫既有 actual-start writer，
不保存服務日期表、不自動切換步驟；下方不再重複呈現開始日表單。結果未明續辦須保留此單獨保存意圖，
不得自行升級成日期表保存。有既有班表時的開始日更正仍沿用原分段預覽與原子重排流程。

current 日期表的客戶及所有目標月嫂確認後，背景 discovery 以 canonical Assignment Plan Preview
驗證契約、訂金、waiting lock、檔期及精確日期；通過才 enqueue 既有 `assignment_plan_apply`。
command identity 綁定 case／plan／confirmed-date version／既有 PreviewFingerprint；相同事實只建立
一份工作，已失敗的同一命令不盲目重送。worker 必須以既有 Apply fresh-read／lock／UoW 完成 conversion，
不得由 UI 或 discovery 寫 assignments、班表、Orders、Finance 或 Payroll。條件未齊時保留確認證據，
下一次 discovery 讀取新的 owner facts 後再判定；有效正式指派存在時不得重做 bootstrap。

同日實際 UI 修正：尚無正式指派的單一月嫂方案，以 Orders current confirmed-service-date version 的完整日期作為該月嫂日期表及檔期保留來源，不再與原推薦的預計期間取交集而產生 0 天。首次正式指派的開始日必須等於目前實際開始日（未保存時為第一個服務日），結束日及 official dates 必須與已確認 recipient snapshot 完全一致；仍經原 Preview／Apply 檢查占用、契約、訂金與檔期鎖。等待訂金鎖只調整本次 canonical 候選投影，不改寫原推薦期間。既有快照的日期內容不符時，Query 呈現過期並保留 immutable 舊內容；明確人工確認可建立新快照，舊確認不得滿足新日期表。人工準備的 actor／reason 稽核欄位不構成日期差異。多月嫂仍依明確分段歸屬，不推測新分段。

`GET /api/v1/orders/{case_no}/matching-plans/{plan_id}/automatic-arrangement` 為唯讀狀態投影，
區分等待確認、等待條件、準備自動排班、queued／running、已生效及失敗；查詢不得 enqueue。
UI 以 owner assignments 回讀證明排班生效，不以 job accepted 取代完成。介面移除人工建立正式排班按钮，
但保留既有 API 及已接受命令的結果未明／回讀恢復入口。

2026-10-15 最新人工裁決：實際開始日改變不新增改期或重簽契約流程。首次轉換保留原 commitment、文件與簽回紀錄；同一 plan、同一月嫂及每位月嫂服務天數不變時，execution 日期可採用 current confirmed-service-date version 中客戶與所有目標月嫂最新確認的 immutable recipient 日期。不得由 caller 自稱已確認或改寫原 commitment dates；Preview 唯讀核對，Apply fresh-lock 重驗，轉換事件保存 snapshot／日期版本引用。未確認、不同人選、服務量不符或檔期衝突仍阻擋，既有契約、訂金及等待檔期鎖關卡維持。

服務安排以唯讀 `GET /api/v1/orders/{case_no}/client-finance/deposit-skip` 顯示 Client Finance 的
目前訂金應收、已核銷額及已生效的放行狀態，不能使用 Preview 的預期結果冒充現況。「未付款人工放行」一鍵接續
既有 deposit-skip Preview／Apply，保存標準操作原因且正式回讀。它不把未付款改為已付款，也不釋放
月嫂 reservation；既有適用條件及正式 writer 不變。契約簽回完成的下一步導向同案服務安排，核銷仍由帳務入口辦理。

名冊實際開始日更正沿用 Orders actual-start writer：無指派只保存日期；有正式指派時預覽各段並以
同一 Apply 原子更新開始日與班表。成功後導向同案服務安排核對，不能留下已改日期與舊班表等待事後補排。
換人入口導向同案推薦確認並開啟既有換人操作；已服務的既有請假代班裁決不變。

### Schedule Projection

由 assignment segment、排休規則及正式 leave outcome 產生完整 assignment-owned 日曆。禁止單日 CRUD、獨立 Generate 或 UI 直接切換 `is_work_day`。

### Leave／Substitution

多日請假為一次 Preview、一個 fingerprint、一次 Apply transaction；每一天保存 immutable outcome。正式結果只允許順延或指定代班。代班建立獨立 assignment；取消或更正以反向／替代事件處理。

2026-09-20 人工裁決：順延處理可選擇指定補班日期。未指定時仍依案件固定週休、國定假日及目前有效的國定假日上班協議自動順延；指定時只將該次服務由原服務日移至明確新日，不得無聲改成其他日期，也不得連帶移動其他既有服務日。原日與新日不得重複計入，全案服務日數守恆；與同案服務日、案件休假條件或人員占用衝突時，Preview／Apply 必須沿既有 typed blocker／conflict fail closed。指定日期須納入 request snapshot、fingerprint、immutable outcome 與正式 generation readback，不建立另一套單日 CRUD 或平行 writer。

2026-08-12 人工裁決：月嫂請假審核的 API、typed client 與管理入口由 Scheduling 擁有，
不得掛在 LINE identity review route 或 `LineAdminApiClient`。LINE 只提供 verified identity、
delivery intent 與通知結果。現有依賴已退役 `services.*` 的 review service 是 `live-drift`，
在 canonical repository／outer UoW、capability、typed result 與 entrypoint replacement 完成前
不得掛入 FastAPI。

2026-08-15 人工裁決：LINE 月嫂請假先寫入 Scheduling request evidence，不自動猜案件、服務日、
代班人或更動 availability／正式排班。request 的 `pending`、`accepted_for_processing`、`rejected`、
`cancelled` 與 `resolved` 是獨立狀態機；只有已受理 request 能由唯一 canonical leave-substitution
receipt 關聯為 `resolved`。receipt 必須證明原 leave outcome 的 staff 與 request staff 相同，且同一
receipt 不得關聯兩筆 request。正式 Apply 的 locks、跨 Domain impacts 與 receipt 不因 request
存在而變更；LINE 通知是 committed durable delivery task，失敗不回滾正式結果。

Batch replay：

- `batch_key` 是一次多日操作的冪等 identity，並綁定 canonical request snapshot、
  Preview fingerprint、actor 與 reason。
- Apply 先以 `batch_key FOR UPDATE` 讀取 header；不存在才可進入施工，存在時必須再鎖定
  並讀取全部 child events。
- header、item count、連續 ordinal、case／assignment linkage、request snapshot 與
  fingerprint 全部完全相同時回傳原 receipt，不再執行 mutation。
- 相同 `batch_key` 搭配不同 request 或 fingerprint 回 `batch_key_request_identity_conflict`；
  header 缺 child、ordinal 重複／缺號或 lineage 不一致屬資料完整性 blocker，不自動補寫。
- batch header、逐日 events、assignment／schedule replacement、payroll impacts、outbox
  與 receipt 必須同一 transaction；rollback 後不得留下可被誤認為成功的 partial batch。

與 Orders AutoComplete 的競爭契約：

- leave-substitution Apply 與 AutoComplete 必須先鎖定同一 Orders lifecycle aggregate，並驗證同一
  expected Orders lifecycle version；不得各自只鎖 Scheduling 或 Orders projection。
- AutoComplete 先提交時，舊 leave Preview 必須以 typed `stale_version`／version conflict 失敗；
  Scheduling generation、assignment／schedule、Client Finance、Payroll、leave outcome、receipt 與
  outbox 全部零寫入。
- leave-substitution 先提交時，必須在同一 transaction 更新正式服務日與 Orders lifecycle version；
  舊 AutoComplete command 必須以 `order_version_conflict` 失敗且零寫入。只有重新讀取新 effective
  generation、official service days 與新 completion instant 後，才能再次判斷完成。
- LINE leave request evidence 或管理員受理狀態不參與此競爭；只有 canonical leave-substitution
  Apply 會取得鎖並改變正式根事實。
- 任一 stale／conflict 路徑不得留下 partial batch，也不得以「先完成後補請假」掩蓋競爭。

### Assignment Lifecycle Projection

`planned`、`active`、`completed` 由正式服務時刻推導；中間休假仍 active。`cancelled` 只由命令產生；`replaced` 只作 legacy 相容。

### Calendar Read

日曆的業務說明使用「排班」「服務日」「工作日」與「歷史指派」，不加「正式」前綴；技術識別名稱維持原名。資料來源與納入時點如下（2026-10-15 澄清）：

| 顯示內容 | 來源步驟 | 納入條件 |
|---|---|---|
| 等待訂金檔期及緩衝提醒 | 媒合決定配對後保留等待訂金檔期 | 有目前有效的 waiting lock／buffer，且日期與查詢期間交集；不表示已有排班工作日 |
| 排班區間、工作日、休假及服務狀態 | 確認服務日期與排班中的排班建立／安排；後續請假、順延、代班修改沿同一 owner 保存 | 有目前有效 assignment／逐日排班且日期與查詢期間交集；只保存日期或產生前段服務說明不形成這些排班資料 |
| 已完成案件的歷史指派區間 | 已保存的 completed 歷史 assignment 與起訖日 | 即使未重啟精算且缺逐日排班，仍依下節規則唯讀顯示；重啟精算使舊歷史指派失效後不再覆蓋目前排班 |
| 長假／暫停接案 | 月嫂不可服務期間設定 | 有目前有效不可服務期間且與查詢期間交集 |

「尋找月嫂與詢問意願」中的每週服務說明不是日曆排班來源。日曆可顯示歷史區間，不表示該區間可計入「每週服務中與工時」；工時表另要求目前有效逐日排班。來源修改套用後，重新查詢取得最新投影。

#### 日曆顯示優先順序與排班替換標準（2026-10-15 澄清）

日曆查詢只讀取、組合目前資料，不寫入或覆寫排班。顯示優先順序與業務操作造成的排班替換分開判定：

| 情況 | 處理標準 |
|---|---|
| 新的每週服務說明或只保存服務日期 | 不替換已存在的排班；後續仍須經排班建立／調整操作及相關 gate 驗證 |
| 同案人員、日期或指派區間有變更 | 經相應改期、換人、請假／順延／代班的 Preview／Apply，通過版本、服務量及占用檢查後，以新有效排班取代舊有效排班；舊紀錄與變更血緣保留，不原地改寫 |
| 只改費用、每日時數或其他不改人員／日期／區間的條件 | 保留原排班版本；相關帳務或工時依其 owner 更新，不因此另建排班 |
| 等待訂金檔期轉成排班 | 契約、訂金與日期確認等關卡符合，排班建立成功後由同一交易轉換檔期保留；不能在日曆查詢時自動轉換 |
| 目前資料與歷史指派區間重疊 | 目前有效排班、檔期保留、緩衝或不可服務資料優先；歷史區間只補沒有目前資料的日期。已重啟精算而失效的舊歷史指派不再補顯示 |
| 多筆目前占用互相衝突 | 排班、等待訂金服務日與不可服務期間不得靠顯示順序互相覆蓋；回 typed conflict，修改操作零寫入，由人員依相應流程調整 |
| 緩衝提醒與其他資料重疊 | 緩衝是提醒，可與排班等資料並列；不取代工作日、不改月嫂服務狀態，也不以緩衝重疊阻擋安排 |

替換後只讀新的有效排班作為目前排班，重新查詢日曆顯示結果；保留歷史不代表舊排班仍同時有效。

逐日顯示 waiting lock、buffer、assignment interval、排班工作日與休假。只組合 typed ViewModel，不在 Query 或 render 時轉移狀態。

Calendar 亦顯示 current 長假／暫停接案的日期、kind 與原因。這些日期不可標為可接案、排班服務日、
assignment leave outcome 或七日 buffer；取消後保留歷史但不再出現在 current availability projection。

Calendar／React 只能顯示 Scheduling typed projection 的 `planned／active／completed` 與逐日
`assignment_status`；不得依 Orders label、瀏覽器日期、occupancy tone 或是否含案件編號自行推導「服務中」。
`assignment_buffer`／`waiting_deposit_buffer` 永不得標為服務中；完成 assignment 的歷史服務日顯示
「服務已結束」，但仍維持唯讀歷史可見性。

Calendar 的「可進行出勤精算案件」必須先以 Scheduling 的單一批次 read
`staff/{staff_id}/assignment-schedules` 取得該月嫂未取消的正式 assignment `case_no` 集合，
再與 Orders 摘要相交。不得以 `orders.staff_id`、`orders.staff_name` 或逐案
`cases/{case_no}/assignment-schedules` fallback 作為 formal-assignment 判定；前兩者可能是投影
漂移，後者會形成 N+1 read。此 query 只授權 Calendar 選案，不授權 Preview 或 Apply 寫入。

#### Calendar presentation 與案件選擇（2026-08-25 人工裁決）

- 沒有 assignment、waiting lock、buffer、不可服務期間或其他 typed occupancy 的日期，不渲染灰色
  空白占位方塊；空白日期不是一種排班事件。月嫂姓名下方只顯示 server typed 的 current 可排班狀態
  與必要人可讀原因，不得由灰階、cell 是否存在或瀏覽器日期自行推導 availability。
- 真實 assignment／lock／buffer／不可服務期間仍依各自 typed kind 顯示，不能為了移除灰塊而隱藏
  排班占用、合法唯讀歷史或 blocker。
- 「可進行出勤精算案件」改為下拉選單。選項由上述單一批次 Scheduling read 與 Orders typed summaries
  的 server／client adapter 組合取得，包含穩定 case identity 與人可讀 label；不得要求操作者手動輸入
  `case_no`，也不得使用 `orders.staff_id`／`staff_name` fallback 或逐案 N+1 查詢補選項。
- 下拉選單須有 loading、合法空、error、retry、stale request cancellation 與 identity-preserving refresh；
  options query 失敗時不掛載 Preview／Apply，且不得保留上一位月嫂的 stale 案件。
- 選定排查案件後，每位月嫂的月曆列須以一個連續區間顯示該案件的完整排班服務檔期；若完整檔期內
  任一天與 assignment、lock、buffer 或不可服務期間衝突，仍顯示整段案件檔期並將整段標示為有衝突，
  衝突天數與原因留在狀態文字／詳細排查中。不得只渲染零碎衝突日期而隱藏同案其餘服務日期。

驗收狀態（2026-08-25）：`completed`。Calendar 已以 typed 下拉選案，並依同日最新人工裁決改為
完整服務檔期連續投影；任一日期衝突時，整段檔期顯示衝突。Focused tests／React build 已通過；
最新 Chrome 實選跨月案件 `115000008`（`2026-09-05 ～ 2026-10-13`），九月投影為 9/5～9/30、
十月投影為 10/1～10/13；同一月嫂若任一天有 typed 衝突，兩個月的可見區段皆顯示整段受影響。
月份切換與清除案件後無 stale 投影或 API error。

#### Completed assignment historical projection（2026-08-12）

完成訂單與 `completed` assignment 一律可在 Calendar 唯讀查閱，完成狀態只禁止
leave／substitution 等 mutation，不得使歷史區段消失。Query 優先顯示
assignment-owned `staff_schedule.assignment_id` 的每日 ownership；若 historical／legacy
資料缺少該 daily ownership，但 `case_staff_assignments` 保有 completed assignment 的起訖日，
Calendar 必須以該區段顯示 `historical_assignment`／「歷史指派」。此 fallback 是歷史占用
view，不能宣稱為排班工作日、不能重算 actual hours、不能產生薪資、不能變更 availability
current projection，也不能授權任何 Apply。

同一天若同時存在 assignment-owned daily schedule、waiting lock、buffer 或其他 current fact，
該 current fact 優先；historical fallback 只填補沒有較高權威逐日事實的日期。Calendar 不得使用
`orders.actual_start_date`、`orders.staff_id`、legacy 無 `assignment_id` 的 `staff_schedule` 或 UI
自行推算，將完成案歷史誤標為「可接案」或「服務工作日」。

## 5. Modules

- `SegmentCoverageValidator`
- `AssignmentIntervalValidator`
- `OccupancyIntervalProjector`
- `OfficialWorkdayProjector`
- `ActualHoursCalculator`
- `CaseServiceConservationValidator`
- `AssignmentStatusProjector`
- `BufferDateProjector`
- `AvailabilityConflictDetector`
- `AssignmentRebuildPlanner`
- `ScheduleDiffBuilder`
- `LeaveResolutionPlanner`
- `SubstitutionOwnershipValidator`
- `SpecialPayProjector`
- `CandidateFingerprint`
- `RebuildLineageBuilder`

Modules 是純函式；不讀 DB、不取現在時間、不 import UI/API。

## 6. Apply transaction

```text
authorize／idempotency lookup
→ lock case aggregate/version
→ 依 preflight impacted set 按 staff_id 升冪鎖定月嫂占用
→ lock batch replay header／children
→ 載入 fresh Orders、Finance 與凍結事實
→ 使用 Preview modules 重建 candidate
→ 驗證 version／fingerprint／coverage／ownership／hours／occupancy
→ 取消受影響舊 assignments 與舊 current schedules
→ 新增 assignments、schedules、locks 與 immutable events
→ 推導 actual hours、status、actual end 及跨域 impacts
→ 委派 Orders lifecycle、Payroll、Client Finance
→ 寫 outbox／receipt
→ 單一 commit
```

對於涉及大量計算的排班指令（例如 `ApplyAssignmentPlan` 與 `ApplyLeaveSubstitutionBatch`），API 應支援回傳 `202 Accepted` 並以 Durable Job 於背景執行。背景 Worker 仍必須嚴格執行此處定義的「單一原子 transaction」，不得因為非同步執行而將 lock 與 commit 拆分為多次。

全 Scheduling commands 共用下列鎖定順序：

1. case／Scheduling aggregate；
2. 全部受影響 `staff` mutex rows，去重後按 `staff_id` 升冪；
3. replay batch header／children；
4. effective generation 與 assignments，按 assignment id 升冪；
5. schedules／waiting locks／buffer facts，按日期與 row id 穩定排序；
6. Payroll／Client Finance obligations，按 owning aggregate identity 穩定排序。

鎖 staff mutex 後必須 fresh 重建 impacted staff set。若 fresh facts 出現 preflight 未包含的
新 staff，不得中途再取得較小或任意順序的 mutex；本次 transaction rollback，回
`scheduling_lock_set_stale`，由呼叫端重新 Query／Preview。任何 repository／Subsystem
不得另訂第二套鎖順序或自行 commit。

鎖後必須重新驗證：Orders Terms／actual start／aggregate version、唯一 effective
generation、原 assignment 仍有效、所有目標 schedule 的日期與 owner、全案 coverage、
staff occupancy、waiting lock、七日 buffer、Payroll／Finance freeze、完成時刻及 Preview
fingerprint。任一不同均零 mutation 回 conflict；不得信任 Preview snapshot 或 UI payload。

## 7. 必要資料模型

- **已確認採用 `generation + effective` 模型**：每次正式 Apply 取消舊有效 generation、完整保留其 assignment／schedule 歷史，並建立新的 effective generation；目前排班、工時、檔期與薪資只讀 effective generation。
- 同一個 `case_no` 同一時間只能有一個 effective scheduling generation；切換 effective generation 必須與新 assignments、schedules、重建事件及 aggregate version 在同一交易完成。
- `UNIQUE(staff_id, work_date)` 與 `UNIQUE(case_no, assignment_sequence)` 必須納入 generation／effective 語意，使歷史 generation 與目前 generation 可共存，同時仍禁止 effective generation 內重複 ownership。
- 建立通用 rebuild command/event，保存 old/new sets、actor、reason、version、fingerprint 及 idempotency key。
- lock day 必須區分 `service` 與 `buffer`；buffer 有獨立 lifecycle。
- `staff_schedule.assignment_id` 必須進入 base schema，正式歷史不得 `ON DELETE CASCADE`。
- Scheduling aggregate 需要獨立 version 與 idempotency receipt。
- 完工後正式日期更正仍須經 canonical generation replacement：舊 effective schedule 退役、
  successor assignment／`staff_schedule`／occupancy 同交易生效，舊 generation 與 rebuild lineage 保留；
  Orders correction command 不得原地修改舊 `work_date`。新有效 assignment 的完成狀態
  必須與已完成 Orders lifecycle 一致，週報只讀 successor effective 工作日。
- batch header 必須唯一 `batch_key`；child event 必須唯一
  `(batch_key, batch_item_index)` 與穩定 event identity，且 ordinals 從 0 連續。

## 8. 驗收

Module 驗證 coverage、full-interval occupancy、七日 buffer、時區、hours 與 fingerprint。
Subsystem 使用隔離 MySQL 驗證 Preview 零寫入、cancel/create、exact batch replay、
batch-key payload mismatch、partial replay corruption、鎖後 impacted-staff set 擴張、
相反 staff 順序的並行命令、stale、占用衝突及 rollback。Domain 覆蓋單／多月嫂、
waiting deposit、全案條款重建、局部請假、順延、代班、buffer 釋放與完整履約取消拒絕。
Calendar Query 必須驗證 completed assignment 在缺少 assignment-owned daily schedule 時仍回傳
唯讀 `historical_assignment`，且不覆蓋同日的 current ownership／lock／buffer，也不顯示為可接案。

### Current anomaly owner decision matrix（2026-08-31）

下表只組合本 Domain 已有的 Assignment Plan 與 Leave／Substitution Q／P／A；不新增
generic remediation 或 Anomalies writer。共同 owner readback 必須綁定 current Scheduling aggregate
version／effective generation，回報 `authoritative_complete`；owner Apply 在既有 outer UoW 內與
receipt／outbox 一併寫入 bounded `anomaly.recheck` intent。readback 不完整、stale 或 unavailable
一律 fail closed。

| Code／subject | Active predicate（current roots） | 唯一合法 owner operation | Completion predicate | Closed unresolved reasons |
|---|---|---|---|---|
| `SCHEDULE-002` / `assignment_id` | current replacement／substitution lineage 不完整：既有 assignment 已失效，但 exact successor、受影響每日 outcome、official ownership 或必要 Payroll／Finance impact 仍有缺口 | 未有任何正式服務日時使用 `Preview／ApplyAssignmentPlan`建立新 effective generation；已有正式服務日時使用 `Preview／ApplyLeaveSubstitutionBatch`只重建受影響 family | exact old/new lineage 存在，每日 outcome、official ownership、全案 coverage／hours 與必要 Payroll／Finance impacts 全部完整 | `replacement_successor_missing`, `daily_outcome_incomplete`, `service_ownership_incomplete`, `payroll_impact_incomplete`, `finance_impact_incomplete`, `owner_readback_incomplete` |
| `SCHEDULE-003` / sorted `assignment_id_a + assignment_id_b` | 兩個 current effective assignments 使同一 staff 的完整占用區間重疊 | 人員在 `Preview／ApplyAssignmentPlan` 明確選定受修正案件與 candidate；Apply 仍以 cancel-old／create-new 重建該案 current generation，並 fresh 驗證另一 assignment 的占用 | 該 canonical pair 在 current effective generations 不再重疊，兩案 coverage／ownership／hours 仍合法 | `correction_target_not_selected`, `staff_occupancy_conflict`, `coverage_incomplete`, `owner_readback_incomplete` |
| `SCHEDULE-006` / `case_no + generation` | current effective generation 的 official service dates、daily ownership、coverage、hours 或 staff occupancy 任一違反本規格，或有效服務量不等於 Orders 契約服務量 | `Preview／ApplyAssignmentPlan` 以 current Orders terms 與 Scheduling roots 重建完整 generation | 同一 current snapshot 下 official dates、ownership、coverage、hours、occupancy 與唯一 effective generation 全部合法 | `official_service_dates_invalid`, `service_ownership_conflict`, `coverage_incomplete`, `hours_mismatch`, `staff_occupancy_conflict`, `generation_conflict`, `owner_readback_incomplete` |

```yaml
convergence:
  status: READY
  requirement_ids: [SCH-ANM-002, SCH-ANM-003, SCH-ANM-006, SCH-ANM-READBACK]
  acceptance_ids: [SCH-ANM-ACTIVE, SCH-ANM-OWNER-QPA, SCH-ANM-TERMINAL, SCH-ANM-FAIL-CLOSED]
  blockers: []
```

## 9. Typed Commands／Ports／Errors

Commands：

- `QueryStaffAvailability`
- `PreviewAssignmentPlan`
- `ApplyAssignmentPlan`
- `PreviewLeaveSubstitutionBatch`
- `ApplyLeaveSubstitutionBatch`
- `AcquireWaitingDepositLock`
- `ReleaseWaitingDepositLock`
- `ConvertWaitingDepositLock`
- `CancelWaitingDepositLock`
- `QueryCaseCalendar`

輸入 ports：

- `OrdersTermsFactsPort`
- `OrdersActualStartFactsPort`
- `ClientDepositSettlementFactsPort`
- `PayrollImpactCandidatePort`
- `ClientFinanceImpactCandidatePort`
- `BusinessClockPort`

Stable errors：

- `invalid_scheduling_intent`
- `case_not_found`
- `staff_not_found`
- `assignment_not_found`
- `coverage_incomplete`
- `service_ownership_conflict`
- `staff_occupancy_conflict`
- `waiting_lock_conflict`
- `buffer_conflict`
- `scheduling_generation_conflict`
- `scheduling_lock_set_stale`
- `stale_preview`
- `batch_key_request_identity_conflict`
- `invalid_batch_replay_snapshot`
- `scheduling_data_integrity_violation`
- `idempotency_conflict`
- `transaction_failed`

## 10. Live writer 退出

### 休假／代班 Calendar Preview 補充裁決（2026-08-12）

- Preview 必須回傳零寫入的 before／after day-cell candidate 與獨立 `apply_readiness`。
- Client Finance、Payroll 或 Orders blocker 不得遮蔽已成立的 Scheduling candidate；UI 必須停用 Apply。
- 代班只替換同一服務日 owner；順延才移動服務日期。兩者都必須維持合約服務日數守恆。
- Apply 必須 fresh rebuild 並重新檢查 blocker、versions、fingerprint 與 occupancy，禁止信任 UI snapshot。
- `SchedulingHolidayQuery` 是 Preview／Apply 共用的版本化、fail-closed read port；國定假日預設為休假、扣除服務日並順延。Holiday facts 必須納入 Preview fingerprint，Apply 必須 fresh-read 並鎖定同一 planning horizon；無法讀取時回 `holiday_calendar_unavailable`。
- Holiday 管理 Query 必須回傳 closed typed rows、`source_identity`、calendar version 與明確
  planning horizon；Preview 為零寫入，Apply 以同一 horizon fresh-lock、驗 expected version 與
  fingerprint，並把 holiday mutation 與 immutable receipt 放在單一 outer UoW。Cache 只在
  commit 後失效，失效失敗不得改寫已提交 receipt。`is_double_pay_default`僅為相容參考，
  不得由 UI 或 Scheduling 自動產生 Payroll 規則。
- Leave／substitution Calendar Preview 的 API view、UI client 與 route payload 必須以同一
  `LeaveSubstitutionPreviewView` 驗證；成功 envelope 的 nullable `error` 不得被 UI 誤判為
  失敗。UI 只 render typed candidate、holiday rows 與 apply readiness。

- `services/assignment_schedule_rest_date_service.py` 的 canonical batch replay、event 與純
  transition 可吸收；直接 UPDATE／DELETE assignment 或 schedule 的 mutation 必須移入
  Scheduling persistence adapter。
- `services/caregiver_availability_lock_*` 與 `services/caregiver_matching_*` 只可經 typed
  Waiting Lock／Assignment commands。
- `services/multi_caregiver_schedule_generation.py`、
  `services/multi_caregiver_schedule_adjustment_service.py`、
  `services/order_assignment_synchronization.py`、`services/payment_service.py` 與
  `services/db_service.py` 的 assignment／schedule writers 遷移後關閉。
- `services/actual_hours_adjustment_confirmation_service.py` 不得再寫權威 actual hours；
  legacy adjustment 僅供異常 recovery。
- final writer scan 必須證明 effective assignment、schedule、waiting lock、buffer、
  rebuild event 與 Scheduling version 都只有本 Domain persistence adapters 可寫。

## Candidate Contact Pool（2026-08-12）

Scheduling／Matching 擁有 case-owned Candidate Contact Pool。它只擁有候選月嫂聯繫事實：候選人、完整 coverage evidence、資訊-1／資訊-2 發送事件與 delivery 狀態、月嫂意願、拒絕理由、人工補登 actor／時間。它不是 `caregiver_matching_plans` 或 `caregiver_matching_plan_segments`，不得建立 availability lock、正式 assignment、staff schedule、日期表 snapshot、客戶履歷傳送或正式指派資格。

- 一次可加入多位候選人；對預計服務日期有部分或全部檔期衝突的人選仍可聯繫協調。加入與每次資訊發送皆須 fresh-read availability，保留目前 coverage evidence，不得把有衝突的人選標示成完整無衝突。
- 初步意願詢問以預計起訖期間檢查檔期，不要求 BeClass 或正式服務日期精算完成；未填需求仍為未知、顯示待確認，不得寫成 false。已填需求才參與啟用的查詢篩選；「偏好服務日」與「每日服務時數」勾選時，只列出符合已填需求的月嫂，未勾選時不以該項排除。查詢畫面每人只顯示空閒／總天數及彙總衝突提醒，不逐日列出衝突。加入／聯絡時重新檢查占用與不可服務期間，不重新套用使用者查詢偏好；詢問 coverage 不形成正式服務日、工時、薪資、assignment 或方案資格。正式 matching plan 仍須原有正式日期及完整 fresh-fact gates。
- 發送資訊-1／資訊-2 是詢問接案意願的唯一聯繫動作；不得另建沒有資料效果的「聯繫與確認意願」命令。
- 每位候選人的意願及資訊寄送紀錄獨立、append-only 且以 candidate entry／event key 冪等；不得由同案其他候選人覆蓋。
- 2026-10-14 人工裁決：候選與詢問使用同一個案件共用資訊入口，未有候選也能查閱；服務條件與費用、照護與飲食需求、每週服務說明三份內容可各自選擇候選月嫂並分開寄送。收件人確認與 Apply 仍逐人核對 canonical bound LINE identity、current facts、preview fingerprint 及 event key，同一份內容與每人的投遞回條分别保留；共用畫面不建立虛構 candidate／assignment。
  每週內容只使用 Orders 已保存且天數相符的 current service dates 與每日時數；當次試算仍零寫入，不可寄送。獨立週說明為補充資訊事件 `info_3_sent`，沒有意願回覆按鈕，不重新啟動資訊-1／2 的詢問期限、全池完成 gate 或人工跟進；不連動薪資、正式指派與排班。
  清單依原 event key／task ID 綁定的 LINE-owned task 投影目前投遞狀態與送達時間；原發送事件不改寫，排入佇列不代表已送達。人工確認沒有 provider task 時仍採其原確認事件。
  工會工作台以候選清單、抽屜逐筆新增候選與卡片內手動意願表單續辦；「前往客戶確認準備」只帶入已願意的人選，不自動建立方案或客戶決策。「尋找月嫂與詢問意願」提供「候選月嫂／多月嫂分段」入口；分段沿用原查詢與正式分段 writer，查詢不建立方案，只有明確採用完整組合才建立正式推薦方案，收據及分段回讀成功後進入客戶確認準備。正式日期、完整 coverage、接受及鎖定規則維持既有契約。名冊換人入口保持既有流程。
- 候選池 readback 必須以 nullable `latest_willingness_event_id` 回傳該候選人最新有效意願事件的既有 event ID。客戶端只有在此 ID 與自己收到的意願回條相同、且意願值相同時，才能確認該次回覆已儲存；較新的同值或異值事件只代表最新狀態，不得確認原操作。
- 客戶同意日期調整、且 Orders Terms 已修改未指派案件的 planned 起訖日後，一般候選資訊預覽與寄送前內容均讀 current Orders 期間。一般寄送或重新聯繫原候選人必須在同一 Scheduling transaction 以相同 current Orders 起訖日重驗 coverage；有衝突仍可繼續協調，期間有異動時更新 candidate contact period／coverage fingerprint、追加前後日期事件並排入新資訊卡，任一步失敗皆 rollback。Preview 零寫入，既有寄送 receipt 重播保留原內容／任務，不建立正式服務日或 assignment；正式 plan／assignment 的期間仍由各自 owner 擁有。
- 未正式排班即可預覽每週服務時間。未有 confirmed service dates 時依候選期間、週休及特殊休假推算並核對 Orders 約定服務天數；不足或超出必須明示，不能靜默視為履約完整。已有 current confirmed dates 時使用精確服務日，包括人工協調的週末上班；同時顯示延長後的 actual conflict 與 buffer 提醒。協調後須重新確認服務日期；正式排班仍以 current owner dates 驗證服務量及實際占用。
- 2026-10-13 人工裁決：前段每週說明顯示 Case Import 原始服務方式，人工週休僅用於當次 server 試算。
  當次日期經 Orders Preview 驗證後零寫入投影；一按「保存預計日期」沿 Orders Service Dates writer 保存，
  無另一步核對／確認，不保存星期設定或 Actual Start，不建立 Scheduling assignment／occupancy。
  重開及客戶確認資訊均使用 current 保存日期；寄送仍保存既有不可變內容快照，不自動轉換原文。
- 2026-10-13 後續人工裁決（只解除建立推薦被預計日期阻擋）：由單一已願意的初步候選建立推薦方案時，
  fresh availability 沿用候選詢問的預計期間；前段每週說明所保存的日期不參與此步的期間／完整組合 gate。
  仍核對 active 候選、原詢問期間及初步意願，真正的檔期衝突與不可服務期間維持阻擋。
  不改寫候選詢問期間、不更換方案期間為預覽日期，也不連動 actual start、正式服務日期或 Scheduling writer。
  正式排班與既有多月嫂正式分段的日期／完整 coverage 檢查維持既有契約；預計、實際開始日可不同。
- 管理員僅能從 `willing` 候選人選定一位，重新檢查可用性後建立一個 segment 的正式 matching plan。
- 正式 matching-plan create command 必須帶 1–191 字元的 `event_key`，並以案件、依序的完整 segments、actor 與 `as_of` 組成 immutable command fingerprint。Apply 先鎖定案件 root、再以 `event_key` 鎖定並重查 receipt；同一完整原命令只回傳已保存的 plan／version／status／segments receipt，不重新檢查已被原命令改變的 availability，也不得依 current plan 或建立時間推測舊結果。相同 key 搭配任一不同 command fact 必須衝突且零寫入。新的 plan、segments 與 receipt 必須在同一 outer UoW 提交；既有歷史 plan 不得回填或臆造 receipt。receipt Query 只證明原命令 identity，unknown-result recovery 仍須另讀 current matching-plan owner state 後才可結束觀測。
- 多位月嫂共同服務仍是顯式 multi-caregiver fallback plan，不能由候選聯繫池直接轉換。
- 選定、撤回或取消不得刪除候選聯繫歷史。正式 plan 後的日期表、客戶與月嫂雙方確認及 assignment gate 僅針對該正式 plan recipients。

### 人工媒合確認（2026-08-24）

2026-10-14 推薦確認人工裁決：同案 active 候選已記錄願意承接，且其詢問期間涵蓋正式方案區段時，
該紀錄直接作為此區段的接案同意，不要求工會再次按正式同意。這是唯讀意願投影，不追加虛構人工
同意、LINE 送達或正式指派；無此候選依據者維持 pending，須返回詢問。區段已有正式意願回覆時，
該回覆優先；月嫂通知不承接可沿既有正式 manual response 記錄 unwilling，仍須 actor、原因、版本、
原命令冪等識別及回讀。原詢問與通知紀錄保留。
人工通知更改意願允許 append 新的 willing／unwilling；同一 outer UoW 同步通知該區段期間對應的
active 初步候選，避免下次推薦又採用舊同意。不建立不存在的候選。工會人工更正仍不作用於已有
effective assignment 的案件；實際人員異動改走換人或代班。

2026-10-14 LINE 意願更正人工裁決：正式方案的月嫂本人於既有互動有效期限內，可在客戶決策為
pending／contact_requested 時反覆修改 willing／unwilling；已接受的方案仍允許月嫂通知 unwilling，
形成換人需求，但不得由 LINE 自行改回 willing 而解除該需求。客戶已 declined 時不開放意願變更。
每次新回覆沿既有 append-only event、原 webhook idempotency key 與 communication version writer；
仍核對互動及區段 recipient、有效方案與原到期時間。caregiver_willingness 互動可重複使用，包含尚未
過期且此前已標 consumed 的月嫂互動；客戶決策互動仍為一次性，取消、過期或失效方案不能重用。
最新正式通知為不承接者，不論是否已有 effective assignment，推薦確認的唯讀待辦投影皆回到待處理，
要求換人及重新取得客戶確認。既有客戶接受或檔期保留不得冒充現行接案同意；不回寫 Orders lifecycle、
歷史決定或指派資料，不自動撤銷檔期、契約或排班。已有指派者由既有換人流程處理；已有 actual-service
proof 者仍轉介請假代班，LINE 不直接執行 replacement／substitution writer。

2026-10-14 R-04 接續裁決：服務前整案換人 Apply 與原 generation transition 同一 outer UoW
退役同案仍有效的 caregiver matching plan，追加帶有 replacement event identity 的不可變歷史，
原方案的月嫂候選 entry 退為 withdrawn，保留原意願、客戶接受與投遞紀錄，不移植至新方案。
新 round 不以原 package 的候選同意或客戶接受跳過重新推薦；新選定人選仍須 fresh availability、
current candidate willingness 與日期完整性檢查。沒有新方案時回到選人／推薦準備；R-04 收據僅表示
換人已啟動，不表示新推薦已建立。前端須正式確認原方案已非 active，才能接續選人；交接回讀失敗
只重讀，不重送 R-04。新方案必須有不同 plan identity，獨立寄送與重新取得客戶決定。
Orders lifecycle 保持原狀；只有已提交 R-04 收據綁定 current effective generation、且該 generation
尚無正式 assignment 時，訂單成立案件可沿既有候選詢問及客戶確認 writer 續辦。過往 R-04、已被
替代的 generation、已恢復正式指派、取消或服務中的案件不得借此開放媒合。Query／Preview 零寫入，
不新增另一個 commit owner、schema、付款／契約或 provider writer。

2026-10-15 R-04 跟進一致性：候選 24 小時逾期掃描、工會人工跟進清單／操作與未送通知取消，
使用同一 current R-04 receipt／effective generation／零 assignment 資格；SQL 掃描先過濾再套用
批次上限，訂單成立不得單獨作為取消通知的理由。資格失效時，只取消原有 pending／retryable_failed
人工跟進通知；取消檢查於 canonical LINE delivery 前執行。既有 completed delivery、lease 中的
processing、其他通知 source、本人驗證及 post-answer Orders Terms receipt gate 均沿原契約。

推薦確認頁提供單一換人入口。尚無 effective assignment 的案件以 Matching-owned 推薦取消、
檔期釋放與新方案建立續辦：有有效檔期鎖時先完成既有 Release Preview／Apply，再取消原 proposed
方案，最後明確建立新推薦；每一步分別保留原命令與回條，結果未明不得跳步或換鍵。取消須 fresh
鎖定並確認沒有 effective assignment、沒有有效檔期鎖，且 caller 提供的 communication version 未變。
新推薦須重新取得客戶決定，原決定不移植。多月嫂更換保留未更換段落的人員與日期；新建立仍經
原完整 coverage 與 availability gate。已有 effective assignment 時沿原 service-before-replacement
Query／Preview／Apply；已有 actual-service proof 則走請假代班，不以推薦取消旁路正式指派。

2026-10-14 財務裁決：尚未建立訂金義務而缺 settlement projection 時，僅在 Client Finance
完整查核並提供 typed 未收款確認後，才允許原檔期 Release。查核借用原 UoW，確認事實與
Finance 版本納入既有 Preview fingerprint，Apply fresh-read；Scheduling 不自行認定缺資料等於零。
未收款確認保存在原 release 事件，換人原因與原命令回條仍沿用既有規則。

換人表單僅必填換人原因，evidence references 可為空，仍保留已有 references 的歷史與原 payload
fingerprint 語意；不得為省略輸入捏造聯繫紀錄。客戶資訊集中查閱，寄送與人工客戶決策在主頁分別
明確確認；建立發送工作不代表送達，履歷仍為 optional attachment。

LINE identity、recipient binding 或 delivery 缺漏時，已登入的內部操作者可透過正式 matching-plan
manual response 記錄特定 segment 的月嫂意願與客戶決策。每筆皆須 actor、非空 reason、目前 plan
version、idempotency identity 與回讀；不得偽造 LINE delivery 或省略正式 plan recipient。LINE callback
仍必須驗證 recipient／delivery state。客戶接受仍只形成 matching decision，後續鎖定、契約與 execution
各自遵守其既有 Preview／Apply gate。

2026-09-14 人工裁決：正式方案寄送客戶確認資訊時，月嫂履歷 PDF 是 optional attachment，缺少履歷、
受控檔案儲存尚未配置或目前履歷不是有效 PDF 都不得阻擋其餘確認資訊與客戶決策入口。系統須在內部
操作介面明確提醒未附履歷，送出的 LINE 卡片省略該履歷下載按鈕；公會人員可沿用既有方式另行以 LINE
手工傳送履歷，但不得把這個系統外動作偽造成受控檔案 delivery。訂單資訊－1、訂單資訊－2、每周服務中
說明、方案有效性、全體月嫂意願、客戶 LINE 綁定與檔期 fresh validation 仍是寄送 blocker。

2026-09-22 人工裁決：退休獨立的「國定假日上班雙方協調」入口與 agreement
Preview／Apply contract。出勤精算的初始建議仍將國定假日視為休假；工會人員在 Orders-owned
正式服務日期月曆逐日選取並完成 Preview／Apply，即代表已核對該組日期是否包含國定假日，無須另一份
matching-plan agreement。正式服務日期版本、actor、原因、日期集合、fingerprint 與冪等 receipt
是此人工確認的唯一 current 稽核事實；後續 Scheduling 投影須保留已確認的正式服務日，不得再讀取
歷史 `matching_holiday_work_agreements` 改寫日期。既有 agreement 資料只保留歷史證據，不再形成
current gate、精算 override、LINE delivery 或回覆事實。

## Historical pairing evidence（2026-08-13）

Historical Order Adoption 可保存一或兩位來源月嫂的不可變配對 evidence。月嫂姓名空白、找不到或
不唯一都不阻擋 Orders status adoption；只形成 bounded review。單一月嫂且共同起訖日可唯一視為
該月嫂自己的歷史區間時，可由 purpose-specific Scheduling writer 建立 `completed`
`case_staff_assignments`。兩位月嫂只有共同起訖日、沒有每人各自區間時，不建立正式 assignment、
不猜測分段，也不寫 `orders.staff_id` 或 `staff_schedule`。

歷史 assignment 即使有起訖日，仍不等於 assignment-owned official service days。缺少逐日 ownership
與 rate snapshot 時 Payroll 固定回 blocker；不得按連續曆日猜算工時、薪資或應付義務。

## 2026-08-21 M3 Matching Coordination amendment

Scheduling 正式收納 `Matching Coordination` 為本 Domain 內的 subsystem／bounded coordination capability；它擁有 criteria snapshot、candidate/package、decision lineage 與 fresh rematch orchestration，但不擁有 Orders terms、正式 assignment、official service dates、leave outcome 或 Payroll obligation。

- `accepted` 只代表 customer decision；後續必須 fresh-read downstream effects，最多產生 typed Assignment conversion/rematch request 或 reference。Matching Coordination 不寫 Orders、Assignment 或 Payroll。
- Phase D 只能透過 typed ports 讀取 Scheduling Leave／Assignment canonical receipt、提交 conversion/rematch request 並保存 reference；不得接管 `leave_substitution`、`assignment_plan` 或其 root writer。
- Query 唯讀、Preview 零寫入、Apply 仍由 owning workflow 取得 fresh facts、lock、single outer UoW 與 receipt；跨域協調不改變本 Domain 的 assignment／leave／service-day SSOT。
- 首次建立 criteria snapshot 的 Preview 沒有既存 snapshot 可供瀏覽器取得 source tuple，必須由後端 fresh-read owner facts 並在回應中回傳 canonical tuple；該 Preview 不接受 client source-version assertion。後續 Apply 必須攜帶 Preview 回傳的完整 canonical tuple 與 fingerprint，並重新 fresh-read 驗證。
- M3 Phase E schema 只屬候選 inventory／spec planning，未授權 DDL、seed、backfill、destructive 或資料庫操作；若需變更，另立 approved schema Work Package 並重跑全部 DB gates。
