# Staff Matching Preferences 與不可服務期間正式規格

## 1. 文件狀態

- 狀態：`approved-by-user-2026-08-13`
- Owner：`Scheduling Staff Matching Profile／Assignments／Matching`
- 歷史實作包已自工作樹移除；需要時依 `../04_已完成與上線封存/README.md` 從 Git 歷史精準取回。
- 目的：讓公會人員維護月嫂配對偏好與不可服務期間，並由同一份 typed facts 同時服務配對中心與行事曆。

## 2. Global → Domain → Subsystem → Module

### Global

- Query 唯讀；Preview 零寫入；Apply 必須 fresh-read、lock、validate、保存 actor／reason／version／fingerprint／idempotency receipt。
- 所有已登入且 enabled 的內部使用者具有相同功能權限；仍保存操作人員身分與 audit。
- Streamlit 只呼叫 typed API，不直接讀寫偏好或不可服務資料表，也不自行解讀 comparison policy。

### Domain ownership

| Owner | 根事實／責任 |
|---|---|
| Scheduling／Staff Matching Profile | 偏好定義、顯示名稱、值型別、是否供配對篩選、月嫂偏好值與各自版本 |
| Orders | 案件的希望服務天數、每日服務時數、下廚需求等正式條款 |
| Scheduling | 長假／暫停接案日期區間、取消歷史、current availability 與 Calendar projection |
| Matching | 消費 Staff／Orders／Scheduling typed facts，產生逐條件結果、候選與排除原因 |

Staff Matching Profile 是 Scheduling 內的 aggregate，不新增第十三個業務 Domain。它不擁有案件需求
或檔期；Matching 不得修改偏好、條款或不可服務期間。

### Subsystems

1. `StaffPreferenceDefinitionWorkflow`：建立、停用與查詢偏好定義。
2. `StaffPreferenceValueWorkflow`：設定月嫂偏好值。
3. `StaffUnavailabilityWorkflow`：建立／取消長假或暫停接案期間。
4. `MatchingRecommendationQuery`：以區域與週間服務提供符合狀態及月嫂原登錄值；偏好不排除候選（2026-10-21 裁決）。
5. `StaffCalendarQuery`：顯示不可服務區間，但不把它誤標為 assignment、正式服務日或一般七日 buffer。

### Modules

- `PreferenceDefinitionValidator`
- `IntegerRangePreferenceValidator`
- `PreferenceMatchEvaluator`
- `UnavailabilityPeriodValidator`
- `UnavailabilityOverlapProjector`
- `MatchingFilterExplanationBuilder`

Modules 必須是純函式，不讀 DB、不取得現在時間、不 import API／UI。

## 3. 自訂月嫂偏好

以下數字偏好 definition／value API 保留其獨立數值語意與既有資料。依 2026-10-21 人工裁決，數字偏好不參與候選提示或排除，也不得覆蓋名冊 canonical 資料；目前兩項服務偏好依 PREF-21-01～05。

### 3.1 定義

公會人員可以建立自訂顯示名稱的月嫂偏好欄位。第一版正式支援 `integer_range` 與
`integer_set`。range 的最小值及最大值皆為整數且 `minimum <= maximum`；set 是已排序且不重複的
正整數集合。定義可選擇：

- `record_only`：只記錄，不進入配對篩選；
- `orders.service_days`：以案件「希望服務天數」比對；
- `orders.service_hours_per_day`：以案件「每日服務時數」比對。

顯示名稱可以修改，但 stable definition identity 不得改變；改名不重建月嫂值。停用定義保留歷史，
不再出現在新增／配對畫面。Matching source 的改變屬語意變更，必須建立新 definition version，
不得靜默改寫歷史查詢意義。

本計畫內建兩個 initial definitions：

| 顯示名稱 | value kind | matching source |
|---|---|---|
| 可承接服務天數 | `integer_range` | `orders.service_days` |
| 可承接每日服務時數 | `integer_set` | `orders.service_hours_per_day` |

舊 `staff_time_slots.slot_name` 只能作 migration source evidence。`4小時_上午`、`4小時_下午`、
`8小時`、`24小時` 可明確轉為數字；`其他` 或無法唯一解析的 `custom_slot_detail` 進人工補登清單，
不得猜測數字。

### 3.2 Matching 語意

- 2026-10-21 最新人工裁決：名冊與候選查詢的服務偏好只保留可承接區域、週間服務；初步詢問及正式分段查詢均僅提供符合提示，不因偏好排除或禁止加入候選池。姓名旁分項顯示月嫂原登錄值與符合／不符合／待確認；細則依末段 PREF-21-01～05。
- integer target 落在月嫂 `[minimum, maximum]` 內，或存在於 integer set 內，為 `matched`；否則 `not_matched`。
- 月嫂未設定啟用中的自訂偏好時為 `source_not_ready`；正式媒合仍可列為 selectable，但排序不得把未知值當成 matched，UI 必須明示尚未登錄。目前兩項偏好只讀 canonical Staff relations；數字偏好不參與候選提示或排除，資料不足顯示待確認。
- Query 回傳 definition identity／version、顯示名稱、target、staff value、result 與 reason code；UI 不解析中文名稱決定規則。
- Query 結果綁定 Staff preference、Orders 與 Scheduling source versions；選擇或 Apply 前必須 fresh recheck。
- 單純 `not_matched` 或 `source_not_ready` 不得投影 `SCHEDULE-005` 或任何硬性異常；只有偏好 root 本身違反 schema/version invariant，或正式 assignment／不可服務期間等其他 owner root 衝突時，才由其對應 anomaly code 處理。

