# Staff Matching Preferences 與不可服務期間正式規格

## 1. 文件邊界與所有權

- 狀態：`current-spec`
- Owner：Scheduling（Staff Matching Profile／Assignments／Matching）
- 單一負責範圍：月嫂接案條件與數字偏好契約、長假／暫停接案不可服務期間、Staff 退役對媒合之約束，以及手動機車通勤查詢契約。
- 關聯引用：見 [Global 共同契約](00_Global_共同契約.md)、[Orders Domain](01_Orders_Domain.md)、[Assignments / Scheduling Domain](02_Assignments_Scheduling_Domain.md)、[Staff Roster Case Preference Read Model](24A_Staff_Roster_Case_Preference_Read_Model正式補充契約.md)、[Staff Roster Case Preference Ownership](24B_Staff_Roster_Case_Preference_Ownership_Clarification.md)

## 2. Domain 分工與 Subsystems

| Owner | 根事實／責任 |
|---|---|
| Scheduling／Staff Matching Profile | 數字偏好定義（`integer_range`/`integer_set`）、月嫂偏好值與版本 |
| Staff | 六項 canonical service capability relations（區域、時段、下廚、節日、排休、胎數）、`care_babies` 與生命週期 |
| Orders | 案件服務天數、每日服務時數、下廚需求等正式條款 |
| Scheduling | 長假／暫停接案日期區間、已承諾排班例外、current availability 與 Calendar projection |
| Matching | 消費 Staff／Orders／Scheduling typed facts，產生條件提示與候選查詢結果（不修改原資料） |

- Subsystems：`StaffPreferenceDefinitionWorkflow`、`StaffPreferenceValueWorkflow`、`StaffUnavailabilityWorkflow`、`MatchingRecommendationQuery`、`StaffCalendarQuery`、`CommuteQueryApplication`。
- Modules（純函式，不讀 DB、不取現在時間、不 import API／UI）：`PreferenceDefinitionValidator`、`IntegerRangePreferenceValidator`、`PreferenceMatchEvaluator`、`UnavailabilityPeriodValidator`、`UnavailabilityOverlapProjector`、`MatchingFilterExplanationBuilder`。
- 管理端只呼叫 bounded typed API，不直接讀寫資料表或自行計算比對規則。

## 3. 接案條件、名冊投影與不排除候選規則

### 3.1 名冊與候選查詢之服務偏好收斂

- **名冊編輯範圍**：名冊「服務偏好」分頁僅維護可承接區域（`staff_regions`）與週間服務（`staff_weekly_rest`）。其餘四項原匯入事實（`staff_time_slots`、`staff_cooking_skills`、`staff_holiday_availability`、`staff_baby_types`）及各自 detail 於「專業資格與服務資料」唯讀保留，提交區域／週間時完整保留其餘四項快照。
- **標準選單限制**：
  - `staff_regions` 新增／變更僅可從新竹市 3 區（東區、北區、香山區）與新竹縣 13 鄉鎮市（共 16 項）選取，不提供「新竹市／新竹縣」或外縣市。
  - `staff_weekly_rest` 新增／變更僅可選「週休一日、週休二日、連續服務」。
  - 既有非標準歷史原值與 detail 仍原樣保留並標示為「既有值」，不自動轉換或清空。
- **候選查詢不排除規則**：
  - 「新增候選月嫂」開啟即自動執行 Query（僅查詢、零寫入），切換案件或關閉抽屜取消未完成請求。
  - 區域與週間服務均**不排除候選**，也不因不符合或待確認禁止加入候選池；料理、每日時數、節日、胎數及獨立數字偏好均不參與候選提示或排除。
  - 姓名旁緊鄰顯示原值與狀態：「區域：月嫂原值 · 符合狀態」、「週間服務：月嫂原值 · 符合狀態」（`matched` / `not_matched` / `pending` /「尚未登錄」）。區域讀 `clients.city`/`address`（不複製完整地址）與 `staff_regions`；週間讀 `clients.service_type` 與 `staff_weekly_rest`（同義辨識「周/週」「一/1」「二/2」，週休二日與週一至週五視為同方式，保留休周六／休周日差異，不把週休二日誤認符合週休一日）。回傳結構化 `matching_conditions.region` 與 `matching_conditions.preferred_service_days`（含 `status`、`required_value`、`staff_values`）及相容 `filter_results`（UI 嚴禁以布林推定未知狀態）；單純 `not_matched` 或 `source_not_ready` 不得投影 `SCHEDULE-005` 或任何硬性異常。

