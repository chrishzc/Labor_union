# Payroll Domain

> 2026-11-05 對帳單支出匯款手續費補充：Payroll 計算之月嫂帳面應付總額維持等於案件總額 `T`（工會不抽成、不賺取平台手續費）；公會實際匯出月嫂薪資時，跨行轉帳內扣 100 元以內之銀行手續費由月嫂負擔（同行免手續費為 0 元），由 Staff Payables 依 [`22` §15.6.4](22_銀行流水匯入與帳務異常處理正式規格.md#outgoing-statement-fee-reconciliation-20261105) 與 [`16` §2.4.1](16_Staff_Payables與Client_Refund正式規格.md) 按「實付＋匯款手續費（0～100）＝應付」直接核銷結清，不修改 Payroll 原始薪資義務金額。

> 2026-11-05 全額補助最新裁決：依 [`22` §17.4.1](22_銀行流水匯入與帳務異常處理正式規格.md#full-subsidy-no-advance-20261105)，補助市民／原住民且正式服務總時數≤本案有效補助上限時，自動免自備、方案一、補助轉交月嫂；不固定120／80，不增加第二份薪資。這是原不由身分／時數判方案的一項明定例外；既有正式金額、付款與日期保留，舊模型衝突不由Excel重算。本次只修改規格。

> 2026-11-03 案件金額與補助流向最新裁決：依 [`22` §17](22_銀行流水匯入與帳務異常處理正式規格.md#case-accounting-schemes-20261103)，月嫂應收合計＝案件總額＝服務費＋樓層費／其他費用；工會不抽成、不收手續費。補助轉交月嫂包含在案件總額內，不新增補助薪資或重複應付；永豐與台新實付由 Staff Payables 分別核銷後合計。除規格22 §17.4.1明定的全額補助免自備例外外，客戶身分不再直接決定三種收付款方案，舊全補助／先墊分支及客戶、月嫂費率差不得反向定義新模型。原 assignment 服務歸屬、正式調整、付款證據與快照保留；本次只修規格，不改薪資程式、費率資料、付款日期或既有金額，新模型的計價銜接仍待後續實作收斂。

> 2026-11-02 差額認列、人工金額更正與政府整期差額的最新實作／驗證見 [規格22 §16.9.1](22_銀行流水匯入與帳務異常處理正式規格.md#accounting-differences-implementation-20261102)。本檔 2026-11-01 的「尚未實作／本次僅規格」為當時記錄，以該續作結果為目前狀態；bank／ledger／allocation 的不可變性與各 owner 歸屬不變。

2026-10-29 補助防護補充：依規格 04 最新人工裁決，補助內月嫂時薪須等於客戶時薪，用盡後可獨立調整；非市民補助內費率／時數／金額為 0，但自費薪資沿用用盡後費率。零補助時數的 tiered snapshot 基本時薪採用盡後費率；不得將整筆月嫂薪資清零。有補助時數時補助內時薪仍須為正整數，原服務歸屬、雙倍日、實付及金流守恆不變。

> 2026-10-29 最新裁決：新政策綁定／個案人工設定案件依規格 04 §0 PRICE-03～08 採補助內與用盡後兩段月嫂時薪；允許按付款來源分期，客戶負擔部分為服務結束月+1、直接補助部分為+2，均為15日。此範圍取代下述固定費率、全補助分類及單一給付日限制；原始快照／實付不可變，未綁定既有案保留原資料。\n


<a id="payroll-amount-correction-20261101"></a>

## 0. 人員應付結果的人工更正（2026-11-01 核准；尚未實作）

依 [`22` §16](22_銀行流水匯入與帳務異常處理正式規格.md#finance-differences-20261101)，核查確認系統月嫂應付結果有誤後，需支持手動更正。Payroll 仍擁有金額及逐 assignment 歸屬，透過原 owner writer 保留原計算、更正前後及操作紀錄；Staff Payables 消費更正後有效義務及原實付，不修改銀行對帳單或已付款 ledger。

這是下述「不接受人工輸入薪資結果」在核查後金額更正情境的明示例外，不開放任意修改 actual hours、服務日、樓層費來源或原不可變費率快照。更正後重新核對，不代表已付款／核銷；原應付正確而實付不足／超額，仍走實付差額處理，不以改應付冒充付清。應付依目前「自動計算／人工更正」模式判斷：自動模式在來源變動後直接更新；人工模式保留人工值，另顯示新計算。人員選「採用新計算結果」後更新金額並恢復自動，之後資料再變直接更新；再次手動更正才切回人工模式，不以歷史上曾更正為永久人工判斷。未採用前重整／重算不覆蓋人工值，恢復自動不刪既有更正紀錄。此規則及驗收見 [`22` §16.4.1](22_銀行流水匯入與帳務異常處理正式規格.md#difference-manual-recalculation-20261101)；原實付及受保護快照不改。已付義務、受保護快照的具體銜接仍依 `22` §16.7 收斂，不自選 schema 或更換 owner。

## 1. Domain 責任

2026-10-30 人工裁決：初步候選月嫂的訂單資訊一顯示薪資單價、預估總薪資與預計付款日，不共用客戶費用／繳款內容。預估僅讀取現有 Payroll 費率政策與 Orders 約定服務量、已知樓層費及預計結束日，沿用補助內／用盡後費率、資金來源分期及給付日期規則；未綁定新政策的案件保留既有 Payroll 政策。預估必須明確標示，未確認雙薪／加價／調整不冒充已確定薪資；來源缺失標示待確認，不改採客戶單價或應付總額。此唯讀計算不建立假 assignment 或正式服務日，不保存義務／實付、不更動 Payroll aggregate version，也不取代正式履約後的薪資計算。

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

服務尚未開始時，管理員以正式 BeClass correction 將單胞胎更正為雙胞胎，屬於目前案件有效
費率事實的更正：同一 outer Unit of Work 必須以 450 重算 open Payroll obligation，後續 Query、
rebuild 與新 assignment 也必須優先採用此 effective correction；原 assignment 快照及已付款事件
維持不可變，差額以既有 adjustment／replacement 規則表達。正式服務開始後不得變更胎數。
- 低收入戶／中低收入戶映射為補助市民政策

### Assignment replacement rate snapshot carry-forward（2026-09-23）

Actual Start 只改日期並由 Scheduling cancel-old／create-new 時，successor assignment 的費率不是重新
選擇政策或重算薪資，而是 source assignment immutable rate snapshot 的 identity carry-forward：

- 每個 successor 必須有且只有一個 source assignment；Payroll persistence adapter 依 Scheduling writer
  回傳的新 assignment identity，將 source 的 `policy_version`、`policy_kind`、`hourly_rate_ntd` 原值寫入
  successor snapshot，並保存可追溯的 source identity。
- 本操作不修改 case payroll policy，不增加 Payroll aggregate version，不新增、重建或調整
  `staff_obligations`／obligation events，也不改任何已付款或應付金額。
- source snapshot 缺失、重複、無法唯一對應或與 candidate lineage 不一致時，Preview／Apply 固定回 typed
  integrity blocker 並零寫入；一般 Actual Start replacement 不得 fallback 到目前 case policy。
- 搬移必須與 Scheduling replacement 位於同一 outer Unit of Work；Scheduling 仍只擁有 assignment／lineage，
  rate snapshot 仍只能由 Payroll persistence adapter 寫入。

上述規則只處理已有 source assignment 的日期 replacement。歷史 Precision Restart 後首次建立正式安排，
若 pairing 原本沒有 source assignment／snapshot，仍依 Orders §3.4.1 在真正建立安排時使用案件已存在的
case payroll policy；不得在 confirmed-date 保存階段建立 snapshot，也不得自行產生政策。

依正式指派／服務資料的既有 writer 自動同步月嫂應付；服務完成時再依實際服務與付款日政策同步金額及日期，不要求人員另建付款義務或先執行薪資重建。沿用 aggregate version、不可變事件及既有差額規則；已付款紀錄不覆寫，來源不完整不得推定為零。

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

歷史訂單承接可證實的原月嫂應付、日期與付款關聯。人工更正實際服務天數時，依已確認的服務量、原有效費率及樓層費等計價依據重算，差異沿 Payroll／Staff Payables 正式流程處理。舊案原本適用的單薪或樓層費計價須有來源依據；匯入或服務到期推進不得單憑歷史身分、服務天數或當期政策重新建立應付。承接、缺項及更正流程見[規格 27 §6](27_歷史訂單生命週期與服務天數帳務正式規格.md#historical-accounting-carry-forward)。

中途取消的樓層費先以 `ROUND_HALF_UP` 算出全案整數，再以最大餘數法按 assignment 服務日分配。完整履約後取消被拒絕，不套用縮減。

正式服務日數、`service_hours_per_day`、hourly rate、樓層費及 adjustment 都是整數，因此正常薪資公式不會產生小數。新架構不支援分時／半日 ownership 或小數每日時數；若 legacy／外部輸入導致非整數金額，必須先進異常中心由人員確認根事實，不得在每日或 assignment 層自行四捨五入掩蓋資料問題。

### Staff Obligation Projection

未核銷的 `staff_obligations` current projection 可依新根事實重建；已有正式付款歷史時不得覆寫，改追加 immutable adjustment／reversal obligation event。`staff_payments` 若存在只可由這些 canonical obligation 投影為 compatibility read model，不得回寫 Payroll SSOT。

Payroll 依正式 assignment 服務歸屬保存月嫂應收，案件月嫂應收合計等於案件總額。資金來源不增加第二份薪資權利，但同筆應付可由永豐 P永、台新 P台 及分次真實付款合計清償；不得重複建立或加付補助，亦不得以「只能一次 payout」拒絕合法部分付款。三方案與對象依 `22` §17，歷史不可變 obligation、付款與分配證據保留。

**已取代，僅供歷史追溯（2026-09-11）**：舊規則曾由身分／全補助分類決定客戶先墊及退款，並限制同一 assignment 不得按資金來源分次 payout；此路由與一次付款限制不再作為新模型契約。原已形成義務、金額及實付不因本次重寫。

付款到期日由既有 Orders／Payroll owner 的正式義務與資金來源分期期程提供；已形成的 `staff_payment_due_date` 及各期 due date 保留，不因方案分類、取消、更正或政府晚入款自動改到下一個 15 日。§17.4.1以正式身分及H≤有效L自動成立免自備，不先要求客戶應付已為0；例外之外，新模型不得只憑身分、固定120小時或現有客戶應付為0，重新推導舊「全補助」流程；未形成或新舊模型接線不明的日期依原 owner 待確認，不自行補定。客戶退款仍由 Client Finance 擁有，不能改寫月嫂應收或付款。

**已取代，僅供歷史追溯**：舊一般／非全補助次月 15 日、全補助第二月 15 日的身分分類推導，只供辨識既有已形成日期及原實作證據；不作新方案分類或批次重算依據。

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

案件／月嫂薪資唯讀查詢保留已取消及已結清的 0 元紀錄，回應金額為非負整數。既有 open 義務仍依 owner invariant 必須大於 0；Query 不改寫狀態、金額或付款紀錄。新增調整命令沿用既有非零驗證。

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

## 9. 服務中換人的付款承接（2026-10-21）

使用者核可服務中換人及帳務銜接的實作。沿用既有 Payroll owner 與 Scheduling outer UoW，不新增付款或月結 lifecycle。

- 原 rate snapshot 逐值承接；原 adjustment allocation 只承接給同一來源家族的原受款月嫂一次，不複製至接任人。透過 assignment lineage 追溯原 allocation，不搬動 immutable allocation。
- 未付款 projection 可關閉後依新服務事實建立。已有付款歷史的原 obligation／event／付款 links 不覆寫；以原 obligation identity 為根，追加 `staff-handover:` immutable 差額，等於新合法 entitlement 減去該根加既有換人差額的 entitlement，並非減去已付額。
- Staff Payables 以原 obligation 加其來源相同的換人差額推導有效應付額；差額列不形成第二張可獨立付款的帳單。剩餘應付為有效應付減實付淨額的正值。已付超過新合法 entitlement 的新增差額，經 Staff Payables typed port 依唯一 correction identity 建立追償。
- 重複交接須沿 Scheduling ancestry 找回原 obligation；既有差額只計一次。已存在不同來源的已付 adjustment、義務來源不唯一、或需沖減既有追償時，回明確 blocker，交由原帳務處理流程核對，不自動抵銷。
- 付款家族的 ancestry 只延續同一月嫂；經過其他月嫂後再接任屬新付款家族，不承接該月嫂早期其他家族的 adjustment／付款／追償。薪資雙薪根事實與正式服務日標記不一致時阻擋，不猜算。
- 已含換人差額的後續代班／條款影響使用相同來源承接與 Staff Payables typed coordination。尚未支援此來源的通用薪資重建入口須回 `payroll_handover_settlement_required`，不得另建原全額義務。歷史付款／結清 overlay 不得當成未付款重開。
- 服務完成的自動帳務同步，沿同月嫂 assignment ancestry 核對原應付加換人差額與目前正式服務薪資；金額及付款日均未改變時直接沿用，不重建已付義務、不重複追償。無法唯一對應或仍有金額／付款日差異時，保留上述帳務核對 blocker。
- 已形成的付款日保留。Preview 零寫入；Apply 在 sorted staff-account locks 下重新讀實付與版本，Payroll 差額、Staff Payables projection／追償、排班與 receipt 同一交易提交；不執行銀行付款或對外通知。
