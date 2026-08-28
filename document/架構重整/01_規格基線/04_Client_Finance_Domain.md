# Client Finance Domain

## 1. Domain 責任

擁有客戶付款條款、訂金／各期款／adjustment／退款／補助退還義務、不可變正式交易與 allocation、核銷 Preview／Apply、超收與退款義務，以及 current balance／settled projection。

不擁有 Orders lifecycle、assignment、正式服務日、客戶身分根值、銀行原始流水或 Alert workflow。

## 2. SSOT

| 資料 | 唯一權威 |
|---|---|
| 付款條款與到期日 | `PaymentTerms` root facts |
| 應收／退款／補助退還義務 | append-only obligation events |
| 收款／退款／adjustment／reversal | immutable client ledger |
| transaction allocation | append-only M:N allocations |
| current balance／settled at | obligation 與 ledger reducer |
| subsidy advance／recovery | immutable client payout event 與 Government Subsidy receipt-allocation fact 的 M:N settlement link |
| `client_payments` | current／compatibility projection |
| review status | root-derived projection，不可人工直接修改 |

每次正式核銷必須完整分配所選銀行流水，且每個所選義務在同一次 Apply 後精確為 `0`。少收、超收、錯案或 ownership 不明不得建立部分正式交易。

## 3. Subsystems

### Payment Terms／Obligation Planning

依 Orders Terms、服務日根事實及費率政策建立訂金、第一期、第二期及調整義務。樓層費只計入一次。條款變更只重算未核銷義務；已核銷差額建立 adjustment 或 refund obligation。

依第 `21` 份正式規格，最後一位月嫂簽回並形成有效簽約前 commitment 時，只建立一次且
唯一的 deposit obligation，使用 commitment 的精確服務日、時數、費率與樓層費計算。客戶
簽回後的 Contract Completion 保留該 deposit identity、金額、ledger 與 allocation，只補足
尚未建立的剩餘正式期款；不得重建、重複計入或因客戶晚簽而撤銷已合法核銷的 deposit。

### 取消帳務 impact 的公開 direction（2026-08-27 人工裁決）

取消 Preview／Apply 對外公開的每一筆 Client Finance impact 必須帶 server-owned、required
`direction`；UI 不得由 `action_kind`、金額正負、before／after 差值或排序推定。固定 enum 與顯示
語意如下：

| `direction` | 公開意義 | `direction_amount_ntd` invariant |
|---|---|---|
| `refund_due` | 應退款：客戶有待收回的款項 | 非負整數且 `> 0` |
| `additional_charge_due` | 應補收：客戶仍有待繳的款項 | 非負整數且 `> 0` |
| `no_finance_change` | 無帳務變動 | 必須為 `0` |

`action_kind` 仍可說明 adjustment／refund／collection 等操作類型，但不具 direction 權威。
若同一取消同時存在多個獨立 impact，結果必須逐筆帶 direction，不得先由 UI 合併成一個淨額
方向。`before_amount_ntd`／`after_amount_ntd` 是 obligation target；既有
`obligation_amount_ntd` 是該 action 新建／變更的 obligation delta（或新建 obligation 金額），
不是客戶實際應退款／補收的金額。另公開 required `direction_amount_ntd`，代表 direction 對
客戶的現金／待收付影響，為非負整數；只有它能和 direction 配對。Direction 是 derived public
view 的必要欄位，實際 obligation、ledger、allocation 與 settlement 仍由本 Domain 根事實重建；
不存在新的帳務根事實或 UI writer。

取消結果對現有 action kind 的 canonical mapping 固定如下；server 必須在建 candidate 時寫入，
caller 不得重算：

表中的 `current_settled_amount_ntd` 是 Client Finance 由 immutable ledger／allocation reducer
重建的目前已結算金額；不是 `before_amount_ntd`（後者是既有 obligation target）。

