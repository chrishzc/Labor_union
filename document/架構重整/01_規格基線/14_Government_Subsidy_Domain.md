# Government Subsidy Domain

> 人工裁決：2026-08-02 確認新增獨立 Domain。  
> 本 Domain 與 Client Finance、Staff Payables、Finance Import 分開；不得把政府撥款
> 映射成客戶收款，也不得由 Finance Import 直接寫正式補助 ledger。

> 2026-08-11 政府溢撥 disposition 可執行契約：`approved`。

## 1. Domain 責任

Government Subsidy 是正式政府補助申請、政府核准、政府撥款／退匯及逐案件分配的唯一
owner。

它負責：

- 年度、季度與 revision 的正式申請批次；
- 批次內 assignment-owned 逐案件申請明細；
- 送件與政府核准不可變事件；
- 政府撥款、退匯及 reversal 的不可變 ledger；
- 一筆政府款項對多筆申請明細的 M:N allocation；
- requested／approved／net allocated／outstanding 的目前投影；
- Preview／Apply、版本、冪等 receipt、outbox 與異常根事實。

它不擁有：

- Excel、銀行 canonical row、occurrence 或 classification；
- 客戶應收、客戶退款、client subsidy return；
- 月嫂薪資或 payout；但全額補助案件的付款日若先於政府季度撥款，Government Subsidy 必須提供可追溯的工會墊付 funding／recovery fact 給 Staff Payables，不能把月嫂 obligation 改寫成客戶退款或 Client Finance receipt。

### Staff payout funding state machine

Government Subsidy 與 Staff Payables 以同一組 root facts 驗證 funding state，而非散落的全額補助特例。輸入為正式月嫂 obligation、到期日、Client Finance 衍生客戶應收、全補助訂單判定、政府 receipt allocation 與既有工會墊付款。全補助訂單僅在補助市民本案時數不超過 120 小時，且樓層費及其他自費項目皆為 0 時成立：

- 未到期：`not_due`；
- 衍生客戶應收大於 0 的案件到期：`client_receipt_required`；
- 全額補助且政府 allocation 恰足：`government_funded`；
- 全額補助到期、政府尚未入帳：`union_advance_due`；
- 部分／超額 allocation、超額墊付或任何不唯一對應：`review_required`，零自動抵銷。

`union_advance_due` 只建立 Staff Payables 的 typed Preview／Apply 工作項。正式 payout 仍由 Staff Payables 建立；後續政府季度入帳只建立對既有墊付的 recovery link，不得新增第二筆月嫂 payout。
- Orders、Scheduling 或 Alert workflow；
- 政府公文檔案的外部保存機制。

## 2. SSOT

| 概念 | 唯一權威 | 性質 |
|---|---|---|
| Claim batch identity | application year＋quarter＋revision | root identity |
| Claim items | 送件時的 assignment、case、staff、hours、unit price、requested amount snapshot | immutable root facts |
| Submission | submit event＋actor＋business time | immutable event |
| Approval | 每筆 item 的 government-approved amount＋approval event | immutable event |
| Government receipt／return | 連結 `finance_import_row_id` 的 ledger event | immutable event |
| Allocation | ledger event ↔ claim item 的 M:N allocation | immutable event |
| Reversal | 指向原 receipt 與原 allocation 的 reversal event | immutable event |
| Requested total | SUM(submitted item requested amount) | derived projection |
| Approved total | SUM(latest valid approval facts) | derived projection |
| Net allocated | SUM(receipt allocations) − SUM(valid reversal allocations) | derived projection |
| Outstanding | approved total − net allocated | derived projection |
| Batch status | submission／approval facts 與 exact totals 的 reducer | derived projection |
| Import reconciliation | 正式 ledger event 直接連結 bank fact | cross-Domain result |

既有 `DECIMAL(...,2)` 是 compatibility storage；新命令只接受整數新台幣，任何小數
government amount 均 fail closed 並送異常中心。

## 3. 不變量

1. Claim item 必須綁定同一案件的有效 assignment、staff 與正式服務根事實；不得使用
   `orders.staff_id`、`planned_hours` 或 UI 計算結果。
2. `requested_amount = claimed_hours × frozen unit price`，送件後不可覆寫。
3. 政府核准不覆寫 requested facts；approval 以新事件保存。
4. receipt／return／reversal 與 allocation 一律 append-only。
5. 每筆 allocation 的 batch 必須同時等於 transaction batch 與 claim item batch。
6. 一般 receipt action 的 allocation 總額必須精確等於 receipt amount；政府溢撥專用 action
   則必須滿足 `claim allocations + government overpayment root = receipt amount`。reversal
   allocation 總額必須精確等於 reversal amount，且不得超過各原 allocation 尚未沖銷餘額。
