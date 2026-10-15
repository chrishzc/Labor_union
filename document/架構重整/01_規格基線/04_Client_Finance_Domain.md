# Client Finance Domain

## 1. Domain 責任

擁有客戶付款條款、訂金／各期款／adjustment／退款／補助退還義務、不可變正式交易與 allocation、核銷 Preview／Apply、超收與退款義務，以及 current balance／settled projection。

不擁有 Orders lifecycle、assignment、正式服務日、客戶身分根值、銀行原始流水或 Alert workflow。

## 2. SSOT

| 資料 | 唯一權威 |
|---|---|
| 付款條款與到期日 | `PaymentTerms` root facts |
| 本案專屬虛擬帳號 | 現行案件由 canonical 9 碼案件編號依 Finance Import 規則確定性產生；舊流程案件可保存實際虛擬帳號對照 |
| 應收／退款／補助退還義務 | append-only obligation events |
| 收款／退款／adjustment／reversal | immutable client ledger |
| transaction allocation | append-only M:N allocations |
| current balance／settled at | obligation 與 ledger reducer |
| 客戶代墊／補助退還／資金回收 | 一般服務費 receivable 與 receipt、服務完成後的 immutable `subsidy_return` obligation／payout，以及 Government Subsidy receipt-allocation fact 的 M:N settlement link |
| `client_payments` | current／compatibility projection |
| review status | root-derived projection，不可人工直接修改 |

每次正式核銷必須完整分配所選銀行流水，且每個所選義務在同一次 Apply 後精確為 `0`。少收、超收、錯案或 ownership 不明不得建立部分正式交易。

## 3. Subsystems

### Payment Terms／Obligation Planning

簽約與應收用詞依第 `21` 份正式規格 §1.1：使用「所有月嫂簽約完成」與「客戶簽約完成」；應收不分正式／非正式，尚未建立應收時僅稱預估金額。

依 Orders Terms、服務日根事實及費率政策建立訂金、第一期、第二期及調整義務。樓層費只計入一次。條款變更只重算未核銷義務；已核銷差額建立 adjustment 或 refund obligation。

2026-10-13 第二期繳款日人工裁決：第二期有應付金額時，Client Finance stage plan 的預計繳款日
固定為第一期款預計入帳日（`first_payment_due_date`）加 15 個曆日；第二期金額為零時不產生日期。
計算不等待第一期實際入帳，也不使用實際核銷日期。訂單資訊、候選／推薦寄送前預覽及契約共用此
owner 計算結果；既有保存的第二期日期不取代本公式。預覽零寫入；未結清義務日期的正式異動仍經
既有 Preview／Apply，已核銷交易與已簽文件不由預覽改寫。

2026-10-13 第二期日期保存裁決：案件初始化正式 Apply 將上述 owner 計算結果保存至
`client_payment_terms.second_payment_due_date` 與初始付款條款事件；期款應收建立或重算時，
同一 outer Unit of Work 同步此欄位與新的 immutable payment-terms event，並使用同一 stage plan
寫入義務日期。第二期金額為零時保存 NULL；查詢與預覽保持零寫入，既有日期補正須走正式 writer。

2026-10-13 條件變更同步裁決：已有付款條款且尚無正式指派／既有帳務義務的案件，修改預計開始日、
服務天數、每日時數或樓層費時，Terms Preview 以新條件重算預計付款階段；正式 Apply 同步有變化的
付款條款與 immutable event。第一期預計日隨預計開始日更新，訂金沿用已保存期限且不得晚於新開始日；
第二期有金額時為第一期預計日＋15 天，無金額時保存 NULL。對尚無既有應收的案件，此條件變更只保存條款，不提前建立應收；
預估金額讀取最新 Orders 與 Finance facts。已有正式指派的條款異動沿用既有應收重算流程，
同步使用新的預計日期，不覆寫既有收款、核銷或簽署 evidence。Finance 日期有異動時納入版本／fingerprint
與同一 outer Unit of Work；與付款計算無關的修改不新增 Finance／Payroll 依賴。

