# `staff_monthly_settlements` 欄位權威性與計算邏輯盤點

- 狀態：討論與裁決用工作清冊；不是 SSOT，不代表 CP-1、Task 或實作核准。
- 分類：`05_服務人員薪資月結與匯款`
- 總索引：[06_欄位權威性與計算邏輯盤點](../../06_欄位權威性與計算邏輯盤點.md)
- 第一遍（live 現況）：已完成
- 第二遍（衍生判定）：已完成
- 根事實展開：已完成
- 規格反查：已完成

- Schema：`db/schema_parts/20_staff_monthly_settlements.sql`
- 父表關係：`staff_id` → `staff.id`
- 子表關係：`staff_monthly_settlement_details`, `staff_actual_transfers`
- 已確認跨表裁決：本表為**一位月嫂、單一薪資月份、單一 revision 的唯一正式薪資核銷 Header**。同一月嫂當月可有多筆不同訂單／assignment，均各自成為 `staff_monthly_settlement_details`，`total_payable` 為全部明細加總。明細只保存金額組成，不是各自獨立的銀行核銷義務；正式匯款 Apply 只需驗證同次所選成功出款的方向淨額恰好等於整張月結 `total_payable`。不得新增部分正式核銷或 `partially_paid`。現況 Schema／Service 仍允許 `partially_paid`，屬已確認實作漂移。
- 已確認跨月更正：已完整支付的月結永不重開。後續才核准的 adjustment 進入該月嫂下一個尚未 finalized 的月份月結，原 paid revision 保持不變。