7. reversal 只能指向 receipt；禁止 reversal-of-reversal。
8. `net allocated` 不得小於 0，也不得大於 approved total。
9. 全額撥款只在 `outstanding = 0` 時成立；退匯後依 ledger 重開 outstanding，不改寫
   原 receipt 或 approval。
10. 無法唯一判斷 batch 或 item allocation 時不得自動分配；產生
    `government_subsidy_review_required`，由人員在異常中心開啟 Preview。
11. Finance Import 的 `reconciliation_status` 只作 compatibility projection；正式答案
    是本 Domain ledger 對 `finance_import_row_id` 的直接關聯。
12. Query 與 Preview 零寫入；Apply 在同一外層 UoW 重新鎖定、重算並驗證。
13. canonical 政府入款超過所有已核准 outstanding 時，已核准範圍可正常 allocation；超額
    必須建立獨立 overpayment root，不得使 claim `net allocated` 超過 approved total。

## 4. Subsystems

### 4.1 Claim Batch Planning

- `PreviewGovernmentSubsidyClaimBatch`
- `ApplyGovernmentSubsidyClaimBatch`
- `SubmitGovernmentSubsidyClaimBatch`

由明確服務根事實建立 revision candidate。Preview 顯示逐 assignment hours、unit price、
整數 requested amount 與總額；Apply 建立 batch/item roots；Submit 追加送件事件並凍結
requested snapshot。

### 4.2 Approval

- `PreviewGovernmentSubsidyApproval`
- `ApplyGovernmentSubsidyApproval`

人員依政府公文逐 item 輸入核准整數金額。Apply 追加 approval event、重建 approved
projection；不得修改原 requested amount。

### 4.3 Receipt Reconciliation

- `PreviewGovernmentSubsidyReceipt`
- `ApplyGovernmentSubsidyReceipt`

Finance Import 傳入 canonical bank fact identity、amount、date 與唯一分類證據。本 Domain
鎖定 batch/items 後建立 allocation candidate。只有「唯一 approved outstanding batch，
且 allocation 可由 approved outstanding 唯一決定」才可自動提出完整 candidate；其他
情況回 review-required，不建立部分 ledger。

### 4.4 Manual Allocation

當 partial receipt 或多個 item 都可能承接款項時，人員明確選擇每筆 item allocation。
後端只接受 item identity＋整數 allocation intent，重新驗證同 batch、outstanding 與總額
守恆；不接受前端傳入 batch status、paid amount 或 remaining amount。

### 4.5 Return／Reversal

- `PreviewGovernmentSubsidyReversal`
- `ApplyGovernmentSubsidyReversal`

以原 receipt identity 與要沖銷的原 allocation identities為根。Apply 追加 reversal
transaction、逐筆 reversal allocation、重建 net allocated／outstanding 與 batch status。

### 4.5.1 Government Overpayment Disposition

當 canonical government incoming bank fact 大於選定 approved outstanding 時，使用專用
`Preview／ApplyGovernmentSubsidyReceiptWithOverage`，不得走一般 receipt action。

同一 outer UoW 必須：

1. 保存完整 canonical incoming bank fact 與全額 government receipt ledger；
2. approved outstanding 範圍內建立正常 claim allocations；
3. 差額建立 `government_subsidy_overpayment` root 與 anomaly；
4. 保存 bank fact、receipt ledger、allocated claims 與 overpayment identity 的 immutable lineage；
5. 不得把差額寫入 Client Finance、Staff Payables 或任一 claim approved amount。

`government_subsidy_overpayment` 最少保存：`overpayment_identity`、來源 bank fact、來源 receipt
ledger、government payer identity、original／remaining amount、status、version、current event、
actor、reason、evidence 與可選的 selected disposition target。狀態機：

```text
pending_review
  ├─ authorized offset decision ─> offset_reserved ─> offset_applied
  └─ authorized return decision ─> return_payable ──canonical outgoing bank fact reconciled──> partially_returned／returned
```

#### Government payer 與退款帳戶主檔（2026-08-11 裁決）

目前唯一合法付款方固定為 `hccg`／「新竹市政府」。Finance Import 對台新入款 memo 含
「新竹市政府」時，分類為 Government Subsidy 並指向此 payer identity；一般補助入款不需要
政府退款帳戶。