### 3.3 月嫂名冊的服務能力投影（2026-08-25 人工裁決）

- 管理端在選定月嫂後，必須以同一份後端 typed read model 顯示已登錄的
  最多照顧寶寶數、可承接區域、可承接時段、交通方式、週間服務／排休、
  特殊節日意願與可承接胎數。這些值來自 Staff Historical BeClass 已正規化並採納的
  Staff／relation facts，也是 Matching 現行消費的來源；前端不得另建假資料或自行解析問卷。
- 這份投影只顯示正規化業務值；不顯示 raw workbook／JSON、銀行資料、身分證、
  指紋、source identity 或冪等鍵。資料空白時明確顯示「尚未登錄」，不得以預設值補齊。
- 月嫂名冊此區是唯讀 Query，不擁有修改上述 roots 的權限；後續修改必須交回
  各自 owner 的專屬 Preview／Apply 工作流。

驗收狀態（2026-08-25）：`completed`。Chrome 由月嫂名冊實際選取 Staff `#531` 後，已讀回並顯示
最多照顧寶寶數、可承接區域、可承接時段、交通方式、週間服務／排休、特殊節日意願與可承接胎數；
focused tests 與 React build 通過，畫面不含 raw workbook／JSON、來源識別或指紋。

## 4. 下廚需求

- HCM 與 Client BeClass 是兩條獨立 intake lane；任一方缺少對方都不得阻擋來源資料落地。
- HCM Client／Order 先建立但尚未唯一綁定 Client BeClass 時，Orders `requires_cooking` 保持
  `NULL`；缺少對方由 current-state anomaly 顯示，不得預設為否。
- 唯一配對後，Case Import reconciliation 才可將 BeClass 問卷的明確 yes／no source value透過
  typed Orders command補入 canonical `requires_cooking`。`是否需要下廚：` 的 `需要下廚`／`不需要下廚`
  為優先的受控來源；若與既有餐點偏好受控答案矛盾，必須回 review，不得以優先規則直接覆寫。空白、
  矛盾或自由文字無法唯一判定時回
  `case_import_cooking_requirement_ambiguous` 進 Import Review，但不撤銷已建立的 HCM roots。
- 此補正僅能改寫 `requires_cooking`；歷史 root 有 `actual_start_date` 而尚無正式 Scheduling segment
  時仍可執行，不得順帶變更日期、時段、工時、費用或其他服務條款。服務資料鎖形成後固定拒絕。
- 原始 `survey_details` 保留為來源 evidence；正規化後布林值進 reconciliation fingerprint、event與
  Orders root。不得在 Matching Query 每次重新解析自由文字。
- 月嫂料理能力使用 `staff_cooking_skills`，保留為匯入服務資訊；依 2026-10-21 裁決退出候選偏好比對。Orders `requires_cooking` 及其 intake／reconciliation 契約維持，不因本次 UI 收斂刪除資料或改變訂單需求。

## 5. 長假／暫停接案

- 管理抽屜統一顯示「暫停接案」（指定起訖日）與「無期限暫停接案」（僅開始日）；新增表單按「新增」才展開，開始日預設業務當天，不提供無指定開始日。兩者均沿用既有 `long_leave`／`paused_service` writer 與恢復規則。
- 抽屜以台北業務當天與全部未取消期間（含首尾日）呈現「目前：暫停接案中／未暫停接案」，不宣稱完整派工資格；未來期間標示「尚未開始」，歷史及取消紀錄預設收合，取消紀錄明示「已取消，不影響接案」且無重複取消操作。載入中或讀取失敗不得顯示未暫停的結論。
- 新增、取消及恢復取得成功收據後，前端通知同一瀏覽器的排班及媒合查詢（包含同源其他分頁）重新讀取 current facts；通知只含 staff identity、不取代後端資格判定。排班同時更新日曆、案件排查與已開啟的檔期詳情；媒合更新候選衝突及多月嫂可選資料，受保護的寫入完成後才刷新，保留分段日期草稿。不改後端 writer、已承諾排班或外部通知流程。
- 抽屜開啟時及異動成功後，自動載入所選月嫂全部歷史與未來紀錄；無資料顯示「無」，不推導完整可派工結論。既有 `GET /api/v1/scheduling/staff/{staff_id}/availability-blocks` 省略日期時以 `after_id`（預設 0）與 `limit`（預設 100、上限 200）依紀錄 id 升冪分頁，沿用原回應陣列與認證；前端依序讀完所有頁，離開時中止，不將新增日期用於篩選紀錄。傳入日期時仍須同時傳入起訖日，維持既有最多 366 天的日期查詢。
- kind 僅允許 `long_leave`、`paused_service`。
- 根事實包含 staff、起訖日期（含首尾日）、kind、reason、建立 actor／時間與取消事件；
  `long_leave` 必須有結束日，`paused_service` 可 open-ended，恢復時以 resume date 前一日封閉期間。
- Apply 預設拒絕同一月嫂的 current overlap，回
  `staff_unavailability_period_conflict`，避免重複事實。
- 建立前須鎖共用 staff occupancy mutex 並 fresh-read assignment、waiting service lock 與 buffer。若與既有
  assignment／正式訂單排程重疊，Preview與管理端必須列出exact case、assignment及日期，預設Apply拒絕並回
  `staff_unavailability_committed_schedule_conflict`。具權限人員可在看過相同fresh conflict snapshot後，以
  明確`force_preserve_committed_schedule`確認保存不可服務申請；此時既有assignment／waiting service lock
  固定優先，不得取消、縮短、改派或標記為不上班，並須保存committed-exception lineage、actor、reason、
  idempotency receipt與兩邊版本。若Apply時衝突集合改變固定stale。
