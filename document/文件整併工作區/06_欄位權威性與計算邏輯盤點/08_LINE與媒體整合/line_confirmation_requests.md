# `line_confirmation_requests` 欄位權威性與計算邏輯盤點

- 狀態：討論與裁決用工作清冊；不是 SSOT，不代表 CP-1、Task 或實作核准。
- LINE 功能續盤：跳過待確認；等待 LINE API 接通與實際測試後重新核對。既有明確裁決保留，不視為撤銷。
- 分類：`08_LINE與媒體整合`
- 總索引：[06_欄位權威性與計算邏輯盤點](../../06_欄位權威性與計算邏輯盤點.md)
- 第一遍（live 現況）：已完成
- 第二遍（衍生判定）：已完成
- 根事實展開：已完成
- 規格反查：已完成

- Schema：`db/schema.sql`、`db/schema_parts/97_line_confirmation_review.sql`
- Writer：`line/line_bot.py`
- Service／API／UI：`services/line_review_service.py`、`api/routes/line_reviews.py`、`ui/components/line_review_manager.py`
- 父表關係：`clients`、`line_users`、`admin_users`
- 子表關係：核准／拒絕通知透過 `line_tasks` 非同步發送。
- 已確認跨表裁決：本表實際承載兩種人工確認流程：月嫂身分認證 `staff_verification`，以及客戶 LINE 帳號重新綁定 `client_rebind`。