| `action_kind` | 條件 | `direction` | `direction_amount_ntd` | `obligation_amount_ntd` |
|---|---|---|---:|---:|
| `create_stage` | `after_amount_ntd > 0` | `additional_charge_due` | `after_amount_ntd` | `after_amount_ntd` |
| `replace_open` | after > before | `additional_charge_due` | `after - before` | `abs(after - before)` |
| `replace_open` | after < before（尚無正式收款歷史） | `no_finance_change` | `0` | `before - after` |
| `cancel_open` | open obligation、無正式收款歷史 | `no_finance_change` | `0` | `before_amount_ntd` |
| `create_adjustment` | `after_amount_ntd - current_settled_amount_ntd > 0` | `additional_charge_due` | `after - current_settled` | `after - current_settled` |
| `create_refund` | `after_amount_ntd - current_settled_amount_ntd < 0` | `refund_due` | `current_settled - after` | `current_settled - after` |
| `unchanged` | before = after 且沒有新 obligation | `no_finance_change` | `0` | `0` |

因此 `replace_open` 減額與 `cancel_open` 都不是退款：它們只減少／取消尚未收取的 open
obligation；真正已有正式收款而新義務下降時，固定使用 `create_refund` 與 `refund_due`。
同一 cancellation response 可含多筆 action，各筆均依本表產生自己的 direction 與
direction amount。

缺少 direction、direction_amount 與 direction 不一致、或 current owner readback 不能唯一確認
方向時，Query／Preview／Apply 回 typed schema／domain error 或 `outcome_unknown`，不建立或
變更正式交易；不得 fallback 成 action kind 或以正負號猜測。舊 caller 若無法驗證該欄位，只能
顯示 schema-drift／unavailable。相同 idempotency identity 的結果重查後，receipt／readback 必須
保留同一 direction。

補助資格與客戶收費採同一組衍生政策：補助市民（含低收入戶／中低收入戶映射）的月嫂服務薪資與政府請款單價均為每小時 350 元；政府先負擔最多 120 小時，第 121 小時起按每小時 350 元形成客戶應收。這使服務薪資在時數層由「政府補助＋客戶超額自費」完整覆蓋。樓層費不受時數補助抵銷，永遠是客戶應收。故「全補助訂單」只表示本案實際時數未超過 120 且無樓層費或其他自費項目，不能作為客戶身分的別名。

Modules：

- `PaymentStageSplitter`
- `DailyClientChargeCalculator`
- `PaymentDueDatePolicy`
- `ObligationDiffCalculator`
- `FinancePreviewFingerprint`

### Reconciliation Preview／Apply

鎖定銀行 facts、account version 與 obligations；驗證方向、案件、external reference、ownership 與完整 allocation。Preview 零寫入；Apply 建立正式 ledger、allocation、projection、audit 與 outbox。

Modules：

- `BankFactEligibilityValidator`
- `ExactAllocationSolver`
- `StageBalanceCalculator`
- `ReconciliationInvariantValidator`
- `ExternalReferenceDeduplicator`

### Immutable Ledger／Reversal

原交易永不 UPDATE。reversal 指向同 case、同 obligation kind、同 ledger 的原交易；不得超過仍可沖銷餘額。

已確認禁止 reversal-of-reversal。若 reversal 疑似錯誤，系統先產生異常警報並停止自動修復，顯示原交易、reversal、有效淨額、受影響義務及合法 recovery actions。只有人員確認實際情況後，才可透過 Client Finance Preview／Apply 新增反方向 adjustment；不得由 projector、scanner 或 ledger reducer 自動補 adjustment。

### Over-receipt／Customer Refund

義務合法下降造成有效實收大於新義務時，差額形成 `over_receipt` 與退款義務。退款後淨應收與淨實收同減；銀行撤銷原收款而義務未降低則是 reversal，重新形成應收。退款不取消已完成訂單，也不解除服務資料鎖。

### Client Subsidy Return

功能已啟用，且與客戶服務費 ledger 分離。它是「工會對客戶的應付」，不是
政府對工會的應收，也不得以 `client_payments.subsidy_refund_*` 作為事實來源。

```text
退還義務
= min(補助時數上限, 有效正式服務時數) × 一般客戶時薪
```

雙倍日不增加退還額。只有服務完成、客戶服務費收齊且資格符合時建立；帳戶不唯一、
少退、超退、退匯／沖正都進異常，不改義務。

#### 季度撥款與工會墊付