- 強制保存後，原不可服務區間仍約束未來媒合與尚未承諾日期；與既有有效assignment重疊的日期是
  `committed_schedule_exception`。Calendar必須同時顯示不可服務宣告與既有服務承諾，不得把任一方隱藏；
  如需改變既有服務，只能另走leave／substitution／cancellation正式流程。
- 取消只追加事件，不刪除或改寫原期間。
- 初步 Candidate Contact Pool 可保留與 current 不可服務期間或檔期重疊的人選並提示協調；這不是正式可用性或排班資格。正式 Matching Query 仍回傳 actual conflict，建立 matching plan／assignment 前須完成日期協調並 fresh-read，實際占用衝突仍 fail closed。七天 buffer overlap 只提醒。
- Calendar 顯示 `staff_unavailability`、kind、期間及原因；不可呈現為可接案、正式服務日、請假代班
  outcome 或七日 buffer。
- 請假／代班是已有 assignment 後的服務異動；本功能是尚未指派前的個人 availability，兩者不可互相取代。

## 5.1 Staff 退役對 Matching 的約束（2026-08-15，WP91 已人工確認）

- 退役生效時間代表月嫂停止接案的時間，不是按下儲存的時間。管理端提供生效日期選擇，轉為該日台北時間 00:00 的既有 `effective_at` 格式，不要求手填完整時間或時區；原因以中文選單對應既有合法代碼，維持選填。
- 月嫂仍有未結束案件時不得直接退役；Preview 與 Apply 均須檢查，失敗應明確說明未結束案件的阻擋原因。既有 version、fingerprint、idempotency 與交易邊界維持不變。
- Staff 退役是獨立 `staff_lifecycle_states` 的 `active -> retired` 根事實；既有 `staff.status`
  保留 legacy `active/inactive` 語意。Matching、Scheduling 或 UI 不得自行寫入、推測或反轉 lifecycle。
- 退役於 business time 生效後，所有新候選、重算、邀請、媒合與新 assignment 必須排除該 Staff，
  並回傳 deterministic exclusion reason。
- 已確認的未來 assignment 不因退役自動取消；變更只能經 Scheduling owner 的替代、取消或改派 command。
- 尚未確認的 candidate、offer、邀請或暫存媒合在退役生效時失去資格，不得被後續 Apply 採用。
- Assignment Plan 採整代重建時，retired Staff 只有在 `staff_id`、區間與 official service dates 均與
  current effective assignment 完全相同時，才視為保留既有義務；新增、延長、移動或增加服務日固定回
  `staff_retired_new_assignment_forbidden`。Apply 必須重新鎖定 Staff current status 後做相同判定。
- 復職必須經 Staff owner 的獨立 typed `ReactivateStaff` command；不得自動恢復過期 availability、偏好、
  邀請或 candidate，重新通過當下資格與必要資料驗證後才可進入 Matching。
- Staff、BeClass、Orders、Payroll、歷史配對及 audit 資料必須保留並可依權限查詢。
- `active -> retired` Apply 必須在 Staff owner 的同一 outer Unit of Work，經 typed effect port 呼叫
  既有 LINE Identity application contract，僅解除 exact staff role；Staff workflow 不直接寫 LINE
  repository、不呼叫 provider，也不解除仍有效的 customer role。
- Staff transition 與 LINE revocation request／outbox 必須原子提交；LINE 邊界失敗時 Staff transition
  不得單獨成功。exact replay 回原 Staff receipt，不建立第二筆解除 request。
- LINE 解除完成後，若同一 LINE user 仍有 active customer role，追加一筆綁定該 revocation request
  identity 的 customer menu intent；若沒有其他 role，沿用既有 default-menu reset。這不改既有解除
  saga 的 retry、provider-success 或 manual-completion 判定。

## 6. Typed errors

- `staff_preference_definition_invalid`
- `staff_preference_definition_conflict`
- `staff_preference_value_invalid`
- `staff_preference_version_conflict`
- `staff_preference_source_not_ready`
- `case_import_cooking_requirement_ambiguous`
- `staff_unavailability_period_invalid`
- `staff_unavailability_period_conflict`
- `staff_unavailability_committed_schedule_conflict`
- `staff_unavailability_force_confirmation_required`
- `staff_unavailability_committed_exception_stale`
- `staff_unavailability_version_conflict`
- `stale_preview`
- `idempotency_conflict`
- `transaction_failed`

## 7. 驗收

- Module：偏好 range、matching comparison、明確下廚 normalization、不可服務日期及 overlap。
- Subsystem：Query 零寫入、Preview 零寫入、Apply replay／payload mismatch／stale／rollback。
- Domain：兩項 canonical 服務偏好提示、月嫂原值與待確認、匯入資料保留、長假與 Calendar／Matching 同源、buffer-only 仍顯示。
- Browser：不可服務期間 mutation controls 只有在操作者展開可見面板後才可掛載；收合時不得留下可由
  螢幕閱讀器或自動化誤觸的隱藏控制。建立不可服務期間必須走 Preview → Apply，並顯示 typed receipt
  的 staff、action、block、aggregate version、idempotency facts 與 fresh readback；其後驗證配對結果刷新、
  Calendar 顯示及取消後恢復。
