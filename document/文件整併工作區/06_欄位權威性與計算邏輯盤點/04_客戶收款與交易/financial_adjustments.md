# `financial_adjustments` 欄位權威性與計算邏輯盤點（待建）

- 狀態：已確認業務必要性；尚未進入 Schema／API／實作設計。
- 分類：跨 `04_客戶收款與交易` 與 `05_服務人員薪資月結與匯款` 的共用財務調整
- 總索引：[06_欄位權威性與計算邏輯盤點](../../06_欄位權威性與計算邏輯盤點.md)
- Schema：待建；本文件不是 Schema 變更核准。
- 父表關係：僅以 `case_no` → `orders.case_no` 直接歸屬訂單；不重複保存 `client_payment_id`。該案唯一的 `client_payments` 由其 `UNIQUE(case_no)` 關係取得。
- 子表關係：客戶端由 `client_payment_transaction_adjustment_allocations` 將 `stage='adjustment'` 的真實交易分配至本表；月嫂端由 `financial_adjustment_staff_allocations` 連至 `case_staff_assignments`，再投影至 `staff_payments.adjustment_amount`、月結明細與既有轉帳分配流程。

## 已確認的業務規則

- 訂金、頭款、尾款各自獨立核銷；任一期差額必須成為異常，不能與其他期抵銷。
- 當正常分期已核銷後，又出現合法的新客戶應收（例如雙倍日造成的差額），新增一筆調整款，不回寫原三期。
- 本表是跨客戶應收與月嫂應付的共用調整事實；不是客戶專屬調整表。`client_payment_transactions` 只保存實際入款、退款或沖銷，`staff_actual_transfers` 只保存實際月嫂匯款；兩端實際金流均不得取代本表的調整原因與義務。
- `financial_adjustments.id` 是同一調整在客戶端與多筆 assignment 之間的共同關聯鍵。客戶端 `stage='adjustment'` 的交易須透過 M:N 分配明細核銷此調整；月嫂端 `financial_adjustment_staff_allocations` 須以同一調整 ID 指向各 `assignment_id`。
- 一筆客戶真實交易可在同一次原子核銷中結清同案多筆調整，但不允許部分正式核銷。只有交易金額被完整分配，且每一筆被選調整在 Apply 後都恰好歸 0，才能同交易建立正式客戶交易與分配；否則原始銀行事實只留在財務匯入／異常層。不得為分配金額而複製銀行交易列或外部流水號。
- `financial_adjustments` 本身就是不可變的財務調整核准事件，`id` 同時是事件 ID 與兩端共同關聯鍵；不另設重複的通用 `source_event_id`。現有 `order_assignment_change_audits.id` 等 audit ID 只能表示特定業務起因，不能取代本表 ID，也不是所有財務調整都必然具備的來源。
- 本表只保存 `case_no`，不再保存可由一案一筆唯一關係取得的 `client_payment_id`。客戶實際交易仍保留自己的 `client_payment_id`，並另以 `financial_adjustment_id` 指向本表事件。
- 同一案件可有多筆調整款；各筆都應獨立計算應收、實收與未結餘額，不能以案件總額互抵。
- 每筆調整款使用帶正負號的 `amount_delta_ntd`：正值代表客戶須補收，負值代表工會須退款。兩者都在同一張表保存；正值由客戶收款交易核銷，負值由退款交易核銷，不另拆兩套資料表。
- 完整例：原客戶應收及月嫂應付均為 2,100，且兩端已各自收付 2,100；Preview 重算後兩端均應為 4,200，因此建立客戶應收 `+2,100`，同時建立月嫂應付 `+2,100`。客戶補付 2,100、工會再付月嫂 2,100 後，客戶端與月嫂端的未結餘額各自歸 0，工會在此調整的淨額仍為 0。若兩端重算後均應為 1,800，則建立客戶退款 `-300` 與月嫂端反向應付 `-300`，並分別核銷。
- 每次核准變更的 Preview 必須同時顯示並記錄：變更前已確認應收、變更後合法應收、`amount_delta_ntd` 與結算動作（補收／退款／無差額）。超收不是事後手動處理；它是核准變更時就明確產生的負值調整款與退款義務。
- 調整款金額必須由核准 Preview 的新合法應收減去目前已確認的應收義務得出；核准事件須保留 Preview 識別、來源變更命令與差額方向，禁止人工直接輸入調整款金額。
- `amount_delta_ntd` 為唯讀公式輸出，任何人不得直接修改。若業務需要額外改變客戶應收，必須新增獨立的「額外調整」事實／命令；它不是覆寫 `amount_delta_ntd`，而是在核准 Preview 的計算差額之外另行影響帳款。
- 最終待收／待退款效果必須可分解為 `computed_amount_delta + Σ(extra_adjustments)`；每筆額外調整都需保留自己的來源、方向與稽核資訊。
- 本表只持久化真正形成帳務義務的 `amount_delta_ntd`，不另存 `amount_before`、`amount_after` 等可由當次 Preview 計算出的重複總額。Preview 可以顯示變更前／後金額，但核准後不得把這些衍生總額當成下一次計算來源。
- 每筆人工額外調整都必須填寫調整原因；原因是獨立的來源事實與稽核內容，不得以空值、通用預設文字或 `notes` 取代。
- 每筆 `financial_adjustments` 都必須同步建立對應的月嫂應付分配，不能只改客戶應收或只改月嫂應付。無論來源是 Preview 公式重算或人工額外調整，兩端都必須同額同方向，並滿足：`client_amount_delta − SUM(staff_assignment_amount_delta) = 0`；工會不因任何調整收取費用或承擔差額。
- Preview 公式重算時，客戶端 `amount_delta_ntd` 與各 assignment 的月嫂應付差額均由同一次核准 Preview 計算；人工不得直接修改計算結果。人工額外調整則必須填寫原因並在 Preview 中指定 assignment 分配，但同樣受兩端總額相等約束。
- 每筆調整以 `adjustment_source_type` 區分 `preview_recalculation` 與 `manual_extra`。前者金額只能由同一次 Preview 的公式重算結果產生；後者允許人員在 Preview 輸入，但原因必填。反向關係由 `reversal_of_adjustment_id` 表示，不另建立 `reversal` 來源類型。
- `reason` 只對 `manual_extra` 必填；`preview_recalculation` 的來源變更與公式結果已構成原因，不要求人員再輸入說明，避免產生通用或無意義文字。
- 同案多月嫂時，Preview 必須由人員逐筆指定 `assignment_id` 的額外調整分配；所有月嫂端分配加總必須恰好等於客戶端額外調整差額。例：客戶 `+300` 可分配 assignment A `+100`、assignment B `+200`；加總不相等即拒絕核准。不得只以 `staff_id` 分配；已取消的 assignment 不可接受分配。
- 尚未發生任何客戶收款、客戶退款、月嫂付款或月嫂更正金流時，調整內容若需修改，一律取消舊調整並從新 Preview 建立新調整，不得就地改寫。
- 任一端已發生真實金流後，原調整與金流紀錄均不可改寫或刪除；後續修正必須新增反向調整，再依新 Preview 建立正確調整。銀行帳實與所有歷史金流加總必須一致。
- 月嫂端若原 assignment 所屬月結已完整支付，後續新核准的調整不得重開或改寫舊月結；其 `financial_adjustment_staff_allocations` 應形成新的月結義務，歸入該月嫂下一個尚未 finalized 的月結月份。
- 反向調整必須以 `reversal_of_adjustment_id` 指向被修正的原始 `financial_adjustments.id`。此欄追蹤的是「應收／應付義務的修正關係」，不得與客戶或月嫂實際金流各自的 `reversal_of_transaction_id` 混用。
- 例：原調整 `+300` 已在兩端發生金流，後來確認合法差額應為 `+240`，新增 `amount_delta_ntd=-60` 並以 `reversal_of_adjustment_id` 指向原 `+300`；原調整與原金流均保留。
- 不保存 `status` 欄位。調整狀態即時投影為：`cancelled_at IS NOT NULL` → `cancelled`；否則客戶端及全部月嫂分配的未結餘額皆為 0 → `settled`；其餘 → `open`。Preview 不建立資料列，因此不設 `planned` 狀態。
- `cancelled_at` 是取消事實，只能在客戶收款、客戶退款、月嫂付款及月嫂更正金流均未發生時寫入。寫入後調整不得再接受任何交易或分配核銷；已發生任一端真實金流時必須改走反向調整。
- Preview 由人員確認後直接原子 Apply；成功建立 `financial_adjustments` 與完整月嫂 assignment 分配即代表核准並執行，不另設獨立核准階段，也不保存 `approved_by_admin_user_id`／`created_by_admin_user_id`。本裁決只省略調整主表的核准人欄位，不改變金額、原因、兩端同額及完整分配驗證。
- 每次 Preview 產生唯一 `apply_idempotency_key`，同一次 Preview 的所有 Apply 重試必須重用同一鍵。DB 以 UNIQUE 保證第一次成功時建立調整及完整 assignment 分配；網路逾時或 caller 重試時只回傳既有結果，不得再次建立相同義務。此鍵同時識別產生該正式調整的 Preview，不參與金額計算。

