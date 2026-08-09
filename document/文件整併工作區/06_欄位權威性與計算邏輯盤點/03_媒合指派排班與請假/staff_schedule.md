# `staff_schedule` 欄位權威性與計算邏輯盤點

- 狀態：討論與裁決用工作清冊；不是 SSOT，不代表 CP-1、Task 或實作核准。
- 分類：`03_媒合指派排班與請假`
- 總索引：[06_欄位權威性與計算邏輯盤點](../../06_欄位權威性與計算邏輯盤點.md)
- 第一遍（live 現況）：已完成
- 第二遍（衍生判定）：已完成
- 根事實展開：已完成
- 規格反查：已完成

- Schema：`db/schema.sql`
- 父表關係：`case_no` → `orders.case_no`, `staff_id` → `staff.id`, `assignment_id` → `case_staff_assignments.id`
- 子表關係：無已宣告子表
- 已確認跨表裁決：本表為月嫂負責案件的「逐日排班事實 (SSOT)」。取代了已被作廢的 `staff_bookings`，正式記錄某月嫂在某日是否為工作日 (`is_work_day`) 以及是否為雙倍薪資日 (`is_double_pay`)。

| 欄位 | Schema 定義 | 現況架構／用途 | 初步分類 | 現況公式 | 直接來源 | 第一層根事實 | 建議權威公式 | 修改命令／Owner | 重算觸發 | 凍結邊界 | 現況漂移／風險 | 裁決 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `id` | `INT AUTO_INCREMENT PRIMARY KEY` | 排班紀錄主鍵。 | 系統鍵 | 不計算。 | DB 自增。 | 排班事實。 | 無。 | Schedule Service | 無 | 不變 | 無 | 已確認：SSOT 鍵 |
| `case_no` | `VARCHAR(50) NOT NULL` | 所屬訂單。 | 關聯鍵 | 不計算。 | 方案轉換帶入。 | `orders.case_no`。 | 必須對應有效訂單。 | Schedule Service | 無 | 不變 | 無 | 已確認 |
| `staff_id` | `INT NOT NULL` | 排定服務的月嫂。 | 關聯鍵 | 不計算。 | Assignment Preview／Apply 帶入。 | `case_staff_assignments.staff_id` 與 `staff.id`。 | 必須與所屬 `assignment_id` 的月嫂一致；不得只靠 case_no／staff_id 猜測工作日歸屬。 | Schedule／Assignment Apply Projection | 新 assignment 建立或重建 | 隨 assignment 的取消／重建更新 | 舊資料或 legacy writer 可缺 assignment ownership。 | 已確認 |
| `assignment_id` | `BIGINT NULL`（multi-caregiver migration `95` 加入；既有未覆核排班可暫為 NULL） | 正式工作日歸屬的 assignment 關聯鍵。 | 關聯鍵／正式排班根關聯 | 不計算。 | Assignment Preview／Apply 產生的正式 assignment。 | `case_staff_assignments.id`。 | 所有新正式排班列必須有非 NULL `assignment_id`，且只屬於一筆非 cancelled assignment；`actual_hours` 只計算此關聯下 `is_work_day = TRUE` 的列。既有 NULL 列僅供覆核，不能混入正式薪資投影。 | Schedule／Assignment Apply Projection | 新 assignment 建立、取消／重建 | 凍結前可隨 assignment 取消／重建；訂單完成且相關帳務核銷／結算後保留歷史 | 主 schema base 未列本欄，易使 reader 漏掉 ownership；migration 已有 FK／索引守衛。 | 已確認：正式工作日 ownership 關聯 |
| `work_date` | `DATE NOT NULL` | 具體排班日期。 | 來源事實 | 不計算。 | 排班邏輯生成。 | 實際日曆日。 | 本表具有 `UNIQUE KEY ukey_staff_date (staff_id, work_date)`。 | Schedule Service | 無 | 不變 | 無 | 已確認 |
| `is_work_day` | `BOOLEAN DEFAULT TRUE` | 本排班日是否為正式工作日。 | 衍生排班投影 | 由訂單固定排休規則、假日、請假／代班設定與 Preview 分段共同產生。 | Assignment Preview 的正式排班日明細。 | 訂單排班條款、已確認的請假／代班命令與 assignment segment。 | `TRUE` 列才計入 assignment official work-day count 與 `actual_hours`；`FALSE` 列只供行事曆顯示排休／請假。不得由 UI／單列 API 直接切換；任一變更均取消舊 assignment、以新 Preview 重建排班。 | Schedule／Assignment Preview Apply Projection | 任一上游排班規則變更 | 訂單尚未完成或相關帳務尚未核銷／結算時可取消重建；兩者均完成後保留歷史，差額走 adjustment／reversal | 現況仍有請假流程直接覆寫／重用既有排班列，與取消舊建新的模型衝突。 | 已確認：排班投影；TRUE 才計工時 |
| `is_double_pay` | `BOOLEAN DEFAULT FALSE` | 本排班日是否套用雙倍薪資的例外投影。 | 衍生排班／薪資條款投影 | 預設永遠為 `FALSE`；只有受控 Preview／Apply 的明確例外才可為 `TRUE`，不得因國定假日自動啟用或由單列 API 直接切換。 | 已確認的特殊日薪資例外條款。 | 客戶／工會確認的特別薪資安排。 | `TRUE` 時，該正式工作日的月嫂薪資與客戶服務費皆按 2 倍計；Preview 必須據此重算所有尚未核銷的客戶應收，不能只提高月嫂成本。 | Special Pay Preview／Apply Projection | 特別薪資例外確認 | 訂單尚未完成或相關帳務尚未核銷／結算時可取消重建；兩者均完成後差額走 adjustment／reversal | 現況文件稱遇國定假日可自動雙倍，且收款計算未納入本欄，會使客戶應收與月嫂應付不一致。 | 已確認：預設 FALSE；客戶負擔雙倍，重算未核銷應收 |
| `notes` | `VARCHAR(255) NULL` | 管理員調整備註。 | 來源事實 | 不計算。 | 手動輸入。 | 人工備註。 | 無。 | Schedule Service | 無 | 不變 | 無 | 已確認 |
| `created_at` | `TIMESTAMP DEFAULT CURRENT_TIMESTAMP` | 建立時間。 | 來源事實 | DB自動填入。 | DB。 | 系統時間。 | 無。 | Schedule Service | 無 | 不變 | 無 | 已確認 |
| `updated_at` | `TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE ...` | 更新時間。 | 來源事實 | DB自動填入。 | DB。 | 系統時間。 | 無。 | Schedule Service | 無 | 無 | 無 | 已確認 |
