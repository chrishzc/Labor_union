# `order_lifecycle_state_events` 欄位權威性與計算邏輯盤點

- 狀態：討論與裁決用工作清冊；不是 SSOT，不代表 CP-1、Task 或實作核准。
- 分類：`01_客戶與訂單生命週期`
- 總索引：[06_欄位權威性與計算邏輯盤點](../../06_欄位權威性與計算邏輯盤點.md)
- 第一遍（live 現況）：已完成
- 第二遍（衍生判定）：已完成
- 根事實展開：已完成
- 規格反查：待盤點

- Schema：`db/schema_parts/104_order_lifecycle_state_history.sql`
- 父表關係：`case_no` → `orders.case_no`
- 子表關係：`order_lifecycle_projection_outbox.lifecycle_event_id` → `order_lifecycle_state_events.id`

| 欄位 | Schema 定義 | 現況架構／用途 | 初步分類 | 現況公式 | 直接來源 | 第一層根事實 | 建議權威公式 | 修改命令／Owner | 重算觸發 | 凍結邊界 | 現況漂移／風險 | 裁決 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `id` | `BIGINT UNSIGNED NOT NULL AUTO_INCREMENT` | append-only lifecycle decision log 每筆紀錄的技術主鍵。 | 稽核／識別 | DB 自增 | 成功事件 INSERT | DB 接受 persistence 寫入 | DB 生成 | Lifecycle persistence | 每個非 replay decision | 建立後不可修改 | 不參與業務規則、狀態判斷、排班或薪資計算。 | 不列業務裁決（已確認） |
| `case_no` | `VARCHAR(50) NOT NULL COMMENT '事件所屬訂單（對應 orders.case_no）'` | 將狀態決策不可變地關聯至所屬訂單。 | 稽核／關聯 | 不計算 | locked command envelope 的 `case_no`；必須對應既有 `orders.case_no`。 | 原始建案 `case_no` | 原值保存；事件建立後不得變更關聯。 | Lifecycle persistence | lifecycle command | 建立後不可修改 | 必須與 envelope、orders 一致；不得由 client 任意指定不存在或不一致的 case_no。 | 已確認 |
| `trigger_event` | `VARCHAR(100) NOT NULL COMMENT '觸發本次狀態評估的事件名稱'` | 描述本次重評估原因的受控命令類型；不是直接決定狀態的來源。 | 稽核／來源事實 | 不計算 | typed lifecycle command | 被接受的業務事件 | 保存標準事件名稱原值；真正狀態仍由 evaluator 依完整根事實判斷。 | Command-specific Application Service | command acceptance | 建立後不可修改 | 禁止自由文字與 vocabulary 漂移。 | 已確認 |
| `before_status` | `VARCHAR(20) NOT NULL COMMENT '狀態評估前的 canonical 訂單狀態'` | 決策前狀態的衍生稽核快照；不具狀態機權威。 | 衍生稽核快照／待移除 | 同一訂單上一筆事件的 `after_status`；首筆由初始狀態推得。 | 前一筆 lifecycle event 與初始建案狀態 | append-only 狀態事件鏈與初始建案狀態 | 長期考慮移除；目前僅供單筆稽核閱讀與偵測歷史鏈斷裂，不可當作業務判斷或狀態機來源。 | Lifecycle persistence | 前一事件或初始狀態改變時僅理論可推；既有快照不回寫。 | 建立後不可修改 | 舊版直接改 `orders.status` 會使它與事件鏈不一致。 | 已確認：長期考慮移除 |
| `after_status` | `VARCHAR(20) NOT NULL COMMENT '狀態評估後的 canonical 訂單狀態；維持或阻擋時可與 before_status 相同'` | 狀態機決策的不可變結果快照，並作為 `orders.status` 當下投影的依據。 | 不可變快照／領域決策 | lifecycle evaluator 輸出 | canonical facts、control states、business time | 付款事件、實際開始確認、正式工作日、取消／hold commands、業務時間 | 僅由純 evaluator 依根事實運算並保存；不得由前端直接指定；事件建立後不可修改。 | Lifecycle evaluator → persistence | lifecycle command | 建立後不可修改 | production caller 未全數收斂前，事件歷史與 `orders.status` 仍可能漂移。 | 已確認 |
| `actor` | `VARCHAR(255) NOT NULL COMMENT '觸發事件的操作者或系統身分'` | 命令操作者或系統工作者的不可變稽核快照。 | 稽核／來源事實 | 不計算 | 已驗證 principal 或 system worker identity | 認證／排程執行身分 | 僅由伺服器驗證後保存原值；不得信任 client payload 的姓名或帳號。 | Command-specific Application Service | command acceptance | 建立後不可修改 | 身分表示需有受控格式，避免 client spoofing。 | 已確認 |
| `business_date` | `DATE NOT NULL COMMENT '狀態評估採用的業務日期'` | 狀態重算發生日期的非權威稽核投影。 | 衍生稽核快照／待移除 | `created_at` 轉為 `Asia/Taipei` 日期。 | DB 事件建立時刻 | DB transaction commit path 與固定 `Asia/Taipei` 時區 | 長期考慮移除；狀態機直接讀取付款確認日、實際開案日、正式服務日等根事實，非由本欄位決定。 | Repository | INSERT | 建立後不可修改 | 合法補登／回溯命令若需記錄生效業務日，應歸屬於該命令的領域事件，不應使本欄位成為狀態判斷來源。 | 已確認：長期考慮移除 |
| `expected_version` | `BIGINT UNSIGNED NOT NULL COMMENT '呼叫端進行樂觀鎖定時讀取的訂單版本'` | 本次 CAS 基準版本的不可變並行控制稽核快照。 | 不可變快照／並行控制 | locked `orders.lifecycle_version` | request expected version 與 locked row | 已成功 lifecycle commands 的順序 | 僅用於命令受理時的樂觀鎖定與事後稽核；不得用於業務判斷、薪資計算或狀態歷史重建。 | Lifecycle envelope／persistence | command acceptance | 建立後不可修改 | 仍須使所有合法 lifecycle writer 遞增 version；遺留 direct writer 會破壞保護。 | 已確認 |
| `idempotency_key` | `VARCHAR(191) NOT NULL COMMENT '同一訂單內唯一的呼叫端冪等鍵'` | 同案命令去重鍵；使網路重試或 webhook 重送回傳原結果，而不重複建立事件或副作用。 | 來源事實／稽核 | 不計算 | client／integration 產生的穩定 command key | 原始業務操作 identity | 保存 canonical key 原值；同一 `case_no` 內唯一且建立後不可改；不參與業務判斷。 | Command-specific Application Service | 首次 command | 建立後不可修改且同案唯一 | key 粒度不足會誤合併不同命令，故 key 必須代表單一業務操作。 | 已確認 |
| `facts_snapshot` | `JSON NOT NULL COMMENT '狀態評估當下的權威事實與決策摘要'` | evaluator input 與 blockers 的非權威稽核副本。 | 衍生稽核快照／待移除 | canonical serialize evaluator facts／decision | typed facts、control states、status decision | 各 Domain 根事實與被接受命令 | 長期考慮移除；完整事件鏈與根事實可重算結果。暫存時只供稽核，絕不可反向作為目前付款、排班或狀態的權威來源。 | Lifecycle evaluator／persistence | command acceptance | 建立後不可修改 | 若下游反過來以 snapshot 當 current facts，會形成錯誤權威。 | 已確認：長期考慮移除 |
| `created_at` | `TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) COMMENT '事件建立時間'` | DB 成功寫入狀態事件的技術稽核時間與排序資訊。 | 稽核／系統事實 | DB current timestamp | INSERT 時刻 | DB transaction commit path | DB 生成；不得由 client 指定或事後修改。 | Repository | INSERT | 建立後不可修改 | 不等於業務日期、命令生效日或狀態判斷依據。 | 已確認 |
