# Multi-Caregiver Admin UI 正式規格

## 1. 文件邊界與所有權

- 狀態：`current-spec`
- Owner：Admin UI Composition（Multi-Caregiver Scheduling Surface）
- 單一負責範圍：工會 React／管理端的多月嫂媒合、排班、行事曆與人力配置 UI composition、畫面分工、呈現與誤操作阻擋；不擁有 assignment、正式服務日、waiting-deposit lock、leave／substitution、薪資、付款、Orders lifecycle、version、idempotency 或 transaction semantics。
- 關聯引用：見 [Global 共同契約](00_Global_共同契約.md)、[Orders Domain](01_Orders_Domain.md)、[Assignments / Scheduling Domain](02_Assignments_Scheduling_Domain.md)、[Payroll Domain](03_Payroll_Domain.md)、[Client Finance Domain](04_Client_Finance_Domain.md)

## 2. 管理端入口

「排班月曆」提供跨案件的月嫂檔期與班次查閱。訂單工作台的「尋找月嫂與詢問意願」辦理媒合，「確認服務日期與排班」及「服務完工」承接案件人力配置。其他入口如需連往同一操作，導向該案件在訂單工作台的對應區域。

### 2.1 服務人員月曆

- 保留年度時間軸與月份跳轉。滑到可見月份即載入，以人員＋年月保存各月查詢狀態；後端仍使用逐人逐月的有界查詢，不在進頁時載入全年。
- 各月區分尚未載入、載入中、已查無班與載入失敗可重試；滑回仍有效月份沿用結果。快滑、跨年或換人後，舊回應不得覆寫新範圍。成功異動僅失效受影響人員與月份。
- S：同一人員在 11 月、12 月都有班。T：查看下月班表。A：從 11 月只左右滑到 12 月，再滑回 11 月，不動月份選單。R：12 月自動載入並顯示，11 月沿用仍有效的結果；月份選單與回本月仍可跳轉。
- 提供上個月、下個月、回到本月與直接年月選擇；切月保留目前選定月嫂。
- 同日多筆 current assignment／waiting lock 必須逐筆呈現，不得用單一 map 結果覆蓋；至少顯示案件／客戶識別、訂單狀態、月嫂與 occupancy 類型。
- waiting-deposit lock 與正式 assignment 必須使用不同語意／樣式呈現；一般洽談候選不得顯示成正式占用。
- 出勤天數與休假調整只能從所選月嫂的 current、未取消正式 `assignment_id` 進入，不得由 `orders.staff_id`、姓名或前端推測正式歸屬。
- 排班月曆提供檔期、正式班次與精算查閱。局部代班與班次調整由案件人力配置承接。

### 2.2 月嫂配對中心