- 真人 LINE 不在本 Work Package 驗收範圍。

Runtime 狀態：`completed`。2026-08-25 已用 Chrome 完成不可服務期間 Preview／Apply、Matching
fresh refresh、Calendar 同源顯示、取消 Preview／Apply 與恢復；此鏈不得因舊 handoff 或舊 Work Package
的 `NOT_RUN` 描述重跑。真人 LINE 仍依本節明確不屬此驗收。

## 2026-08-21 M3 coordination amendment

Staff Matching Preferences／不可服務期間仍由本規格與 Scheduling owner 擁有；M3 Matching Coordination 只能透過 typed query／port 讀取 current preference、lifecycle、availability 與 unavailability facts，不能寫入偏好、不可服務期間、assignment、leave 或正式服務日。

`accepted` 只代表 matching decision；M3 需 fresh-read 本規格提供的 source versions，若 facts 變動則回 `rematch_required`，並透過 typed Assignment conversion/rematch request 交回 owning workflow。M3 Phase D 不接管本 Domain root writer；本 amendment 不授權 production code、schema／DB、provider 或真人 LINE 驗收。

## 2026-09-02 Staff／BeClass 接案偏好 canonical ownership 裁決（Issue #104）

### 範圍與分類原則

本裁決只定義資訊架構、canonical ownership、資料形態與 read/write boundary；不授權 UI、schema、migration、backfill、re-import、production DB、deploy 或 cutover。資料目前存在於 Staff 或 BeClass adoption storage，不代表它自動成為可編輯的 Staff Matching Preference；只有本節明列為 Staff Matching Profile definition/value 的資料，才可由該 owner 的 mutation boundary 寫入。

「接案偏好相關資訊」分成兩類：

1. **Staff Matching Profile 可寫偏好**：由 Scheduling／Staff Matching Profile 擁有 definition、typed value 與 aggregate version。
2. **Staff 服務能力／接案事實**：由 canonical Staff scalar／relation facts 擁有；Matching、名冊與其他 UI 只能透過 typed read model 消費，不得因顯示或媒合用途而改變 owner，也不得透過 Staff Matching Profile API 寫回。

### Staff Matching Profile canonical owner 與 API boundary

第一版正式 value shape 維持本規格 §3.1：`integer_range`（`minimum`、`maximum`）與 `integer_set`（排序且不重複的正整數 `values`）。Definition 至少包含 stable `preference_key`、`display_name`、`value_kind`、`is_filterable`、`order_fact_key`、`comparison_operator`、`active` 與 version；每位 Staff 的 profile 以 preference key 對應 typed value，並有獨立 aggregate version。

目前正式的兩個 initial definitions 維持：

| 業務主題 | value shape | matching source | ownership |
|---|---|---|---|
| 可承接服務天數 | `integer_range` | `orders.service_days` | Scheduling／Staff Matching Profile |
| 可承接每日服務時數 | `integer_set` | `orders.service_hours_per_day` | Scheduling／Staff Matching Profile |

正式 HTTP boundary 是 `/api/v1/scheduling/staff-matching-preferences`：

- Read：`GET /definitions`、`GET /staff/{staff_id}`。
- Definition write：`POST /definitions/{preference_key}/preview` → `POST /definitions/{preference_key}/apply`。
- Staff value write：`POST /staff/{staff_id}/preview` → `POST /staff/{staff_id}/apply`。
- 所有 mutation 都必須經 owner workflow 的 version／fingerprint／idempotency／actor／reason 契約；UI、Case Import、Matching 或 Staff relation adapter 不得直接寫 preference storage。
- 新增自訂 preference definition 必須是明確的管理端定義行為並通過 typed definition validator。任何 Staff／BeClass 欄位或 relation 的存在，本身不是新增 definition 的授權。

### Staff／BeClass 接案相關事實 inventory

以下資料屬於接案／媒合時可能需要讀取的 canonical service facts，但**不是** Staff Matching Profile 可寫偏好：

| 業務主題 | canonical data shape | current ownership／用途 | #104 write boundary |
|---|---|---|---|
| 最多照顧寶寶數 | Staff scalar `care_babies` | Staff canonical profile fact；可供名冊／Matching read projection | 不得由 preference profile 寫入 |
| 可承接區域 | relation `staff_regions`：標準值 + topic-local other detail | Staff service capability fact | 只讀；若未來要人工修改，須另由該 fact owner 明確定義 command |
| 可承接時段 | relation `staff_time_slots`：標準值 + topic-local other detail | Staff service capability fact；內建每日時數查詢直接使用此唯一來源（MATCH-CAP-02） | 不寫入數字偏好副本；無法唯一解析時不得猜測 |
| 下廚能力 | relation `staff_cooking_skills`：標準值 + topic-local other detail | Staff capability；Matching 對 Orders `requires_cooking` 消費 | 不得由 preference profile 寫入 |
| 交通方式 | relation `staff_transportation` | Staff service capability fact | 不得由 preference profile 寫入 |
| 特殊節日意願 | relation `staff_holiday_availability`：標準值 + topic-local other detail | Staff service capability／availability fact | 不得由 preference profile 寫入 |
| 週間服務／排休 | relation `staff_weekly_rest`：標準值 + topic-local other detail | Staff service capability／availability fact | 不得由 preference profile 寫入 |
| 可承接胎數／型態 | relation `staff_baby_types`：標準值 + topic-local other detail | Staff service capability fact；`[其它].4` 含「三胞胎」時可依既有 adoption 規則得到 `care_babies = 3` | 不得由 preference profile 寫入 |

