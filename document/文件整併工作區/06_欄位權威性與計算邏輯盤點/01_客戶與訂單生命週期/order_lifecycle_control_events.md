# `order_lifecycle_control_events` 欄位權威性與計算邏輯盤點

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

| 欄位 | Schema 定義 | 現況架構／用途 | 初步分類 | 現況公式 | 直接來源 | 第一層根事實 | 建議權威公式 | 修改命令／Owner | 重算觸發 | 凍結邊界 | 現況漂移／風險 | 裁決 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `id` | `BIGINT UNSIGNED NOT NULL AUTO_INCREMENT` | append-only 控制命令事件的技術主鍵。 | 稽核／識別 | DB 自增。 | 成功 INSERT。 | DB 接受 control command persistence 寫入。 | DB 生成；不參與控制語意、訂單狀態、排班或薪資計算。 | control command service | INSERT | DB trigger 禁止更新／刪除 | 技術主鍵，不列業務裁決。 | 不列業務裁決（已確認） |
| `case_no` | `VARCHAR(50) NOT NULL` | 將控制命令事件不可變地關聯至訂單。 | 稽核／關聯 | 不計算。 | command envelope 的 locked case_no。 | 已確認不可變的 `orders.case_no`。 | 保存所屬訂單關聯；必須對應既有訂單，不得由 caller 任意指定不存在或不一致的 case_no。 | control command service | 每個控制命令 | DB trigger 禁止更新／刪除 | FK 指向 `orders.case_no`；envelope 必須鎖定同一 aggregate。 | 已確認（沿用 case_no 關聯規則） |
| `control_type` | `ENUM( 'cancellation', 'actual_start_reconfirmation', 'human_hold' ) NOT NULL` | 命令所屬控制機制類型，決定其領域語意。 | 來源事實／受控命令類型 | 由 typed command 正規化；不接受任意字串。 | Cancellation／ActualStartReconfirmation command class；歷史 human hold event。 | 已受理的取消或實際開案重確認命令；既有 human hold 歷史。 | 欄位保留；`human_hold` 控制類型長期考慮移除，不得再新增 UI／API／狀態機依賴。剩餘類型仍不能從 `action` 或自由文字推得。 | control command service | 控制命令受理 | 不可變 | 現況 enum、typed command、API route 與 blocker registry 都含 human_hold，移除需跨層收斂。 | 已確認：human_hold 長期考慮移除 |
| `control_key` | `VARCHAR(100) NOT NULL` | 控制識別；移除 human hold 後，剩餘類型皆為固定值。 | 衍生控制識別／待移除 | cancellation 固定 `order_cancelled`；reconfirmation 固定 `actual_start_reconfirmation`；歷史 human hold 才是 caller 指定。 | 目前由 typed command 正規化。 | 剩餘類型的 `control_type`；既有 human hold 歷史 key。 | 長期考慮移除：新增資料僅由 `control_type` 推得固定 key，不再接受自訂 key。保留舊欄位僅供歷史讀取，移除前遷移 current-state identity。 | control command service | 控制命令受理 | 不可變 | 先前以多個 human hold 為保留理由已失效；現況與 control_type 重複。 | 已確認：隨 human_hold 長期考慮移除 |
| `scope` | `ENUM('order', 'enter_service', 'auto_complete') NOT NULL` | 控制命令影響的生命周期範圍；移除 human hold 後，剩餘類型皆為固定範圍。 | 衍生控制設定／待移除 | cancellation 固定 `order`；reconfirmation 固定 `enter_service`；歷史 human hold 才可為 `enter_service`／`auto_complete`。 | 目前由 typed command 正規化。 | 剩餘類型的 `control_type`；既有 human hold 歷史 scope。 | 長期考慮移除：新增資料由 `control_type` 推得固定 scope，不再接受 human hold scope。保留舊欄位僅供歷史讀取，移除前遷移 current-state。 | control command service | 控制命令受理 | 不可變 | 先前把它視為 human hold 來源事實的判斷已撤回；對剩餘類型屬重複欄位。 | 已確認：隨 human_hold 長期考慮移除 |
| `action` | `ENUM('activate', 'clear') NOT NULL` | 本次對控制狀態的不可變命令。 | 來源事實／受控命令 | activate → state active；clear → state cleared。 | typed command。 | 已受理的啟用或解除控制命令。 | 必須保存：current-state 無法取代完整啟用／解除歷史。需符合目前投影狀態，不能 clear 未 active 的控制。 | control command service | 控制命令受理 | 不可變 | 若允許直接改 current-state，會失去命令稽核與狀態機重新評估依據。 | 已確認 |
| `actor` | `VARCHAR(100) NOT NULL` | 下達控制命令的操作者或系統工作者不可變稽核快照。 | 稽核／來源事實 | 不計算。 | 已驗證 principal 或 system worker identity。 | 認證／排程執行身分。 | 僅由伺服器驗證後保存原值；不得信任 client payload 的姓名或帳號。 | control command service | 控制命令受理 | 不可變 | 仍需核對所有 API caller 均從 authenticated principal 填入。 | 已確認（沿用 actor 規則） |
| `reason` | `VARCHAR(500) NOT NULL` | 控制命令的原始文字理由與 current-state 顯示原因。 | 來源事實／稽核 | 不計算；trim 後非空。 | 取消或實際開案重確認 typed command 的 reason。 | 已受理命令時的人工理由。 | 保留：取消時為 `orders.cancel_reason` 的來源；實際開案重確認現行 UI 亦輸入理由。既有 event 不可改；更正應新增合法命令。 | control command service | 控制命令受理 | 不可變 | human_hold 不再構成保留理由；自由文字不適合當作固定類型分析鍵。 | 已確認：先保留 |
| `expected_version` | `BIGINT UNSIGNED NOT NULL` | 控制命令 CAS 的命令端版本基準。 | 不可變快照／並行控制 | 必須等於 command envelope request version，首次處理時等於 locked aggregate lifecycle version。 | command envelope／typed command。 | 已成功 lifecycle commands 的順序。 | 僅用於命令受理時的樂觀鎖定與事後稽核；不得用於業務判斷、薪資計算或狀態歷史重建。 | control command service | 控制命令受理 | 不可變 | replay 時允許 aggregate 已前進一版且需有對應 lifecycle event；遺留 direct writer 會破壞保護。 | 已確認（沿用 expected_version 規則） |
| `idempotency_key` | `VARCHAR(191) NOT NULL` | 同案控制命令重送去重鍵。 | 來源事實／稽核 | 不計算；同 `case_no` 唯一。 | command envelope／typed command。 | 原始業務操作 identity。 | 保存 canonical key 原值；同一 `case_no` 內唯一且建立後不可改；不參與業務判斷。 | control command service | 首次命令 | 不可變 | replay 會驗證事件所有欄位與 payload hash 完全一致；key 粒度不足會誤合併不同命令。 | 已確認（沿用 idempotency_key 規則） |
| `payload_hash` | `CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL` | 命令 payload 的衍生 SHA-256 重播檢查值。 | 衍生完整性檢查／待移除 | SHA-256(canonical UTF-8 `payload_snapshot`)。 | control command service。 | `payload_snapshot` 的 canonical JSON；其根源為已受理控制命令的專屬資料。 | 長期考慮移除；非安全簽章、非業務來源。重播直接比較 canonical payload 即可驗證完全一致。 | control command service | 控制命令受理 | 不可變 | 能改 DB 者可連 payload 與 hash 一起改；目前只提供重複檢查。 | 已確認：長期考慮移除 |
| `payload_snapshot` | `JSON NOT NULL` | 混合式命令／重播副本：取消為 `{}`；開案重確認混放舊／新日期、訂金識別、Preview 雜湊與套用收據；歷史 human hold 有期限資料。 | 衍生稽核快照／待移除 | canonical JSON object。 | typed command 正規化。 | 訂單實際開始日、付款／訂金事實、assignment／正式工作日與控制事件等各自的權威資料。 | 長期考慮移除。不得成為目前事實來源；重播改以不可變命令事件與各權威資料的關聯驗證，不再保存混合 JSON。 | control command service | 控制命令受理 | 不可變 | 現況把多種概念塞入 JSON，且未逐類 schema 約束，易被誤作來源。 | 已確認：長期考慮移除 |
| `created_at` | `TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)` | DB 寫入不可變控制命令事件的技術時間；同交易複製為 current-state changed_at。 | 稽核／系統事實 | DB current timestamp。 | INSERT。 | DB transaction commit path。 | 僅用於稽核與事件排序；不得由 caller 指定或修改，不等於取消生效日、實際開始日或其他業務日期。 | Repository | INSERT | 不可變 | 不得拿來推導 lifecycle decision。 | 已確認 |