## 已確認的最小欄位

| 欄位 | Schema 定義 | 現況架構／用途 | 初步分類 | 現況公式 | 直接來源 | 第一層根事實 | 建議權威公式 | 修改命令／Owner | 重算觸發 | 凍結邊界 | 現況漂移／風險 | 裁決 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `id` | 待建；建議 `BIGINT AUTO_INCREMENT PRIMARY KEY` | 不可變財務調整事件 ID，也是客戶交易與月嫂 assignment 分配的共同關聯鍵。 | 系統鍵／事件識別 | DB 生成。 | 核准 Preview 成功建立財務調整事件。 | 本次已核准的財務調整事實。 | 僅作事件識別與跨表關聯，不參與金額計算；不得另以通用 `source_event_id` 複製同一身分。 | Financial Adjustment Service／DB | 核准調整 | 建立後不可修改 | 若另建通用事件 ID，會形成兩套財務調整身分；若改用特定 audit ID，將無法涵蓋其他調整來源。 | 已確認採用 |
| `case_no` | 待建；建議 `VARCHAR(50) NOT NULL`，FK → `orders.case_no` | 財務調整所屬訂單。 | 關聯鍵 | 不計算。 | 核准 Preview 的訂單身分。 | `orders.case_no`。 | 僅保存此訂單鍵；由 `client_payments.UNIQUE(case_no)` 取得該案唯一客戶帳務摘要，不新增重複的 `client_payment_id`。所有 assignment 分配與客戶交易必須驗證為同案。 | Financial Adjustment Service | 建立調整 | 建立後不可修改 | 若同時保存 `case_no` 與 `client_payment_id`，會重複表達一案一筆關係並產生配對漂移風險。 | 已確認採用 |
| `adjustment_source_type` | 待建；建議 `ENUM('preview_recalculation', 'manual_extra') NOT NULL` | 決定調整金額的合法產生方式與驗證規則，不影響兩端打平公式。 | 來源分類 | 不計算。 | 核准 Preview 的命令類型。 | 公式重算或人工額外調整的業務動作。 | `preview_recalculation` 禁止人工輸入金額；`manual_extra` 允許 Preview 輸入但原因必填。反向調整仍保留自身的來源類型，另以 `reversal_of_adjustment_id` 表示修正關係。 | Financial Adjustment Service | 建立調整 | 建立後不可修改 | 若不區分，人工數字可能被冒充為公式結果，或公式結果被人工覆寫。 | 已確認採用 |
| `amount_delta_ntd` | `BIGINT NOT NULL` 且不得為 0 | 此事件實際新增的客戶應收／退款義務；月嫂端有效 assignment 分配總和必須同額同方向。 | 核准後的不可變帳務義務 | `preview_recalculation` 為新舊合法金額差；`manual_extra` 為 Preview 中核准的人工額外調整額。 | 同一次核准 Preview。 | 訂單與 assignment 的第一層計價事實，或具必填原因的人工額外調整決策。 | 僅保存 `amount_delta_ntd`；正值為客戶補收及月嫂增加應付，負值為客戶退款及月嫂反向應付。不得保存 `amount_before`／`amount_after` 後再拿來計算。 | Financial Adjustment Service | 核准調整 | 建立後不可修改；更正走取消或反向調整 | 若同時持久化變更前、變更後與差額，會產生三份可互相漂移的衍生結果；若允許 0，會建立沒有帳務效果的事件。 | 已確認採用 |
| `reason` | 待建；建議 `VARCHAR(255) NULL` | 人工額外調整的業務理由。 | 條件式來源事實 | 不計算。 | `manual_extra` Preview 的人員輸入。 | 人員核准額外調整的業務決策。 | `adjustment_source_type='manual_extra'` 時 trim 後必須非空；`preview_recalculation` 不要求輸入，建議保存為 `NULL`。不得以通用預設文字或 `notes` 代填。 | Financial Adjustment Service | 建立人工額外調整 | 建立後不可修改；更正走取消或反向調整 | 若所有來源都必填，公式重算會產生無意義文字；若人工調整可空白，則失去稽核原因。 | 已確認採用 |
| `reversal_of_adjustment_id` | 待建，自我 FK，`NULL` 允許 | 反向調整指向被修正的原始財務調整。一般新調整為 `NULL`。 | 稽核／因果關聯 | 不計算。 | 核准反向調整命令。 | 被修正且不可改寫的 `financial_adjustments.id`。 | 僅反向調整可填；必須同一訂單，不得指向自身，也不得用金額、日期或備註推測關係。反向調整本身仍須滿足客戶端金額等於月嫂端 assignment 分配總和。 | Financial Adjustment Service | 建立反向調整 | 建立後不可修改 | 若缺少明確關聯，只能靠同案、同額或時間猜測修正鏈；若與交易沖銷欄位混用，會混淆義務與銀行帳實。 | 已確認採用 |
| `cancelled_at` | 待建；建議 `TIMESTAMP NULL` | 尚未發生任何一端真實金流時，記錄本調整已由新 Preview 取消。 | 取消事實 | 不計算。 | 取消命令成功時間。 | 調整仍無任何客戶／月嫂金流且管理員核准取消。 | 僅在兩端均無金流時可由 `NULL` 寫為取消時間；一旦寫入不得恢復，也不得再接受核銷。`status` 由本欄與兩端餘額投影，不另存。 | Financial Adjustment Service | 取消未核銷調整 | 首次寫入後不可修改 | 若保存 status，會與實際核銷進度漂移；若沒有取消事實，則無法區分尚未核銷與已作廢。 | 已確認採用 |
| `apply_idempotency_key` | 待建；建議 `VARCHAR(191) NOT NULL UNIQUE` | Preview 確認後原子 Apply 的唯一冪等識別，同時指認產生此正式調整的 Preview。 | 不可變技術來源鍵 | Preview 產生一次，所有同次 Apply 重試重用原值。 | 核准前的 Preview。 | 同一次人員確認的調整 Apply 意圖。 | 第一次成功建立調整與完整子分配；相同鍵重試只能回傳既有結果，不得新增第二筆義務。不同 Preview 必須使用不同鍵。 | Financial Adjustment Service | Preview 產生／原子 Apply | 建立後不可修改 | 缺少此鍵時，DB 已成功但前端逾時重試可能重複建立客戶與月嫂兩端調整。 | 已確認採用 |
| `created_at` | 待建；建議 `TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP` | 調整及其完整 assignment 分配成功原子 Apply 的建立時間。 | 稽核／技術事實 | DB 建立時寫入。 | DB 時鐘。 | 正式調整建立事件。 | 保留；沿用已確認技術建立時間規則，不代表獨立核准階段、不記錄核准人，也不參與金額或狀態計算。 | DB／Financial Adjustment Service | 原子 Apply | 建立後不可修改 | 無。 | 已確認：技術建立時間 |

最小欄位集合至此收斂；不新增 `status`、核准人、`amount_before`、`amount_after`、通用 `source_event_id` 或可覆寫備註欄位。本文件仍只是討論提案，不代表 Schema／API／實作核准。
