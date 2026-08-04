# `caregiver_availability_locks` 欄位權威性與計算邏輯盤點

- 狀態：討論與裁決用工作清冊；不是 SSOT，不代表 CP-1、Task 或實作核准。
- 分類：`03_媒合指派排班與請假`
- 總索引：[06_欄位權威性與計算邏輯盤點](../../06_欄位權威性與計算邏輯盤點.md)
- 第一遍（live 現況）：已完成
- 第二遍（衍生判定）：已完成
- 根事實展開：已完成
- 規格反查：已完成

- Schema：`db/schema_parts/99a_caregiver_availability_locks.sql`
- 父表關係：`plan_id` → `caregiver_matching_plans.id`
- 子表關係：`caregiver_availability_lock_days` (逐日鎖定明細), `caregiver_availability_lock_events` (生命週期稽核)
- 已確認跨表裁決：本表為「等待訂金階段的配對方案鎖定批次 (Lock Batch Header)」。等待訂金代表雙方已簽約並確認月嫂；訂金逾期只形成帳務／催收異常，不得自動解除檔期。合法終止只來自具權限的「回復未綁定」、取消訂單，或訂金核銷後轉正式 assignment。每個 assignment 預計結束日後 7 天另有獨立 buffer lock facts，並在整案第一個正式服務開始時同交易解除；buffer 不得計入正式服務日、工時或薪資。

| 欄位 | Schema 定義 | 現況架構／用途 | 初步分類 | 現況公式 | 直接來源 | 第一層根事實 | 建議權威公式 | 修改命令／Owner | 重算觸發 | 凍結邊界 | 現況漂移／風險 | 裁決 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `id` | `BIGINT AUTO_INCREMENT PRIMARY KEY` | 鎖定批次的技術主鍵。 | 系統鍵 | 不計算。 | DB 自增。 | 鎖定事實。 | 無。 | Availability Lock Service | 無 | 寫入後凍結 | 無 | 已確認：SSOT 鍵 |
| `plan_id` | `BIGINT NOT NULL` | 對應的媒合方案。 | 關聯鍵 | 不計算。 | 業務請求。 | `caregiver_matching_plans.id`。 | 必須對應有效方案。 | Availability Lock Service | 無 | 不變 | 無 | 已確認 |
| `status` | `ENUM(...) NOT NULL DEFAULT 'active'` | 鎖定批次狀態 (active/released/converted/cancelled)。 | 狀態欄位 | 狀態機推進。 | 受控回復、取消或轉正式命令。 | 已接受的明確業務命令；時間逾期不是狀態事件。 | `active → released` 只由合法回復未綁定；`active → cancelled` 只由訂單取消；`active → converted` 只由訂金核銷後正式轉換。禁止排程依逾期自動釋放。 | Availability Lock Service | 受控命令成功 | 終態凍結 | 舊文件／欄位說明曾把時間逾期列為來源，與已確認簽約保留檔期規則衝突。 | 已確認：無自動逾期釋放 |
| `is_active` | `TINYINT(1) NULL` | 供 Unique Key 使用的鎖定旗標。 | 系統鍵 | active 時為 1，其餘為 NULL。 | 狀態機邏輯。 | `status` 對應。 | `status='active'` 時必為 1。 | Availability Lock Service | 狀態改變 | 終態凍結 | 無 | 已確認 |
| `created_by` | `VARCHAR(100) NOT NULL` | 建立鎖定的管理員。 | 來源事實 | 不計算。 | Session。 | 登入身分。 | 無。 | Availability Lock Service | 無 | 寫入後凍結 | 無 | 已確認 |
| `released_by` | `VARCHAR(100) NULL` | 執行回復未綁定、取消、轉正式或正式服務開始時 buffer 解除命令的操作者／系統命令身分。 | 來源事實 | 不計算。 | 已接受命令的 actor。 | 登入身分或具明確 command／event identity 的後端流程；不得是「逾期排程」。 | `status != 'active'` 時必填且可追溯至合法命令。 | Availability Lock Service | 受控狀態轉移 | 終態凍結 | 若只記「system」且沒有 command/event identity，無法區分轉正式、取消與錯誤自動解鎖。 | 已確認：移除逾期排程來源 |
| `created_at` | `TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP` | 建立時間。 | 來源事實 | DB自動填入。 | DB。 | 系統時間。 | 無。 | Availability Lock Service | 無 | 寫入後凍結 | 無 | 已確認 |
| `released_at` | `TIMESTAMP NULL` | 解除時間。 | 來源事實 | 狀態推進時寫入。 | 系統時間。 | 解鎖事實時間。 | `status != 'active'` 時必填。 | Availability Lock Service | 解除時寫入 | 終態凍結 | 無 | 已確認 |
| `updated_at` | `TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE ...` | 更新時間。 | 來源事實 | DB自動填入。 | DB。 | 系統時間。 | 無。 | Availability Lock Service | 無 | 無 | 無 | 已確認 |