### 3.2 六母題 relation QPA 與 `[其它]` 所有權

- 六個 canonical relations（`staff_regions`、`staff_time_slots`、`staff_cooking_skills`、`staff_holiday_availability`、`staff_weekly_rest`、`staff_baby_types`）提供 Staff owner typed Q/P/A（`GET /api/v1/staff/case-preference-manual/options`、`GET /api/v1/staff/case-preference-manual/{staff_id}`、`POST /api/v1/staff/case-preference-manual/{staff_id}/preview`、`POST /api/v1/staff/case-preference-manual/{staff_id}/apply`）：Preview 綁定六關係 snapshot fingerprint；Apply 先鎖 Staff parent，再依 table name 排序鎖六 relation rows，重用 `admin_command_receipts`。
- 六組 `[其它]` 永久跟隨原母題（`[其它]`→下廚、`[其它].1`→區域、`[其它].2`→時段、`[其它].3`→排休、`[其它].4`→胎數、`[其它].5`→節日），嚴禁合併為 generic `other`；`staff_transportation` 無 `[其它]` 來源，保持 `source_not_ready`。
- 自訂服務時段選 `4`/`8`/`24` 小時時，起迄跨度須精確對應 240 分鐘（不扣休）、510 分鐘（含 30 分休）與 1440 分鐘，編碼為 `4小時(09:00-13:00)`、`8小時(08:30-17:00)`、`24小時(09:00-次日09:00)`，無效時間回 typed 422 零寫入。

### 3.3 獨立數字偏好 API（保留契約、不參與候選篩選）

`/api/v1/scheduling/staff-matching-preferences` 保留現有 `integer_range`／`integer_set` definition 與 Staff value Q/P/A（寫入 `staff_matching_preference_values`，涵蓋 `orders.service_days`、`orders.service_hours_per_day`、`record_only`；另 HTTP 查詢鍵名 `preferred_service_days` 仍維持保留但來源對應 `staff_weekly_rest`），維持版本、fingerprint 與獨立語意，但不參與目前候選提示或排除（不從 `staff_matching_preference_values` 補值），也不得覆蓋名冊 canonical relations。

### 3.4 下廚需求 intake 與補正

- HCM 與 Client BeClass 獨立匯入；尚未唯一綁定時 `orders.requires_cooking` 保持 `NULL`。
- 唯一配對後由 Case Import reconciliation 補入 `requires_cooking`（`是否需要下廚：` 優先於餐點偏好；矛盾或無法唯一判定時回 `case_import_cooking_requirement_ambiguous` 進 Import Review）。服務資料鎖形成後拒絕改寫。

## 4. 長假／暫停接案（不可服務期間）

- 管理抽屜提供「暫停接案」（`long_leave`，必有起訖日，含首尾日）與「無期限暫停接案」（`paused_service`，可 open-ended，恢復時以 resume date 前一日封閉），開始日預設台北業務當天。
- 抽屜開啟及異動後載入全部歷史與未來紀錄（`GET /api/v1/scheduling/staff/{staff_id}/availability-blocks` 省略日期時以 `after_id`／`limit` 依 id 升冪分頁，傳入日期時最多 366 天）；呈現「目前：暫停接案中／未暫停接案」（載入／失敗不誤判），未來標示「尚未開始」，取消紀錄收合且不重複取消。
- 新增、取消及恢復取得成功收據後，前端通知同瀏覽器之排班／媒合查詢（僅帶 `staff_id`）重讀 current facts，受保護寫入完成後才刷新。
- Apply 預設拒絕同月嫂重疊區間（`staff_unavailability_period_conflict`）。建立前鎖 staff occupancy mutex 並檢查 assignment、waiting lock 與 buffer：與既有正式排程重疊時預設拒絕並回 `staff_unavailability_committed_schedule_conflict`，須經具權限人員核對 exact conflict snapshot 後以 `force_preserve_committed_schedule` 確認保存（此時既有正式排程固定優先，重疊日標為 `committed_schedule_exception`，Calendar 並存顯示雙方不可隱藏）。
- 取消採 append-only 事件；不可服務期間為排班前個人 availability，不可取代請假／代班流程。

