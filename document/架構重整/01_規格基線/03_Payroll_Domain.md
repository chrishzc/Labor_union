# Payroll Domain

## 1. Domain 責任

Payroll 依有效 assignment、正式服務日、Orders Terms、身分費率政策、special-pay 及不可變調整，計算逐 assignment 的整數月嫂應付義務。

Payroll 不建立 assignment、不處理客戶收款、不核銷銀行出款、不產生 Excel，也不接受人工輸入 actual hours、薪資或樓層費結果。

唯一例外是第 `27` 份正式規格的歷史 lifecycle branch：Payroll 可消費 Orders application 已確認、逐
assignment 且具 provenance 的 `actual_service_days` 根事實，依單薪建立義務；仍不得接受人工輸入
actual hours、費率、薪資或樓層費結果，也不得把該天數偽造成正式 `service_dates`。

## 2. SSOT

| 概念 | 唯一權威 |
|---|---|
| 有效 assignment | Scheduling 的非 cancelled assignment |
| 正式服務日 | assignment-owned `staff_schedule` 工作日 |
| 每日服務時數 | Orders Terms |
| actual hours | 正式服務日數 × 每日服務時數 |
| 月嫂費率 | 版本化 Payroll Rate Policy 在 assignment 建立時形成的條款快照 |
| 雙倍薪日 | 明確 special-pay event；不從 Holiday 猜測 |
| 樓層費 | Orders 條款＋實際服務日 ownership 的整數守恆分配 |
| 調整額 | 不可變 adjustment 及其 assignment allocations |
| 逐 assignment 應付 | `staff_obligations` current projection；不可變來源為 `staff_obligation_events`，`staff_payments` 若存在只可作 compatibility read projection |

費率政策：

- 一般市民：300
- 補助市民：350
- 非市民：320
- 雙胞胎案件：450；優先於身分費率，並由 Case Import 的正式胎數事實決定

既有雙胞胎案件的不可變 Case／assignment 費率快照不得原地改寫。保留資料 migration
只可由已確認為 `twins / 450` 的 Case 快照補上缺少的 assignment 快照；既有快照費率
不是 450、Case 快照缺失或胎數來源歧義時，一律阻擋並交人工裁決。
- 低收入戶／中低收入戶先映射為補助市民政策

## 3. Subsystems

### Official Service Facts

篩選有效 assignment、驗證每日唯一 ownership，推導服務日、actual hours、double-pay days／hours。

### Compensation Terms

解析版本化身分費率與 special-pay 條款；UI 不得指定 hourly rate。

### Payroll Calculation

```text
actual_hours = official_work_day_count × service_hours_per_day
double_pay_hours = double_pay_work_day_count × service_hours_per_day
service_salary = (actual_hours + double_pay_hours) × hourly_rate
total_payable = service_salary + floor_fee_allocated + effective_adjustments
```

雙倍日原始工時已包含於 actual hours，再加一次 double-pay hours，結果恰為兩倍。

歷史分支固定 `double_pay_hours = 0`，並允許實際服務天數少於或大於原合約天數；歷史樓層費隨天數
比例增減後再按逐 assignment 天數守恆分配。完整公式、來源、重算與正常流程回歸契約見
`27_歷史訂單生命週期與服務天數帳務正式規格.md` §6、§8。

中途取消的樓層費先以 `ROUND_HALF_UP` 算出全案整數，再以最大餘數法按 assignment 服務日分配。完整履約後取消被拒絕，不套用縮減。

正式服務日數、`service_hours_per_day`、hourly rate、樓層費及 adjustment 都是整數，因此正常薪資公式不會產生小數。新架構不支援分時／半日 ownership 或小數每日時數；若 legacy／外部輸入導致非整數金額，必須先進異常中心由人員確認根事實，不得在每日或 assignment 層自行四捨五入掩蓋資料問題。

### Staff Obligation Projection

未核銷的 `staff_obligations` current projection 可依新根事實重建；已有正式付款歷史時不得覆寫，改追加 immutable adjustment／reversal obligation event。`staff_payments` 若存在只可由這些 canonical obligation 投影為 compatibility read model，不得回寫 Payroll SSOT。

2026-09-11 人工裁決：Payroll 對同一 assignment 只建立一筆 `total_payable` 月嫂應付，不得按「政府補助／雇主自費」資金來源拆成兩筆 obligation 或兩次 payout。非全補助的補助市民訂單由客戶依一般 Client Finance 付款條款先代墊完整服務薪資，服務完成後再退符合資格的補助款；多位月嫂或代班仍各自依其 assignment 與實際服務量形成獨立整筆義務，並非補助分段。

Orders 在第一次形成正式 `actual_end_date` 時，以 `calculate_staff_payment_due_date` 建立唯一 `staff_payment_due_date`。一般案件及非全補助的補助市民訂單為結案後次一曆月 15 日；只有「全補助案件」為結案後第二曆月 15 日。全補助案件必須同時是補助市民、訂單有效正式服務時數不超過 120 小時，且 Client Finance 衍生客戶應付為 0；客戶不需代墊或支付服務薪資。實務申請通常排滿 120 小時，但「剛好 120 小時」不是必要判定條件。補助資格本身、超過 120 小時、或仍有任何客戶應付，都不得套用全補助付款日。原日形成後不因取消、實際服務日更正或晚形成差額自動改到下一個 15 日。非全補助案件的客戶補助退還由 Client Finance 在服務完成後另建 `subsidy_return` 義務，與本 Domain 的月嫂應付完全分離。