Case Import 的 Staff Historical BeClass adoption 只負責把已知 workbook source 正規化到上述 canonical Staff scalar／relations。採納完成後，raw workbook 欄名或欄序不成為 runtime owner；Matching／名冊不得重新解析問卷來創造另一份偏好事實。

### 六組 `[其它]` 的母題 ownership

六組 other detail 必須永久跟隨原母題，不得合併為 generic `other`，也不得跨母題轉用：

| BeClass 欄位 | canonical parent relation | 母題 |
|---|---|---|
| `[其它]` | `staff_cooking_skills` | 下廚能力 |
| `[其它].1` | `staff_regions` | 可承接區域 |
| `[其它].2` | `staff_time_slots` | 可承接時段 |
| `[其它].3` | `staff_weekly_rest` | 週間服務／排休 |
| `[其它].4` | `staff_baby_types` | 可承接胎數／型態 |
| `[其它].5` | `staff_holiday_availability` | 特殊節日意願 |

`staff_transportation` 沒有對應 `[其它]` 欄位，不得為求欄位對稱而新增或借用其他母題的 detail。

### 明確排除：不是接案偏好

- 一般個人資料：姓名、電話、email、地址、生日、身分識別資料。
- `education`、`emergency_contact_name`、`emergency_contact_phone`、`admin_notes`；已有 canonical storage 不改變其語意分類。
- 銀行／匯款資料、IP、credential、token、secret。
- `has_massage_cert` 是嬰幼兒按摩證書的 dedicated Staff fact；不得再複製成一般 certification 或 matching preference。
- 一般資格證明由 `staff_certifications` 擁有；資格證明不是因媒合可能參考就自動成為 preference。
- BeClass `項次`／`查詢序號` 不保存，也不得建立 canonical preference identity。

### Evolution rule 與 Issue #104 驗收

- 既有 Staff／BeClass fact 若未來需要變成可編輯 preference，必須另有明確需求，先定義 stable preference identity、typed value、matching semantics、migration/read source 與專屬驗收，再經 Staff Matching Profile owner 的 Preview／Apply boundary；本 Issue 不預先建立 storage 或 UI requirement。
- 名冊／Matching 可以讀既有 canonical facts，但 read projection 不取得 writer ownership。
- 六組 `[其它]` 已逐一綁定原母題；不存在共用 `other`。
- 本節完成「包含／排除清單、每個包含主題 owner/data shape、read/write API boundary、六組 other ownership、未知不升格」五項 Issue #104 驗收；runtime、DB 與 production 均無變更。

### T01-4/5 Staff 六母題人工維護邊界（2026-09-06）

依最新人工裁決，六個 canonical relation facts 增加 Staff owner 的 typed Query／Preview／Apply：
`staff_regions`、`staff_time_slots`、`staff_cooking_skills`、`staff_holiday_availability`、`staff_weekly_rest`、`staff_baby_types`。每次 Preview 綁定六關係 snapshot fingerprint；Apply 先鎖 Staff parent，再依 table name 排序鎖定六 relation rows，fresh-read 後驗證 fingerprint，並重用 `admin_command_receipts` 的新 command family。

既有 numeric Staff Matching Profile QPA、各 relation 的 canonical adoption 與 transportation 的 `source_not_ready` 唯讀語意均保留；本邊界不新增 version table、schema、migration，也不把 raw workbook 或其他能力欄位升格為可寫偏好。

## 2026-10-13 內建媒合條件共用名冊 canonical 來源（歷次裁決；偏好項目及排除語意由 2026-10-21 取代）

### 六項接案條件與自訂服務起迄（2026-10-13 最新人工裁決）

使用者要求按需要新增條件，以標準下拉維護，取消「新增說明」與新的說明儲存，
並讓可承接時段自訂開始／結束時間，儲存前須符合服務時數與休息規則。
Staff owner 以 `RELATION_OPTIONS` 提供 authenticated
`GET /api/v1/staff/case-preference-manual/options` 的 typed 選項；可承接區域提供全台
22 縣市及新竹既有北區／東區／香山區，下廚沿葷食／素食，節日沿 BeClass 已採納選項，
胎數沿單胞胎／雙胞胎，排休沿連續服務／週休1日／週休2日與已認可的週一至週五／休周六／休周日。
新選單不提供依賴自由說明的「其他」；既有非標準值與來源說明保留、唯讀，不批次清除資料。
人工新增或修改 `detail` 被拒絕；既有完全未變的 relation 保留，SQL 不 delete／reinsert 未變列。

服務時段選 4／8／24 小時，每列接受 typed `service_hours`、`start_time`、`end_time`、
`end_day_offset`（0 當日／1 次日，HH:MM 24 小時制）。跨日須明確提供 offset，不自行猜測。
沿 `01_Orders_Domain.md` 的服務時數規則：4 小時班起迄跨度恰為 240 分鐘、不扣休息；
8 小時班恰為 510 分鐘，含 30 分鐘休息；24 小時班恰為 1440 分鐘。
不完整、無效時間或跨度不符在 Preview／Apply 均回 typed 422，且零寫入。
原有未設定起迄的時段可完整原樣保留；新增或異動時段必須符合上述規則。

