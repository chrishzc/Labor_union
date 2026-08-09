# `line_rich_menu_publications` 欄位權威性與計算邏輯盤點

- 狀態：討論與裁決用工作清冊；不是 SSOT，不代表 CP-1、Task 或實作核准。
- LINE 功能續盤：跳過待確認；等待 LINE API 接通與實際測試後重新核對。既有明確裁決保留，不視為撤銷。
- 分類：`08_LINE與媒體整合`
- 總索引：[06_欄位權威性與計算邏輯盤點](../../06_欄位權威性與計算邏輯盤點.md)
- 第一遍（live 現況）：已完成
- 第二遍（衍生判定）：跳過待確認（待 LINE 實測）
- 根事實展開：跳過待確認（待 LINE 實測）
- 規格反查：跳過待確認（待 LINE 實測）

- Schema：`db/schema.sql`
- Service：`services/line_rich_menu_service.py`
- 父表關係：`media_assets`、`admin_users`；設定來源為 `config/line_menu.json`。
- 子表關係：成功發布後可能建立 `line_tasks`，把新 Rich Menu 綁定至既有 staff／union_staff 使用者。
- 已確認跨表裁決：本表是 Rich Menu 發布工作與不可變設定快照的合併表；MySQL 為 runtime 發布狀態權威，`config/rich_menu_ids.json` 只是舊程式相容橋接。

