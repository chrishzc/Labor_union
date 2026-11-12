# Payroll Domain

## 1. 文件邊界與所有權

- 狀態：`current-spec`
- Owner：Payroll Domain（`domains/payroll/`、`subsystems/payroll/`）
- 單一負責範圍：月嫂應付薪資計算公式、費率政策快照、兩段式計價月嫂時薪、樓層費守恆分配、`staff_obligations`／`staff_obligation_events` 寫入、人工金額結果更正模式、`PAYOUT-002` 晚到來源處置，以及服務中換人薪資承接。
- 關聯引用：見 [Global 共同契約](00_Global_共同契約.md)、[Orders Domain](01_Orders_Domain.md)、[Assignments / Scheduling Domain](02_Assignments_Scheduling_Domain.md)、[Client Finance Domain](04_Client_Finance_Domain.md)、[Staff Payables / Export Domain](05_Staff_Payables_Export_Domain.md)、[Staff Payables 與 Client Refund](16_Staff_Payables與Client_Refund正式規格.md)、[案件帳務三方案與補助流向](22A_案件帳務三方案與補助流向正式規格.md)、[帳務差額處置與工作台 UI](22B_帳務差額處置與工作台UI正式規格.md)、[歷史訂單生命週期與服務天數帳務](27_歷史訂單生命週期與服務天數帳務正式規格.md)。

## 2. 核心不變量與資料模型（SSOT）

| 概念 | 唯一權威 |
|---|---|
| 有效 assignment | Scheduling 的非 `cancelled` assignment |
| 正式服務日 | assignment-owned `staff_schedule` 工作日 |
| 每日服務時數 | Orders Terms |
| actual hours | `正式服務日數 × 每日服務時數` |
| 月嫂費率 | 版本化 Payroll Rate Policy 於 assignment 建立時凍結的條款快照 |
| 樓層費 | Orders 條款＋實際服務日 ownership 的整數守恆分配 |
| 調整額 | 不可變 adjustment 及其 assignment allocations |
| 逐 assignment 應付 | `staff_obligations` current projection（不可變來源為 `staff_obligation_events`；`staff_payments` 僅唯讀相容投影） |

### 2.1 核心計價與費率政策

1. **案件總額守恆**：月嫂帳面應付合計等於案件總額 `T`（`服務費 + 樓層費／其他費用`）。工會不抽成、不收取平台手續費；政府補助轉交月嫂包含於 `T` 內，不得額外新增補助薪資或重複應付（三方案關係見 [案件帳務三方案與補助流向](22A_案件帳務三方案與補助流向正式規格.md)）。
2. **基礎身分時薪預設（未綁定個案新兩段政策時）**：
   - 一般市民：`300` 元／小時
   - 補助市民（含低收入戶／中低收入戶）：`350` 元／小時
   - 原住民：`350` 元／小時
   - 非市民：`320` 元／小時（非市民補助內費率／時數／金額為 `0`，全額自費薪資沿用用盡後／自費費率 `320`，零補助時數之 tiered snapshot 基本時薪採用盡後費率，不得將整筆月嫂薪資清零）
   - 雙胞胎案件：`450` 元／小時（優先於身分費率，並由 Case Import 正式胎數事實決定）