Staff 純 Domain 將驗證完成的完整 tuple 編為既有 `staff_time_slots.slot_name` 的 canonical
identity，例如 `4小時(09:00-13:00)`、`8小時(08:30-17:00)`、`24小時(09:00-次日09:00)`；
此為正式服務時段值，不把時間存入自由說明 `custom_slot_detail`。新時段的 detail 為 NULL，
同時数可保存不同完整時段，同一完整時段仍須唯一。Query 由同一 Staff Domain 解碼回 typed
四欄；原有明確上午／下午四小時值可投影其既有時間，未異動時保留原 identity。
無 schema／migration 或第二份同步副本；沿既有 parent lock、fresh 六 relation snapshot、
human Preview fingerprint、receipt 與 outer UoW。Matching read adapter 透過 Staff 既有
時段解碼投影服務時數，8.5 小時跨度仍比對 8 小時服務，不能比成 8.5 小時。
本步不增加案件與月嫂起迄重疊的 Matching eligibility 條件；MATCH-CAP-02 仍比對每日服務時數。

新增／移除／時間異動使 Preview 失效；未選的新列須選擇或移除後才能 Preview。
UI 無新增或修改說明控制，不由 UI 判定服務時數是否合法；唯一驗證在 Staff Domain。
不部署、不更動 production／既有歷史資料、不發送外部 provider 效果。

Authority：使用者明確不接受名冊與媒合不同步，並指定「偏好服務日」是「服務方式，例如周休二日」。本裁決取代內建候選篩選原先以數字偏好比對總服務天數／每日時數的來源選擇。

- **MATCH-CAP-01：服務方式。** UI 顯示「服務方式」，HTTP 的 `preferred_service_days` key 保留。案件讀 Client-owned `clients.service_type`；月嫂讀 `staff_weekly_rest.rest_type` 與 `custom_rest_detail`。比對週間服務／排休方式，不比對 `orders.service_days`，也不套用數字天數 tolerance。保存的原文不改寫；查詢時辨識「周／週」、「一／1」、「二／2」同義寫法；週休二日、週一至週五視為同方式，休周六與休周日保留差異，週休一日沿既有慣例代表休周日，連續服務代表無固定週休。
- **MATCH-CAP-02：每日服務時數。** 案件需求仍為 `orders.service_hours_per_day`；月嫂唯一來源為 `staff_time_slots.slot_name` 與 `custom_slot_detail`。Staff 已驗證自訂完整時段由同一 Domain 投影其服務時數；明確正整數「N小時」及既有四小時上午／下午標準值轉成對應時數；不從 `staff_matching_preference_values` 補值或覆蓋。`其他` 只讀本母題 detail，且只接受上述可明確辨識值，混合／含糊文字不得猜測。
- **MATCH-CAP-03：一致性與失敗。** 名冊既有 writer 保存後，下一次查詢 fresh-read 原關聯表，無第二份同步副本。案件需求空白時初步詢問不套用對應篩選；已填需求不相符、月嫂資料空白或無法辨識時，勾選的初步篩選不列入該月嫂；取消勾選可詢問並協調。正式分段查詢仍只提供條件結果，不因這兩項排除 selectable candidate。
- **MATCH-CAP-04：效果上限。** 只修改本機 Domain 比對、Scheduling availability read adapter／query、checkbox 文案、direct tests 與必要正式規格／地圖。Staff／Client writer、交易邊界、資料表、migration、數字偏好 API 與既有資料不變；不部署、不切入口、不發送外部通知。

驗收：① 只登錄名冊的週休二日與 8 小時，即可通過相同需求，數字偏好無資料亦可；② 週休二日不可當成休周日，8 小時不可匹配 12 小時，單獨勾選／合併勾選結果皆正確；③ 名冊修改服務方式／時數後下一次查詢反映新值，即使數字偏好殘留舊值也不影響；④ 空白案件需求、其他明確值、未知／含糊值與正式分段行為符合 MATCH-CAP-03；⑤ HTTP key 與候選 schema 相容，UI 顯示「服務方式」。

convergence: READY；blocking gaps: none。已辨識的非阻擋事實：目前本機月嫂保存「週一至週五」、畫面期間的案件保存「休周日」，本裁決下為不相符；不得為產生候選而改寫它們。


## 2026-10-21 服務偏好收斂與姓名旁提示（最新人工裁決）

Authority：使用者確認兩頁預覽，要求名冊「服務偏好」與配對池只保留可承接區域、週間服務；原匯入資訊移到「專業資格與服務資料」保留顯示。不符合仍可顯示、選取、加入候選池；姓名旁必須直接顯示月嫂原登錄值，例如案件週休一日、月嫂週休二日時顯示「週間服務：週休二日 · 不符合」。本節取代較早的初步詢問硬性偏好篩選、每日時數／料理及自訂數字偏好參與候選篩選之敘述；不改變任職、檔期、正式服務日及正式排班資格。