### PAYOUT-002 late obligation disposition（2026-08-31 人工裁決）

`PAYOUT-002` 是 Payroll obligation／lineage 完整性，不是 Staff Payables 薪資計算。每筆 late source
只能由 Payroll 追加唯一 immutable disposition：`delta>0` 追加 source-bound adjustment obligation；
`delta<0` 追加 reduction／reversal obligation；`delta=0` 仍保存 reviewed/disposition event，證明已正式
重算且無金額影響。舊 obligation event 永不改寫。

若 `delta<0` 且既有 payout 已使 actual paid 超過修正後合法 amount，Payroll 先完成合法 obligation
correction，再以 exact `payroll_correction_identity` 建立 Staff Payables overpayment recovery；未實際收回
不阻擋 `PAYOUT-002` terminal，後續由 Staff Payables recovery 自己追蹤。完成條件是 late source 已有唯一
正式 disposition/correction、current obligation version、delta consequence 與 fresh owner readback一致；
Anomalies 不得自行計算 delta 或寫 Payroll／Staff Payables root。

## 4. Modules

- `EffectiveAssignmentSelector`
- `OfficialServiceDayOwnershipValidator`
- `ActualHoursCalculator`
- `DoublePayHoursCalculator`
- `IdentityToPayrollPolicyMapper`
- `AssignmentRateResolver`
- `SpecialPayTermValidator`
- `ServiceSalaryCalculator`
- `FloorFeeAllocator`
- `StaffAdjustmentProjector`
- `StaffPayableCalculator`
- `MoneyNTDRoundingPolicy`
- `StaffPaymentProjectionBuilder`
- `FrozenObligationPolicy`
- `DueDateProjection`

## 5. Ports 與交易

輸入 ports：`OfficialServiceFactsPort`、`OrdersTermsPort`、`PayrollTermsPort`、`AdjustmentLedgerPort`。

輸出 ports：`StaffObligationRepository`、`PayrollImpactPreviewPort`、`PayrollRootFactsOutboxPort`。

`RebuildPayrollForCase` 接受外層 Unit of Work，不自行 commit：

```text
鎖 Terms／assignments／service days
→ 讀取費率與 adjustments
→ 純計算 Preview
→ 驗證 hours、ownership、floor-fee、整數金額
→ 鎖 staff_payments
→ 重建未核銷 projection 或追加已核銷後差額義務
→ 寫 outbox
→ caller 統一 commit
```

當 `RebuildPayrollForCase` 涉及大量計算或跨月重算時，API 應支援回傳 `202 Accepted` 並建立 Durable Job 於背景執行。背景 Worker 負責啟動並統一 commit 該 Unit of Work，確保不可核銷、追加義務與 Outbox 在同一交易內完成，遵守原子性不變。

## 6. 驗收

- cancelled／休假／buffer 不計薪。
- actual-hours 快取不符時拒絕，不採快取。
- 多月嫂各依服務 ownership、費率與 special-pay 計算。
- 20 天 3,000 元樓層費、中途服務 5 天得到 750；3／2 天分配為 450／300。
- 完整履約後取消拒絕且薪資不變。
- 未核銷可重算；已付款只追加事件。
- 所有新義務均為整數 NTD。

## 7. Typed Commands／Results／Errors

Commands：

- `PreviewPayrollImpactForCase`
- `RebuildPayrollForCase`
- `QueryCasePayroll`
- `QueryStaffPayrollObligations`
- `PreviewStaffPayrollAdjustment`
- `ApplyStaffPayrollAdjustment`

Results 必須分開回傳逐 assignment 根事實、公式輸入、整數計算結果、未核銷重建、
已核銷後差額義務、blockers、version 與 fingerprint；不得只回總額。

Stable errors：

- `invalid_payroll_facts`
- `official_service_ownership_conflict`
- `payroll_rate_policy_not_found`
- `special_pay_terms_invalid`
- `non_integer_payroll_input`
- `floor_fee_allocation_violation`
- `staff_obligation_frozen`
- `payroll_candidate_stale`
- `idempotency_conflict`
- `transaction_failed`

## 8. Live writer 退出

- `services/assignment_payroll_reconciliation_service.py` 的可證明公式與 reconciliation
  可吸收，但 obligation persistence 必須歸 Payroll。
- `services/multi_caregiver_schedule_adjustment_service.py`、
  `services/multi_caregiver_schedule_generation.py`、
  `services/order_assignment_synchronization.py` 與
  `services/actual_hours_adjustment_confirmation_service.py` 不得再直接寫 actual hours 或薪資。
- `services/payment_service.py` 建立 `staff_payments` 的入口遷移後關閉。
- `services/staff_monthly_settlements.py` 只保留 legacy read-only；不得建立新 Payroll SSOT。
- final writer scan 必須證明 `staff_obligations`／`staff_obligation_events`、rate snapshot、
  floor-fee allocation 與 payroll adjustment 只有 Payroll persistence adapter 可寫；
  `staff_payments` 只允許 compatibility read projection，不得成為新 obligation writer。
