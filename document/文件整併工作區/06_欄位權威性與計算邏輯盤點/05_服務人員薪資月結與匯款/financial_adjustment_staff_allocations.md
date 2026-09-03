# `financial_adjustment_staff_allocations` 欄位權威性與計算邏輯盤點（待建）

- 狀態：已確認業務必要性；尚未進入 Schema／API／實作設計。
- 分類：`05_服務人員薪資月結與匯款`
- 總索引：[06_欄位權威性與計算邏輯盤點](../../06_欄位權威性與計算邏輯盤點.md)
- Schema：待建；本文件不是 Schema 變更核准。
- 父表關係：`financial_adjustment_id` → `financial_adjustments.id`；`assignment_id` → `case_staff_assignments.id`
- 子表關係：本表加總投影至 `staff_payments.adjustment_amount`，並可作為後續 `staff_monthly_settlement_details` 的來源；實際月嫂匯款只核銷整張月結，不直接指向本表。

## 已確認的業務規則

- 本表不是實際匯款表，而是共用財務調整在月嫂應付端的 assignment 級義務分配。
- 同一筆 `financial_adjustments` 可分配給多筆 assignment；不得只以 `staff_id` 分配，因為應付、服務日期與後續月結都以 assignment 為界。
- 同一共用調整的所有有效 assignment 分配加總必須恰好等於客戶端 `financial_adjustments.amount_delta_ntd`；不相等即拒絕核准。此規則適用 Preview 公式重算、人工額外調整與反向調整，確保每筆調整的工會淨額固定為 0。
- 已取消的 assignment 不可新增分配。原 assignment 後續因排班重建而取消時，未核銷調整應隨新 Preview 取消舊分配並建立對應新分配；已發生真實金流時不得改寫舊資料，必須走反向調整。
- `staff_payments.adjustment_amount` 只可由本表針對同一 `assignment_id` 的有效分配加總投影，不再是人工直接輸入的來源事實。
- 本表只負責說明共用財務調整如何歸入各 assignment、並進一步形成月結金額；它不是獨立銀行核銷義務。當包含此分配的有效月結已完整支付時，該調整即隨整張月結完成；不另建匯款至本表的 allocation，也不保存部分已付／追回中間狀態。
- 若原 assignment 的基礎薪資月結已完整支付，本表後續新核准的調整不得投影回舊月結或改寫其 `staff_payment` 快照；它必須作為新的月結義務進入該月嫂下一個尚未 finalized 的月份月結。
- 本表不建立自己的 `status`、`cancelled_at` 或 `reversal_of_allocation_id`。尚未發生金流時，取消父 `financial_adjustments` 即使其全部子分配失效，再由新 Preview 建立新父調整與完整分配；已發生金流後，以新的父反向調整及同額反向 assignment 分配保留歷史。不得只取消或反向部分子分配而讓父調整仍有效。
- 最小欄位集合固定為：`id`、`financial_adjustment_id`、`assignment_id`、`amount_delta_ntd`、`created_at`。同一父調整對同一 assignment 應先在 Preview 合併為一筆分配，避免以多列重複表達相同義務。

## 已確認的最小欄位

| 欄位 | Schema 定義 | 現況架構／用途 | 初步分類 | 現況公式 | 直接來源 | 第一層根事實 | 建議權威公式 | 修改命令／Owner | 重算觸發 | 凍結邊界 | 現況漂移／風險 | 裁決 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `id` | 待建；建議 `BIGINT AUTO_INCREMENT PRIMARY KEY` | 分配列技術主鍵。 | 系統鍵 | DB 生成。 | 成功建立分配列。 | 核准後持久化的分配事實。 | 保留；僅供識別與關聯，不參與金額計算。 | Financial Adjustment Service／DB | 建立分配 | 建立後不變 | 無現況欄位。 | 已確認：最小子表技術鍵 |
| `financial_adjustment_id` | 待建 | 所屬共用財務調整。 | 關聯鍵 | 不計算。 | 同次核准的調整父表。 | `financial_adjustments.id`。 | 必須存在且與 assignment 屬同一訂單。 | Financial Adjustment Service | 建立分配 | 建立後不變 | 若沒有此鍵，客戶與月嫂兩端只能靠案件或金額猜測關聯。 | 已確認：共同調整鍵 |
| `assignment_id` | 待建 | 接受此應付調整的正式指派。 | 關聯鍵 | 不計算。 | Preview 中逐筆指定。 | `case_staff_assignments.id`。 | 必須與父調整同案，且建立時不得為 cancelled。 | Financial Adjustment Service | 建立分配 | 建立後不變；更正走取消／反向調整 | 僅存 `staff_id` 無法維持排班、薪資與月結血緣。 | 已確認：以 assignment 分配 |
| `amount_delta_ntd` | `BIGINT NOT NULL` | 此 assignment 應付增加或減少的帶符號整數元金額。 | 核准後不可變義務 | Preview 公式重算時由該 assignment 新舊合法應付差額產生；人工額外調整時由人員在 Preview 指定。 | 同一次核准 Preview。 | 新舊 assignment 薪資根事實，或有必填原因的人工分配決策。 | 同一父調整的全部分配總和必須等於 `financial_adjustments.amount_delta_ntd`；人工不得繞過 Preview 直接改值。子分配建立後不可單獨取消或反向。 | Financial Adjustment Service | 核准調整 | 建立後不變；更正跟隨父取消或父反向調整 | 若只保存 `staff_payments.adjustment_amount`，原因與分配歷史會消失；若允許子分配單獨變更，會破壞兩端同額。 | 已確認：所有調整同額分配、摘要唯讀 |
| `created_at` | 待建；建議 `TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP` | 分配列建立時間。 | 稽核／技術事實 | DB 建立時寫入。 | DB 時鐘。 | 分配建立事件。 | 保留；沿用已確認技術建立時間規則，不參與調整金額、有效性或月結計算。 | DB／Financial Adjustment Service | 建立分配 | 建立後不變 | 不能取代父調整的核准與因果事件。 | 已確認：技術建立時間 |

現況結構缺口：`staff_monthly_settlement_details.staff_payment_id` 為必填，且同一 `staff_payment` 不得進入另一張未取消月結；因此已付 assignment 的後續調整目前沒有合法的新月份月結來源關聯。

已確認不再增加子表狀態、取消、反向或獨立付款欄位；本文件仍只是討論提案，不代表 Schema／API／實作核准。