既有案件修改付款相關條件時，即使尚未建立執行 assignment、但已有客戶期款應收，也須經同一
Terms Preview／Apply 重算既有期款及保存付款條款日期。優先沿用 current confirmed service dates
或此次正式替代日期；尚無確認日期時使用 Orders 約定服務量。只異動已存在的期款，不因補正
提前建立應於客戶簽約完成時才建立的第一期／第二期應收。未核銷期款沿原 identity 更新金額及日期；已核銷
依既有 owner 差額規則追加 adjustment／refund，保留 ledger、allocation 與已簽 evidence。
缺漏／過期的第二期條款日期在此次 Apply 由同一公式補正；日期事件、Finance 版本、Terms receipt
與 Orders 更新同交易保存。未指派案件的差額 identity 綁定此次 Orders 版本，不因空 generation 重用。
不完整 Finance roots、未指派卻已有 Payroll 義務及既有 nonstage 帳務限制仍維持 typed conflict。
修改後的候選付款 Query 使用 current Orders 確認／預計服務日期與同一 Finance stage plan，
不因舊媒合方案期間已過期而抹除付款資訊，也不借用舊 commitment 的服務量。一般完整契約
查詢與正式簽署保留其原有方案／commitment 過期驗證；Query 不寫入日期、義務或簽署資料。

使用者介面一律稱為「客戶應付」，意思是客戶應付給工會的金額；內部既有 accounting
`receivable` 型別可保留。服務本金公式固定為 `有效正式服務時數 × 有效服務單價`，雙胞胎為
每小時 450。服務前的合法胎數更正必須在同一交易同步付款條款與所有 open 義務；已核銷金額
不得覆寫，差額形成 adjustment 或 refund。正式服務開始後不得再變更胎數，完工確認當下即凍結本金。

一般市民遇工會突發狀況時，system admin 可經專用 Preview／Apply 人工允許案件在訂金尚未付清時繼續後續流程。此入口不得自動執行，且不適用低收入戶、中低收入戶或非市民；Apply 必須保存 actor、明確原因、idempotency receipt 與 immutable payment-terms event。放行不修改訂金服務天數、金額、義務或 `deposit_settled`，而是以獨立 typed override 經 durable outbox 交由 Orders 正式 writer 將仍在 `洽談中` 的案件推進為 `訂單成立`；Scheduling 只讀此 override，不得自行改寫 Orders。Operational Stage 必須將訂金關卡標為完成並顯示「定金未付，已人工放行」，不得誤標為已核銷。後續付款仍走既有核銷流程，payment terms 的下一次正式變更會使既有放行失效並要求重新確認。

LINE 第三方服務群組不接受上述未付款放行取代核銷；只有
`client_deposit_settlement_projection.settlement_state = settled` 才能綁定群組或發送邀請。

第 `27` 份正式規格的歷史 lifecycle branch 可用每位月嫂已確認 `actual_service_days` 的總和取代逐日
服務日期作為歷史服務量來源；Client Finance 仍自行擁有費率、補助、自費、樓層費、obligation direction
與核銷。歷史服務量可少於或大於原合約天數，既有已核銷金額差異只能追加 adjustment／refund，不得
覆寫 immutable ledger。

依第 `21` 份正式規格，所有月嫂簽約完成時建立訂金應收（deposit obligation），只建立一次，
使用同時保存的 commitment 精確服務日、時數、費率與樓層費計算。客戶簽約完成時，
Contract Completion 保留該 deposit identity、金額、ledger 與 allocation，建立其餘尚未建立的
期款應收；不得重建、重複計入或因客戶晚簽而撤銷已合法核銷的 deposit。

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