政府補助的申請與撥款是 Government Subsidy Domain 的季度流程；客戶補助退還仍由本
Domain 擁有。兩者的金流方向不同，永遠不得互相抵銷或改寫對方 ledger：

```text
Government Subsidy: 政府 → 工會 → claim-item allocation
Client Finance:      工會 → 客戶 → subsidy-return obligation / payout
```

若客戶在其 claim quarter 的第一個曆月實際結案，補助退款日期固定為「實際結案月份
加兩個曆月的 15 日」。該日相關 claim item 尚未有政府入帳 allocation 時，系統建立
`subsidy_advance_due` read-only reminder；人員核對銀行對帳單與應付資料後，在銀行系統
完成付款。系統不產生付款指令，也不因到期直接寫入 client ledger。付款後匯入的唯一
canonical outgoing bank fact 才可經 Preview／Apply 核銷已建立、未清償的
`subsidy_return` 義務；這是客戶 payout，不是客戶收款、也不是政府 receipt。

之後政府整季款項入帳時，Government Subsidy 先完成 receipt → claim-item allocation，
再透過 committed outbox 提供不可變 allocation fact。Client Finance 只可依該 fact 對
既有墊付建立 `subsidy_advance_recovery` settlement link。每個 `subsidy_return`
obligation 必須先以不可變 entitlement link 對應 claim item；不得以 case number 或金額
模糊猜配。recovery 不得新增第二筆客戶 payout，也不得把已結清的客戶 obligation 重開。未墊付案件則可依同一 eligibility 走正常
`subsidy_return` payout。

政府核准額、政府實收額與已墊付款任一不一致，或 claim item／客戶 payout 對應非唯一
時，禁止自動打平，建立 typed anomaly 與人工 Preview。`subsidy_refund_*` 與
`subsidy_return_*` 的 legacy projection 欄位只允許 preserve-data migration 讀取；
不再是正式 writer 或 query SSOT。

一般退款與客戶補助退還不得共用 ledger transaction type 或 reversal type：

| 業務線 | payout entry type | return／reversal entry type | obligation projection |
|---|---|---|---|
| 一般客戶退款 | `refund` | `refund_reversal` | `refund` 的 `pending → partially_refunded → refunded` |
| 客戶補助退還 | `subsidy_return` | `subsidy_return_reversal` | `subsidy_return` 的獨立 payable progress；不與一般退款互抵 |
| 客戶收款沖正 | 不適用 | `reversal` | 只重開原 receivable，不得重開任何 payable |

同一 Client Finance outer UoW 可以共用技術性 receipt／outbox 實作，但不得以共用
`refund` entry type、共同餘額或共同狀態 reducer 混淆兩條業務線。

### Adjustment Accounting

adjustment 是獨立義務，不修改歷史服務費。一筆銀行交易可明確 allocation 到多筆 adjustment，但每筆所選義務都必須完整核銷。

adjustment 的原因、方向或歸屬若不能從已確認根事實唯一決定，必須先進異常中心，由人員查看完整事件鏈並啟動 typed Adjustment Preview／Apply；不得為了讓差額歸零而自動建立。

Adjustment 必須明確宣告 scope：

- `client_only` 只建立客戶 adjustment obligation／ledger event，不要求 staff
  allocation、不檢查或遞增 Payroll version，也不發出 Payroll outbox。
- `client_and_staff` 必須讓 client delta 與所有 staff allocation 的整數 NTD
  加總完全相等，並在同一交易檢查及遞增 Client Finance／Payroll 兩端版本。
- 兩種 scope 都必須經 Preview／Apply、Client Finance version compare-and-swap、
  idempotency receipt、不可變事件及 Client Finance outbox。reversal 必須沿用原
  adjustment scope，不得用 `client_only` 局部沖回雙端 adjustment。

### Projection／Query

從 obligation 與 ledger events 重建各 stage receivable、received、due date、settled at。總額只供顯示，不得掩蓋單期差異。對 Orders 只輸出 typed `ClientSettlementFacts`；取消 impact 的每一筆公開結果必須包含上述 `direction`，不得讓 caller 由 action kind 或 amount 推定。

## 4. Ports

輸入：