## 5. Staff 退役對 Matching 的約束

- 管理端選取退役生效日期轉為該日台北時間 `00:00` 的 `effective_at`，原因選填。
- 月嫂仍有未結束案件時不得退役（Preview／Apply 皆阻擋）。
- Staff 退役寫入 `staff_lifecycle_states`（`active -> retired`），在同一 Staff outer UoW 透過 typed port 僅解除 LINE `staff` role（保留 `customer` role 與 successor menu intent），失敗整筆回滾。
- 退役生效後，所有新候選、重算與新 assignment 排除該 Staff；已確認未來 assignment 保留，變更走 Scheduling replacement/cancellation；Assignment Plan 重建僅保留與 current effective assignment 完全一致之區段，新增或移動回 `staff_retired_new_assignment_forbidden`。
- 復職須走獨立 `ReactivateStaff` command 並重新驗證當下資料，不自動恢復過期邀請或偏好。

## 6. 人工機車通勤查詢（COMMUTE-21）

- **手動觸發**：僅在新增候選、已加入候選卡片與多月嫂分段介面提供單人查詢；開頁、換頁或重讀零 Google API 呼叫，結果不影響排序、資格或排班。
- **來源與傳輸**：起點取 Staff `city/address`、終點取案件 `city/address`（缺地址回 typed block 零用量）；後端以 `GOOGLE_MAPS_ROUTES_API_KEY` 呼叫官方 HTTPS `computeRoutes`（`TWO_WHEELER`），金鑰與 raw 地址／payload 不進 job、log、receipt 或前端參數。
- **紀錄與防重**：沿 `background_jobs` 以單次 `event_key` 在 outer transaction enqueue 並 claim running（`max_attempts=1`），commit 後才呼叫 Google；同 key 重播不重送，不同命令回 conflict；timeout／未知結果視為用量待確認不 blind retry。查詢結果僅於當次畫面呈現，不持久寫入。
- **計次與帳務核對**：依 `America/Los_Angeles` 計費月統計本系統已送出、計費、待確認、免費 1000 次額度與估計美元（`200 / no-route` 計入估計計費，`401/403/429/5xx` 不計費，其餘無法唯一判定之 `4xx` 與 timeout 列待確認）；管理員可透過 `POST /api/v1/scheduling/commute-usage/reconciliation` 人工登錄 Google 報表累計數與 cutoff 時間，估算只疊加 cutoff 之後本機計費。
- **入口**：`GET /api/v1/scheduling/commute-usage`、`POST /api/v1/orders/{case_no}/caregivers/{staff_id}/commute`、`POST /api/v1/scheduling/commute-usage/reconciliation`。

## 7. Typed errors

`staff_preference_definition_invalid`、`staff_preference_definition_conflict`、`staff_preference_value_invalid`、`staff_preference_version_conflict`、`staff_preference_source_not_ready`、`case_import_cooking_requirement_ambiguous`、`staff_unavailability_period_invalid`、`staff_unavailability_period_conflict`、`staff_unavailability_committed_schedule_conflict`、`staff_unavailability_force_confirmation_required`、`staff_unavailability_committed_exception_stale`、`staff_unavailability_version_conflict`、`staff_retired_new_assignment_forbidden`、`stale_preview`、`idempotency_conflict`、`transaction_failed`。

## 8. 驗收標準

1. 名冊偏好僅維護區域與週間服務，四項匯入能力於資格區唯讀保留，儲存區域／週間不清除四項原值與 detail；六組 `[其它]` 嚴格不跨母題。
2. 候選查詢自動載入、零寫入，區域與週間僅顯示原值與符合／不符合／待確認提示，不排除任何候選；料理、時數與數字偏好不參與篩選。
3. 不可服務期間嚴格驗證重疊與已承諾排程衝突；強制保存時保留既有 assignment 優先權，Calendar 與 Matching 同源更新。
4. Staff 退役與 LINE `staff` 角色解除原子提交，未結案阻擋、已確認未來指派保留、新排班禁止。
5. 通勤查詢僅單人手動觸發、same-key 不重複計費、缺地址／未設金鑰零外部請求、帳務核對依 cutoff 疊加計算。