取消不加收取消費。服務中取消以已確認實際服務時數重算服務本金；訂金、第一期及其他已正式
核銷款項均依 allocation reducer 計入 `current_settled_amount_ntd`，不得只扣其中一期或重複收取。
已收總額大於實際應付時建立退款，小於時才形成補收。

缺少 direction、direction_amount 與 direction 不一致、或 current owner readback 不能唯一確認
方向時，Query／Preview／Apply 回 typed schema／domain error 或 `outcome_unknown`，不建立或
變更正式交易；不得 fallback 成 action kind 或以正負號猜測。舊 caller 若無法驗證該欄位，只能
顯示 schema-drift／unavailable。相同 idempotency identity 的結果重查後，receipt／readback 必須
保留同一 direction。

2026-09-11 人工裁決把補助市民訂單分為兩條互斥路徑：

- **全補助案件**：補助市民訂單的有效正式服務時數不超過 120 小時，且沒有樓層費或其他客戶應付，故衍生 `client_payable_amount = 0`；客戶不需代墊或支付服務薪資，也不建立 `subsidy_return`。實務申請通常排滿 120 小時，但不是必要條件。
- **非全補助的補助市民訂單**：客戶依正常付款條款先代墊完整服務薪資及其他客戶應付項目；補助額不得在服務前或服務中抵減 client receivable。服務正式完成後，才依補助資格、有效服務時數上限與凍結補助單價另建退給客戶的 `subsidy_return`。

兩條路徑都不得把同一月嫂報酬拆成「政府補助／雇主自費」兩段。超過 120 小時或仍有任何客戶應付，就不是全補助案件。樓層費及其他非補助項目永遠由客戶負擔，且不計入補助退還額。

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

### Historical Payment Evidence／Settlement（2026-08-28 人工裁決）

對使用系統前且已正式採納的 historical case，付款與本 Domain 結清仍須依方向分開：客戶付款給
工會只清償 `receivable_from_client`；工會一般退款給客戶只清償 `payable_to_client/refund|adjustment`；
工會退還客戶補助款只清償 `payable_to_client/subsidy_return`。客戶補助退款的收款人是客戶，屬本
Domain；不得投影成 Government Subsidy 或 Staff Payables 已完成。

首要證據是 Finance Import 匯入的 canonical bank facts，能正常核銷時固定走既有 reconciliation。
舊銀行／帳務證據缺失、歸屬不明或無法可靠還原時，才允許歷史人工 `paid | settled` Q/P/A；它必須
綁定 historical adoption、payer/payee/direction 與 exact obligation identities，並保存 actor、reason、
evidence、版本、fingerprint、idempotency、receipt及outbox。未知付款日期保存 null／unknown，不得用
匯入日或操作日補值。這是替代 evidence source，不是 generic balance editor，也不得偽造 Finance Import
row、bank allocation或另一帳務方向。

`paid` 是特定付款方向與義務的 payment fact；`settled` 是本 Domain 選定 obligations 的合法歷史處分。
兩者都不能推定 Staff Payables 或 Orders Step 11完成。後續退款、退匯、reversal、服務／金額更正或新
obligation依strictly-newer owner event更新current projection，未被舊event exact綁定的義務保持open。
完整跨Domain契約見
`../02_決策與退役執行記錄/PROV-20260828-historical-payment-and-owner-settlement-spec.md`。

### Immutable Ledger／Reversal

原交易永不 UPDATE。reversal 指向同 case、同 obligation kind、同 ledger 的原交易；不得超過仍可沖銷餘額。

已確認禁止 reversal-of-reversal。若 reversal 疑似錯誤，系統先產生異常警報並停止自動修復，顯示原交易、reversal、有效淨額、受影響義務及合法 recovery actions。只有人員確認實際情況後，才可透過 Client Finance Preview／Apply 新增反方向 adjustment；不得由 projector、scanner 或 ledger reducer 自動補 adjustment。

### Over-receipt／Customer Refund