- 單一月嫂能完整覆蓋時優先採單段；只有無單人完整覆蓋時才進入 2–4 段多月嫂方案，初始多段 UI 預設 2 段。
- Draft 階段可以暫時出現空缺、重疊或尚未完整覆蓋；UI 必須顯示 diagnostics，而不是在編輯途中偽造合法結果。
- 候選與日期依剩餘未覆蓋區段更新；找不到完整方案時仍顯示可行部分、未覆蓋日期與原因。
- 月嫂意願確認與客戶確認包為分開的經辦動作。客戶確認包、附件、重寄及預覽見 [媒合規格 §3.2](02A_媒合候選池與客戶決定及通勤規格.md#32-客戶推薦確認手動更正與服務前整案換人r-04)。
- 每次聯繫或正式發送前必須由 server fresh-read current availability／lock／plan；本機 cache 只可加速互動，不能決定正式可行性。
- 多月嫂方案在所有目標月嫂 willingness gate 未通過前不得實際送履歷；可回報未同意的月嫂／區段。
- 寄送備註為單一共用欄位；多人方案的對外內容須明確揭露由多位月嫂共同完成。
- 正式聯繫／鎖定／轉換前，server 必須驗證：
  - 每位月嫂至多一個連續區段。
  - 日期位於 current availability。
  - 區段排序後無 gap／overlap。
  - 區段完整覆蓋案件需求。

  錯誤需定位到月嫂與日期。

<a id="case-staffing"></a>

### 2.3 案件人力配置

- 一般案件在訂單工作台開啟「多月嫂排班」。成立或服務中從「確認服務日期與排班」進入，完工後從「服務完工」進入。
- 編輯時以一至四個區塊呈現各月嫂的月曆。已有正式指派時，每個區塊對應一個 current assignment。同一指派可包含交錯的服務日，以正式逐日班次標示。同一月嫂有多筆正式指派時，各自顯示。
- 一般首排切換為多月嫂排班後收起總月曆，顯示各月嫂月曆與「儲存班表」。首排的分配、調整依據及儲存規則見 [Scheduling §3.4.1](02_Assignments_Scheduling_Domain.md#multi-caregiver-service-correction)。
- 已有正式班表時，從服務安排開啟多月嫂排班會收起「現行服務日期」區塊。返回服務安排時恢復顯示。
- 案件人力配置仍有未保存的排班草稿時，離開編輯前提示「放棄／留在本頁」。
- 確認實際開始日前可在月曆核對與選取服務日。已有正式指派時，以逐段唯讀月曆呈現開始日變更預覽。確認後仍以月曆顯示正式服務日，符合編輯條件時可開啟「多月嫂排班」調整。開始日確認與正式重排依 [Orders §3.5](01_Orders_Domain.md#35-actual-start-previewapply)。
- 編輯日曆以月嫂與畫面所選月份查詢現行檔期。首排總月曆於已確定單一月嫂時顯示該人檔期，多月嫂編輯日曆各自顯示該人檔期。日期格將其他案件的正式班次、檔期保留及月嫂不可服務分別標為「已有排班」「檔期保留」「不可服務」。本案的既有班表不作為衝突提示。換月或更換月嫂後以新查詢結果呈現，讀取失敗顯示提示。日期格標示供經辦核對，正式時段衝突依 [Scheduling §3.1](02_Assignments_Scheduling_Domain.md#31-同日分時占用與甘特月曆shift-0105) 由後端判定。
- 增加行數只建立 draft row；減少行數只建立 cancellation candidate。沒有 Preview／Confirm／Apply 前不得取消正式 assignment 或排班。
- 已服務紀錄的更正、後續排班的調整與確認順序見 [Scheduling §3.4.1](02_Assignments_Scheduling_Domain.md#multi-caregiver-service-correction)。
- 已付款、已進有效月結、已結算或具有其他 owner lock 的事實不得由 staffing UI 直接覆寫。
- 正式區段增減、日期調整與換人均使用 Scheduling owner Query／Preview／Apply；UI 不自行計算新的 canonical assignment collection。

<a id="service-date-merge-split-ui"></a>

### 2.4 合併或分裂日期

- 「確認服務日期與排班」在「多月嫂排班」旁提供「合併或分裂日期」。操作服務量、人員與帳務效果的唯一規則見 [Scheduling §3.4.2](02_Assignments_Scheduling_Domain.md#service-date-merge-split)。
- 依目前逐日排班的實際服務時數顯示操作。至少有兩個 4 小時服務日才提供合併，有一個 8 小時服務日即提供分裂。只有一種可用操作時直接開啟並顯示模式標籤，兩種皆可用時提供切換，皆不可用時顯示空態與取消。
- 步驟 1 在月曆選擇來源日期，顯示已選數量及可移除的日期。合併選兩個各 4 小時的服務日，分裂選一個 8 小時的服務日。月曆可切換月份。
- 步驟 2 選擇套用日期及服務月嫂。合併顯示一列 8 小時，分裂顯示兩列各 4 小時，時段顯示「月嫂跟客戶自行協調」。套用欄位可先填，來源未選齊時顯示提示。進入功能、切換操作及填寫草稿皆不保存資料。寬畫面左右並列兩個步驟，窄畫面由上至下排列。標題列右上方使用小型外框取消按鈕。
- 已合併的日期再觸發分裂時，帶出該次原有兩日；已分裂的任一結果日期再觸發合併時，帶出同組兩日及原來的一日，不要求重新手選原日期。畫面顯示將恢復的日期、人員與工時，沿既有儲存操作生效；配對及復原範圍依 [Scheduling](02_Assignments_Scheduling_Domain.md#service-date-merge-split)。
- 原本總服務天數的數值與進度顯示保持不變，標明「原訂服務天數」。另顯示 owner Query 提供的實際排班日數與總服務時數，避免把減少或增加的日期誤認為合約天數變更。排班開始及最後服務日依目前實際安排呈現。
- 合併或分裂後的日期格與排班明細顯示當日服務時數及月嫂，時段欄固定顯示「月嫂跟客戶自行協調」。不得同時把原訂上下班時間呈現為該日實際時段；未調整日期維持既有呈現。明確復原後依該次原值顯示，原本未覆寫的正常排班恢復原訂時段，不永久保留協調文字。
- 儲存後回讀 owner 的生效結果，才更新日曆與摘要；取消則保留原資料。離開未保存草稿沿用既有提示。正式班表成功調整後，重新查詢的工時報表與日曆使用相同逐日資料；單純事前日期確認不冒充正式工時。
- 已有合併／分裂結果時變更開始日，顯示將取消結果並恢復正常排班的預覽，只提供「取消合併／分裂結果並重新排班」確認操作，不顯示「採用新建議」或「保留人工選日並重新核對」。取消及重排效果依 [Scheduling §3.4.2](02_Assignments_Scheduling_Domain.md#service-date-merge-split)，確認成功並完成正式讀回後，日曆、摘要與合併／分裂入口一起更新。

| S：具體情境與前提 | T：使用者任務 | A：操作 | R：可判定結果 |
|---|---|---|---|
| 畫面原顯示 20／20 天及現行月曆。 | 調整日期並辨認實際服務量。 | 開啟功能、合併兩個 4 小時服務日後儲存。 | 開啟時無資料變化；成功後仍顯示原訂 20／20 天，另顯示實際 19 日及 80 小時，受影響日期顯示協調文字。 |
| 目前逐日排班分別測試僅可合併、僅可分裂、兩種皆可用、兩種皆無。 | 選擇可用的日期調整操作。 | 開啟調整，兩種皆可用時切換操作。 | 單一模式直接開啟且僅顯示標籤。兩種皆可用時可切換，選取日及套用欄位隨操作變化。兩種皆無時顯示空態及取消。 |
| 有可用操作，來源日期尚未選齊。 | 分辨來源與套用欄位，填寫草稿。 | 開啟調整，先填套用欄位，再用月曆選取及移除來源日期。以寬畫面及窄畫面查看。 | 畫面依序分出兩個步驟，窄畫面上下排列且可操作。來源未選齊前仍可填套用欄位，儲存維持停用。 |
| 已選好合併或分裂日期，但尚未儲存。 | 放棄調整。 | 按標題列右上角的外框取消按鈕，再重新讀取。 | 原日期、人員、時段、工時及帳務皆維持，沒有成功提示或部分結果。 |
| 已保存合併或分裂結果，重新開啟案件。 | 再次操作以復原正常排班。 | 選擇該次結果並觸發反向操作，核對畫面後儲存。 | 自動帶出對應原日期及人員，成功讀回後日曆與實際日數恢復；原訂天數及帳務維持，取消復原則保留調整後班表。 |

## 3. 共用 Preview／Apply 與 concurrency

- 各管理端入口對相同正式 mutation 呼叫同一 owning application contract。
- Query 唯讀；Preview 零正式寫入；Apply fresh-read current owner facts 並依 owning version／fingerprint／idempotency contract 執行。
- UI 顯示 draft、loading、previewed 或 pending 不等於成功；只有 terminal receipt 與 fresh owner readback 可顯示正式完成。
- conflict／stale 時保留使用者可理解的 draft，但必須重新 Query／Preview；不得自動重送 Apply。
- UI 不得直接 INSERT／UPDATE assignment、schedule、lock、payroll、payment 或 event table。

## 4. 局部代班工作面

- 具排班操作權限的管理員從原案件「服務安排 → 多月嫂排班」直接調整，沿用 [案件人力配置](#case-staffing) 的畫面與正式班表讀取，不另設代班待辦工作面。
- 畫面呈現所選日期、人員、協調依據與原因，以及預覽回傳的班表與應付影響。確認後讀回正式結果才顯示完成。人工局部代班與其他排班調整的範圍及儲存規則見 [Scheduling §3.4.1](02_Assignments_Scheduling_Domain.md#multi-caregiver-service-correction)，頁籤與連結的移除邊界見 [入口治理](19_Global_Entry_Point_Governance.md#32-已停用移除之端點與替代邊界)。

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
- 代班不得改變 Client Finance 的客戶應收義務；UI 不得用月嫂薪資差額反算或修正客戶付款。
- 已付款／結算事實若需更正，導向 current adjustment／reversal／re-settlement owner workflow，不提供一般表格直接覆寫。

## 8. 驗收標準

1. 依 §2 從排班月曆查閱檔期與班次，從訂單工作台辦理媒合及案件人力配置。多月嫂排班可逐人選日並核對後儲存。
2. 月曆只由 current typed Query 顯示 assignment／lock，占用與正式服務不混淆。
3. matching draft 可顯示 partial diagnostics，但任何聯繫、履歷、lock、convert 與 Apply 都由 server fresh validation 決定。
4. staffing 減段、換人與日期調整都必須 Preview／Confirm／Apply；歷史服務與已結算事實不可被 UI 直接覆寫。
5. 多日 leave/substitution 為一個 atomic batch，逐日 outcome 可稽核且 replay 不重複。
6. 所有時數、薪資、費用與 eligibility 計算來自 owning Domain result；UI 無第二套業務公式。
7. conflict／timeout／unknown outcome fail closed，成功只能由 terminal receipt＋fresh readback 宣告。

| S 情境 | T 任務 | A 操作 | R 可觀察結果 |
|---|---|---|---|
| 已選月嫂在當月有本案和他案班次，次月有另一筆他案班次 | 核對並調整服務日期 | 確認實際開始日前查看月曆，確認後開啟多月嫂排班並切月，再返回服務安排 | 編輯時收起「現行服務日期」，返回時恢復。個人月曆當月僅標出他案班次為「已有排班」，切月後顯示次月班次。能否安排由 [Scheduling §3.4.1](02_Assignments_Scheduling_Domain.md#multi-caregiver-service-correction) 的時段檢查判定。 |
| 一般首排已有有效推薦方案、簽約承諾，兩位月嫂有可用檔期 | 建立首份班表 | 開啟多月嫂排班、分配全部服務日，補齊需要的調整依據後按「儲存班表」 | 畫面可直接儲存並回讀兩位月嫂的正式班次。缺少必要條件時顯示阻擋，服務日期及正式班表無部分寫入。 |
| 管理員已在原案件協調好後續服務日的人員調整 | 直接修改班表 | 從原案服務安排開啟多月嫂排班，選日、選人、填寫依據後預覽並確認 | 沿同一案件人力配置顯示班表與應付影響，正式讀回後顯示完成，不要求代班待辦識別或待辦版本。正式成功及拒絕條件依 [Scheduling 驗收](02_Assignments_Scheduling_Domain.md#4-驗收標準)。 |
