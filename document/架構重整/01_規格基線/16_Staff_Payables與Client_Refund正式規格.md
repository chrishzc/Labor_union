# Staff Payables 與 Client Refund 正式規格

## 1. 文件邊界與所有權

- 狀態：`current-spec`
- Owner：Staff Payables Domain（`domains/staff_payables/`）、Client Finance Domain（`domains/client_finance/`）
- 單一負責範圍：月嫂應付核銷、待核對頁方案一共同確認與分來源核銷、少付超過 100 元部分付款／超付追償（`staff_overpayment_recovery`）、客戶退款／補助退還（`refund`／`subsidy_return` 分離）、多收另立退款（`ApplyClientReceiptWithOverage`）、退款少退／超退追償（`client_over_refund_recovery`）、退匯人工選款（`refund-return`）、服務中換人超付銜接。
- 關聯引用：見 [Global 共同契約](00_Global_共同契約.md)、[Payroll Domain](03_Payroll_Domain.md)、[Client Finance Domain](04_Client_Finance_Domain.md)、[Staff Payables / Export Domain](05_Staff_Payables_Export_Domain.md)、[Finance Import Domain](09_Finance_Import_Domain.md)、[Accounts Payable Export 與現金需求清冊](16A_Accounts_Payable_Export與現金需求清冊規格.md)、[銀行流水對帳與手動補登](22_銀行流水匯入與帳務異常處理正式規格.md)、[案件帳務三方案與補助流向](22A_案件帳務三方案與補助流向正式規格.md)、[帳務差額處置與工作台 UI](22B_帳務差額處置與工作台UI正式規格.md)、[歷史訂單生命週期與服務天數帳務](27_歷史訂單生命週期與服務天數帳務正式規格.md)。

## 2. 核心流程：Staff Payables

### 2.1 責任分離與根事實