義務合法下降造成有效實收大於新義務時，差額形成 `over_receipt` 與退款義務。退款後淨應收與淨實收同減；銀行撤銷原收款而義務未降低則是 reversal，重新形成應收。退款不取消已完成訂單，也不解除服務資料鎖。

### Client Subsidy Return

功能已啟用，且與客戶服務費 ledger 分離。它是「工會對客戶的應付」，不是
政府對工會的應收，也不得以 `client_payments.subsidy_refund_*` 作為事實來源。

本節只適用於已由客戶代墊的非全補助案件；全補助案件因客戶未支付服務薪資，不建立 `subsidy_return`。客戶先支付的完整服務薪資是一般 Client Finance receivable／receipt；在服務尚未終結前不得建立、預付或核銷 `subsidy_return`。正式完工，或中途取消且實際服務時數已確認後，待該次重算的客戶服務費已收齊、補助資格可唯一確認，才建立一筆對客戶的補助退還義務。這筆退款不改寫原客戶收款、不抵銷月嫂應付，也不代表政府已撥款。

```text
退還義務
= min(補助時數上限, 有效正式服務時數) × 凍結補助單價
```

雙倍日不增加退還額。只有服務已完工，或中途取消的實際時數已確認，且客戶服務費收齊、資格符合時建立；帳戶不唯一、
少退、超退、退匯／沖正都進異常，不改義務。

#### 客戶補助退款案件查詢（2026-10-01 人工裁決）

「客戶補助退款」是案件查詢，不是僅限已建立 `subsidy_return` 的付款清單。所有具補助資格、需由客戶先付款的未取消案件都可查詢；全補助且客戶不需付款、非補助資格、已完成補助退款的案件不列入待退清單。使用者不需逐案手動建立退款義務才能查詢。此查詢不更改前述正式退款建立、客戶款收齊、銀行出款或取消帳務規則。

- 已存在正式退款帳務時，金額與日期以 Client Finance owner projection 為準；缺少收款帳戶不使案件從查詢消失。
- 尚未建立正式退款帳務時，使用既有補助時數上限、有效服務條件及案件凍結付款條款單價呈現明示的「預估」金額；歷史實際服務量已有正式 projection 時優先使用。無足夠條件時保留案件並呈現金額待確認，不以零冒充。
- 日期只有已結案的實際結案日期或正式退款日期可提供；依既有結案月加兩曆月的 15 日規則呈現。未結案為待結案，不使用預定結束日期冒充實際日期。
- 預估清單不是正式應付帳款或已收款證據。正式退款仍需經既有 owner writer；查詢零寫入、無 commit、無外部效果。每次退款一次全額退清，不顯示已退／剩餘金額或自行推算到期狀態。
- `GET /api/v1/finance-reports/client-subsidy-returns` 使用管理員權限，支援 bounded `page_size`（1～200）、`after_case_no`、案件／客戶搜尋、exact `case_no` 與選用的應退款月份；預設不以月份隱藏案件，月份篩選只列已確定日期。typed view 僅輸出案件、客戶名稱、訂單狀態、金額、日期、預估標記與下一頁游標，不輸出銀行帳戶或其他個資。
- 畫面一次顯示全部符合篩選條件的結果與完整筆數／合計，不讓使用者逐頁查閱。前端自動取得既有 bounded API 的所有批次；例如同月 11＋2 筆須合併顯示 13 筆。任一批次失敗不把部分結果當成完整結果，條件變更或離開頁面須取消整次載入。

此案件查詢的 bounded implementation scope 為 Domain projection、Client Finance query、MySQL 唯讀 adapter、Finance Reports transport 與既有 FinancePage 補助頁籤，不改 schema、正式 writer 或付款流程。驗收須覆蓋無退款義務仍可查、取消與全補助排除、凍結單價／補助時數、未知金額日期、正式帳務優先、分頁搜尋與月份切換、實際 localhost GET／Browser 案件金額 readback。其 test roots 與 implementation paths 由 `client-subsidy-return-query` Arch Map leaf 及既有 presentation leaf 管理；完成上述驗收即停止此 slice。