`government_payers` 是 singleton master；`government_payer_receiving_accounts` 是其有效期間
帳戶歷程。退款帳戶可長期不存在。只有人員在 `GOVSUB-006` 選擇「建立退還政府應付」而無有效
帳戶時，異常中心的同一 typed form 才能讓具 system-admin 權限者新增／更新帳戶。

- 不建立日常「資料維護」分頁；不在一般銀行匯入、補助申請或應付清冊中編輯此主檔；
- 新增帳戶必填 bank code、account number、account name、effective date、reason、evidence；
  舊資料不得原地覆寫，改以關閉舊有效期間後新增版本；
- `ApplyGovernmentSubsidyOverpaymentReturn` fresh-read 取得唯一 active account，並將完整帳戶
  fingerprint 與遮罩 display 值 snapshot 到政府退還應付；帳戶空白時 Preview fail closed，回
  `government_subsidy_recipient_account_missing`；
- offset 一律使用 fixed payer identity `hccg`，因此不再依 UI 或自由文字猜測付款方。

#### Offset 規則

- `Preview／ApplyGovernmentSubsidyOverpaymentOffset` 只接受 overpayment identity 與明確的 claim
  batch/item targets，不接受前端傳入 remaining 或 resulting status；
- target 必須已正式 submitted、approved、同一政府付款方且仍有 outstanding；draft、未核准、
  不同政府付款方或不唯一時不得 reserve／apply；
- 尚無合法 target 時維持 `pending_review`，不能先猜測未來案件；
- offset allocation 使用原 overpayment credit，不新增虛構銀行 receipt；
- allocation 總額不得超過 overpayment remaining 或 target outstanding；
- 一次 offset Apply 必須配置完整 overpayment remaining；可依明確順序分配多個 target，最後一個 target 只在 overpayment 原始可用餘額小於其 outstanding 時形成一次 partial allocation。不得由人員任意保留 overpayment remaining，也不得對同一 overpayment／claim item 反覆追加第二次 partial offset；原始匯款金額不足只表示最後一筆 allocation 小於 target outstanding，overpayment credit 本身仍須在該 Apply 歸零並進入 `offset_applied`；
- 同一 overpayment credit 不得同時成為 return payable。

#### Return payable 規則

`Preview／ApplyGovernmentSubsidyOverpaymentReturn` 需人工選定有效政府收款資訊 snapshot：
agency identity/name、bank code、account number masked/display value、account fingerprint、effective
date、due date、法源／核准 evidence reference。Apply 建立獨立
`government_overpayment_return` payable obligation；不得使用 client refund 或 staff payable 表示。

該 obligation 是系統唯一可交會計的「政府退款單」，可進下一期應付明細，列型別固定為
`government_overpayment_return`，輸出 remaining、government recipient snapshot、來源
overpayment/receipt identity 與 due date。清冊是唯讀交辦資料，不命令、執行或推定會計已匯款。

2026-08-27 人工裁決：不採 offset 的政府入款溢撥，其差額一律建立退回同一 government payer
有效收款帳戶的 `government_overpayment_return` obligation；此低機率事件仍不得直接沖銷、轉入
Client Finance／Staff Payables 或留作未來 claim 的無主 credit。帳戶不存在或不唯一時保持
`pending_review` 並要求先完成政府收款帳戶主檔 Q/P/A。

會計可因緊急情況在清冊日期前先行於系統外匯款；系統只在後續匯入 canonical outgoing bank
fact 後，以退款對象的 canonical 收款帳戶與金額對回既有退款單，經
`Preview／ApplyGovernmentOverpaymentReturnReconciliation` 追加不可變對帳紀錄並更新 remaining。
退款單的 due date／明細產生日期不是配對條件；例如 7/15 退款單可由 7/1 的實際出款列核對。
若同一對象與金額有多筆合法退款單，Preview 必須要求人員選定唯一退款單；實際多匯不得增加
原 obligation，少匯保留 remaining。系統不得把「清冊生成」或「會計排程」視為付款事實。

若 canonical outgoing bank fact 已解析為政府收款帳戶、可唯一對應尚未結清的政府退款單，且
實際金額大於該退款單 remaining，Government Subsidy 必須投影 state-only `GOVSUB-007`。
它只保留實際出款、原退款單、超額與來源版本的不可變證據；不得部分核銷、不得自動建立新的
政府退款單、不得抵扣其他補助或 claim。人員仍由既有 Finance Import manual review 依另行核准的
命令處理；沒有這項命令時 alert 保持 active。

