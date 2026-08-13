# Staff Matching Preferences 與不可服務期間正式規格

## 1. 文件狀態

- 狀態：`approved-by-user-2026-08-13`
- Owner：`Scheduling Staff Matching Profile／Assignments／Matching`
- 實作包：[72_Matching_Preferences_and_Staff_Unavailability_Work_Package.md](../02_決策與退役執行記錄/72_Matching_Preferences_and_Staff_Unavailability_Work_Package.md)
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

- filter checkbox 預設勾選；取消只影響本次 Query。
- integer target 落在月嫂 `[minimum, maximum]` 內，或存在於 integer set 內，為 `matched`；否則 `not_matched`。
- 月嫂未設定啟用中的偏好時為 `source_not_ready`；勾選該 filter 時不可列為 selectable，取消後可顯示。
- Query 回傳 definition identity／version、顯示名稱、target、staff value、result 與 reason code；UI 不解析中文名稱決定規則。
- Query 結果綁定 Staff preference、Orders 與 Scheduling source versions；選擇或 Apply 前必須 fresh recheck。

## 4. 下廚需求

- Case Import 邊界可將 BeClass 問卷轉成 Orders canonical `requires_cooking` 條款。
- 只接受可明確判定的 yes／no source value；空白、矛盾、自由文字無法唯一判定時回
  `case_import_cooking_requirement_ambiguous` 進 Import Review，不預設為否。
- 原始 `survey_details` 保留為來源 evidence；正規化後布林值進 Case Import intent、candidate、fingerprint、
  import event 與 Orders root。不得在 Matching Query 每次重新解析自由文字。
- 月嫂料理能力使用 `staff_cooking_skills`。案件不需要下廚時條件為 `not_applicable`；需要下廚時，
  至少有一筆有效料理能力才為 `matched`。

## 5. 長假／暫停接案

- kind 僅允許 `long_leave`、`paused_service`。
- 根事實包含 staff、起訖日期（含首尾日）、kind、reason、建立 actor／時間與取消事件；
  `long_leave` 必須有結束日，`paused_service` 可 open-ended，恢復時以 resume date 前一日封閉期間。
- Apply 預設拒絕同一月嫂的 current overlap，回
  `staff_unavailability_period_conflict`，避免重複事實。
- 建立前須鎖共用 staff occupancy mutex 並 fresh-read assignment、waiting service lock 與 buffer；
  任一既有承諾重疊皆拒絕，不能用不可服務期間掩蓋 assignment 或 waiting lock。
- 取消只追加事件，不刪除或改寫原期間。
- Matching 勾選「檔期」時，與 current 不可服務期間重疊者為 actual conflict 並排除；取消檔期 filter
  時可顯示，但必須保留警告，且建立 matching plan／assignment 前仍 fail closed。
- Calendar 顯示 `staff_unavailability`、kind、期間及原因；不可呈現為可接案、正式服務日、請假代班
  outcome 或七日 buffer。
- 請假／代班是已有 assignment 後的服務異動；本功能是尚未指派前的個人 availability，兩者不可互相取代。

## 6. Typed errors

- `staff_preference_definition_invalid`
- `staff_preference_definition_conflict`
- `staff_preference_value_invalid`
- `staff_preference_version_conflict`
- `staff_preference_source_not_ready`
- `case_import_cooking_requirement_ambiguous`
- `staff_unavailability_period_invalid`
- `staff_unavailability_period_conflict`
- `staff_unavailability_version_conflict`
- `stale_preview`
- `idempotency_conflict`
- `transaction_failed`

## 7. 驗收

- Module：偏好 range、matching comparison、明確下廚 normalization、不可服務日期及 overlap。
- Subsystem：Query 零寫入、Preview 零寫入、Apply replay／payload mismatch／stale／rollback。
- Domain：五項預設 filter、自訂偏好加入／停用、長假與 Calendar／Matching 同源、buffer-only 仍顯示。
- Browser：建立偏好、填月嫂值、建立不可服務期間、配對結果刷新、Calendar 顯示、取消後恢復。
- 真人 LINE 不在本 Work Package 驗收範圍。
