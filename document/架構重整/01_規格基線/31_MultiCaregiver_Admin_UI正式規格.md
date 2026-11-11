# Multi-Caregiver Admin UI 正式規格

## 1. 文件邊界與所有權

- 狀態：`current-spec`
- Owner：Admin UI Composition（Multi-Caregiver Scheduling Surface）
- 單一負責範圍：工會 React／管理端的多月嫂媒合、排班、行事曆與人力配置 UI composition、畫面分工、呈現與誤操作阻擋；不擁有 assignment、正式服務日、waiting-deposit lock、leave／substitution、薪資、付款、Orders lifecycle、version、idempotency 或 transaction semantics。
- 關聯引用：見 [Global 共同契約](00_Global_共同契約.md)、[Orders Domain](01_Orders_Domain.md)、[Assignments / Scheduling Domain](02_Assignments_Scheduling_Domain.md)、[Payroll Domain](03_Payroll_Domain.md)、[Client Finance Domain](04_Client_Finance_Domain.md)

## 2. 三分頁產品結構

多月嫂日常操作固定集中於同一產品入口的三個分頁：

1. `服務人員月曆`
2. `月嫂配對中心`
3. `案件人力配置`

訂單頁不得保存完整媒合、人力正式配置、換月嫂、排班移除或另一套 Preview／Apply 入口。若存在相容 deep link，只能導向 current owner page，不得形成第二套操作流程。

### 2.1 服務人員月曆

- 視角為「一位月嫂／一個月份」。
- 提供上個月、下個月、回到本月與直接年月選擇；切月保留目前選定月嫂。
- 若仍有未套用的休假／代班草稿，切換月份或離開前必須明確提示「放棄／留在本頁」。
- 同日多筆 current assignment／waiting lock 必須逐筆呈現，不得用單一 map 結果覆蓋；至少顯示案件／客戶識別、訂單狀態、月嫂與 occupancy 類型。
- waiting-deposit lock 與正式 assignment 必須使用不同語意／樣式呈現；一般洽談候選不得顯示成正式占用。
- 出勤天數與休假調整只能從所選月嫂的 current、未取消正式 `assignment_id` 進入，不得由 `orders.staff_id`、姓名或前端推測正式歸屬。
- 分頁一只處理逐日休假、順延、單日代班與 read-only 日曆／精算；區段新增、移除、換人與起訖調整屬分頁三。

### 2.2 月嫂配對中心

- 單一月嫂能完整覆蓋時優先採單段；只有無單人完整覆蓋時才進入 2–4 段多月嫂方案，初始多段 UI 預設 2 段。
- Draft 階段可以暫時出現空缺、重疊或尚未完整覆蓋；UI 必須顯示 diagnostics，而不是在編輯途中偽造合法結果。
- 候選與日期依剩餘未覆蓋區段更新；找不到完整方案時仍顯示可行部分、未覆蓋日期與原因。
- `聯繫與確認意願` 與 `傳送履歷` 是兩個不同動作，不得合併成一次 side effect。
- 每次聯繫或正式發送前必須由 server fresh-read current availability／lock／plan；本機 cache 只可加速互動，不能決定正式可行性。
- 多月嫂方案在所有目標月嫂 willingness gate 未通過前不得實際送履歷；可回報未同意的月嫂／區段。
- 單月嫂可依 current communication contract 補寄；多月嫂需全員 gate。履歷備註為單一共用欄位；多人方案的對外內容須明確揭露由多位月嫂共同完成。
- 正式聯繫／鎖定／轉換前，server 必須驗證每位月嫂至多一個連續區段、日期位於 current availability、區段排序後無 gap／overlap 且完整覆蓋案件需求；錯誤需定位到月嫂與日期。

### 2.3 案件人力配置

- Current formal staffing 顯示 1–4 行，一行只代表一個 current assignment；預設行數為 current 未取消 assignment 數量。
- 同一月嫂若存在不連續區段，不得在 UI 合併成單一假區段。
- 增加行數只建立 draft row；減少行數只建立 cancellation candidate。沒有 Preview／Confirm／Apply 前不得取消正式 assignment 或排班。
- 已開始服務的 assignment 不得回溯換人或改寫歷史服務日；合法 replacement／split 只可依 Scheduling current contract 對未來日期生效。
- 已付款、已進有效月結、已結算或具有其他 owner lock 的事實不得由 staffing UI 直接覆寫。
- 正式區段增減、日期調整與換人均使用 Scheduling owner Query／Preview／Apply；UI 不自行計算新的 canonical assignment collection。

## 3. 共用 Preview／Apply 與 concurrency