3. **補助內與用盡後兩段時薪**：綁定政策或個案人工設定之案件，依 [Client Finance](04_Client_Finance_Domain.md#2-核心不變量與計價規則) 兩段計價契約設定補助內與用盡後月嫂時薪；有補助時數時，補助內月嫂時薪必須等於客戶時薪且為正整數，用盡後可獨立調整。
4. **雙胞胎快照更正與保護**：
   - 既有雙胞胎案件的不可變 Case／assignment 費率快照不得原地覆寫；資料修復僅能由已確認為 `twins / 450` 的 Case 快照補齊缺少的 assignment 快照，來源不符或歧義時阻擋。
   - 服務尚未開始時，管理員以正式 BeClass effective 胎數更正將單胞胎改為雙胞胎時，同一 outer UoW 以 `450` 重算未核銷 Payroll obligation；原已付款事件及快照保持不可變，差額沿既有 adjustment／replacement 表達。正式服務開始後不得變更胎數。
5. **資金來源分期與到期日**：
   - 客戶自費負擔部分預計付款日為「服務結束月 `+ 1` 個月之 15 日」；直接補助轉交部分為「服務結束月 `+ 2` 個月之 15 日」。已形成的 `staff_payment_due_date` 與各期到期日保留，不因方案、取消、更正或政府入款時間而覆寫。
   - 方案一共同確認時（詳 [Staff Payables 與 Client Refund](16_Staff_Payables與Client_Refund正式規格.md#staff-payout-scheme1-and-differences)），Payroll 僅將既有單筆應付 `T` 按正式補助額 `S` 承接缺席的 `T - S`（沿原應付日）與 `S`（服務結束月 `+ 2` 個月之 15 日）來源分期。案件通過服務完成條件後，人工方案確認與銀行明細預檢均優先採 Orders 實際服務結束日，缺值時採訂單結束日，兩者均缺時阻擋新建分期。既有分期、已付款、總額及服務歸屬沿原正式資料。

### 2.2 薪資計算公式與整數守恆

```text
actual_hours     = official_work_day_count × service_hours_per_day
service_salary   = actual_hours × hourly_rate
total_payable    = service_salary + floor_fee_allocated + effective_adjustments
```

- 正式服務日的工時依服務歸屬與適用費率計算，國定假日出勤與其他正式服務日使用相同的工時及費率規則。此計算口徑也適用於改約、取消、代班／換人及應付重建。
- 中途取消案件的樓層費先以 `ROUND_HALF_UP` 計算全案整數，再以最大餘數法按有效 assignment 服務日數分配（同餘數時依 `assignment_id` 升冪決定）。完整履約後取消一律拒絕，不得縮減薪資。
- 正式服務日數、`service_hours_per_day`、hourly rate、樓層費與 adjustment 皆須為整數 NTD。非整數異常輸入須進 [Anomalies Domain](06_Anomalies_Domain.md)，不得在每日或 assignment 層私自四捨五入。
- **一般訂單服務量**：按月嫂歸屬加總正式排班的有效服務工時。
- **歷史已完成訂單基準服務量**。尚無採用的服務量更正時，基準總工時取 HCM 匯入的 `orders.service_days × orders.service_hours_per_day`，以已採納的唯一歷史指派確認月嫂。月嫂時薪先取 `assignment_payroll_rate_snapshots.hourly_rate_ntd`，缺指派快照時取 `case_payroll_rate_policy_snapshots.hourly_rate_ntd`。基準計算直接使用登記服務量。
- **已採用的歷史多人服務量**。有 [歷史服務歸屬更正](27_歷史訂單生命週期與服務天數帳務正式規格.md#historical-service-attribution-correction) 時，以該版本的各人服務量為計薪依據，按各人的可證實費率及本節樓層費規則計算。原登記總量只供基準比較。

## 3. 公開契約與流程

### 3.1 候選月嫂唯讀預估

- 訂單候選預覽顯示月嫂薪資單價、預估總薪資與預計付款日，不共用客戶繳款內容。
- 計算僅唯讀參考 Payroll 政策與 Orders 約定服務量、已知樓層費及預計結束日；明確標示為預估（未含未來調整，來源缺值標待確認），不建立假 assignment、不保存義務、不遞增 Payroll aggregate version。

### 3.2 未核銷重建與已核銷追加（`RebuildPayrollForCase`）

- 依正式指派與服務資料異動自動同步應付；`staff_obligations` 未核銷時依最新根事實重算，已有正式付款歷史時禁止覆寫原 obligation，改追加 immutable adjustment／reversal obligation event。
- 歷史服務完成案件優先承接可證實的原月嫂應付。尚無服務量更正且缺原應付時，具備唯一歷史指派、HCM 登記服務量、費率、採納的歷史結束日及付款來源即可建立基準應付。已採用多人服務量時依 [服務歸屬更正的應付拆分](#service-attribution-payroll-correction) 同步。新建應付或原應付尚未形成付款日時，按歷史結束月份套用 §2.1 付款日政策，依各款項來源形成對應日期。重匯或重新同步使用同一款項身分，保留原應付、已形成日期與付款關聯。缺計算依據或來源有衝突時回報具體缺項，交由原資料 owner 處理。
- `RebuildPayrollForCase` 接受 caller 外層 Unit of Work（鎖定 Terms／assignments／服務日 → 讀取費率與 adjustments → 純計算 Preview → 驗證整數與 ownership → 鎖定 `staff_payments` → 更新投影／追加事件 → 寫 outbox → caller 提交）。
- 涉及大量跨月重算時支援回傳 `202 Accepted` 與 Durable Job，於單一交易內原子完成。
- 案件／月嫂薪資唯讀查詢保留已取消或已結清的 `0` 元紀錄（非負整數）；既有 open 義務 invariant 仍須大於 `0`，且 Query 零寫入。

### 3.3 應付結果人工金額更正模式（`DIFF-RECALC-01`）

- 核查確認系統月嫂應付結果有誤時，可透過 Payroll formal writer 執行人工金額更正（保留原計算、更正前後與操作紀錄；禁止藉此修改 actual hours、服務日、樓層費來源或原費率快照）。
- 款項目前處於 **自動計算** 模式時，來源變動後直接更新金額；處於 **人工更正** 模式時，保留人工值並另列最新系統計算供人員確認。人員選取「採用新計算結果」後，更新為最新系統計算並恢復自動模式（保留原更正審計紀錄），詳細狀態規則見 [帳務差額處置與工作台 UI](22B_帳務差額處置與工作台UI正式規格.md#22-人工金額更正與來源重新計算diff-recalc-01)。
- 同人員一對一未付款來源換代沿 successor 承接模式；拆分或多月嫂接手時不複製單一人工總額。

### 3.4 Assignment Replacement 費率承接

- Scheduling 因 Actual Start 變更日期執行 cancel-old／create-new 時，successor assignment 必須一對一承接 source assignment 不可變 rate snapshot（`policy_version`、`policy_kind`、`hourly_rate_ntd` 與 source identity），位於同一 outer UoW，不修改 case payroll policy 或遞增 Payroll version，亦不得 fallback 回現行 case policy。source snapshot 缺失或歧義時固定回傳 typed blocker 並零寫入。
- 歷史 Precision Restart 首次建立正式安排且原本無 source snapshot 時，於真正建立安排時採用案件已存在之 case payroll policy（不在保存確認日期時提前建立 snapshot）。

### 3.5 服務中換人付款承接（`staff-handover:`）

- 服務中換人於 Scheduling outer UoW 與 sorted staff-account locks 下完成 Preview／Apply：
  - 未付款 projection 可關閉並依新服務事實重建；已付款原 obligation／event／links 保持不可變，以原 obligation 為根追加 `staff-handover:` immutable 差額（等於「新合法 entitlement − (原根＋既有換人差額之 entitlement)」）。
  - 付款家族 ancestry 僅延續同一月嫂；經其他月嫂轉手後再回任視同新付款家族。原 adjustment allocation 只承接給同一來源家族之原受款月嫂一次。
  - 若實際已付超過更新後合法 entitlement，Payroll 先完成 obligation correction，再以唯一 `payroll_correction_identity` 透過 Staff Payables typed port 建立追償義務；若未支援通用路徑或存在跨來源已付衝突，回傳 `payroll_handover_settlement_required` 交人工核對。

<a id="service-attribution-payroll-correction"></a>

#### 3.5.1 服務歸屬更正的應付拆分

- [服務歸屬更正](02_Assignments_Scheduling_Domain.md#multi-caregiver-service-correction) 依正式班次或已採用的各人歷史服務量重算受影響月嫂的有效應付，沿 §2.1、§2.2 採用可證實的費率與服務量，按既有樓層費及付款來源規則分配。原費率快照與付款家族保留來源關聯。歷史同步讀取已採用的多人版本，沿該版本的應付身分重播。
- 無付款歷史的受影響待付列依 §3.2 退出並由新應付承接。有付款歷史時保留原 obligation 與付款關聯，依 §3.5 追加更正差額，按原受款人及付款來源交由 [Staff Payables](16_Staff_Payables與Client_Refund正式規格.md#service-attribution-settlement) 承接。接任或實際服務月嫂的款項獨立建列。
- 原應付曾人工更正時，依 §3.3 顯示原人工值及新試算，經辦確認處置後才提交。單筆人工總額不得複製到拆分後各款。費率、來源或原應付有歧義時回 typed blocker 並指出待核項。

### 3.6 `PAYOUT-002` 晚到義務處置

- 每筆晚到服務／調整來源只能由 Payroll 追加唯一 immutable disposition：`delta > 0` 追加 adjustment obligation，`delta < 0` 追加 reduction／reversal obligation，`delta = 0` 保存 reviewed disposition event。
- `delta < 0` 導致已實付超額時，Payroll 先立合法 correction，再通知 Staff Payables 建立 overpayment recovery；回收本身未實際完成前不阻擋 `PAYOUT-002` disposition 完成。Anomalies 不得越權計算 delta 或寫入 Payroll root。

### 3.7 Typed Ports、Commands、Errors 與 Live Writer 邊界

- **輸入 Ports**：`OfficialServiceFactsPort`、`OrdersTermsPort`、`PayrollTermsPort`、`AdjustmentLedgerPort`。
- **輸出 Ports**：`StaffObligationRepository`、`PayrollImpactPreviewPort`、`PayrollRootFactsOutboxPort`。
- **Commands**：`PreviewPayrollImpactForCase`、`RebuildPayrollForCase`、`QueryCasePayroll`、`QueryStaffPayrollObligations`、`PreviewStaffPayrollAdjustment`、`ApplyStaffPayrollAdjustment`。
- **Stable Errors**：`invalid_payroll_facts`、`official_service_ownership_conflict`、`payroll_rate_policy_not_found`、`non_integer_payroll_input`、`floor_fee_allocation_violation`、`staff_obligation_frozen`、`payroll_candidate_stale`、`payroll_handover_settlement_required`、`idempotency_conflict`、`transaction_failed`。
- **Writer Exit**：`staff_obligations`／`staff_obligation_events`、rate snapshot、floor-fee allocation 與 payroll adjustment 僅限 Payroll persistence adapter 寫入；`services/assignment_payroll_reconciliation_service.py`、`services/multi_caregiver_schedule_*.py`、`services/order_assignment_synchronization.py`、`services/actual_hours_adjustment_confirmation_service.py`、`services/payment_service.py` 與 `services/staff_monthly_settlements.py` 均不得寫入新 Payroll SSOT。

## 4. 驗收標準

- 多月嫂服務歸屬更正按各人服務量、費率、樓層費及付款來源產生應付。人工值經確認處置，拆分後只留下各人合法待付餘額。歷史多人版本重跑薪資同步不重建基準應付或遺失原付款連結。

1. `cancelled`、休假與 buffer 日不計薪；actual-hours 快取與正式日數不符時拒絕使用。
2. 多月嫂同案按各自服務 ownership、凍結費率 獨立計算，合計等於 `T`（`20` 天樓層費 `3,000` 元，中途服務 `5` 天得 `750` 元，再依 `3 / 2` 天按最大餘數法分得 `450 / 300` 元）。
3. 完整履約後取消申請被拒絕且薪資不變；未核銷義務重算更新、已付款義務僅追加差額事件，全部新義務為整數 NTD。
4. 雙胞胎更正、`staff-handover:` 換人差額、兩段時薪與方案一 `T - S`／`S` 分期拆分於同一 UoW 原子成立；0～100 元轉帳手續費由 Staff Payables 核銷結清，不竄改 Payroll 原始義務總額。
5. 歷史服務完成案件具備 §3.2 資料時，從 HCM 登記工時與 Payroll 費率建立可核銷應付，依自費及直接補助來源形成各自付款日，且重匯不重複入帳。無正式班表或人工服務天數紀錄仍可計薪。