#### Disposition command contract

所有 disposition Apply 必須具 `government_subsidy.overpayment.disposition` capability，並接受
expected overpayment version、Preview fingerprint、stable idempotency key、actor、reason、evidence
與 correlation id。Apply 鎖定 bank row、receipt、overpayment、targets、recipient snapshot 與
active anomaly，fresh rebuild 後同交易寫 events／allocations／payable、CAS version、outbox、receipt。
不同 payload 重用 key、已 disposition、stale target 或跨付款方一律 conflict，零部分寫入。

### 4.6 Query

- batch cursor list；
- batch summary；
- item allocation detail；
- immutable transaction／reversal timeline；
- bank fact reference；
- blockers、review facts 與 available typed actions。

所有 Query bounded、遮蔽敏感銀行資訊且不觸發狀態轉移。

## 5. Modules

| Module | Input | Output／不變量 |
|---|---|---|
| ClaimBatchIdentity | year、quarter、revision | deterministic identity；quarter 1–4 |
| ClaimItemSnapshotBuilder | official assignment service facts、rate | frozen integer request snapshot |
| ClaimTotalReducer | item snapshots | exact integer total |
| ApprovalValidator | request snapshot、approval facts | 每 item nonnegative integer、總和守恆 |
| ReceiptEligibility | canonical bank fact、approved batches | unique candidate 或 typed review |
| AllocationValidator | receipt、batch、item outstanding | same-batch、positive integer、exact total |
| ReversalEligibility | source receipt／allocations、existing reversals | only receipt target、remaining limit |
| NetAllocationReducer | immutable allocations | receipt minus reversal，範圍 `0..approved` |
| BatchStatusReducer | submit／approval／net allocation | draft／submitted／approved／partially_paid／paid |
| PreviewFingerprint | versions、bank identity、candidate、contract version | deterministic hash |

Modules 為純函式，不讀 DB、clock、FastAPI、Streamlit 或 Finance Import repository。

## 6. Ports 與交易

必要 ports：

- `GovernmentSubsidyClaimFactsPort`
- `OfficialAssignmentServiceFactsPort`
- `GovernmentSubsidyBankFactPort`
- `GovernmentSubsidyLedgerPort`
- `GovernmentSubsidyAllocationPort`
- `GovernmentSubsidyReceiptPort`
- `GovernmentSubsidyOutboxPort`
- `GovernmentSubsidyAnomalyPort`

Government Subsidy 的 receipt Apply 成功後，必須在同一交易寫入逐 claim-item 的
`GovernmentSubsidyReceiptAllocated` outbox fact。該 fact 供 Client Finance 建立工會
墊付款的 recovery settlement link；它不是客戶退款命令，也不得直接修改
`client_payments`、client obligation 或 client ledger。

Finance Import Apply 的 outer transaction：

```text
lock Finance Import command／bank fact
→ append classification event
→ call GovernmentSubsidyReceiptPort with borrowed UnitOfWork
→ lock claim account／batch／items／source receipt as required
→ fresh rebuild candidate
→ append government transaction＋allocations
→ CAS aggregate version and projections
→ append Government Subsidy outbox
→ save Finance Import reconciliation audit／receipt
→ commit once
```

任何 validation、stale、ledger、allocation、outbox 或 receipt failure 均使整筆 rollback。
內層 repository 不得 commit。

## 7. Typed API

```text
GET  /government-subsidy/claim-batches
GET  /government-subsidy/claim-batches/{batch_id}
POST /government-subsidy/claim-batches/preview
POST /government-subsidy/claim-batches/apply
POST /government-subsidy/claim-batches/{batch_id}/submit/preview
POST /government-subsidy/claim-batches/{batch_id}/submit/apply
POST /government-subsidy/claim-batches/{batch_id}/approval/preview
POST /government-subsidy/claim-batches/{batch_id}/approval/apply
POST /government-subsidy/receipts/preview
POST /government-subsidy/receipts/apply
POST /government-subsidy/reversals/preview
POST /government-subsidy/reversals/apply
POST /government-subsidy/receipt-overages/preview
POST /government-subsidy/receipt-overages/apply
POST /government-subsidy/overpayments/{identity}/offset/preview
POST /government-subsidy/overpayments/{identity}/offset/apply
POST /government-subsidy/overpayments/{identity}/return/preview
POST /government-subsidy/overpayments/{identity}/return/apply
```