- **PREF-21-01：名冊與保留資料。** 服務偏好僅顯示及維護 `staff_regions`、`staff_weekly_rest`。`staff_time_slots`、`staff_cooking_skills`、`staff_holiday_availability`、`staff_baby_types` 原登錄值與各自 detail 在「專業資格與服務資料／匯入服務資訊」唯讀顯示；不刪除、清空、重匯或改寫。沿既有六 relation QPA writer，前端每次提交均完整保留其餘四項快照，stale 與原交易邊界維持。既有數字偏好 API／資料保留其獨立契約，不增加第二份偏好副本。
- **PREF-21-02：候選與選用。** 取消四項偏好 checkbox；改為「查詢可詢問月嫂」。區域、週間服務均不排除候選，也不因不符合或待確認禁止加入候選池；料理、每日時數、節日、胎數及數字偏好均不參與此查詢的偏好提示或排除。初步詢問仍提示檔期衝突，正式分段／建立方案／正式排班沿原 fresh-read、日期與占用資格。舊 request `filters` 結構保留相容，但偏好 flags 不恢復硬性篩選。
- **PREF-21-03：來源與原值。** 區域需求讀 `clients.city`／`address`，月嫂讀 `staff_regions`（其他沿本母題 detail）；週間需求讀 `clients.service_type`，月嫂讀 `staff_weekly_rest.rest_type`／`custom_rest_detail`。週間比對沿 MATCH-CAP-01 的同義方式；顯示值保留原文，不把週休二日改寫為案件的週休一日。每列回傳 typed `matching_conditions.region` 與 `matching_conditions.preferred_service_days`，各包含 `status`（`matched`／`not_matched`／`pending`）、`required_value`、`staff_values`；區域需求顯示縣市，只有地址時顯示「依案件服務地址」，不把完整住宅地址複製到每位候選的提示；既有 `filter_results` 只保留這兩項 bool 相容投影，UI 不以 bool 推測未知狀態。
- **PREF-21-04：畫面與未知。** 兩項提示都緊鄰姓名，分別顯示「區域：月嫂原值 · 符合狀態」、「週間服務：月嫂原值 · 符合狀態」；所有已登錄值均保留可讀，不能僅寫「不符合」。案件需求缺漏、月嫂尚未登錄或週間資料無法明確辨識時標示「待確認」，不得當成符合或不符合；無登錄值顯示「尚未登錄」。狀態有文字，不僅依賴顏色；檔期提醒另列。已登錄但需求缺漏時仍顯示月嫂原值。
- **PREF-21-05：範圍。** 本機正式規格、兩頁 UI、必要 typed 查詢投影及 focused tests／畫面驗證；不新增 schema、migration、writer、交易或 provider 邊界，不修改 DB、commit、push 或部署。地區同義字及同名行政區的完整辨識策略不在本次變更範圍；不自行引入行政區碼或改寫原值。
- **PREF-21-06：可承接區域選項（後續人工裁決）。** 新增／變更區域只可選新竹市的東區、北區、香山區，以及新竹縣的竹北市、竹東鎮、新埔鎮、關西鎮、湖口鄉、新豐鄉、芎林鄉、橫山鄉、北埔鄉、寶山鄉、峨眉鄉、尖石鄉、五峰鄉，共 16 項。新竹市、新竹縣及其他縣市名稱不列為新選項。沿 Staff owner `RELATION_OPTIONS` 與既有 `/options`、Preview／Apply 驗證，不新增 UI 私有清單。既有區域原值及 detail 仍可查閱並原樣保存；非現行選項在原資料列標為「既有值」，不提供給新增列，不自動轉換、清空或遷移。配對提示的既有文字比對及不排除候選語意維持。行政區名稱核對：[新竹市行政區域](https://dep-n-district.hccg.gov.tw/ch/home.jsp?id=10&parentpath=0)、[新竹縣十三鄉鎮市](https://www.hsinchu.gov.tw/cp.aspx?n=101)。
- **PREF-21-07：週間服務選項與人工判讀（後續人工裁決）。** 以客戶主要三種服務方式為準，名冊新增選項僅「週休一日、週休二日、連續服務」；週一至週五、休周六、休周日等不再提供新增。既有原值、數字寫法及 detail 不改寫或清空，原資料列可顯示「既有值」並原樣保存。沿既有周／週與一／1、二／2同義比對；新選項收斂不另行推測或改變既有特殊值的語意。配對畫面同時保留上方客戶週間需求原文及每位姓名旁月嫂原文；無法明確判讀標為「待確認」，明確不符仍顯示「不符合」。即使所有月嫂皆不符合或待確認，也照常列出及允許加入候選池，供人員直接語意比對並協調，不為取得符合者改寫任何一方資料。
- **PREF-21-08：候選清單自動載入（後續人工裁決）。** 開啟「新增候選月嫂」即自動查詢可詢問人選並讀取已加入狀態，不要求先按查詢；共用候選查詢介面採相同行為。初始即顯示載入中，成功顯示人選或明確空結果，失敗顯示原因與「重新查詢」入口；成功後也可手動重新查詢 current facts。抽屜重開、切換案件均重新讀取；關閉／卸載取消未完成查詢，舊案件或舊請求結果不得覆蓋目前畫面。自動行為只有 Query，不自動新增候選、寄送或建立方案。候選池狀態與多月嫂分段選單沿既有自動讀取，不把需人工填寫並確認的操作改為自動寫入。

驗收：① 名冊偏好僅兩項可編輯，四項匯入資訊在資格區可讀；保存區域／週間後其他四 relation 與 detail 完全保留。② 案件週休一日、月嫂週休二日，姓名旁顯示月嫂「週休二日 · 不符合」且可加入。③ 區域不符同樣保留原登錄區域、可加入；兩項相符／不符／缺資料／無法辨識均有正確提示。④ 料理、時數及舊數字偏好差異不影響候選集合；舊 flags 不能重啟排除。⑤ 查詢零寫入、下一次查詢反映 current relations；正式排班及占用資格維持。⑥ focused Python／React 驗證與實際元件瀏覽器畫面檢查，清楚區分 mock API 驗證與真 DB 驗證。

## 2026-10-21 人工逐位機車通勤查詢與月免費額度（COMMUTE-21）

Authority：使用者接受官方 Routes API 費用，確認月嫂名冊地址為起點，要求人員逐位手動觸發、自行決定查詢人數並計算本月免費額度；明確授權依此規劃實作。此節為本次 T3 bounded implementation package：owner 維持 Scheduling matching-coordination，不新增 Domain、資料表、migration 或第二份地址主檔。

- **COMMUTE-21-01：手動效果。** 新增候選、已加入候選卡片及多月嫂分段已選人員各提供單人查詢。開頁、名單重新讀取及切換案件零 Google 呼叫；不提供整批、背景查詢或自動重試。查詢結果不改候選資格、原排序、意願、排班或任何 business root。
- **COMMUTE-21-02：來源與傳輸。** 起點由 Staff current city/address、終點由案件 current client city/address 組成；僅管理員可觸發，staff 須沿既有 status 與 lifecycle active 規則。缺地址先 typed block 且零用量。後端固定官方 HTTPS computeRoutes、TWO_WHEELER、單一起訖點，僅要求距離與時間。金鑰只讀 GOOGLE_MAPS_ROUTES_API_KEY；未設定回 typed unavailable，零 Google 請求。地址、key、原始 provider payload 不進 job、log、receipt 或前端請求參數。
- **COMMUTE-21-03：持久紀錄與重送。** 沿 existing background_jobs canonical command，單次人工 event_key 綁定 case/staff/immutable admin actor。外部請求前在同一 outer transaction enqueue 並 claim running，commit 後才呼叫 Google；max_attempts=1。同 key 同命令不再呼叫 provider，不同命令 typed conflict。Google 回傳距離僅用於當次畫面，不持久保存、跨操作快取或寫入 staff/client；重播只能證明原操作已受理，不宣稱可恢復未保存的距離。外部成功但 receipt 未確認、連線逾時或 process interruption 均保守視為用量待確認，不能 blind retry。現有 worker 只能將到期、已達 max_attempts 的 lease 關閉，不重送 provider。
- **COMMUTE-21-04：計次。** 所有管理員共用後端紀錄，按 America/Los_Angeles calendar month，使用 UTC 起訖範圍查 metadata。免費 1000 次及分級單價是 2026-10-21 官方 observed pricing；Google 改價時須更新此值與測試，非工會固定業務限制。畫面分開顯示本系統已送出、已知估計計費、待確認、免費已用、保守剩餘、超額及未稅美元估價。未送出不計；200/no-route 計入估計計費；401/403/429/5xx 視為不計費；其他無法由 HTTP 狀態唯一裁決的 4xx 與 timeout 待確認，不把所有失敗當免費。
- **COMMUTE-21-05：帳務核對。** 不假稱已接入 Google 帳單 API。管理員可從 Google 報表人工登錄同帳務帳戶、全部專案、本月 Compute Routes Enterprise 累計次數及實際報表 cutoff，沿 metadata-only canonical job 保存核對者、月份、次數與 UTC 截止時間。只接受本計費月內、不晚於現在且含時區的截止時間；預設未核對。採最新 cutoff，估算等於該累計數加 cutoff（含）之後本系統已知計費；早於 cutoff 的本機紀錄不重複加計。其餘系統在 cutoff 後的用量仍須後續核對，畫面明示估算及最終以 Google 帳務為準。
- **COMMUTE-21-06：公開入口。** admin-only GET /api/v1/scheduling/commute-usage；POST /api/v1/orders/{case_no}/caregivers/{staff_id}/commute，僅接受 event_key；POST /api/v1/scheduling/commute-usage/reconciliation，僅接受 event_key/month/count/through。回應 no-store、typed identity/error；API 不接 raw 地址或 batch staff IDs。
- **COMMUTE-21-07：顯示。** 成功顯示機車單程公里、預估分鐘、查詢時間、Google Maps attribution 及 beta 路線提醒；無路線、缺地址、未設定、連線錯誤各明確說明，不能用零公里或汽車路線替代。查詢中禁止重複點擊；結果未明以原 key 確認；重查明示增加用量。切換人員/案件卸載舊結果，不以舊結果覆蓋新人選。

實作 write set：subsystems/scheduling/commute_query.py、infrastructure/http/google_routes.py、infrastructure/mysql/commute_query_repository.py、api/routes/commute.py、api/main.py router registration、React commute client/components 與三個既有媒合入口、對應 module tests、此 owner spec／map、NAS 既有 environment template／操作文件。既有 dirty成果保留，不 commit/push/deploy，不建立或填寫真實 key，不查真實地址。

驗收工作包：A1 手動單人、零自動 provider；A2 claim-before-effect、same-key 不重送、typed conflict；A3 來源缺漏/退役/未設定零計費；A4 月界/DST/免費/付費/unknown；A5 全帳戶人工核對不重複加計；A6 UI identity、loading/error、Google attribution/beta；A7 focused Python/React regression、real MySQL connection-local temporary-table check、build、模擬資料 browser capture、git diff check 及 architecture closure。操作上限：Google 實際 API 驗收須先由使用者申請與設定；本次只用 fake provider。無 schema diff，migration gate 不適用；既有 development DB 僅建立連線專用 temporary tables，關閉即移除，不改既有 rows。

參考：[官方單價](https://developers.google.com/maps/billing-and-pricing/pricing)、[計費月界](https://developers.google.com/maps/billing-and-pricing/pay-as-you-go)、[狀態與帳務](https://developers.google.com/maps/reporting-and-monitoring/reporting)、[Routes 儲存與標示政策](https://developers.google.com/maps/documentation/routes/policies)。