- 分頁二與分頁三對相同正式 mutation 必須呼叫同一 owning application contract，不得各自維護不同演算法。
- Query 唯讀；Preview 零正式寫入；Apply fresh-read current owner facts 並依 owning version／fingerprint／idempotency contract 執行。
- UI 顯示 draft、loading、previewed 或 pending 不等於成功；只有 terminal receipt 與 fresh owner readback 可顯示正式完成。
- conflict／stale 時保留使用者可理解的 draft，但必須重新 Query／Preview；不得自動重送 Apply。
- UI 不得直接 INSERT／UPDATE assignment、schedule、lock、payroll、payment 或 event table。

## 4. 多日休假／順延／代班 UI

- 每個選定休假日逐列顯示處置，合法選項為 owning Scheduling contract 允許的 `順延` 或 `代班`。
- 代班必須由使用者明確選擇月嫂；候選顯示可先列同案既有月嫂，再列其他 current available staff，但正式可用性仍由 server fresh-read 判定。
- 同一次多日期操作只形成一個 Preview candidate 與一個 Apply transaction；每個日期仍保存獨立 immutable outcome，由共同穩定 `batch_key` 串聯。
- 任一 item 驗證失敗時整批不得留下部分正式 mutation。
- 代班必須產生 current Scheduling contract 定義的獨立 assignment／lineage；原 assignment 與代班 assignment 同日不得重複成為正式服務 owner 或重複計薪。
- 無合法代班人時，只能依 current Scheduling rule 採用可成立的順延／補足方案或回 blocker；UI 不猜測人選或日期。

## 5. Read model 與日曆精算呈現

### 5.1 Assignment 明細

管理端 read model 至少可呈現：

- `assignment_id`
- 月嫂識別／顯示名稱
- current／調整前後的服務區段
- 原排定服務量
- 休假／代班／補足服務量
- current actual service days／`actual_hours`
- gap／overlap／availability conflict diagnostics

實際欄位名稱以 typed Query schema 為準；本文件不要求 UI 從 raw table 自行組算。

### 5.2 全案摘要

至少呈現 current owner Query 已提供的：

- 全案服務起訖投影
- Orders 目標服務量
- 所有 current 非取消 assignment 的實際服務量合計
- 是否存在未補足、重疊或其他 blocker

UI 不自行以 `planned_hours`、姓名或 `orders.staff_id` 補值。

## 6. Waiting-deposit lock 與轉正式

- 客戶／方案確認後、正式訂金 gate 完成前，UI 只顯示 current waiting-deposit lock，不得先建立正式 assignment 假象。
- Lock acquire／release／cancel／convert 的合法性、日期衝突、Finance deposit gate、Orders／Scheduling version 與 transaction 由 current formal specs 擁有。
- `回復未綁定` 只可在 owning contract 判定仍可 release 的情況下顯示；必須二次確認，且不得刪除既有 willingness、communication 或 audit history。
- 訂金／正式 assignment 已成立後，不得再用 `回復未綁定` 繞過正式 staffing／cancellation contract。
- lock conflict 必須顯示可理解的月嫂／日期 blocker；UI 不得以局部成功或前端 state 冒充 lock 已完成。

## 7. 薪資與費用顯示邊界

- `actual_hours`、特殊薪資日、代班薪資 impact、樓層費與應付結果全部由 Scheduling／Payroll owner 計算；UI 只顯示 typed result。
- 國定假日與代班日均不得由 UI 自動設為雙倍薪；只有 current formal contract 允許且有明確個案約定時，才可由管理員對指定正式服務日提出 special-pay input 並保留 reason／audit。
- 代班不得改變 Client Finance 的客戶應收義務；UI 不得用月嫂薪資差額反算或修正客戶付款。
- 已付款／結算事實若需更正，導向 current adjustment／reversal／re-settlement owner workflow，不提供一般表格直接覆寫。

## 8. 驗收標準

1. 管理端只存在一個三分頁多月嫂產品入口；相容入口不得形成第二套正式流程。
2. 月曆只由 current typed Query 顯示 assignment／lock，占用與正式服務不混淆。
3. matching draft 可顯示 partial diagnostics，但任何聯繫、履歷、lock、convert 與 Apply 都由 server fresh validation 決定。
4. staffing 減段、換人與日期調整都必須 Preview／Confirm／Apply；歷史服務與已結算事實不可被 UI 直接覆寫。
5. 多日 leave/substitution 為一個 atomic batch，逐日 outcome 可稽核且 replay 不重複。
6. 所有時數、薪資、費用與 eligibility 計算來自 owning Domain result；UI 無第二套業務公式。
7. conflict／timeout／unknown outcome fail closed，成功只能由 terminal receipt＋fresh readback 宣告。