#### 季度撥款與客戶補助退還

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

2026-10-14 人工裁決：已保留等待訂金檔期、但尚未建立訂金應收的案件，Client Finance
可提供 typed `UnreceivedDepositConfirmation`，確認沒有客戶帳務義務、義務事件或 ledger 歷史後，
允許 Scheduling 沿原 Release Preview／Apply 釋放檔期並換人。不存在的 settlement projection
本身不是未收款證據，不得補造零金額義務、結算、收款或退款；既有結算 projection 仍沿用原淨額門禁。
任何正式財務歷史存在而結算資料缺漏時，回 `deposit_receipt_unconfirmed` 並交財務核對，
不得把取消過的義務、退款或 reversal 歷史忽略成「未收款」。

此確認 Query 借用 Scheduling 外層交易，先鎖 Finance account，再完整讀取同案的義務、
義務事件與 ledger；不建立 account、不寫帳務、不自行 commit。account 不存在保留明示的
`None` 來源版本，與現存 version 0 區別；空根事實須由完整查詢確認，不能由缺列推定。
來源版本與確認事實納入既有 Release fingerprint；Apply 在同一交易重新查核，發現新收款、
義務或版本異動時拒絕釋放。成功的確認來源保存於 Scheduling 原檔期釋放事件，原 key 的
replay 回原操作，不重複釋放或新建財務事實。

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
- `QueryHistoricalClientPaymentRepair`
- `PreviewHistoricalClientPaymentRepair`
- `ApplyHistoricalClientPaymentRepair`

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
- `historical_client_payment_not_eligible`
- `historical_client_payment_direction_ambiguous`
- `historical_client_payment_obligation_binding_invalid`

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

## 8. 客戶收款帳號（2026-09-15 人工裁決）

- 每個案件的服務款項使用 Client Finance 擁有的專屬虛擬帳號，不得讀取 `staff_bank_accounts`，
  也不得以全域工會／代收付帳戶填入客戶契約。
- 虛擬帳號與 Finance Import 共用同一規則：固定前綴 `99781699` 加案件編號前三碼及後六碼轉為
  三碼序號；僅能表示後六碼數值不大於 999 的 canonical 9 碼案件編號。無法表示時必須 fail closed。
- Contract Signing 只消費 `client_virtual_account` typed projection；銀行核銷以相同規則解析帳號，
  並且只有在案件唯一且同案同金額的未清償應收義務唯一時才可自動配對，否則保留 pending。
- 舊流程虛擬帳號由管理員以含「虛擬帳號」與「市府訂單號碼」欄位的 XLSX 經 Preview／Apply 匯入；
  空白案件編號、格式不符與查無既有訂單的列直接略過，不建立 anomaly 或預覽錯誤。匯入對照是較公式
  推導更高順位的來源事實：收到的虛擬帳號只要存在匯入對照，核銷候選只取匯入對照，不得再合併公式
  候選；匯入對照唯一時直接解析該案件，對應多個案件時保留 pending。只有完全沒有匯入對照時，才可
  使用現行公式候選。案件對外顯示帳號亦採相同順位：唯一匯入帳號優先；同案存在多個不同匯入帳號時
  必須明確回傳不唯一，不得任選其一或退回公式。
- 既有版本化工會／代收付帳戶 Query／Preview／Apply 仍保留供其既有用途，但不再是客戶契約來源。

### 8.1 客戶名冊單案虛擬帳號修改（2026-10-15 人工裁決）

狀態：SPEC_READY；convergence：READY，無 blocking gap。Authority：使用者要求在客戶名冊新增修改功能，
並明確選擇「以新帳號取代本案原有匯入帳號，後續契約與收款辨識使用新帳號」。
同日最新人工裁決：「不用原因跟預覽功能」；單案修改直接儲存，不填原因、不執行人工或隱藏預覽。