- Staff Payables 擁有：`staff_obligations` projection 消費、不可變 `payout／return／reversal` ledger、obligation link、`payable | partially_paid | completed | recovery_required | anomaly` 投影與同月嫂彙整清冊來源；不擁有訂單狀態、服務日、薪資公式或月結 (`draft/finalized`) 狀態機。
- **根事實**：Payroll 產生的 `staff_obligations`、assignment identity 與 rate snapshot、canonical bank payout fact（或 [手動補登](22_銀行流水匯入與帳務異常處理正式規格.md#6-案件帳務手動補登與自動銷帳) 來源）、payout/return/reversal event、allocation link、各銀行正式對象證據、version 與 receipt。
- **銀行月嫂出款對象**：永豐 `P永` 自動核銷依匯入辨識的對象與配對義務，人工核銷依經操作者確認的應付義務。兩者均免驗交易收款帳號與月嫂主要帳戶。台新 `P台` 依原始備註辨識唯一月嫂姓名並比對所選義務。
- `staff_monthly_settlements`、`staff_monthly_settlement_details`、`staff_actual_transfers`、`staff_payment_transactions`、`staff_transfer_allocations` 僅供歷史唯讀查詢或明確 backfill；`staff_payments` 僅唯讀相容投影。

### 2.2 Payout Reconciliation Preview／Apply

- **Commands**：`PreviewStaffPayout`、`ApplyStaffPayout`、`PreviewStaffPayoutReturn`、`ApplyStaffPayoutReturn`、`PreviewStaffPayoutReversal`、`ApplyStaffPayoutReversal`、`PreviewStaffPayoutDifference`、`ApplyStaffPayoutDifference`、`PreviewStaffOverpaymentRecovery`、`ApplyStaffOverpaymentRecovery`。
- **Apply 共用交易步驟**：依 canonical staff mutex order 加鎖 → 鎖定 version、bank facts、帳號快照與義務 → 重建並驗證 fingerprint 與 expected version → 依事件別 guard 驗證 → append ledger event 與 links → 更新 projection、version、outbox 與 receipt → outer UoW 單次提交（Apply route 回 `202 JobAccepted` 僅代表排入 durable command，完成須由 job／root 讀回確認）。
- **事件別 Guard**：
  - **一般 payout（含 0～100 元手續費）**：收款對象＋交易日月份唯一匹配，且 `0 <= (選定義務剩餘合計 - 銀行實付) <= 100` 時，動態計算 `transfer_fee_ntd = remaining_total - bank_outflow`（可為 `0`～`100`），直接核銷結清為 `completed`（`remaining = 0`），保留原應付、實付與手續費。
  - **payout difference**：用於 `差額 > 100` 部分付款或 `實付 > 應付` 超付追償。
  - **return／reversal**：指向有效 payout；`return` 須綁銀行退匯入款，`reversal` 須人工原因與 capability，均不得超過尚未重開額。
- 手動補登之銀行對象條件依 [手動補登規格](22_銀行流水匯入與帳務異常處理正式規格.md#6-案件帳務手動補登與自動銷帳)，不要求補造帳號快照。

<a id="staff-payout-scheme1-and-differences"></a>

### 2.3 待核對頁方案一共同確認、不足額與 100 元手續費

- **待核對頁直接確認方案一**（核銷選項「補助方案一：核銷自備款，補助款保留待付」）：
  - 適用範圍：已確認同一案件、同一月嫂及單筆原應付的永豐出款（即使尚未保存方案或尚無正式分期）。以 Payroll 有效應付 `T` 與 Government Subsidy `S` 為權威來源（不接受前端傳入或差額反推；`S` 不明、`S >= T`、已有衝突方案或客戶補助退款時拒絕）。
  - Preview 零寫入顯示 `T`、`S`、自備待付、實付、手續費與補助待付；缺分期時由 [Payroll Domain](03_Payroll_Domain.md#21-核心計價與費率政策) 承接 `T - S`（原應付日）與 `S`（服務結束月 `+ 2` 月 15 日）。
  - Apply 在單一 outer UoW 內鎖訂單身分、補助來源與付款事實，原子提交方案事件 split、缺席分期與自備款核銷（同鍵重播回原結果、來源變動 409）。單獨於案件頁設定方案不執行本入口之自備款核銷。
- **方案一分來源核銷**：已建立自備／補助分期時，永豐 `P永` 僅核銷自備款分期、台新 `P台` 僅核銷補助款分期，各自依原分期到期月份比對該來源餘額（不拿全案 `T` 比較、亦不因同月合併）；含各自內扣手續費後兩者均清償始結清整筆應付。
- **少付超過 100 元部分付款（`ApplyStaffPayoutDifference(mode=underpayment)`）**：
  - 銀行對帳「核對交易」可選「足額核銷本次款項（含 100 元內手續費）」、「付款不足，先核銷實付」、「付款超額，另列追收」及上述永豐方案一選項。
  - 在單一 UoW 內依義務 ID 順序寫入 payout event 與 allocation，計算 `remaining = obligation_amount - net_valid_payout`（> 0 轉 `partially_paid`），下期清冊僅列 `remaining`，不改變 Payroll 原始應付或重複建單；後續新補款繼續對同一義務結清。退匯／沖正僅重開指定來源付款額。

### 2.4 超額付款與追償（`staff_overpayment_recovery`）

- 銀行實付大於選定 `remaining` 時，`ApplyStaffPayoutDifference(mode=overpayment)` 寫入全額 payout event、將原義務清零（`completed`），並以差額建立獨立 `staff_overpayment_recovery`（`recovery_required` 異常，不進 AP 清冊，嚴禁自動從他案或未來薪資扣抵）。
- **追償狀態機**：`open／partially_recovered` ──(canonical 退回入款，`remaining > 0`)──> `partially_recovered`；(`remaining == 0`)──> `recovered`；(`staff_payables.recovery.adjust` authorized adjustment)──> `adjusted`。
- Preview intent 綁定 `bank_total < remaining_total`（`underpayment`）或 `bank_total > remaining_total`（`overpayment`），金額相等改走一般 payout；永豐唯一對應月嫂主帳戶之退回入款保留待人工配對至開立中的追償。

### 2.5 Typed Errors、人工入口與 Legacy Exit

- **Typed Errors**：`staff_payable_not_found`、`staff_payable_candidate_stale`、`idempotency_conflict`、`staff_obligation_not_exactly_settled`、`staff_bank_account_ambiguous`、`staff_payout_amount_mismatch`、`staff_payout_difference_mode_invalid`、`staff_overpayment_recovery_target_ambiguous`、`staff_overpayment_recovery_adjustment_forbidden`、`staff_payout_reversal_invalid`、`transaction_failed`、`accounts_payable_export_has_anomaly`、`accounts_payable_archive_failed`。
- **Legacy Exit**：停止所有 `staff_monthly_settlements*` runtime writer；legacy payment route 固定 `410 Gone`；adjustment 與 `finance_import_dispatch` 嚴禁寫入月結表或 `staff_actual_transfers`。

## 3. 核心流程：Client Refund

### 3.1 責任分離與 `refund`／`subsidy_return` 排他

- Client Finance 擁有客戶退款與補助退還義務、出款 ledger、exact allocation、version 與收款沖正後重開應收；退款不解除不可逆服務鎖或倒退訂單狀態。
- **排他禁止**：不得用負數收款代表退款、覆寫原 receipt、混用 `refund` 與 `reversal`、執行 `reversal-of-reversal` 或無退款義務直接付款。
- 一般退款使用 `refund`／`refund_reversal`（`pending → partially_refunded → refunded`）；客戶補助退還使用 `subsidy_return`／`subsidy_return_reversal`；客戶收款沖正固定為 `reversal`。兩條退款業務線不得共用剩餘額或進度 reducer。

### 3.2 Refund Obligation Planning 與客戶超收另列退款

- **Commands**：`CreateCustomerRefundObligation`、`AdjustRefundObligation`、`ApplyClientReceiptWithOverage`、`ApplyClientRefundWithOverage`。
- **來源**：一般退款源自提交後的取消結算／調整單；客戶補助退還由確認屬方案二（`R台`）之案件於正式服務／帳務成立條件具備時按 [補助應付交接規則](16A_Accounts_Payable_Export與現金需求清冊規格.md#manual-subsidy-plan-payables-handoff) 承接，禁止僅憑身分或 `S` 直接自動建單。
- **`ApplyClientReceiptWithOverage`**：須選定銀行入款、唯一案件、唯一應收義務及人員確認，於同一 outer UoW 內：(1) append 全額實收 receipt → (2) 原應收額度內建立 allocation → (3) 差額建立 `customer_refund` payable（關聯該 receipt）→ (4) 寫入 receipt、version 與 outbox。不得僅留超收警示而遺漏實收現金事實。

### 3.3 Refund／Reversal Preview、Apply、手續費與超退追償

- **Queries／Commands**：`QueryClientRefundReversal`、`Preview/ApplyClientRefund`、`Preview/ApplyClientSubsidyReturn`、`Preview/ApplyClientReceiptReversal`、`Preview/ApplyClientRefundReturn`、`Preview/ApplyClientRefundReversal`。
- **Apply 八步與差額規則**：檢查 idempotency → 加鎖 account、bank facts、obligations／reversal targets → 重建驗證 expected version 與 fingerprint → append ledger 與 allocations → 重算 remaining → 更新 projection／outbox／receipt → 單次提交。
  - **0～100 元手續費直接結清**：`R永`／`R台` 依各自對象規則（`R永` 驗帳號快照；`R台` 未命中月嫂姓名時以原始備註唯一六碼定位案件，不要求帳號快照）＋交易日月份唯一匹配且 `0 <= 應退餘額 - 銀行實付 <= 100` 時，動態計算 `transfer_fee_ntd` 結清為 `refunded`。
  - **少退超過 100 元**：須人員明確選取部分退款模式，核銷實付並轉 `partially_refunded` 保留餘額；同案同對象同銀行同月多筆明確合併補助退款應逐筆檢驗原資格與日期。
  - **超退（`銀行實付 > 應退餘額`）**：由 `ApplyClientRefundWithOverage` 在原義務額內結清，並將超額建立獨立 `client_over_refund_recovery`（`R台` 沿同一六碼與整期資金驗證，多筆合併僅立一筆追償）。

### 3.4 `client_over_refund_recovery` 與退匯／沖正契約

- **正交投影**：`refund_progress`（`not_required | pending | partially_refunded | refunded`）與 `refund_review`（`normal ↔ review_required`）；`client_over_refund_recovery` 獨立使用 `open | partially_recovered | recovered | adjusted`。
- **Commands**：`QueryClientOverRefundRecovery`、`Preview/ApplyClientOverRefundRecoveryReceipt`、`Preview/ApplyClientOverRefundRecoveryAdjustment`。
- **結清規則**：追償入款僅接受未使用 canonical incoming bank fact 且入款 `<= remaining`（部分追回允許轉 `partially_recovered`；禁止自動以其他案件新應收抵銷）。無現金調整限具 `client_finance.recovery.adjust` capability。
- **退匯（`refund-return`）與沖正**：不設自動退匯辨識；唯既有已分類為客戶退匯且確認唯一案件之銀行流水，可由人員於同案抽屜選取本案有效原退款走 `Preview/ApplyClientRefundReturn` 重開原退款義務。所有逾期退款提醒於有效 bank fact 核銷歸零後自動解除（未匯入流水禁止標記 `payment_failed`／`submitted`）。

### 3.5 Client Refund Typed Errors 與 Legacy Exit

- **Typed Errors**：`client_finance_case_not_found`、`client_obligation_not_found`、`client_finance_candidate_stale`、`client_finance_version_conflict`、`idempotency_conflict`、`invalid_client_refund_intent`、`client_refund_bank_allocation_incomplete`、`client_refund_exceeds_remaining_amount`、`client_refund_return_invalid`、`client_over_refund_recovery_not_found`、`client_over_refund_recovery_amount_exceeded`、`client_over_refund_recovery_target_ambiguous`、`client_over_refund_recovery_adjustment_forbidden`、`client_receipt_reversal_invalid`、`client_finance_storage_unavailable`。
- **Writer Exit**：退場所有負收款、覆寫原交易、跨案抵銷及 `client_payments` 直接更新；Data Browser 禁止寫入 ledger。

## 4. 跨 Domain 交易與換人銜接

- **歷史付款來源順位**：優先消費 Finance Import 對帳單；僅系統前採納之歷史訂單於舊來源無法還原時使用 owner-specific 人工 `paid | settled`。Client Finance settlement、Staff Payables completion 與 Orders 結案為三個獨立投影。
- **服務中換人銜接（`staff-handover:`）**：Staff Payables 消費 Payroll 的換人更正；換人差額不得被 AP 清冊或自助查詢拆成獨立第二張 payable，實付高於有效新應付時依唯一 correction 建立單次追償（重播／連續換人不重複計追償）；未收回追償不阻擋合法排班交接或新月嫂薪資。

<a id="service-attribution-settlement"></a>

### 4.1 服務歸屬更正的核銷與追償

- 消費 [Payroll 服務歸屬更正](03_Payroll_Domain.md#service-attribution-payroll-correction) 的正式差額與款項承接資料。原出款、核銷及沖正留在原受款月嫂、原款項來源與分期。依各來源有效核銷及既有手續費規則算出待付餘額。其他月嫂的新應付獨立核銷。
- 依 §2.4 對原受款月嫂及原款項來源計算新增淨超付。各來源分別處理待付與追償，以唯一 Payroll 更正、受款人、款項來源及既有追償餘額防重。一般單核銷確認順序依 [服務歸屬更正交易契約](02_Assignments_Scheduling_Domain.md#multi-caregiver-service-correction)。歷史單補證依 [歷史服務歸屬](27_歷史訂單生命週期與服務天數帳務正式規格.md#historical-service-attribution-correction)。
- 供 [歷史帳務完成投影](27_歷史訂單生命週期與服務天數帳務正式規格.md#7-帳務完成投影) 讀取各月嫂有效待付、已核銷及未處理追償。

## 5. 驗收標準

- 多月嫂歸屬更正涵蓋未付、部分付款、已付、自備與補助分來源及沖正後狀態。原核銷留在原受款人及來源，新月嫂可獨立核銷。原受款人超付只立一次追償，重送或連續更正不重複追收。

1. Unit／Subsystem 驗證整數 NTD、精確與差額核銷守恆、`0～100` 元手續費結清、超過 `100` 元部分付款保留餘額、方案一 `T - S`／`S` 分來源共同確認、return／reversal 重開及 idempotency 防重／conflict。
2. 隔離 MySQL Domain 與 Global E2E 驗證：超收 `3,000 / 2,500` 建 `customer_refund 500` 並出款核銷；超退 `750 / 500` 建 `client_over_refund_recovery 250` 與後續收回；同一批次同時存在月嫂付款與客戶退款互不抵銷；失敗注入證實跨 Domain UoW 原子全批回滾。