| 欄位 | Schema 定義 | 現況架構／用途 | 初步分類 | 現況公式 | 直接來源 | 第一層根事實 | 建議權威公式 | 修改命令／Owner | 重算觸發 | 凍結邊界 | 現況漂移／風險 | 裁決 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `id` | `BIGINT AUTO_INCREMENT PRIMARY KEY` | 發布工作技術主鍵。 | 系統鍵 | 不計算。 | DB 自增。 | 發布請求建立事實。 | 保留作 worker claim、重試與通知 idempotency 定位鍵。 | DB／Rich Menu Service | 建立工作 | 不變 | 無。 | 已確認：SSOT 鍵 |
| `menu_config_id` | `VARCHAR(100) NOT NULL` | 被發布的 Rich Menu 設定 ID。 | 發布命令輸入事實 | 由管理員選定 menu id，Service 在設定檔確認存在且 enabled。 | `config/line_menu.json` 選定項目的 `id`。 | 管理員要求發布哪一個選單。 | 保留；建立工作後不因設定檔後續修改而改變。 | Rich Menu Service | 建立工作 | 建立後不變 | 無實體 FK；設定項目移除後只能靠 snapshot 還原。 | 已確認：保留發布目標設定 ID |
| `audience_role` | `ENUM('customer','staff','union_staff') NOT NULL` | 發布目標角色，供查詢目前選單及成功後派送綁定任務。 | `config_snapshot` 衍生索引／routing 投影（不具獨立權威性） | `audience_role = config_snapshot.audience_role`。 | 被選定 menu 的不可變設定快照。 | `config_snapshot.audience_role`。 | 保留作索引與 routing 投影；只能由 Service 從 snapshot 產生並保證相等，caller 不得分開指定。 | Rich Menu Service | 建立工作 | 建立後不變 | 若與 snapshot 不一致，可能把選單派給錯誤角色。 | 已確認：保留物化投影，來源固定為 snapshot |
| `config_revision` | `CHAR(64) NOT NULL` | 建立發布工作時整份 `line_menus` 設定檔的 SHA-256 revision。 | 整體設定版本 provenance | `SHA256(canonical_json(full line_menus config))`。 | Json Config Service。 | 建立當下整份 Rich Menu 設定內容。 | 保留以追溯工作建立時所屬的整體設定版本；不得作單一 menu 內容比較、去重或發布輸入來源。 | Json Config Service／Rich Menu Service | 建立工作 | 建立後不變 | 其他 menu 改動也會改變 revision，即使本筆 snapshot 完全相同。 | 已確認：保留整體設定版本 provenance |
| `config_snapshot` | `JSON NOT NULL` | 本次實際發布使用的單一 Rich Menu 完整設定快照。 | 不可變命令快照／發布輸入權威 | `menu.model_dump(mode='json')`。 | 建立工作時驗證過的 Rich Menu config。 | 此次送往 LINE 的尺寸、外觀、按鈕與 action。 | 保留為實際發布內容唯一權威；worker 只讀 snapshot，不得在執行時以最新設定替換。 | Rich Menu Service | 建立工作 | 建立後不變 | 若 worker 重讀 live config，排隊期間的設定變更會偷偷改變已核准工作內容。 | 已確認：保留不可變發布快照 |
| `status` | `ENUM('pending','processing','published','failed') NOT NULL DEFAULT 'pending'` | 發布工作的目前狀態。 | 狀態機權威欄位 | pending → processing → published；可重試錯誤回 pending，終止錯誤為 failed；人工 retry 使 failed → pending。 | Rich Menu worker／retry command。 | 發布工作是否待執行、執行中、成功或失敗。 | 所有轉換由 Service 命令執行，並與時間、錯誤、重試欄位原子更新。 | Rich Menu Service／worker | claim、成功、失敗、重試、stale recovery | published 後凍結；failed 可重試 | processing stale recovery 直接回 pending，屬同一工作續跑而非新 publication。 | 已確認：保留發布工作狀態機 |
| `line_rich_menu_id` | `VARCHAR(100) NULL` | LINE API 成功建立後回傳的 Rich Menu ID。 | 外部系統回應事實 | LINE `POST /v2/bot/richmenu` 回應的 `richMenuId`。 | LINE Messaging API。 | LINE 平台實際建立的選單資源。 | 保留；只有發布成功路徑可寫，status=published 時必須存在。 | Rich Menu worker | LINE 建立成功 | published 後不變 | LINE 建立成功但後續圖片／DB 失敗時，清理失敗可能留下平台孤兒資源。 | 已確認：保留 LINE 資源 ID |
| `previous_line_rich_menu_id` | `VARCHAR(100) NULL` | 現況記錄同 `menu_config_id` 發布前的 current Rich Menu ID；依已確認 scope，正確前版應屬同一 `audience_role`。 | 前一版本關聯投影／跳過待確認 | 目標公式：本筆發布成功前，同 audience_role 且 is_current=TRUE 的 `line_rich_menu_id`。 | 前一筆同 audience_role 的 current publication。 | 同角色 publication 成功歷史。 | 需依已確認的 audience_role 版本鏈修正來源；是否仍需持久欄位待 LINE 實測後確認。 | Rich Menu worker | 發布成功 | 寫入後不變 | 現況依 menu_config_id 找前版；角色可編輯時會指到不同角色的舊版本。 | 跳過待確認（待 LINE 實測） |
| `image_asset_id` | `BIGINT NULL`、FK `media_assets.id` | 本次發布實際使用的圖片資產。 | 發布輸入／結果關聯事實 | uploaded 模式建立工作時寫入；generated 模式由 worker 產生資產後補寫。 | config snapshot 或 Media Storage Service。 | 實際上傳至 LINE 的圖片檔。 | published 時必須指向實際使用資產；刪除資產只 SET NULL 會降低歷史可驗證性。 | Rich Menu Service／worker | 建立工作或產圖完成 | published 後不變 | FK ON DELETE SET NULL 允許已發布版本失去圖片關聯。 | 跳過待確認（待 LINE 實測） |
| `requested_by_admin_user_id` | `BIGINT NULL`、FK `admin_users.id` | 建立發布工作的管理員；legacy import 可為 NULL。 | 人工命令 actor 事實 | API 從 authenticated admin principal 寫入。 | Server 驗證管理員身分。 | 誰要求發布此版本。 | 正式新工作必須來自 Server principal；不得由 caller 自填。 | Rich Menu API／Service | 建立工作 | 建立後不變 | NULL 同時代表 legacy import 或無 actor，需依建立來源解讀。 | 跳過待確認（待 LINE 實測） |
| `retry_count` | `INT NOT NULL DEFAULT 0` | 已發生的失敗嘗試次數。 | 可由嘗試事件推導的 worker 控制狀態 | 每次 `_fail_publication` 加一；人工 retry 重設 0。 | worker 失敗結果。 | 實際發布嘗試及其結果。 | 現況沒有獨立 attempt 表，因此暫作重試控制權威；若建立 attempt history 才可改為衍生。 | Rich Menu worker | 每次失敗／人工 retry | 執行中可變 | 人工 retry 清零會失去全生命週期嘗試總數。 | 跳過待確認（待 LINE 實測） |
| `max_retries` | `INT NOT NULL DEFAULT 3` | 此工作可自動重試的上限快照。 | 重試政策輸入快照 | 建立工作時使用 DB default 3。 | Schema default／發布政策。 | 建立當下允許的自動重試次數。 | 保留為每筆工作的政策快照；建立後不變且不得由 UI 任意調高。 | Rich Menu Service | 建立工作 | 建立後不變 | 政策來源只藏在 DB default，程式設定不明確。 | 跳過待確認（待 LINE 實測） |
| `next_retry_at` | `DATETIME NULL` | retryable 失敗後，下次允許 worker claim 的時間。 | worker 排程控制狀態 | `UTC now + min(60 × 2^(retry_count-1), 3600) seconds`。 | retry_count、固定 backoff 公式、Server UTC clock。 | 最近一次 retryable 失敗時點及失敗次數。 | 保留作跨程序 durable scheduler 狀態；pending 且非 NULL 時 worker 必須等到到期。 | Rich Menu worker | retryable failure／claim 成功／人工 retry | 執行中可變 | backoff 公式寫死於 Python，未版本化。 | 跳過待確認（待 LINE 實測） |
| `processing_started_at` | `DATETIME NULL` | 最近一次 processing claim 的開始時間，用於回收卡住工作。 | worker lease 時間 | claim 時 UTC now；超過 10 分鐘仍 processing 則回 pending 並清空。 | Server UTC clock。 | 最近一次 worker claim 成功時點。 | 保留作 durable stale-recovery 控制欄位；不是首次開始時間。 | Rich Menu worker | claim／完成／失敗／stale recovery | 執行中可變 | 固定 10 分鐘 timeout 寫死於 SQL。 | 跳過待確認（待 LINE 實測） |
| `is_current` | `BOOLEAN NOT NULL DEFAULT FALSE` | 每個受眾角色目前實際使用哪一筆成功 publication 的查詢投影。 | audience_role 範圍的 current 物化投影 | 發布成功時先將同 audience_role 的所有 publication 設 FALSE，再將本筆設 TRUE。 | 同 audience_role 的 published publication history。 | 每個實際受眾角色目前應使用哪一筆成功 publication。 | 保留物化 current 投影；唯一範圍是 audience_role。menu_config_id 只識別設定項目，不決定角色目前版本。 | Rich Menu worker | 發布成功 | 後續同角色版本發布時可轉 FALSE | 現況仍依 menu_config_id 清除 current，可能使同角色同時多筆 TRUE。 | 已確認：current scope 為 audience_role |
| `error_code` | `VARCHAR(100) NULL` | 最近一次發布錯誤代碼；成功或人工 retry 時清空。 | 最近錯誤投影 | RichMenuPublishError.code 或 publish_exception；stale recovery 寫 stale_recovered。 | worker／recovery。 | 最近一次未成功執行的錯誤分類。 | 保留供 worker／管理員判讀目前錯誤；不是完整 attempt history。 | Rich Menu worker | failure／retry／success／recovery | 執行中可變 | pending retry 仍保留上次錯誤，語意不是目前 status。 | 跳過待確認（待 LINE 實測） |
| `error_message` | `TEXT NULL` | 最近一次發布錯誤訊息，最多保存 4000 字；成功或人工 retry 時清空。 | 最近錯誤顯示投影 | `str(exception)[:4000]`。 | worker exception。 | 最近一次失敗的技術訊息。 | 僅供診斷與顯示，不作 retryability 或狀態判斷來源。 | Rich Menu worker | failure／retry／success | 執行中可變 | 可能含外部 API 回應內容，需避免敏感資訊。 | 跳過待確認（待 LINE 實測） |
| `created_at` | `DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP` | 發布工作建立時間。 | 技術建立時間 | DB default。 | DB INSERT。 | 工作持久化時點。 | 保留並統一解讀為 UTC。 | DB | 建立工作 | 不變 | DB session timezone 漂移風險。 | 跳過待確認（待 LINE 實測） |
| `started_at` | `DATETIME NULL` | 此工作第一次被 worker claim 的時間。 | 技術首次開始時間 | claim 時 `COALESCE(started_at, UTC_TIMESTAMP())`。 | Server UTC clock。 | 第一次處理嘗試開始時點。 | 保留作等待時間與生命週期追蹤；重試不得重設。 | Rich Menu worker | 首次 claim | 首次寫入後不變 | 與 processing_started_at 名稱相近但語意不同。 | 跳過待確認（待 LINE 實測） |
| `published_at` | `DATETIME NULL` | 發布成功並切換 current 的時間。 | 技術成功時間 | 完成 publication transaction 時 UTC now；legacy import 亦寫入。 | Server UTC clock。 | DB 接受 published 終態及 current 切換的時點。 | status=published 時必須存在，其他狀態為 NULL。 | Rich Menu worker／legacy import | 發布成功 | published 後不變 | 不代表 LINE 使用者已全部完成 rich menu link 任務。 | 跳過待確認（待 LINE 實測） |
| `failed_at` | `DATETIME NULL` | 自動重試耗盡或不可重試而進入 failed 的時間。 | 技術終止失敗時間 | 最終 `_fail_publication` 時 UTC now；人工 retry 清空。 | Server UTC clock。 | 最近一次進入 failed 終態的時點。 | status=failed 時必須存在；人工 retry 回 pending 時清空。 | Rich Menu worker／retry command | 最終失敗／人工 retry | failed 期間保留 | 人工 retry 後失去前一次 failed 時點，非完整歷史。 | 跳過待確認（待 LINE 實測） |
| `updated_at` | `DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP` | 發布工作列最後變動時間。 | 技術更新時間 | DB on-update。 | DB。 | 任一持久欄位最後變動時點。 | 保留作技術排序，不代替狀態專用時間。 | DB | 任一更新 | 持續更新 | 不代表最近一次 worker claim 或外部 LINE 回應時間。 | 跳過待確認（待 LINE 實測） |