| 欄位 | Schema 定義 | 現況架構／用途 | 初步分類 | 現況公式 | 直接來源 | 第一層根事實 | 建議權威公式 | 修改命令／Owner | 重算觸發 | 凍結邊界 | 現況漂移／風險 | 裁決 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `id` | `BIGINT AUTO_INCREMENT PRIMARY KEY` | 技術主鍵。 | 系統鍵 | 不計算。 | DB 自增。 | 月結單事實。 | 無。 | Settlement Service | 無 | 不變 | 無 | 已確認：SSOT 鍵 |
| `staff_id` | `INT NOT NULL` | 所屬月嫂。 | 關聯鍵 | 不計算。 | 結算程式代入。 | `staff.id`。 | 無。 | Settlement Service | 無 | 不變 | 無 | 已確認 |
| `settlement_month` | `DATE NOT NULL` | 此月嫂月結所涵蓋的正式發薪月份，固定該月首日。 | 衍生群組鍵／快照識別 | 基本薪資取 `month_start(orders.staff_payment_due_date)`；已付後新 adjustment 取下一個尚未 finalized 月結月份。 | 訂單層正式應付日或後續調整的下一開放月結規則。 | 訂單完成日、客戶付款類型與不可變財務調整事件。 | 不接受 caller 任意指定語意；基本薪資明細須依訂單日期完整收集，後續調整則依下一開放月份收集。不得從 `staff_payments.due_date`、View 或銀行 `occurred_at` 推測。 | Settlement Service | 候選集合重建 | revision 建立後不變 | 現況 API 接受明確月份且未驗證來源；View／staff payment 又存在重複日期。 | 已確認：訂單日期或後續調整規則唯一決定 |
| `revision` | `INT UNSIGNED NOT NULL DEFAULT 1` | 同一月嫂同一月份、在付款前因合法更正而重建的月結版本。 | 系統鍵／版本事實 | 同人同月上一 revision + 1。 | 月結重建命令。 | 尚未付款月結的合法更正。 | 只用於未付款月份的版本化重建；已完整支付的 revision 永不重開或被同月新 revision 取代，後續 adjustment 進下一個未 finalized 月份。 | Settlement Service | finalized 前或未付款 revision 合法更正 | 建立後不變 | 若 paid 後仍以 revision 重開同月，會讓既有銀行分配失去穩定對象。 | 已確認：paid 後不重開 |
| `total_payable` | `DECIMAL(12, 2) NOT NULL DEFAULT 0.00` | 該月嫂本月份所有基本薪資與後續調整義務合計。 | 衍生計算／定稿快照 | `SUM(staff_monthly_settlement_details.payable_amount)`。 | 同一 staff、訂單正式應付月份相同的全部基本 assignment，加上歸入本月的全部後續調整。 | assignment 薪資根事實、訂單正式應付日與不可變財務調整分配。 | 必須等於完整候選集合加總；不得由 caller 挑選、不得以 `staff_payments.due_date` 或 View fallback 混入／漏列。 | Settlement Service | 月結 Preview／重建 revision | finalized 前可重建草稿；finalized 後走新 revision／正式更正 | 現況由 caller 提供 details，Service 未驗證訂單日期或候選集合完整性。 | 已確認：同人同月完整加總 |
| `total_paid` | `DECIMAL(12, 2) NOT NULL DEFAULT 0.00` | 已完整核銷的月結實付摘要。 | 衍生投影 | 同一月結下成功 `staff_actual_transfers` 依交易方向計算淨額。 | 通過整張月結完整歸零驗證的正式銀行轉帳事件。 | `finance_import_rows` 的原始出款事實、月結 `total_payable` 與核銷 Preview。 | 正式 Apply 後必須精確等於 `total_payable`；不符出款留在匯入／異常層，不得形成部分 `total_paid`。不再透過逐訂單／逐元件 allocation 計算。 | Remittance Service | 完整核銷或反向更正 Apply | 正式交易不可改寫；摘要可重建 | 現況 CHECK 允許 `total_paid < total_payable`，且 Service 會寫部分值；另以 `staff_transfer_allocations` 回配明細屬不必要複雜度。 | 已確認：只投影整月完整核銷 |
| `status` | `ENUM(...) NOT NULL DEFAULT 'draft'` | 月結草稿、定稿、覆核、取消及完整付款狀態。 | 工作流狀態 | 由月結命令與完整核銷結果推進。 | 覆核、定稿、取消及完整付款事實。 | 月結 revision 與正式匯款核銷。 | 新流程只允許 `draft`／`review_required`／`finalized`／`paid`／`cancelled`；`paid` 僅在 `total_paid = total_payable` 時成立。`partially_paid` 不得新增，僅供歷史相容並標記長期考慮移除。 | Settlement Service／Remittance Service | 狀態命令或完整核銷 Apply | paid／cancelled 後依正式更正規則處理 | 現況 Schema 與 `staff_actual_transfers.py` 明確允許 `partially_paid`，違反全域歸零規則。 | 已確認：不新增 partially_paid |
| `finalized_at` | `TIMESTAMP NULL` | 定稿時間。 | 來源事實 | 狀態推進時寫入。 | 系統時間。 | 覆核完成事實。 | 無。 | Settlement Service | 無 | 不變 | 無 | 已確認 |
| `created_at` | `TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP` | 本月結 revision 建立時間。 | 稽核／技術事實 | DB 建立時寫入。 | DB 時鐘。 | 月結 revision 建立事件。 | 保留；只用於追查月結 revision 建立時點，不參與薪資月份、應付總額或付款狀態計算，也不能取代月結狀態事件或正式財務稽核。 | DB／Settlement Service | 建立 revision | 建立後不變 | 無。 | 已確認：沿用技術建立時間規則 |
| `updated_at` | `TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP` | 本月結 revision 最後更新時間。 | 稽核／技術投影 | DB 於列更新時覆寫。 | 任一 Header 欄位更新。 | 最近一次資料列異動。 | 保留；可用於除錯與判斷月結投影新鮮度，不參與薪資或付款計算，也不能取代具原因與操作者的不可變事件。 | DB | 任一列更新 | 持續覆寫 | 只能知道最後更新時間，不能說明修改內容或原因。 | 已確認：沿用技術更新時間規則 |