- `OrdersTermsFactsPort`
- `OfficialServiceDaysPort`
- `ClientEligibilityPolicyPort`
- `FinanceImportCanonicalIncomingFactsPort`
- `FinanceImportClientReceiptDispatchPort`
- `FinancialAdjustmentFactsPort`
- `GovernmentSubsidyReceiptAllocationFactsPort`

輸出：

- `ClientFinanceImpactPreviewPort`
- `ClientSettlementFactsPort`
- `ClientFinanceRootFactsOutboxPort`
- `ClientFinanceQueryPort`

基礎設施：

- `ClientObligationRepository`
- `ClientLedgerRepository`
- `TransactionAllocationRepository`
- `ClientFinanceProjectionRepository`
- `IdempotencyReceiptRepository`
- `UnitOfWork`

不得提供同步 Alert writer；只在交易內寫 outbox facts。

## 5. 驗收

- 三階段義務及多流水完整核銷。
- 一筆流水跨多義務時，每筆義務皆完整歸零。
- 少收／超收初次對帳零正式交易並形成異常 fact。
- obligation 後降建立 over-receipt／refund obligation。
- 合法退款與 reversal 的淨額結果不同且正確。
- 補助退還建立、到期、精確退款、退匯重開。
- 第一個季度月結案案件在兩曆月內未獲政府入帳時，建立可追溯的墊付待辦；墊付後的
  政府 receipt 只核銷墊付款，絕不重複退還客戶。
- 補助退款日為結案月份加兩曆月的 15 日；未清償的客戶補助退還必須出現在
  Accounts Payable Query／Export，並以 `client_subsidy_return` 類型與月嫂應付款區分。
- 政府撥款、核准或墊付額不一致時，零自動 settlement 並建立 anomaly。
- 取消帳務每筆 impact 都公開 `refund_due`／`additional_charge_due`／`no_finance_change` direction；
  UI 顯示 server enum，不從 action kind 或金額正負推定，且 direction／direction_amount 不一致時零寫入。
- Domain blocker 不因 Alert resolve 被繞過。
- 任一 ledger／allocation／projection／outbox 失敗整筆 rollback。

## 6. Typed Commands／Results／Errors

Commands：

- `QueryClientFinance`
- `PreviewClientReceiptReconciliation`
- `ApplyClientReceiptReconciliation`
- `PreviewClientRefund`
- `ApplyClientRefund`
- `PreviewClientAdjustment`
- `ApplyClientAdjustment`
- `PreviewClientReversal`
- `ApplyClientReversal`
- `PreviewClientSubsidyReturn`
- `ApplyClientSubsidyReturn`
- `QueryClientSubsidyAdvanceQueue`
- `PreviewClientSubsidyAdvance`
- `ApplyClientSubsidyAdvance`
- `RebuildClientObligationsForCase`

Stable errors：

- `client_finance_case_not_found`
- `invalid_client_finance_intent`
- `bank_fact_not_eligible`
- `client_obligation_not_found`
- `allocation_not_exact`
- `client_receipt_underpaid`
- `client_receipt_overpaid`
- `client_finance_identity_ambiguous`
- `reversal_target_invalid`
- `reversal_amount_exceeded`
- `adjustment_evidence_required`
- `client_finance_candidate_stale`
- `idempotency_conflict`
- `transaction_failed`
- `subsidy_advance_not_due`
- `subsidy_advance_already_recovered`
- `subsidy_advance_settlement_ambiguous`
- `client_finance_direction_missing`
- `client_finance_direction_amount_mismatch`

## 7. Live writer 退出

- `services/client_payment_writer.py`、`services/client_payment_transactions.py`、
  `services/client_receipt_reconciliation.py`、`services/client_subsidy_return_obligations.py`
  與 `services/client_subsidy_return_transactions.py` 的合法規則可吸收至本 Domain。
- `services/client_payment_snapshots.py` 與 `services/db_service.py` 只能建立／更新
  compatibility projection，不得成為 obligation 或 ledger SSOT。
- Finance Import、API、Streamlit 與 scripts 不得直接 UPDATE `client_payments`、
  `client_payment_transactions` 或 reconciliation projection。
- final writer scan 必須證明 obligation event、client ledger、allocation、refund、
  adjustment、reversal 與 settled projection 都只有 Client Finance adapters 可寫。