- VA-01：有名冊寫入權限的管理人員可在案件詳細資料新增或修改「匯入虛擬帳號」。
  新值沿用既有 `99781699` 加六位數字的格式；內建帳號仍依案件編號產生，不可人工改寫。
- VA-02：Client Finance 提供 `GET /api/v1/admin/client-finance/cases/{case_no}/virtual-account`
  與同路徑的 `POST /apply`。Query 零寫入，回傳本案全部舊對照與 `mapping_ids`；Apply 不接受原因或 preview fingerprint。
  Apply 原子取代本案全部匯入對照，其他案件不變；禁止將已匯入對應其他案件的帳號指派給本案。
  無對照時可新增，多筆舊對照時可整理為單一新帳號；不提供清空或刪除帳號操作。
- VA-03：沿用既有匯入對照與公式順位。儲存後契約的下一次資料投影及收款辨識讀取新對照；
  不改寫已簽契約、歷史流水、核銷分配或對外發送文件。移除舊匯入對照不建立帳號停用清單，
  完全沒有匯入對照的帳號仍依第 8 節公式解析。
  已產生但未簽的客戶契約可依規格 21 的既有未簽 PDF 命令重新產生新版本，帶入新帳號；由 Contract Signing 擁有文件版本，不由帳號 writer 改檔。
- VA-04：現有對照無獨立 owner version；Query 回傳不可變 mapping row IDs 作為本案集合的版本依據。
  Apply 以 `expected_mapping_ids` 對照 fresh-lock 後的 current IDs，防止讀取後被另一個匯入／修改更換對照；
  不一致回 typed HTTP 409，不自動重試。空集合以空陣列表示，取代同值但 row IDs 改變仍視為 stale。
  不使用 Preview fingerprint／digest／snapshot token；使用既有匯入 writer 的同一互斥鎖，跨案占用亦在鎖內重查。
- VA-05：單一 outer UoW 同時保存對照與 `admin_command_receipts` 的 actor、reason、before／after。
  使用者不填原因；receipt 的 reason 固定記錄「後台客戶名冊虛擬帳號更新」。既有必填 `preview_fingerprint`
  儲存欄位填入同一 command digest，僅符合既有 schema，不代表預覽契約，也不作 concurrency 檢查。
  人工來源為 canonical 單列命令的 content digest，`source_row=2` 表示其標準表頭後第一列；
  receipt 的獨立 command family 區分人工修改與 XLSX 匯入，不假稱上傳過 workbook。
  同 key／command／actor 回原 receipt，異內容或異 actor 固定拒絕。
- VA-06：UI 只保留帳號輸入、取消與直接儲存；不提供修改原因、預覽或額外確認步驟。
  草稿、送出中、結果未明、已儲存但回讀失敗均沿用名冊關閉保護；stale 需重新讀取後再儲存。
  結果未明以同一 key 核對，成功後回讀帳號、名冊清單及詳情，才顯示完成。

驗收：VA-A1 無／單／多舊對照可改成單一新值且不影響他案；VA-A2 格式錯誤、查無案件、跨案占用、
stale 與異內容／異 actor replay 均拒絕且零 mutation；VA-A3 同命令 replay 不重做，receipt 保存失敗整筆 rollback；
VA-A4 契約及核銷沿用既有 resolver 消費新對照；VA-A5 UI 不填原因、不預覽即可直接儲存，回讀及結果未明關閉鎖可驗證。
來源：最新人工裁決＋第 8 節（格式／順位）＋Global 2.3（concurrency）＋既有 mapping／receipt schema（執行機制）。
本次僅授權本機程式、測試與規格變更；不含正式資料修改、schema migration、銀行／LINE 外部效果或部署。
