# `order_lifecycle_control_state` 欄位權威性與計算邏輯盤點

- 狀態：討論與裁決用工作清冊；不是 SSOT，不代表 CP-1、Task 或實作核准。
- 分類：`01_客戶與訂單生命週期`
- 總索引：[06_欄位權威性與計算邏輯盤點](../../06_欄位權威性與計算邏輯盤點.md)
- 第一遍（live 現況）：已完成
- 第二遍（衍生判定）：已完成
- 根事實展開：已完成
- 規格反查：待盤點

- Schema：`db/schema_parts/106_order_lifecycle_control_facts.sql`
- 父表關係：`case_no` → `orders.case_no`
- 子表關係：無已宣告子表
- 已確認跨表裁決：`human_hold` 控制類型長期考慮移除；本表保留既有 human hold 投影僅供歷史讀取，不得新增 UI／API／狀態機依賴。

| 欄位 | Schema 定義 | 現況架構／用途 | 初步分類 | 現況公式 | 直接來源 | 第一層根事實 | 建議權威公式 | 修改命令／Owner | 重算觸發 | 凍結邊界 | 現況漂移／風險 | 裁決 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `case_no` | `VARCHAR(50) NOT NULL` | current-state 投影所屬訂單；與 type／key 組成主鍵。 | 稽核／關聯投影 | 不計算。 | 同交易 control event 的 `case_no`。 | 已確認不可變的 `orders.case_no`。 | 保存目前控制投影所屬訂單；不得獨立寫入，必須與 `current_event_id` 所屬事件同案。 | control command service | 首次控制命令 | current projection 可覆寫；主鍵不可改 | FK 指向 orders；仍需 service 保證與 event 同案。 | 已確認（沿用 case_no 關聯規則） |
| `control_type` | `ENUM( 'cancellation', 'actual_start_reconfirmation', 'human_hold' ) NOT NULL` | current-state 投影的控制類型。 | 衍生控制識別 | 取最新 control event 的 type。 | 同交易 control event。 | 最新不可變 control event 的 `control_type`。 | 不得獨立寫入；隨事件投影。`human_hold` 長期考慮移除，既有投影僅供歷史讀取。 | control command service | 每次同 identity 控制命令 | current projection 可覆寫 | 現況 enum／投影仍含 human_hold，移除需與歷史資料相容。 | 已確認（沿用 human_hold 裁決） |
| `control_key` | `VARCHAR(100) NOT NULL` | current-state 投影的控制識別；與 type 組成主鍵。 | 衍生控制識別／待移除 | 取最新 control event 的 key。 | 同交易 control event。 | 最新不可變 control event 的 `control_key`；移除 human hold 後可由 type 推得。 | 長期考慮移除；不得獨立寫入。保留歷史 human hold key 前，需先遷移 current-state identity。 | control command service | 每次同 identity 控制命令 | current projection 可覆寫 | 與 control type 重複的原因已隨 human_hold 移除裁決失效。 | 已確認（沿用 control_key 裁決） |
| `scope` | `ENUM('order', 'enter_service', 'auto_complete') NOT NULL` | current-state 控制影響範圍。 | 衍生控制設定／待移除 | 取最新 control event 的 scope。 | 同交易 control event。 | 最新不可變 control event 的 `scope`；移除 human hold 後可由 type 推得。 | 長期考慮移除；不得獨立寫入。保留歷史 human hold scope 前，需先遷移 current-state。 | control command service | 每次同 identity 控制命令 | current projection 可覆寫 | 對剩餘控制類型為重複欄位。 | 已確認（沿用 scope 裁決） |
| `state` | `ENUM('active', 'cleared') NOT NULL` | 該控制 identity 的目前結果，供 lifecycle facts／Calendar read 使用。 | 衍生投影／待移除 | 最新 action `activate` → active；`clear` → cleared。 | `current_event_id` 指向的最新同 identity control event 的 `action`。 | 最新不可變 control event 的 action。 | 長期考慮移除：既然保留 `current_event_id` 且複合 FK 保證 identity 一致，讀取時由 action 推得；不可作獨立業務來源。 | control command service | 每次同 identity 控制命令 | current projection 可覆寫 | 目前僅為查詢／索引便利而重複保存；完整歷史在 control events。 | 已確認：長期考慮移除 |
| `current_event_id` | `BIGINT UNSIGNED NOT NULL` | 指向產生目前投影的最新 control event。 | 衍生關聯投影 | 最新同 identity event 的 id。 | control command INSERT `lastrowid`。 | 最新不可變 control event。 | 必須保留為 current-state 到完整命令歷史的關聯；不得被 caller 指定。其 event 必須與同列 case/type/key 完全一致。 | control command service | 每次同 identity 控制命令 | current projection 可覆寫 | 複合 FK 強制 event identity 一致；讀取端以它 JOIN event payload 驗證／讀取 actual-start 事實。 | 已確認（技術關聯） |
| `release_policy` | `ENUM('manual', 'expires_at') NULL` | human hold 的解除政策投影。 | 衍生投影／待移除 | human hold activate 時取 payload；其餘／release 為 NULL。 | 歷史 human hold control event／payload。 | 已受理 human hold 命令的解除政策。 | 隨 `human_hold` 長期考慮移除；既有資料僅供歷史讀取，不得新增 UI／API／狀態機依賴。 | control command service | 歷史 human hold 命令 | current projection 可覆寫 | 對保留的取消與開案重確認控制永遠無值。 | 已確認（沿用 human_hold 裁決） |
| `expires_at_utc` | `DATETIME(6) NULL` | human hold 的自動解除 UTC 時刻投影。 | 衍生投影／待移除 | human hold `expires_at` policy 時取 payload；其餘為 NULL。 | 歷史 human hold control event／payload。 | 已受理 human hold 命令的到期時刻。 | 隨 `human_hold` 長期考慮移除；既有資料僅供歷史讀取，不得新增 UI／API／狀態機依賴。 | control command service | 歷史 human hold 命令 | current projection 可覆寫 | 對保留的取消與開案重確認控制永遠無值。 | 已確認（沿用 human_hold 裁決） |
| `confirmed_start_date` | `DATE NULL` | actual-start reconfirmation clear 後保存新確認日期。 | 衍生投影／待移除 | clear 時取 normalized command `new_actual_start_date`；active 為 NULL。 | `orders.actual_start_date`／同交易 control event payload。 | 已確認的 `orders.actual_start_date`；control event 只保留歷史 receipt。 | 長期考慮移除：目前實際開始日只以 `orders.actual_start_date` 為權威。不可成為獨立來源或覆寫訂單日期。 | control command service | 開案重確認 clear | current projection 可覆寫 | 現況與 orders 及 event payload 三重重複；Calendar read loader 未使用本欄位。 | 已確認：長期考慮移除 |
| `deposit_settlement_identity_hash` | `CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NULL` | actual-start reconfirmation clear 後保存當次有效訂金結算識別。 | 衍生稽核投影／待移除 | clear 時取 normalized command 的 settlement identity；active 為 NULL。 | 同交易 control event payload。 | 目前有效訂金由 client payment 與 immutable payment transaction 根事實聚合；event payload 只留歷史 receipt。 | 長期考慮移除：不得用此欄判斷目前訂金有效性；讀取端直接聚合付款領域事實。 | control command service | 開案重確認 clear | current projection 可覆寫 | 與 event payload 重複，Calendar read loader 未使用本欄位。 | 已確認：長期考慮移除 |
| `reason` | `VARCHAR(500) NOT NULL` | 目前控制命令理由的重複投影。 | 衍生投影／待移除 | `current_event_id` 指向事件的 `reason`。 | 同交易 control event。 | 最新不可變 control event 的 `reason`；其根源為已受理取消或實際開案重確認命令的人工理由。 | 長期考慮移除：讀取 current view 時由 `current_event_id` JOIN 事件取得；不可成為獨立或可漂移來源。 | control command service | 每次同 identity 控制命令 | current projection 可覆寫 | 目前只為便利顯示而重複保存。 | 已確認：長期考慮移除 |
| `changed_by` | `VARCHAR(100) NOT NULL` | 最近一次改變控制的操作者重複投影。 | 衍生投影／待移除 | `current_event_id` 指向事件的 `actor`。 | 同交易 control event。 | 最新不可變 control event 的 `actor`；其根源為伺服器驗證的 principal／system worker identity。 | 長期考慮移除：讀取 current view 時由 `current_event_id` JOIN 事件取得；不可成為獨立或可漂移來源。 | control command service | 每次同 identity 控制命令 | current projection 可覆寫 | 目前只為便利顯示而重複保存。 | 已確認：長期考慮移除 |
| `changed_at` | `TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)` | 最近一次改變控制的時間重複投影。 | 衍生投影／待移除 | `current_event_id` 指向事件的 `created_at`。 | 同交易 control event。 | 最新不可變 control event 的 DB `created_at`。 | 長期考慮移除：讀取 current view 時由 `current_event_id` JOIN 事件取得；不可成為業務日期、狀態判斷或獨立時間來源。 | control command service | 每次同 identity 控制命令 | current projection 可覆寫 | DB default 與 event created_at 雙重時間來源，實際 INSERT SELECT 取 event time。 | 已確認：長期考慮移除 |