Apply 只接受 intent、expected aggregate version、Preview fingerprint、actor、reason、
idempotency key 與 correlation id。不得接受衍生 totals、status、outstanding 或前端算好的
projection。

Stable errors：

- `government_subsidy_batch_not_found`
- `government_subsidy_batch_candidate_not_unique`
- `government_subsidy_claim_facts_invalid`
- `government_subsidy_assignment_facts_stale`
- `government_subsidy_approval_invalid`
- `government_subsidy_bank_fact_invalid`
- `government_subsidy_review_required`
- `government_subsidy_allocation_total_mismatch`
- `government_subsidy_allocation_cross_batch`
- `government_subsidy_allocation_exceeds_approved`
- `government_subsidy_reversal_target_invalid`
- `government_subsidy_reversal_amount_exceeded`
- `government_subsidy_overpayment_not_found`
- `government_subsidy_overpayment_target_ambiguous`
- `government_subsidy_overpayment_target_not_eligible`
- `government_subsidy_overpayment_already_disposed`
- `government_subsidy_return_recipient_invalid`
- `government_subsidy_overpayment_disposition_forbidden`
- `government_subsidy_version_conflict`
- `stale_preview`
- `idempotency_mismatch`
- `transaction_temporarily_unavailable`

只有最後一項可使用相同 idempotency key bounded retry。

## 8. Anomalies 與人工入口

至少提供：

- `GOVSUB-001`：銀行 government subsidy 無唯一 approved batch；
- `GOVSUB-002`：partial／ambiguous item allocation；
- `GOVSUB-003`：receipt／allocation／projection integrity 不一致；
- `GOVSUB-004`：reversal target 或剩餘可沖銷金額不一致；
- `GOVSUB-005`：claim item 與 assignment service facts 漂移。
- `GOVSUB-006`：政府入款超過 approved outstanding，等待 offset 或 return disposition。

異常中心顯示 bank fact、候選批次、item outstanding、既有 allocation 與合法 action。
人員 action 只能導航至本 Domain Preview，不得直接寫 allocation、paid amount 或 status。

### 8.1 Current anomaly owner decision matrix（2026-08-31）

共同 owner readback 以 Government Subsidy aggregate version、batch／item versions 與相關 immutable
ledger／allocation identities 形成 snapshot token，並回報 `authoritative_complete`。既有 Q／P／A
成功後在同一 outer UoW 寫入 bounded `anomaly.recheck` intent；Anomalies 不重算金額或修改
claim／ledger／allocation roots。

| Code／subject | Active predicate（current roots） | 唯一合法 owner operation | Completion predicate | Closed unresolved reasons |
|---|---|---|---|---|
| `GOVSUB-001` / `bank_fact_identity` | canonical government incoming bank fact 沒有唯一 approved outstanding batch，或尚未形成該唯一 batch 的完整 receipt allocation | `Preview／ApplyGovernmentSubsidyReceipt`；需人員指定 item allocation 時仍沿用同一 receipt Preview／Apply 的 Manual Allocation intent | bank fact 唯一綁定 approved batch，全額以合法 claim allocations 或已核准 overage disposition 守恆，receipt／allocation／projection 一致 | `approved_batch_not_unique`, `receipt_allocation_incomplete`, `amount_not_conserved`, `owner_readback_incomplete` |
| `GOVSUB-002` / `bank_fact_identity + batch_id` | batch 已唯一，但 partial receipt 或多個 item 候選使 allocation 無法由 approved outstanding 唯一決定 | `Preview／ApplyGovernmentSubsidyReceipt` 的 Manual Allocation intent；人員只提供 item identities 與整數 allocation | selected items 同 batch、不超過 outstanding，且 allocations 總額與 receipt amount 精確守恆 | `item_allocation_ambiguous`, `item_outstanding_exceeded`, `allocation_total_mismatch`, `owner_readback_incomplete` |
| `GOVSUB-004` / `reversal_bank_fact_identity + source_receipt_id` | reversal target 不是唯一合法 receipt／allocation set，或 reversal amount 與可沖銷 remaining 不一致 | `Preview／ApplyGovernmentSubsidyReversal`，綁定 exact original receipt 與 selected original allocation identities | 只追加合法 reversal transaction／allocations；總額等於 reversal amount、不超過各原 allocation remaining，net allocation 與 batch status 一致 | `reversal_target_ambiguous`, `reversal_target_invalid`, `reversal_amount_exceeded`, `reversal_allocation_incomplete`, `owner_readback_incomplete` |

