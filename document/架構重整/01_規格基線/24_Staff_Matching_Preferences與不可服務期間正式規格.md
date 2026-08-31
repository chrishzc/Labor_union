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
4. `MatchingRecommendationQuery`：組合五項內建條件與啟用中的自訂偏好條件。
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

- 偏好只影響媒合排序與 explanation，不是接案資格或硬性排除條件。filter checkbox 僅控制本次 Query 是否將該偏好納入排序權重／說明，不得因此移除 selectable candidate。
- integer target 落在月嫂 `[minimum, maximum]` 內，或存在於 integer set 內，為 `matched`；否則 `not_matched`。
- 月嫂未設定啟用中的偏好時為 `source_not_ready`；仍可列為 selectable，但排序不得把未知值當成 matched，UI 必須明示尚未登錄。
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
  typed Orders command補入 canonical `requires_cooking`。空白、矛盾或自由文字無法唯一判定時回
  `case_import_cooking_requirement_ambiguous` 進 Import Review，但不撤銷已建立的 HCM roots。
- 此補正僅能改寫 `requires_cooking`；歷史 root 有 `actual_start_date` 而尚無正式 Scheduling segment
  時仍可執行，不得順帶變更日期、時段、工時、費用或其他服務條款。服務資料鎖形成後固定拒絕。
- 原始 `survey_details` 保留為來源 evidence；正規化後布林值進 reconciliation fingerprint、event與
  Orders root。不得在 Matching Query 每次重新解析自由文字。
- 月嫂料理能力使用 `staff_cooking_skills`。案件不需要下廚時條件為 `not_applicable`；需要下廚時，
  至少有一筆有效料理能力才為 `matched`。

## 5. 長假／暫停接案

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
- Matching 勾選「檔期」時，與 current 不可服務期間重疊者為 actual conflict 並排除；取消檔期 filter
  時可顯示，但必須保留警告，且建立 matching plan／assignment 前仍 fail closed。
- Calendar 顯示 `staff_unavailability`、kind、期間及原因；不可呈現為可接案、正式服務日、請假代班
  outcome 或七日 buffer。
- 請假／代班是已有 assignment 後的服務異動；本功能是尚未指派前的個人 availability，兩者不可互相取代。

## 5.1 Staff 退役對 Matching 的約束（2026-08-15，WP91 已人工確認）

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
- Domain：五項預設 filter、自訂偏好加入／停用、長假與 Calendar／Matching 同源、buffer-only 仍顯示。
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
