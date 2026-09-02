# `case_staff_assignments` 欄位權威性與計算邏輯盤點

- 狀態：討論與裁決用工作清冊；不是 SSOT，不代表 CP-1、Task 或實作核准。
- 分類：`03_媒合指派排班與請假`
- 總索引：[06_欄位權威性與計算邏輯盤點](../../06_欄位權威性與計算邏輯盤點.md)
- 第一遍（live 現況）：已完成
- 第二遍（衍生判定）：已完成
- 根事實展開：已完成
- 規格反查：已完成

- Schema：`db/schema.sql`
- 父表關係：`case_no` → `orders.case_no`, `staff_id` → `staff.id`
- 子表關係：`actual_hours_adjustments`, `assignment_schedule_leave_substitution_events`
- 已確認跨表裁決：本表為正式訂單服務指派的核心實體。配對方案轉為正式訂單時產生指派；案件服務資料鎖成立前，任何條款、分段、請假或代班變更均取消舊有效指派並建立新指派。全案條款變更重建全部有效 assignments；局部請假／順延／代班只重建受影響 family，但都重新驗證全案守恆。assignment 的連續區間（含休假日）均占用月嫂檔期。`actual_hours` 是正式工作日與訂單每日服務時數的衍生投影，不是可人工覆寫的來源事實。