2026-08-31 supersession：

- `GOVSUB-003`：immutable roots內部有效且只有derived projection漂移時可deterministic rebuild；已有
  typed reversal/correction語意時只沿用該existing append-only owner command；root structural conflict
  fail closed，禁止generic compensation。
- `GOVSUB-005`：frozen claim item immutable。未submit draft與已submit claim均以Government Subsidy-owned
  versioned successor/correction lineage承接，exact綁original claim item及fresh Scheduling snapshot
  identity/token/version；既有approval／receipt／allocation不得靜默搬移或改寫。
- `GOVSUB-007`：合法退款部分核銷existing return obligation，actual超額部分建立Government-owned
  versioned append-only recovery root；未來只由canonical incoming bank fact typed reconciliation核銷。
  目前lawful payout workflow固定自行commit且拒絕`actual > remaining`，所以原子建立路徑維持
  `BOUNDARY_REQUIRED_GOVSUB007_ATOMIC_EXCESS_UOW`；existing recovery readback/reconciliation可獨立完成，
  不得用兩次commit、直接SQL、Client Finance抵扣或write-off冒充建立成功。

```yaml
convergence:
  status: READY
  ready_requirement_ids: [GOV-ANM-001, GOV-ANM-002, GOV-ANM-003, GOV-ANM-004, GOV-ANM-005, GOV-ANM-007-READBACK, GOV-ANM-READBACK]
  acceptance_ids: [GOV-ANM-ACTIVE, GOV-ANM-OWNER-QPA, GOV-ANM-AMOUNT-CONSERVATION, GOV-ANM-TERMINAL, GOV-ANM-FAIL-CLOSED]
  excluded_authority_required: []
  blockers: [BOUNDARY_REQUIRED_GOVSUB007_ATOMIC_EXCESS_UOW]
```

## 9. Legacy 遷移

可保留並吸收：

- `subsidy_claim_batches`
- `subsidy_claim_batch_items`
- `government_subsidy_transactions`
- `government_subsidy_allocations`

但必須 additive 補齊 aggregate version、immutable submit／approval events、apply receipts、
outbox、整數 contract 與 append-only triggers。既有 rows 先做 read-only backfill／驗證，
不得覆寫歷史金額。

下列路徑必須退出：

- `services/government_subsidy_reconciliation.py` 的自行 commit／直接 projection update；
- Finance Import legacy dispatcher 直接寫政府補助表；
- 任何以金額唯一相等就直接過帳、卻沒有 Preview fingerprint／人工 review 的 fallback；
- UI 直接修改 batch paid amount、status 或 allocation。

Government Subsidy 新 owner migration 已完成；若正式 repository、schema 或 typed command
依賴缺失，`government_subsidy` Apply 仍必須 fail closed，不得回退至舊 reconciliation writer。

## 10. pytest 驗收

### Module

- 整數 requested／approved／allocated／outstanding 守恆；
- partial receipt、multiple batches、ambiguous items 形成 review；
- 一般 receipt、reversal allocation exact total；溢撥 receipt 則驗證
  `claim allocations + overpayment root = bank amount`；
- 禁止 reversal-of-reversal 與超額沖銷；
- deterministic status／fingerprint。

### Subsystem

- Query／Preview 零寫入；
- Apply fresh rebuild、stale、version、idempotency mismatch／exact replay；
- partial failure at transaction、allocation、projection、outbox、receipt 時整筆 rollback；
- borrowed outer UoW 不自行 commit；
- 人工 allocation 修正後同一 bank fact 正式入帳。
- overpayment disposition 的 offset／return 互斥、stale target、capability、idempotency 與
  transaction rollback。

### Domain

- 隔離真實 MySQL 驗證 FK、same-batch constraint、unique import row、append-only trigger、
  CAS、concurrent Apply、reversal 與 exact replay；
- 多筆 government receipts 對同批次 partial→paid；
- reversal 後 paid→partially_paid／approved 的正確重開；
- 溢撥 root 的 pending_review→offset_reserved／return_payable，以及 partial return remaining；
- legacy backfill 不改 requested／approved 歷史。

### Global

- 真實格式 Excel → Finance Import classification → Government Subsidy Preview → 人工確認
  → Apply → ledger／allocation／receipt／outbox；
- 無唯一批次時只進異常中心且零正式 ledger；
- correction 後 Apply、timeout replay、projector pause／recovery 不重複交易；
- Government Subsidy 與 Client Finance 各自帳務不互相抵銷。