| 欄位 | Schema 定義 | 現況架構／用途 | 初步分類 | 現況公式 | 直接來源 | 第一層根事實 | 建議權威公式 | 修改命令／Owner | 重算觸發 | 凍結邊界 | 現況漂移／風險 | 裁決 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `id` | `BIGINT AUTO_INCREMENT PRIMARY KEY` | 確認請求技術主鍵。 | 系統鍵 | 不計算。 | DB 自增。 | 請求建立事實。 | 保留作 Review API、通知 idempotency 與人工操作定位鍵。 | DB／LINE Bot | 建立請求 | 不變 | 無。 | 已確認：SSOT 鍵 |
| `request_type` | `ENUM('staff_verification','client_rebind') NOT NULL` | 確認流程類型：月嫂身分認證或客戶 LINE 重新綁定。 | 流程類型事實 | 由觸發流程固定選擇。 | LINE webhook／客戶綁定流程。 | 使用者觸發的業務動作。 | 只允許兩種受控流程代碼；不得由 Data Browser 任意變更。 | LINE Bot | 建立請求 | 建立後不變 | 類型決定其餘 nullable 欄位的有效組合。 | 已確認：保留審核類型 |
| `line_user_id` | `VARCHAR(100) NOT NULL` | 發起請求的 LINE UID；staff verification 為待認證帳號，client rebind 為申請改綁的新帳號。 | 申請來源事實 | 取 LINE webhook／綁定 API 驗證所得 user id。 | LINE Platform event principal。 | 實際發起請求的 LINE 帳號。 | 保留；不得接受 UI 自填或以顯示名稱替代。 | LINE Bot | 建立請求 | 建立後不變 | client rebind 時與 `new_line_user_id` 值重複。 | 已確認：保留申請人 UID |
| `client_id` | `INT NULL`、FK `clients.id` | client rebind 的目標客戶；staff verification 為 NULL。 | 關聯根事實 | 由姓名／手機查得唯一客戶後寫入。 | `clients.id`。 | 被申請改綁的客戶主檔。 | client rebind 必填且必須存在；staff verification 必須為 NULL。 | LINE Bot | 建立 rebind 請求 | 建立後不變 | Schema 只保證非 NULL 時存在，未保證與 request_type 的組合。 | 已確認：保留客戶 FK |
| `client_name` | `VARCHAR(100) NULL` | client rebind 建立當下複製的客戶姓名，列表與通知目前優先讀取。 | 冗餘客資快照／長期考慮移除 | 現況為 `client_name = clients.name`（建立當下）。 | `clients.name`。 | `clients.name`。 | 不具獨立權威性，依既有客資裁決一律隨 `clients.name` 讀取；停止作顯示與通知來源並長期考慮移除。 | Line Review Query／Presenter（過渡期） | 客戶姓名更正 | 無獨立凍結 | 客戶姓名更正後，本欄、列表與通知仍可能顯示舊姓名。 | 已確認：套用客戶主檔權威規則，長期考慮移除 |
| `old_line_user_id` | `VARCHAR(100) NULL` | client rebind 申請建立時，客戶當下已綁定的舊 LINE UID。 | 命令前置條件快照 | 建立請求時取 `clients.line_user_id`；核准時再次比對目前值。 | `clients.line_user_id`。 | rebind 命令建立時的原綁定關係。 | 保留作 optimistic precondition；若核准時 clients 值已變更則拒絕套用。 | LINE Bot／Line Review Service | 建立 rebind 請求 | 建立後不變 | 若誤與客戶主檔同步，將失去偵測申請後資料漂移的能力。 | 已確認：保留舊 UID |
| `new_line_user_id` | `VARCHAR(100) NULL` | client rebind 要求改綁的新 LINE UID；live writer 與 `line_user_id` 寫入相同值。 | 重複命令輸入／長期考慮移除 | `new_line_user_id = line_user_id`。 | `line_user_id`。 | LINE Platform 驗證所得的申請人 UID。 | 不具獨立權威性，長期考慮移除；核准 rebind 時直接使用 `line_user_id` 作新目標帳號。 | Line Review Service（過渡期） | 建立 rebind 請求 | 建立後不變 | 兩欄若發生不同值，無法判斷哪一個才是申請人要求的新帳號。 | 已確認：重複欄位，長期考慮移除 |
| `status` | `ENUM('pending','approved','rejected','cancelled') NOT NULL DEFAULT 'pending'` | 確認請求目前狀態。 | 狀態機權威欄位 | 新增 pending；管理員核准／拒絕；相同對象重送時取消舊 pending。 | Line Review Service 接收 LINE Bot／Review API 命令。 | 請求是否仍待處理及其最終決策。 | 只允許 pending → approved／rejected／cancelled；終態不可再次處理。取消也必須經 Service 正式轉換，不由 LINE Bot 直接改表。 | Line Review Service | 建立、審核、重送取消 | 終態凍結 | 現況取消路徑由 LINE Bot 直接 UPDATE，繞過統一狀態機 owner。 | 已確認：保留申請狀態，由 Service 統一轉換 |
| `reviewed_by_admin_user_id` | `BIGINT NULL`、FK `admin_users.id` | Web 管理中心核准或拒絕的已驗證管理員。 | 人工決策 actor 事實 | 從 authenticated admin principal 寫入；開發終端舊流程為 NULL。 | `request.state.admin_principal.id`。 | 實際執行 Web 審核的人員。 | 正式人工審核必須使用 Server 驗證 principal；不得由 caller 自填。 | Line Review API／Service | approve／reject | 終態後不變 | 開發終端路徑允許 NULL，會留下無法追溯 actor 的終態。 | 已確認：保留審核員 FK |
| `reviewed_by_line_user_id` | `VARCHAR(100) NULL` | 透過 LINE 執行審核的人員 UID；功能近期將測試，目前尚未接通 API。 | 規劃中人工決策 actor 事實 | LINE 審核成功時寫入 webhook 驗證過的 reviewer UID；目前 caller 尚未接通。 | LINE Platform 驗證所得的 reviewer principal。 | 實際透過 LINE 執行審核的人員。 | 保留供即將接通的 LINE 審核流程使用；不得由 request body 自填，且 reviewer 必須通過管理員身分與權限驗證。 | LINE Review API／Service（待接通） | LINE approve／reject | 終態後不變 | 現況尚未有 live caller；若直接信任請求字串會產生 actor 冒用。 | 已確認：保留，近期接通 LINE 審核 API |
| `decision_reason` | `TEXT NULL` | 核准備註、拒絕原因，或自動取消的固定說明。 | 終態決策說明事實 | 拒絕必填；核准可選；重送取消時由 Service 寫入「新申請 #{new_request_id} 已建立，本請求自動取消」。 | Review UI／API 或重送命令。 | 當次終態決策的人工作業說明，或取代本請求的新 request id。 | 保留；取消不新增欄位，沿用本欄記錄取代原因與新請求 ID；不得作狀態或權限判斷來源。 | Line Review Service | approve／reject／cancel | 終態後不變 | 現況 cancelled 保持 NULL，無法直接追查被哪一筆新申請取代。 | 已確認：取消沿用本欄記錄取代原因 |
| `reviewed_at` | `DATETIME NULL` | 核准或拒絕時間；現況與同一 transaction 寫入的 `resolved_at` 相同。 | 衍生技術時間／長期考慮移除 | `reviewed_at = resolved_at` if status in approved／rejected；其他狀態為 NULL。 | `status`、`resolved_at`。 | 請求進入 approved／rejected 終態的時點。 | 不具獨立權威性，長期考慮移除；查詢核准／拒絕時間直接使用 `resolved_at`。 | Line Review Service（過渡期） | approve／reject | 終態後不變 | 與 `resolved_at` 同時寫入，形成兩份相同答案。 | 已確認：重複衍生欄位，長期考慮移除 |
| `resolved_at` | `DATETIME NULL` | 請求離開 pending 的 Server UTC 時間；核准、拒絕或取消都會寫入。 | 技術終結時間 | 所有終態轉換統一取 Server／DB UTC clock。 | DB Server UTC clock。 | 請求進入終態的時點。 | 所有終態都必須存在；前端不得指定。 | Line Review Service | approve／reject／cancel | 終態後不變 | 現況取消使用 `NOW()`、核准與拒絕使用 `UTC_TIMESTAMP()`；DB session timezone 非 UTC 時會漂移。 | 已確認：保留並統一使用 UTC |
| `created_at` | `DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP` | 請求建立的技術時間，用於待辦排序與逾時提醒。 | 技術建立時間 | DB default。 | DB INSERT。 | 請求持久化時點。 | 保留；統一解讀為 UTC。 | DB／LINE Bot | 建立請求 | 不變 | DB session timezone 若非 UTC，會與 Review Service 的 UTC 邊界比較漂移。 | 已確認：沿用技術建立時間規則 |
| `updated_at` | `DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP` | 請求列最後變動時間。 | 技術更新時間 | DB on-update。 | DB。 | 任一欄位最後變動時點。 | 保留作技術追蹤，不代替 reviewed_at 或 resolved_at。 | DB | 狀態或決策欄位更新 | 持續更新 | 不代表最後一次查看或通知時間。 | 已確認：沿用技術更新時間規則 |