| 欄位 | Schema 定義 | 現況架構／用途 | 初步分類 | 現況公式 | 直接來源 | 第一層根事實 | 建議權威公式 | 修改命令／Owner | 重算觸發 | 凍結邊界 | 現況漂移／風險 | 裁決 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `id` | `BIGINT AUTO_INCREMENT PRIMARY KEY` | 技術主鍵。 | 系統鍵 | 不計算。 | DB 自增。 | 指派事實。 | 無。 | Order Sync Service | 無 | 不變 | 無 | 已確認：SSOT 鍵 |
| `case_no` | `VARCHAR(50) NOT NULL` | 所屬訂單。 | 關聯鍵 | 不計算。 | 方案轉換帶入。 | `orders.case_no`。 | 必須對應有效訂單。 | Order Sync Service | 無 | 不變 | 無 | 已確認 |
| `staff_id` | `INT NOT NULL` | 指派月嫂。 | 關聯鍵 | 不計算。 | 方案轉換帶入。 | `staff.id`。 | 必須對應有效月嫂。 | Order Sync Service | 無 | 不變 | 無 | 已確認 |
| `assignment_sequence` | `INT NOT NULL` | 接力順序 (同案第幾位月嫂)。 | 來源事實 | 不計算。 | 繼承自 `segment_order`。 | 方案區段排序。 | 無。 | Order Sync Service | 無 | 不變 | 無 | 已確認 |
| `assigned_start_date` | `DATE NULL` | 新正式指派在 Preview／Apply 時確認的分段開始日。 | 來源事實／指派命令輸入 | 不計算。 | 排班 Preview 的分段設定。 | 管理員確認後套用的 assignment segment 起日。 | 新 assignment 建立時寫入，必須不晚於 `assigned_end_date`，並與其生成的正式工作日相容；不得原地 UPDATE。上游條款、日期、請假、代班或分段變更時，在凍結前取消舊 assignment、以新 Preview 產生新 assignment。 | Assignment Preview／Apply Command | 新 assignment 建立與任一上游規則變更 | 訂單尚未完成或相關帳務尚未核銷／結算時可取消重建；兩者均完成後凍結，差額走 adjustment／reversal | 現況請假流程仍直接改寫指派日期，違反取消舊建新的模型。 | 已確認：Preview 分段輸入；凍結前可取消重建 |
| `assigned_end_date` | `DATE NULL` | 新正式指派在 Preview／Apply 時確認的分段結束日。 | 來源事實／指派命令輸入 | 不計算。 | 排班 Preview 的分段設定。 | 管理員確認後套用的 assignment segment 迄日。 | 新 assignment 建立時寫入，必須不早於 `assigned_start_date`，並與其生成的正式工作日相容；不得原地 UPDATE。上游條款、日期、請假、代班或分段變更時，在凍結前取消舊 assignment、以新 Preview 產生新 assignment。 | Assignment Preview／Apply Command | 新 assignment 建立與任一上游規則變更 | 訂單尚未完成或相關帳務尚未核銷／結算時可取消重建；兩者均完成後凍結，差額走 adjustment／reversal | 現況請假流程仍直接改寫指派日期，違反取消舊建新的模型。 | 已確認：Preview 分段輸入；凍結前可取消重建 |
| `original_assigned_start_date` | `DATE NULL` | 與建立時 `assigned_start_date` 重複的歷史快照。 | 重複資料／長期考慮移除 | `assigned_start_date` 初始值複製。 | `assigned_start_date`。 | 同一 assignment 的 Preview 分段輸入。 | 因 assignment 建立後不允許原地改寫，本欄位不提供額外資訊；長期考慮移除。 | 無 | 停用 | 凍結 | 與 `assigned_start_date` 永遠相同，增加同步與閱讀複雜度。 | 已確認：長期考慮移除 |
| `original_assigned_end_date` | `DATE NULL` | 與建立時 `assigned_end_date` 重複的歷史快照。 | 重複資料／長期考慮移除 | `assigned_end_date` 初始值複製。 | `assigned_end_date`。 | 同一 assignment 的 Preview 分段輸入。 | 因 assignment 建立後不允許原地改寫，本欄位不提供額外資訊；長期考慮移除。 | 無 | 停用 | 凍結 | 與 `assigned_end_date` 永遠相同，增加同步與閱讀複雜度。 | 已確認：長期考慮移除 |
| `planned_hours` | `DECIMAL(10, 2) NULL` | 預計總工時的遺留快取。 | 衍生投影／長期考慮移除 | 預排 assignment-owned 工作日數 × `orders.service_hours_per_day`。 | 預排正式工作日與訂單每日服務時數。 | `staff_schedule.assignment_id/work_date/is_work_day` 的預排工作日，以及 `orders.service_hours_per_day`。 | 不具獨立權威性；Preview／UI 需要時即時計算，不保存為薪資、actual hours 或其他欄位的來源。 | 無 | 停用 | 凍結 | 與 `actual_hours` 同屬可推導數值，保存後易被錯當來源；長期考慮移除。 | 已確認：長期考慮移除 |
| `actual_hours` | `DECIMAL(10, 2) NULL` | 該正式指派的實際總工時投影，也是薪資計算讀取值。 | 衍生投影／快取 | `assignment_official_work_day_count × orders.service_hours_per_day`。 | 正式 assignment-owned 工作日與訂單每日服務時數。 | `staff_schedule.assignment_id/work_date/is_work_day` 所代表的本指派正式工作日，以及 `orders.service_hours_per_day` 正式條款。 | 不得由 `planned_hours`、人工微調、前端或薪資結果反推／覆寫。任一上游條款、服務日期、分段、請假或代班變更時，在凍結前取消舊有效指派並重建工作日與本值；凍結後差額僅以 adjustment／reversal 留存。 | Schedule／Assignment Rebuild Projection | 正式工作日或任一上游條款變更 | 訂單尚未完成或相關帳務尚未核銷／結算時可重建；兩者均完成後不覆寫歷史快照 | 現況仍有 `planned_hours + adjustment`、`actual_hours_adjustments` 與 direct writer 路徑，違反單一公式，必須收斂。 | 已確認：正式工作日數 × 訂單每日服務時數 |
| `hourly_rate` | `DECIMAL(10, 2) NULL` | 本 assignment 的 Preview 薪資條款快照。 | 衍生條款快照 | 依客戶身分政策映射：一般市民 → 300；補助市民 → 350；非市民 → 320。原始 `低收入戶`／`中低收入戶` 先映射為補助市民政策。 | `clients.identity_status` 經受控薪資費率政策。 | 客戶原始身分資格與其已確認政策映射。 | 每筆新 assignment 在 Preview／Apply 時套用政策產生薪資條款；任一上游資料合法調整時，在凍結前取消舊 assignment、重新 Preview／重建本值。`staff payment service_salary = actual_hours × hourly_rate`，再加 `floor_fee_allocated`。 | Assignment Preview／Apply Projection | 新 assignment 建立與任一上游條款變更 | 訂單尚未完成或相關帳務尚未核銷／結算時可重建；兩者均完成後凍結，差額走 adjustment／reversal | 現況媒合 UI 允許管理員逐段手填；live calculator 又存在另一套身分費率，兩者均與已確認薪資政策漂移，必須收斂。 | 已確認：依客戶身分的 Preview 薪資條款 |
| `floor_fee_allocated` | `DECIMAL(12, 2) NOT NULL DEFAULT 0.00` | 本指派承接的樓層費整數分配投影。 | 衍生投影 | 正常履約由 Preview 分配訂單樓層費；中途取消先按全案實際服務天數縮減，再按各 assignment 實際服務日重新分配。 | 訂單樓層費條款、原合約服務天數、逐日實際服務 owner 與 Preview。 | `orders.floor_fee`、`orders.service_days` 與已確認的 assignment-owned 實際服務日。 | 不具獨立費用權威。取消後有效樓層費為 `ROUND_HALF_UP(原樓層費 × 全案實際服務天數 ÷ 原服務天數)`；再以最大餘數法分配整數元，餘數相同依固定 assignment 順序。必須守恆 `Σ effective floor_fee_allocated = 客戶端已認列樓層費`；代班只轉移，不創造或重複。 | Assignment／Cancellation Preview／Apply Projection | 樓層費、上游條款、實際服務日、分段或代班變更 | 案件服務資料鎖成立前可取消重建；鎖成立後差額走 adjustment／reversal | 現況公式空白且欄位可保存小數，容易被誤當可直接填寫的薪資來源。 | 已確認：整數、取消比例與雙端守恆 |
| `status` | `ENUM(...) NOT NULL DEFAULT 'planned'` | 指派生命週期投影。 | 狀態投影 | Preview 是純試算、不建立 DB assignment；Apply 後依 assignment-owned 正式服務日時刻自動投影，取消／重排舊指派一律為 `cancelled`。 | Assignment Apply／Cancellation command、正式工作日與案件統一服務時段。 | 已接受的建立／取消命令及 assignment-owned 正式工作日。 | `planned`＝尚未到第一個正式服務日開始時刻；`active`＝已到第一個開始時刻且尚未到最後一個結束時刻，中間休假空窗仍 active；`completed`＝已到最後一個正式服務日結束時刻；`cancelled` 只作有效性篩選，排除目前排班與薪資。禁止人工直接修改；`replaced` 長期移除。 | Assignment Apply／Cancellation／進度 Projection | Apply、取消或業務時間跨越 | 案件服務資料鎖成立前仍可取消／重建任一有效狀態；鎖成立後差額走 adjustment／reversal | 現況仍有 `replaced` enum／caller，且切換時刻未由統一時段定義。 | 已確認：完整且全衍生狀態 |
| `replacement_reason` | `VARCHAR(255) NULL` | 重排原因的遺留單欄位。 | 重複稽核資料／長期考慮移除 | 不計算。 | 無；應由不可變取消／重建命令事件保存。 | 受理的取消／重建命令及其原因。 | 一次重排可影響多筆舊、新 assignment，原因應屬命令事件，不屬單一 assignment 欄位；長期考慮移除。 | 無 | 停用 | 凍結 | 單欄位無法完整表達批次重排或原因歷程。 | 已確認：長期考慮移除 |
| `replaced_assignment_id` | `BIGINT NULL` | 一對一替換關聯的遺留欄位。 | 重複關聯／長期考慮移除 | 不計算。 | 無；應由不可變取消／重建命令事件保存舊、新 assignment 集合。 | 同一重排命令的 input／output assignment 集合。 | 一筆舊 assignment 可拆成多筆新 assignment，或多筆舊指派重建為其他分段，單一 FK 不可正確表示；長期考慮移除。 | 無 | 停用 | 凍結 | 現況 FK 迫使錯誤的一對一模型，且與 cancelled + rebuild 規則衝突。 | 已確認：長期考慮移除 |
