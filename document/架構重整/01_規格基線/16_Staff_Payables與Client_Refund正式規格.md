# Staff Payables 與 Client Refund 正式規格

> 2026-11-05 最新人工裁決：全額補助免自備依規格22 §17.4.1；補助市民／原住民且正式服務總時數≤本案有效補助上限，自動免自備、方案一、轉交月嫂。會計清冊須區分永豐／台新出款及月嫂／客戶對象，月嫂欄位顯示公會自訂編號＋姓名，完整契約及驗收見本文件 §2.5.4。文件階段之後，使用者已授權「執行程式修正、資料補登及修復後驗收」；實際通過範圍及7筆資料補登阻擋見[原工作包執行結果](../帳務工作台實作工作包.md#accounts-payable-excel-execution-20261105)。既有退款不得一律補快照當成已修復。

> 2026-11-05最新案件顯示裁決：依[22 §18](22_銀行流水匯入與帳務異常處理正式規格.md#finance-six-surfaces-ui-20261104)，四主入口保留，案件改精簡摘要與客戶繳款／人工補助方案兩區塊，全站抽屜沿客戶名冊同寬；期款通知含最近成功時間與按鈕，已齊／免繳鎖定。人工方案可提前保存，不改各期應繳、原金融事實或日期，款齊且保存後移出；問題帳務／核銷集中銀行對帳，補助與應付於案件結束後依原owner處理。舊三分頁與案件內核銷已取代，舊證據保留；正式接線／本機metadata升級及既有驗收結果見22 §18.10，政府報表沿原既有模板。**已取代，僅供歷史追溯**：當時「僅文件、正式程式／API／DB未修改」描述原規格交付階段；本輪文件清理不代表重新施工或發送通知。

> 2026-11-03 收付方案與核銷最新裁決：[`22` §17](22_銀行流水匯入與帳務異常處理正式規格.md#case-accounting-schemes-20261103) 為三方案、銀行來源與驗收契約，`04` §0.3／Payroll `03`／Government Subsidy `14` 各保留原 owner。永豐一般月嫂款 P永＋台新轉交月嫂補助 P台 合計清償案件總額，不在總額外再加付；永豐正常退客戶 R永 與台新退客戶先墊補助 R台 分開。台新出款不能一律視為客戶補助退款，必須確認真實對象。先檢查22 §17.4.1全額免自備例外，其餘款項未齊先不判、齊款且證據唯一才分類，分類不代替實際付款／退款核銷；政府直付客戶不產生工會待退款或對客戶收補助的追蹤責任。本次只修規格，不修改程式、API、資料或既有歷史證據；先前身分驅動的預估／自動應退條文不再決定新模型方案，既有期程及不可變交易不因本次自動改寫。

> 2026-11-02 差額認列、人工金額更正與政府整期差額的最新實作／驗證見 [規格22 §16.9.1](22_銀行流水匯入與帳務異常處理正式規格.md#accounting-differences-implementation-20261102)。本檔 2026-11-01 的「尚未實作／本次僅規格」為當時記錄，以該續作結果為目前狀態；bank／ledger／allocation 的不可變性與各 owner 歸屬不變。

> 2026-10-29 最新裁決：依規格04 §0新增獨立左側「帳務參數設定」及客戶名冊Drawer個案調整。新計價案件移除舊固定門檻全補助分類（2026-11-05明定例外另依22 §17.4.1），月嫂薪資可按來源分期：客戶負擔部分為服務結束月次月15日，直接補助部分為次次月15日。不得以實際入帳月份移動日期；分期總額與實付守恆，既有流水及已形成歷史資料不回寫。\n


<a id="payout-differences-20261101"></a>

## 0. 差額處理最新裁決（2026-11-01 核准；尚未實作）

跨帳務簡化流程、七種處理及驗收見 [`22` §16](22_銀行流水匯入與帳務異常處理正式規格.md#finance-differences-20261101)。在明示範圍內取代較早「差額僅顯示」與退匯操作設計；既有完成驗收不延伸至新增需求。

- 薪資／客戶退款由人員確認差額與處理方式。少付先記實付、餘額續付；超付保留全額出款，超額另列追償。原款結清不等於衍生款完成。
- 系統原應付有誤才更正：月嫂金額委派 Payroll `03` §0，客戶退款委派 Client Finance `04` §0.2；不修改對帳單。原金額正確但實付不同，仍走差額處理，不以降低原應付冒充付清。
- 直接核銷並認列差額須有已確認的適用規則，不能由特定追償非現金調整推論所有帳務均可任意計損益。
- **PAYOUT-ASSUME-01**（2026-11-01 已確認；尚未實作）：月嫂薪資多付與客戶退款多退均可選「工會承擔超付款，不再追回」，由人員確認承擔金額及依據後處理。Staff Payables 擁有月嫂超付追償；Client Finance 擁有客戶超退追償。原應付及實際全額出款不改，承擔另列，指定追償無剩餘且正式處理成立後顯示「已由工會承擔，不再追回」；原付款與追償紀錄保留，不自動扣其他案件／未來薪資，不補造收回款或新增第二筆出款。完整結果與驗收依 [`22` §16.3.4](22_銀行流水匯入與帳務異常處理正式規格.md#difference-union-assume-overpayment-20261101)；本次不修改實作或推定現有入口已支援。
- 歷史原因已確認無法查明，只記案件人工核銷並保留原差額與操作紀錄；該類案件排除實際金額統計，不補現金、不直接計損益、不推定另一 owner 或 Orders 完成；不等同原歷史付款 evidence／義務 settled。
- 不設退匯辨識或處置功能；下述 canonical return 綁原出款規則保留歷史事實及資料解讀用途，不再作為本次新增功能或驗收要求。既有 reversal 不一併刪除，API／writer 退役依正式 entry governance 及後續授權處理，本次不改程式／資料。
- 版本衝突、逾時及結果未明回原畫面處理，不另設操作異常業務章節，未明結果不重複核銷。其他細則見 `22` §16.7。

## 1. 文件狀態與裁決

- 狀態：`approved-architecture-baseline`
- 人工核准日期：2026-08-03
- Staff Payables 月結裁決：`confirmed-inherited`
- Client Refund 納入正式 Client Finance：`consolidated-decision`
- Client Refund implementation status：`proven`
- 2026-08-10 金流證據與超收裁決：`approved`
- 2026-08-11 差額付款與追償可執行契約：`approved`
- **已取代，僅供歷史追溯（2026-09-11）**：當時客戶代墊、月嫂整筆應付與服務後補助退還的 `reconfirmed-by-user` 紀錄；現行方案／分次付款依 `22` §17，原真實義務、核銷及已形成日期保留。
- 2026-10-29 案件帳務 UI、差額只顯示與共用警示：U12 已授權並完成本機程式及後端驗收；完整行為及證據見 [`22` §15](22_銀行流水匯入與帳務異常處理正式規格.md#finance-20261029)，仍沒有手續費核銷或自動結清授權。既有 `REFUND_OVERAGE` writer 的收據 enum 由 236／1058 append-only 補齊，不重定義退款／追償規則。
- 本文件覆蓋舊稿中「人工月結 aggregate」與「一般客戶退款 deferred／missing」的矛盾。
- 2026-08-03 原始核准只啟用 Inventory v2 evidence；後續 Commands、schema、pytest 與
  legacy exit 的實作，必須各自依人工核准的 decision／Work Package 授權。

### 1.1 共通金流證據邊界（2026-08-10 裁決）

- 系統只被動匯入銀行對帳單；canonical bank fact 是實際收款、付款、退匯或扣回的唯一
  現金根事實。
- 應付帳款清冊是每月 5 日交會計師的付款指示與封存快照，不是付款指令執行結果；產生、
  下載、封存或交付清冊都不得將 obligation、ledger 或提醒改為已付款／已退款／已完成。
- 所有實際付款結果都必須由後續匯入的 canonical bank fact 經 Preview／Apply 核銷後才
  改變。未看到流水不代表付款失敗，只表示仍待付款或待核對。
- 所有退款先建立退款單，再產生交會計的應付明細並等待對帳單。退款單的 due date／明細
  產生日期只服務排程，不是後續銀行列核銷條件；緊急先匯時，canonical outflow 仍以
  收款對象的 canonical 收款帳戶與金額（多筆候選時人工唯一選定）對回既有退款單。
- 金額或對象不唯一時，必須保留原始銀行事實與 typed anomaly；不得猜測 allocation、
  不得直接建立已付款紀錄，也不得重複列出可能已付款的義務。
- 「退匯」只指銀行已退回既有出款的後續銀行事實；客戶超收後交會計師處理的項目名稱為
  「客戶退款應付／退款清冊列」，不得混稱為退匯。

2026-08-28 successor例外：上述bank fact唯一現金根事實與exact allocation仍是一般／新案件及可正常
還原歷史交易的規則；它不排除`PROV-20260828-historical-payment-and-owner-settlement-spec.md`核准的
pre-system historical owner-specific人工付款證據。該例外必須保存獨立source kind、payer/payee/direction、
exact obligations與audit lineage，不得偽造Finance Import row或bank allocation，也不得跨owner推定結清。

## 2. Domain：Staff Payables

### 2.1 責任與 SSOT

Staff Payables 擁有：

- Payroll 已建立之 assignment-owned 月嫂應付義務的付款生命週期與投影；
- 正式銀行出款、退匯／沖正的 immutable ledger event；
- payout event 與 payable obligation 的 allocation／link；
- `payable | partially_paid | completed | recovery_required | anomaly` 衍生投影；
- 應付款清單、同月嫂彙總與 XLSX 歸檔。

Staff Payables 不擁有：

- 訂單狀態、服務日、薪資公式或義務初始金額；
- 客戶退款義務；
- 人工 month-end close、draft、finalized、revision 或 paid 月結狀態機。

### 2.2 根事實與衍生值

根事實：

1. Payroll 產生的 immutable staff payable obligation；
2. assignment identity、正式服務日與 rate snapshot；
3. canonical bank payout fact；
4. payout／return／reversal ledger event；
5. obligation allocation／link；
6. bank account identity snapshot；
7. aggregate version 與 idempotency receipt。

衍生值：

- 應付餘額；
- `payable | partially_paid | completed | recovery_required | anomaly`；
- 指定付款日應付款清單；
- 同一月嫂、同一付款日的 XLSX 聚合列；
- payout anomaly 與重新應付狀態。

`staff_monthly_settlements`、`staff_monthly_settlement_details`、
`staff_actual_transfers`、`staff_payment_transactions` 與
`staff_transfer_allocations` 只作歷史查詢／遷移來源，不得形成新流程依賴。
live `staff_payments` 若存在，只能是 canonical Payroll obligation 的 compatibility
projection，不得成為第二個義務 SSOT 或被 Staff Payables 反向改寫。

### 2.3 Subsystem：Payable Obligation Projection

責任：把 Payroll 已提交的 obligation event 投影成 Staff Payables root facts。

Modules：

- `StaffPayableObligationConsumer`
- `StaffPayableIdentity`
- `StaffPayableProjectionReducer`
- `StaffPayableVersionGate`

不變量：

- obligation identity 唯一且可重播；
- 金額為正整數 NTD；
- 來源必須綁定 assignment 與 rate snapshot；
- 來源事件重送不得建立第二筆義務；
- adjustment 建立新不可變 event／allocation，不修改舊義務歷史。
- 同一 assignment 的薪資權利及案件合計不得重複建立；合法資金來源分期及永豐 P永／台新 P台 分次付款可合計清償原應收。各筆款項沿既有 owner 及已形成到期日，不因新方案重新拆造超出案件總額的義務。
- 月嫂核銷依正式應付及真實付款，不由客戶身分或政府是否已入款推定已付。實際不足額仍依 §2.4.1 核銷實付、餘額待付。**已取代，僅供歷史追溯**：舊全補助／非全補助的身分分支及只能整筆支付限制不再套用；既有次月／第二月 15 日等 due date 保留，不批次改期。

### 2.4 Subsystem：Payout Reconciliation

Commands：

- `PreviewStaffPayout`
- `ApplyStaffPayout`
- `PreviewStaffPayoutReturn`
- `ApplyStaffPayoutReturn`
- `PreviewStaffPayoutReversal`
- `ApplyStaffPayoutReversal`
- `PreviewStaffPayoutDifference`
- `ApplyStaffPayoutDifference`
- `PreviewStaffOverpaymentRecovery`
- `ApplyStaffOverpaymentRecovery`

共同 Apply 交易：

1. 以 canonical staff mutex order 取得 lock；
2. 鎖定 aggregate version、bank facts、bank account snapshot 與 obligations；
3. 重建 candidate，驗證 Preview fingerprint 與 expected version；
4. 依事件別 guard 驗證；
5. append payout／return／reversal event；
6. append obligation links；
7. 更新 projection、version、outbox 與 receipt；
8. 由 outer Unit of Work 單次 commit。

HTTP Preview 的 `candidate` 必須是 closed typed public view（不可向管理端透傳
`dict[str, Any]`）；各 Apply route 回 `202 JobAccepted` 時只表示 durable command 已排入，
不表示付款、ledger event、allocation 或 resulting status 已完成。完成結果只能由後續 job
outcome／canonical bank fact 讀回判定。

事件別 guard：

- 一般 payout：選定銀行出款與選定 obligation 的當下剩餘款精確相等；
- payout difference：只允許已確認唯一月嫂、唯一銀行帳戶 snapshot 與同一付款範圍內的
  obligations；銀行總額可以小於或大於 obligation remaining，但每一元銀行出款都必須由
  payout allocation 或 overpayment recovery root 完整表達；
- return：必須指向一筆仍有效的 payout 與 canonical 銀行退匯入款，重開相同義務；
- reversal：必須指向一筆仍有效的錯誤 payout，不要求銀行入款，但要求人工 reason、
  operation capability 與不可重複沖正；
- return／reversal 都不得超過目標 payout 的尚未重開金額。

帳戶不一致、收款人不唯一或 allocation 不唯一時，整筆仍不得建立正式 payout，轉 typed
blocker／anomaly。只有金額差異且 ownership 唯一時，才可使用專用 difference action；
一般 payout action 仍維持 exact-only。

#### 2.4.1 公會對月嫂付款不足

公會實際出款小於選定 obligation remaining 時，先核銷實際付款，剩餘款繼續列待付。
後續補款沿同一 obligation 核銷剩餘款，不修改原應付全額或重複計算薪資。

2026-10-29 差額顯示補充：案件頁以應付減有效實付顯示手續費參考，不認列費用、不扣減 obligation，也不因差額在 100 元以內或人員解除警示而結清。少付超過 100 元及任何超付依 `22` §15.7–15.8 進共用帳務警示；恰好少付 100 元不觸發此新增門檻。這是顯示／警示契約，以下不足額核銷、remaining、補款、超額追償及原正式 owner 規則不變。

`ApplyStaffPayoutDifference(mode=underpayment)` 必須在單一 Staff Payables UoW 內：

1. append 每筆 canonical bank outflow 對應的 immutable payout event；
2. 依 obligation identity 順序 deterministic allocation，allocation 總額必須等於銀行總額；
3. 計算 `remaining = obligation_amount - net_valid_payout`，不得由 UI 傳入；
4. remaining 大於零時投影為 `partially_paid`，保留待付餘額；
5. 下一次應付清冊只輸出 remaining，不得重列原 obligation amount；
6. 後續新的 canonical outflow 可繼續清償 remaining；歸零才轉 `completed`。

銀行對帳的人工核對清單可從「處理月嫂付款」選取一位月嫂的待付款項，再進入「處理付款不足或超額」。使用已選取的銀行流水，不要求重新輸入流水編號；成功核銷後原流水不再列入人工核對，剩餘款仍列待付。新的足額補款流水按當下剩餘款自動核銷。

畫面可選「足額核銷剩餘款」、「付款不足，先核銷實付」及「付款超額，另列追收」。
不足額處理成功且重新讀取餘額後，才開放「繼續核銷剩餘款」；結果未明時保留原命令，不開新操作。
分次付款後的退匯／沖正只重開指定來源付款的金額，保留其他有效付款，再計算剩餘款。

不得因部分出款更新 Payroll obligation 原始金額，也不得建立第二筆薪資義務。清冊生成與
重新下載不改變 remaining。

#### 2.4.2 公會對月嫂付款超額與追償

公會實際出款大於選定 obligation remaining 時，`ApplyStaffPayoutDifference(mode=overpayment)`
必須：

1. 保存完整 canonical outflow 與全額 payout ledger event；
2. obligation 額度內建立 payout allocation，使原 obligation 歸零並轉 `completed`；
3. 差額建立獨立 `staff_overpayment_recovery` root，不能提高 Payroll obligation；
4. 保存 bank fact、payout event、obligation 與 recovery identity 的 immutable lineage；
5. 投影 `recovery_required` anomaly，且 recovery 不得進入應付清冊；
6. 不得自動從其他案件或未來薪資扣抵。

`staff_overpayment_recovery` 最少保存：`recovery_identity`、`staff_id`、來源 bank fact、來源
payout event、來源 obligation identities、原始追償額、remaining、status、version、actor、
reason、evidence 與 current event identity。狀態機為：

```text
open／partially_recovered ──canonical incoming return allocation；remaining>0──> partially_recovered
open／partially_recovered ──canonical incoming return allocation；remaining=0──> recovered
open／partially_recovered ──authorized adjustment──> adjusted
```

回收款只接受唯一月嫂與唯一 open recovery 的 canonical incoming bank fact。預設要求一次
足額收回；若實際入款不足，仍保存實收並降低 remaining，作為疏失補救。授權 adjustment
必須具 `staff_payables.recovery.adjust` capability、不可變 reason/evidence、expected version
與 idempotency receipt；不得由 UI 直接修改 remaining。

正常匯入的永豐退回入款，若交易參考帳號唯一對應月嫂主帳戶，保留帳號綁定及待人工處理分類，由人員明確配對至既有追償，再核銷實收。不得因舊的退回分類名稱未出現而拒絕正式銀行根事實；不自動收回、不把一般入款轉成月嫂付款，帳號不唯一或已使用的流水仍阻擋。

#### 2.4.3 Staff payout difference typed contract

Preview intent 只接受：bank fact identities、obligation identities、`mode`、evidence references。
Apply 另接受 expected aggregate version、Preview fingerprint、stable idempotency key、actor、
reason 與 correlation id。Preview 回傳：bank total、obligation remaining total、allocations、
remaining payable、recovery amount、resulting states 與 blockers。

金額關係必須與 mode 一致；`underpayment` 要求 `bank_total < remaining_total`，`overpayment`
要求 `bank_total > remaining_total`。相等時必須改走一般 payout action。stale、已使用 bank
row、跨月嫂、帳戶不唯一或 mode 不符時零正式寫入。

### 2.5 Global／Application Subsystem：Accounts Payable Query／Export

本 Subsystem 置於本文件是為了記錄帳務來源契約；正式 owner 是跨 Domain
read-only reporting application，不是 Staff Payables Domain。它只能透過 Staff Payables
與 Client Finance typed view ports 組合輸出，不擁有 ledger 或付款狀態。

清冊及業務流程說明使用「月嫂應付款」「客戶退款單」，不使用「義務」作為款項名稱；內部 `obligation`、資料表、API、事件名稱與付款規則維持原名（2026-10-15 用詞裁決）。

月嫂應付款與客戶補助退款的建立時點不同：

- 月嫂應付款：排班成功建立時，由 Payroll 計算並保存；僅確認日期或排班作業尚未成功，不視為已建立。後續合法排班／條件修改依同一 owner 重算。
- 客戶補助退款：依本案已確認方案、客戶應退對象及正式來源，由 Client Finance 提供應退 projection；既有義務沿合法服務／帳務更正及原日期更新，資料不足保留待確認。**已取代，僅供歷史追溯**：舊案件計價資料及日期足夠即自動建客戶退款、不待服務費收齊的路由。客戶各期未齊不判方案，但已確認真實交易仍可核銷。
- 應付清冊：查詢時才把上述已建立、符合付款日與未清償條件的款項彙整成明細；預估補助金額不能當成待付款明細。

清冊查詢前的來源步驟與納入條件：

| 款項 | 從哪個步驟已有資料 | 清冊讀取來源／納入條件 |
|---|---|---|
| 月嫂應付款（一般案件） | 確認服務日期與排班中的排班建立／安排，由 Payroll 同交易計算及保存；換人、代班或相關條件變更沿既有 owner 重算 | Staff Payables 目前應付投影；必須尚待付款、付款日已確定且等於所選目標付款日，並通過帳戶與異常檢查。不因只有前段服務說明而建立，也不以完工狀態單獨判斷是否列入 |
| 月嫂應付款（歷史完成案件） | 歷史完成訂單採納時依原服務天數建立基準帳務；實際天數設定保存新版後重算 | 不要求重啟精算。缺少 materialized service-pay 帳務的既有採納完成案件，依下列唯讀歷史投影取得金額；已有帳務時不重複投影 |
| 客戶一般退款 | 取消或帳務更正後，Client Finance 確認已收金額超過應收並建立退款單 | 目前未退完金額、到期日及建單時收款帳戶快照；依目標付款日與正常 review 條件篩選 |
| 客戶補助退款 | 本案已確認屬客戶應退的方案／對象及正式 Client Finance 來源；不能以 S 或身分自動建單 | 正式 `subsidy_return` projection 及未退完金額；沿已形成到期日列入同份清冊，缺值不當作零，P台 與政府直付不列此款 |

來源已存在不代表立即列入所有月份清冊；仍須符合下列 Export 的付款日、未清償、帳戶及異常排除規則。重新查詢讀取最新款項；重新匯出產生新 Excel，舊下載與封存檔不自動改寫。產生清冊不執行匯款，也不將款項改為已付款。

Query：

- `QueryAccountsPayable(target_payment_date)`
- `QueryAccountsPayableArchive(year)`

退款付款與事後核銷邊界：所有客戶退款都先由 Client Finance 建立 `payable_to_client`
退款單，再由 Accounts Payable Query 產出給會計的付款明細；系統不執行匯款。後續 canonical
outgoing bank row 只能以退款單建立時固化的收款帳戶快照與可清償金額核銷，不能以 `due_date`、
付款明細產生日期或銀行交易日期作為配對條件。故 7/15 期的退款單即使會計在 7/1 緊急匯款，
仍可在銀行流水匯入後正確補登；無帳戶快照或銀行列未解析出收款帳戶時必須 fail closed。

客戶退款少匯（2026-08-11 人工核准）：canonical outgoing bank amount 小於同一退款單集合
remaining 時，Client Finance 在同一 UoW 保存不可變的不足來源事實（bank-row set、退款單 set、
帳戶快照、已匯額、remaining、版本、actor/reason/evidence、receipt 與 outbox），並將原退款單
投影為剩餘 payable；不得建立第二張退款單或由 UI 改 remaining。outbox 投影
`client_refund_underpayment`；後續只能以**新的**同帳戶 canonical outgoing row 對原退款單
remaining 做 Preview → Apply，全部歸零才解除。日期不參與此流程。

Export：

1. 在一致 read snapshot 讀取 `payable`／`partially_paid` 的月嫂款項，只取正數 remaining，不重列原始應付總額；以及 review=`normal` 的
   `pending`／`partially_refunded` 客戶退款義務；
   歷史訂單也只讀 Payroll 已建立的正式 obligation、其同一 assignment binding 與 Staff Payables 的目前餘額。
   已採納舊案若缺少義務，單案查核明確列為「尚未建立月嫂應付帳務」，由既有服務天數帳務 Preview／Apply 補建；
   Query 不從歷史來源重算薪資、不產生預定 obligation identity，也不將未建立義務的金額列入付款清冊（2026-10-20 人工要求移除平行帳務）。月嫂列只接受
   `due_date = target_payment_date`；較早月份未付款項不得混入所選月份清單；
2. 月嫂列依 `staff_id + target_payment_date + outgoing_bank + recipient_bank_identity` 聚合；永豐／台新出款分列，不能只因同月同人合併；完整條件依 §2.5.4；
3. anomaly／completed／refunded／review-required 不進應付款清單；
4. client refund row 只輸出 remaining amount，並明確標示
   `customer_refund` 或 `subsidy_return`，不得重複輸出已清償金額；
   `subsidy_return` 的 target payment date 是結案月份加兩個曆月的 15 日，且列必須
   顯示為 `client_subsidy_return`，不得與月嫂 payout 合併或抵銷；
5. 只生成一次 workbook bytes；
6. 使用者下載 bytes 與 archive bytes 必須完全相同；
7. archive 名稱不可覆蓋，保存 SHA-256 receipt；
8. Query／下載／歸檔不改變 payable 狀態。

清冊列應能追溯 obligation identity、款項類型、案件、收款帳戶 snapshot、remaining amount
與重開／追償原因。被 anomaly 或付款證據待確認 blocker 排除的義務，必須另有可查詢的
排除原因與人工處理入口，不能靜默消失。

XLSX 是輸出快照，不是月結 entity。

### 2.5.1 預估資金需求與已確定清冊（2026-10-15 人工裁決）

現行來源與清冊契約：保留已存在的唯讀查詢、正式義務、付款條件、下載／封存及核銷證據；畫面位置與狀態依 `22` §18，方案與補助轉交對象依 §17。**已取代，僅供歷史追溯（2026-10-15）**：原雙頁籤／統一付款工作區及身分驅動預估客戶退款的 SPEC_READY 與實作紀錄，只證明舊版本，不構成新 UI 或三方案已完成。

目的：工會先查看已排班案件未來可能支出的金額與日期，安排資金；交會計的付款清冊只列已建立且符合付款條件的款項。「已確定」表示已有帳務項目，不表示金額永久凍結或已付款；合法服務／帳務更正後仍讀取最新金額。兩者共用既有帳務來源，各自明確標示用途，不新增帳務狀態或寫入 owner root。

顯示位置：依 `22` §18 的進行中案件／銀行對帳／政府補助清單／每月帳務四主入口；精簡案件抽屜僅期款結果、通知與人工補助安排兩區塊，完整付款／退款／歷史沿原銀行或合法工具查閱，保留來源清單脈絡。原資金預估、人員付款與會計清冊功能保留合法相關工具入口，不另復活舊付款主導航或雙頁籤；正式待付、預估及來源待確認仍須分開，未知金額不得當 0。

§2.5 已確定清冊的來源、付款條件、Excel 下載／封存與核銷規則維持不變。下載明示使用「會計清冊月份」，不受畫面款項類型／狀態／搜尋篩選改寫。歷史已付款與沖正從案件／人員明細查閱，不重複列為待付款。下列流程圖描述來源查詢用途，不代表獨立頁籤；補助先以金額及待確認流向記錄，只有本案正式確認為退客戶時才形成客戶退款來源。

#### 預估資金需求流程圖

```mermaid
flowchart TD
    A["排班成功建立後納入<br/>月嫂來源：薪資計算與應付帳務"]
    B["排班服務量及原 owner 補助金額 S<br/>方案／轉交對象未確認時保留待確認<br/>不直接建立客戶退款"]
    C["客戶退款單已建立<br/>來源：一般退款或補助退款單<br/>目前未退完金額與付款日"]
    A --> Q
    B --> Q
    C --> Q
    Q["查詢時讀取最新來源<br/>保留未付款項與資料不足項目<br/>已有補助退款單時，替代同案預估"]
    Q --> R["預估資金需求<br/>依付款月份顯示明細與已知金額小計<br/>日期未知的項目另列"]
    M["排班、服務量或付款條款修改並儲存<br/>退款單建立或變更、付款核銷完成"]
    M --> U["重新查詢來源或工作區重新整理<br/>同步受影響案件抽屜及背景列"]
    U --> Q
```

資料來源與納入條件：

- 新案件從「確認服務日期與排班」的排班成功建立開始納入；只有「尋找月嫂與詢問意願」的服務說明、媒合意願或保存服務日期不算已排班。排班以目前有效指派及有效工作日為準，不把已被取代的排班重複計入。
- 月嫂款項讀取既有 Payroll／Staff Payables 查核資料的未付款金額及付款日；已有應付帳務時標示「已確定」。歷史服務資料計算的項目標示「預估」；已排班但缺少薪資計算依據的月嫂仍保留明細，金額為待確認，不由此查詢建立帳務。已付清或結清者排除。
- 補助 S 仍讀原 owner 的有效資格、補助上限與服務量／費率來源；方案及轉交對象尚未確認時保留待確認，不把 S 預設成客戶應退或新增月嫂薪資。已完成歷史案件沿原 actual-service owner；重新進入一般流程後讀有效來源，不改歷史核銷。
- 先檢查22 §17.4.1全額免自備例外；其餘客戶各期未齊不自動判方案，資料足夠也不等於已確認退款對象。既有正式客戶退款與已確認的真實交易仍沿 owner 核銷，不把分類門檻變成所有交易的入帳前置。**已取代，僅供歷史追溯**：舊「身分／服務資料足夠即自動同步客戶應退」不再決定新三方案。
- 客戶一般退款及補助退款讀取已建立、仍未退完的退款單。補助退款單建立後，改用退款單的未退完金額與付款日，同案不再重複估算；退款已付清後，也不重新產生同案補助退款預估。來源已有未付款項時，即使沒有目前排班仍可追蹤；取消案件不再產生未建單的補助退款預估，已建立未清償款項保留。
- 正式退款及月嫂款沿各自 owner 的已形成付款日；未確定流向／日期時列待確認，不把預估寫入付款條款。**已取代，僅供歷史追溯**：舊未建客戶退款一律按預計結束月加兩月 15 日預估的做法，不可用來創造新應退或重算日期；已存在的日期及原歷史證據保留。

#### 已確定款項清冊流程圖

```mermaid
flowchart TD
    A["排班成功建立<br/>Payroll 計算並保存月嫂應付款<br/>來源：目前應付帳務與付款日"]
    B["已採納的歷史服務完成案件<br/>來源：既有應付帳務<br/>缺少帳務時依歷史服務資料計算"]
    C["取消或帳務更正後確認溢收<br/>Client Finance 建立客戶一般退款單<br/>來源：未退完金額、付款日、收款帳戶快照"]
    D["依本案方案及正式來源確認應退客戶<br/>由 Client Finance 提供既有退款義務<br/>來源：未退完金額、原付款日、收款帳戶快照"]
    A --> Q
    B --> Q
    C --> Q
    D --> Q
    Q["查詢所選月份的同份清冊<br/>月嫂：付款日等於該月15日且仍有剩餘款<br/>客戶退款／補助退款：付款日不晚於該月月底<br/>且未付清、收款資料完整、通過異常檢查"]
    Q --> R["已確定款項清冊<br/>列出符合付款條件的目前未付款金額"]
    R --> X["重新讀取來源並產生 Excel<br/>下載與封存同一份檔案<br/>不執行匯款或變更付款狀態"]
    M["排班或帳務更正、退款單變更<br/>或付款核銷完成"]
    M --> U["工作區重新整理或切換付款月份<br/>同步受影響案件抽屜及背景列"]
    U --> Q
```

資料來源與納入條件：

- 月嫂應付款在排班成功建立時已有資料；只確認日期不會建立應付款。清冊不以訂單是否完工單獨判斷納入，而是讀取應付帳務、付款日、目前付款狀態及收款資料。
- 已採納的歷史服務完成案件不必重啟精算。已有應付帳務時讀取該帳務；缺少帳務時，沿用 §2.5 的歷史投影：最新歷史實際天數，缺少時使用原服務天數，再沿既有薪資、調整額及付款日規則計算。資料不足或已結清者不列入，查詢不補建帳務。
- 排班資料僅提供有效服務量，不能直接決定應退客戶。正式清冊只接受原 owner 已成立的客戶退款／月嫂義務及合法歷史來源；未確認方案／對象的補助不冒充已確定待付，已有義務仍按真實餘額查閱。
- 月嫂款項沿用所選月份 15 日的付款日篩選；客戶一般退款及補助退款納入所選月份月底以前仍未退完的款項，包含 16 日至月底及以前月份餘額。退款依各自 due date 歸屬，不新增付款日期政策或獨立退款清冊。缺日期或收款資料在付款清單保留待確認，不冒充可付款清冊。
- 月嫂未付款或部分付款且 remaining 為正時可列入，並須有唯一主收款帳戶、收款人及銀行資料；清冊與 Excel 只列目前 remaining，同案查核 API 分開呈現原始應付總額及未付款餘額。客戶退款必須仍開啟且餘額為正，建單時收款帳戶快照完整，並通過退款來源異常檢查。客戶部分退款列目前未退完金額；已付清、結清、缺少收款資料或未通過其他異常檢查者不列入。
- 「已確定」表示有款項依據，不表示金額永久凍結或已付款。重新匯出會再次查詢來源，因此修改發生在畫面查詢與下載之間時，新 Excel 可能與先前畫面不同；同一次下載及封存使用相同檔案，舊下載及封存檔不自動改寫。

月嫂部分付款（2026-10-15 修正）：依 §2.4.1，`partially_paid` 不因部分付款本身被清冊視為異常。來源查詢及彙整同時接受 `payable`／`partially_paid`，使用 Staff Payables 目前正數餘額；付款日、歷史結清證據、收款帳戶及其他異常檢查仍適用。個案查核依所選付款月份回傳 `selected_month` 或 `other_month`，缺少日期或收款資料時仍說明排除原因。原始應付金額、部分付款狀態、付款紀錄及異常處理紀錄不因查詢、下載或封存被修改。

#### 來源查詢與畫面更新時機

來源完成正式儲存／核銷並確認結果後，依 `22` §18 在原抽屜脈絡重新讀取正式資料，更新案件摘要、原分頁及背景清單相應列；來源尚未儲存、失敗或結果未確認時不先顯示成功。本節不要求新增推送或定時器，亦不要求人員跳頁才能看到本次成功結果。

| 操作／變更 | 預估資金需求 | 已確定款項清冊 |
|---|---|---|
| 排班、服務量、付款條款或帳務修改完成 | 下次查詢依最新來源重新計算／讀取金額及日期 | 下次查詢讀取更新後帳務，重新判斷是否符合付款條件 |
| 客戶補助退款單建立 | 下次查詢以退款單替代同案預估 | 下次查詢才可能納入，仍須符合付款日、餘額及收款資料條件 |
| 付款／退款核銷完成 | 下次查詢減少未付款金額或移除付清項目 | 下次查詢更新剩餘款或移除付清項目；月嫂部分付款只列 remaining，仍須符合付款日及其他付款條件 |
| 重新進入對應查詢工具，或工作區「重新整理」 | 重新向 API 查詢 | 重新向 API 查詢 |
| 「重新查詢預估」 | 重新向 API 查詢 | 不適用 |
| 切換付款月份 | 只篩選已載入資料，不重新向 API 查詢；未知日期項目仍保留 | 重新查詢同月份清冊；月嫂按 15 日，客戶退款按月底 |
| 重新下載 Excel | 預估查詢不提供付款清冊匯出 | 重新查詢來源、產生新檔並封存；既有檔案不變 |

原實作核對來源（來源查詢與清冊仍有效；舊 UI／身分自動退款路由已取代，僅供歷史追溯）：`subsystems/staff_payables/cash_requirements_query.py`、`infrastructure/mysql/cash_requirements_repository.py`、`subsystems/staff_payables/accounts_payable_export.py`、`infrastructure/mysql/accounts_payable_export_sources.py`、`api/routes/finance_reports.py`、`ui_react/src/components/CashRequirementsPanel.tsx` 及 `ui_react/src/pages/FinancePage.tsx`。2026-10-15 依使用者後續指示修正月嫂部分付款的查詢篩選與彙整，API 回傳格式、金額公式、帳務建立時點與付款寫入流程沿用既有契約。

| Requirement／Acceptance | 規格與來源 | 驗收 |
|---|---|---|
| `CASHPLAN-01` 範圍 | 從已建立排班開始納入原 owner 的未付及預估來源；補助金額不等於客戶應退，方案／對象未確認時保留待確認；媒合中、只有服務說明或只保存服務日期的案件不納入。已排班案件後續完成仍可追蹤未付款項；取消案件不再估算未履約支出，已建立的未清償款項仍保留 | 相同媒合案件在排班建立前不出現，建立後出現；完成／取消不造成已建立未付款項消失 |
| `CASHPLAN-02` 月嫂來源 | 既有 Payroll／Staff Payables 目前未付款金額及 owner 付款日；不得由前端以預計天數另算一套薪資，不重複列入已付清金額 | 多位月嫂與代班依各自來源合計守恆；已付清排除，更正後重新查詢更新 |
| `CASHPLAN-03` 補助流向與退款來源 | S 與本案方案／對象分開；只有正式確認屬客戶應退時由 Client Finance 提供退款義務／餘額，月嫂補助為 P台、政府直付不建工會待退款 | 各期未齊不判方案，但不阻擋已確認真實交易；正式及預估同源不重複計款，未知不猜零 |
| `CASHPLAN-04` 日期與缺值 | 讀原 owner 正式日期及已形成條款；未確認流向／日期時標待確認，不因 S 或身分補造退款日 | 原服務日、due date 及歷史來源保留；舊預計結束月加兩月 15 日的自動預估路由已取代，僅供歷史追溯 |
| `CASHPLAN-05` 呈現與更新 | 依 `22` §18 精簡案件只呈現期款與人工安排；正式付款、預估、待確認原因及實付由原付款工具／銀行核對／月報依原口徑呈現；核銷結果成功後在原脈絡更新，不先更新未確認結果 | 原清冊查詢與封存維持唯讀；不以舊 UI 隱藏待確認原因／卡片的限制覆蓋已核准六畫面 |
| `CASHPLAN-06` 位置與入口 | 四主入口及案件兩區塊抽屜依 `22` §18，相關付款／退款工具保留原合法來源，不新增舊付款主頁 | 正式／預估分開合計、同款只計一次；會計清冊下載／封存不等同政府補助清單 |

實作契約與驗證範圍：

- 新增管理員唯讀 `GET /api/v1/finance-reports/accounts-payable/cash-requirements`；`page_size` 預設 100、範圍 1～200，以 `after_case_no` 按案件排序分批讀取。每批使用一致性唯讀快照，結束時 rollback；不執行 commit、建單或付款。
- Typed 回應為 `rows` 與 `next_cursor`。每列包含 `row_id`、案件、受款人、款項類型、預估／已確定、來源、來源金額、未付款金額、付款日期、日期是否預估及待確認原因；未知金額／日期保留 null，不輸出銀行帳戶或身分證字號。
- 畫面完整載入所有批次後才顯示月份小計；批次失敗不顯示部分合計，離開原查詢工作區依既有規則取消未完成查詢。月份篩選保留日期未知的獨立區塊；重新查詢讀取最新 owner 金額與日期。會計清冊相關工具維持既有付款月份查詢及 Excel 下載／封存，不把舊頁籤作新主導航。
- 使用有效指派的目前排班工作日與 Orders 工時取得預估服務量；已完成歷史案件已有歷史實際服務量 projection 時沿用該 owner 資料。正常流程重啟後不得用舊歷史服務量覆蓋目前排班。月嫂金額由既有 Staff Payables 查核來源提供；客戶退款由 Client Finance 依已確認方案及正式來源提供。**已取代，僅供歷史追溯**：舊 `project_subsidy_return` 的身分自動預估只作原實作證據，不反向決定新方案或客戶應退。

**歷史驗證對照**：下表保存舊版測試位置及當時覆蓋範圍；全補助排除、身分預估退款及鍵盤雙頁籤等舊行為已取代，僅供歷史追溯，不能證明現行 `CASHPLAN-01`～`06` 或 `22` FIN-UI-A01～A14 已通過。仍有效的唯讀、守恆、部分付款及封存契約可沿原來源驗證；本次文件清理未執行或改寫這些測試。

| Acceptance | 直接驗證 |
|---|---|
| `CASHPLAN-01`～`04` | `tests/domains/staff-payables/subsystems/staff-payables/integration/test_cash_requirements_query.py`：排班邊界、取消保留未付款、補助上限／全補助排除、正式退款替代、未知值、重新查詢及來源金額守恆 |
| `CASHPLAN-05`～`06` | 同 root 的 `test_cash_requirements_api.py`：管理員 GET、typed null、無銀行欄位、批次上限及拒絕 POST；既有 Finance presentation root 的 `cash_requirements.test.tsx`：完整載入、部分失敗拒絕、月份小計、未知日期保留、重新查詢與鍵盤頁籤切換 |
| 月嫂部分付款 | 同 integration root 的 `test_accounts_payable_export_sources.py`、`test_accounts_payable_export_workflow.py`、`test_accounts_payable_query_api.py` 及 `test_accounts_payable_export_disposable_mysql.py`：正數剩餘款、所選付款日、帳戶及其他異常排除、API／個案查核／XLSX 金額一致、重新查詢更新及付清後排除；原應付金額與帳務狀態不因查詢改寫 |
| 既有流程 | 原 accounts-payable source／workflow／archive／case audit、staff payout reconciliation／public contract、client refund overage 與 FinancePage 查詢／下載 regression；本機 DB GET 前後帳務 facts 比較與實際瀏覽器畫面核對 |

Owner：既有跨 Domain Accounts Payable reporting application 負責唯讀組合；Payroll／Staff Payables 與 Client Finance 分別擁有原金額及日期規則。此裁決只增加明示的資金預估投影，不修改應收、應付、退款建立時點或核銷規則，不新增資料表／migration、fingerprint、付款副作用或另一套 writer。

**歷史來源追溯（舊 UI 與身分退款路由已取代，僅供歷史追溯）**：2026-10-15 當次使用者的資金調控目的、「從已建立排班開始，包含尚未成立的預估客戶補助退款」選擇，以及「財務查詢與對帳工作台 → 應付帳款」內設置「預估資金需求」與「已確定款項清冊」兩個頁籤的明確指示（`PRODUCT_REQUIREMENT`）；本規格 §2.5、`04_Client_Finance_Domain.md` 的補助退還與預估金額規則、`03_Payroll_Domain.md` 的付款日及薪資規則。金額計算沿既有 owner，預估付款日為本節明示的預估用途，不替代正式退款日期。

**已取代，僅供歷史追溯（2026-10-15 收斂紀錄）**：下列狀態僅記錄舊版來源與雙頁籤需求當時的收斂結果；不代表新三方案或抽屜介面已收斂、實作或通過驗證。

```yaml
spec_route:
  status: SPEC_READY
  requirements: [CASHPLAN-01, CASHPLAN-02, CASHPLAN-03, CASHPLAN-04, CASHPLAN-05, CASHPLAN-06]
convergence:
  status: READY
  blockers: []
package_route:
  status: NO_PACKAGE_REQUIRED
  reason: 同一 reporting owner 的完整執行由本節契約、直接 source/test roots 與驗證矩陣承接；本次無獨立交接、資料 migration、付款或外部副作用，不另建重複 package。
```

### 2.5.2 帳務四主入口與精簡案件抽屜（2026-11-05核准；正式接線結果見22 §18.10）

現行操作與驗收唯一依[22 §18](22_銀行流水匯入與帳務異常處理正式規格.md#finance-six-surfaces-ui-20261104)、FIN-UI-A01～A36，本段只同步此Domain的展示責任，不移轉金融owner：

- 預設進行中案件，另有銀行對帳、政府補助清單、每月帳務；所有抽屜與客戶名冊同寬，手機全寬，保留原來源搜尋／範圍／捲動／焦點。
- 案件標頭只顯示一次案號／客戶，精簡摘要含月嫂、實際起訖、T；同頁只有客戶繳款、補助退款方案兩區塊。移除上方目前事項、全期金流卡、獨立收付款／歷史及案件內核對，不刪原流水或證據。
- 期款七欄沿原日期與金額，入帳資訊只用已核銷正式分配；通知時間取本期最後成功發送，已齊／免繳按鈕灰色鎖定，部分未清可通知餘額。內容、近期紀錄及返回在同案抽屜，不另造通知頁或冷卻規則，不把未確認銀行列暗示為本案已匯入。
- 歷史自動分類沿22 §17.4；進行中人工設定補助轉月嫂／退客戶／政府直付，可在前三期未齊時保存。提前保存不改應繳、免繳、實付、日期或既存義務；客戶款齊且方案保存後移出，沒有第二次強制確認。
- 補助及應付清單／Excel在原正式服務結束後依§2.5.5及原owner承接最後正式保存的人工安排，原金融未清事實照實保留；人工安排不是付款證據，也不新增T之外的薪資。問題帳務與核銷由銀行對帳處理；完整金流、歷史、差額及付款／退款工具保留原合法來源。
- 原入帳通知等不同業務類型與舊頁面整併另議，本次不刪API／CLI或原通知紀錄；未儲存方案可繼續／捨棄，結果未確認不冒充成功。移出後原報表／月報仍能查同案。

正式精簡抽屜、通知來源與人工方案保存已依22 §18接線，既有限定測試、Browser及本機schema-only升級結果只沿22 §18.10原證據，不把舊PASS套成新版或本輪重驗。本輪只清理文件，未修改程式、資料或發送通知；人工方案到應付流程的交接已由§2.5.5核准，本輪只更新規格，不據此宣稱下游程式已接通；先前「交接細節另待草案確認」已取代，僅供歷史追溯。**已取代，僅供歷史追溯**：先前「僅文件／正式程式及DB尚未實作」、三分頁與同案核銷、舊23項預覽均屬當輪範圍，原驗收及不可變金融事實保留。

### 2.5.3 收付款完成狀態（2026-10-20 人工修正）

依本次人工指示，實際收付款後，帳務清單必須呈現「已收款／已付款」，不得持續顯示待確認。此節取代 §2.5.1、§2.5.2 中付款主清單只列未付項目的呈現限制；會計清冊仍只匯出符合既有條件的未付餘額，不改 writer、交易邊界或銀行外部效果。

- 付款清單保留已付款及歷史已結清項目。既有唯讀 cash requirements 每列增加 `payment_status`：`pending`、`partially_paid`、`paid`、`settled`；與 `certainty` 分開。銀行付款投影 completed 或 exact current 歷史 paid 證據顯示「已付款」；歷史 settled 顯示「已結清」，不能冒稱已匯款。部分付款顯示剩餘款，已付／結清列未付餘額為零，不增加待付小計；款項種類、既有預估及服務結束篩選保留，增加部分付款／已付款／已結清篩選。付款日期沿原來源，不以到期日冒稱實際匯款日。
- 服務中換人造成超付款時，付款清單顯示已付款、未付額零及追償提示；原帳務負餘額與獨立追償仍保留。不得將負餘額當成待付款，或因該列使整份付款清單無法查詢。
- 客戶帳務摘要增加 `receipt_status`：`pending`、`unpaid`、`partially_received`、`received`、`settled`。清單分別顯示待確認、待收款、部分收款、已收款、已結清；已收款篩選包含部分收款。canonical receipt／reversal 淨額與 exact current 歷史 paid 證據提供收款依據；歷史 settled 不等於實際收款。`receipt_entry_count` 保持只計 canonical receipt，不能拿其他 ledger 類型當收款證據。
- 政府補助收款列沿既有 owner `substatus_code` 呈現收款狀態：`paid` 顯示已收款、`partially_paid` 顯示部分收款；服務結束確認仍是獨立欄位，不取代入款狀態。
- 歷史 owner overlay 只有 obligation identity、金額快照與 obligation version 都符合目前義務時才有效；有效 paid／settled 不再列為未收／未付。沖正或後續版本造成新餘額時，重新查詢須顯示目前狀態，不沿用失效的歷史確認。
- 直接驗證包含：已採納歷史收付款、正常付款、部分收付款、沖正後重新未付、歷史金額／版本失效、無帳務資料與零餘額；Query 不建立付款或結清事實。

### 2.5.4 三方案、全額補助免自備及會計 Excel（2026-11-05人工確認；限定實作及資料缺口分列）

Authority：使用者要求依最新三方案重整應付帳款 Excel 修正方案，補入已確認全額補助免自備條件、公會自訂編號＋月嫂姓名及既有漏列資料驗證，並檢查殘留舊規格；**已取代，僅供歷史追溯**：當時「只授權文件變更，不修改程式或資料」為原文件階段；後續限定修正／驗收及資料補登0／7受阻的執行結果見原帳務工作包accounts-payable-excel-execution-20261105節，不把未知退款來源改成可付款，也不將舊狀態外推為本輪重驗。跨域判斷唯一依規格22 §17、§17.4.1，本節擁有會計清冊的唯讀組合／輸出契約；不建立另一套方案、帳本或 writer。

**APX-SOURCE-01／原流程同源**：案件帳務與清冊消費相同正式 owner 的金額、對象、付款用途及既有日期。Payroll 擁有月嫂應收，Staff Payables 擁有月嫂實付與剩餘款；Client Finance 擁有正常／補助客戶退款及收款帳戶快照。Accounts Payable 只經 typed view／port 組合，新流程的補助歸屬依§2.5.5最後正式保存的人工安排，歷史自動辨識只依原範圍比對，不因未知／不同自動否定人工安排；不由身分、舊 `directly_subsidized`／`installment_funding` 標記、銀行名稱或畫面預估另判方案。保留既有認證下載入口、固定工作表與十欄、分批查詢界線及封存方式；不另建補助專用 Excel、資料表或付款流程。

| 方案／正式款項 | 受款對象、來源與出款銀行 | 會計清冊行為 |
|---|---|---|
| 方案一：客戶與政府分別入款 | 月嫂；Staff Payables；一般款P永由永豐，補助轉交P台由台新 | 依原正式付款分配、各期日期及正數未付餘額分列；兩銀行合計只清償原月嫂應收T，不再加薪資 |
| 方案一全額補助免自備子情境 | 補助市民／原住民且H≤有效L，S＝T、B＝0；補助轉交月嫂P台 | 不要求客戶入款、人工免自備確認或先有三筆零額期款；依月嫂正式待付來源列台新款，不建立客戶R台 |
| 方案二：客戶先墊後退 | 客戶；Client Finance正式補助退款R台；台新 | 列正式未退餘額及既有到期日，收款快照／異常檢查仍適用；月嫂原應付另按Staff Payables，不因客戶退款再次增加月嫂款 |
| 方案三：政府直接付客戶 | 此補助不由工會出款 | 不建立／匯出這筆補助的工會待付款；月嫂原有正式應付及其他正常退款不因此消失 |
| 正常客戶退款（獨立於補助方案） | 客戶；Client Finance正常退款R永；永豐 | 與補助退款區分；不得因收款人是客戶就一律標為台新 |

**APX-ROUTE-02／銀行、彙整與餘額**：出款銀行依正式用途P永／P台／R永／R台傳遞，與收款人帳戶的銀行代碼分開。不能再採「月嫂一律永豐、客戶退款一律台新」。月嫂只在 `staff_id＋付款日＋出款銀行＋收款帳戶` 相同時合併，永豐與台新必須分列；保留原案件／obligation追溯。正式分配缺失、用途／對象不唯一或新舊來源矛盾時保留待確認及具體原因，不由清冊自行拆分金額、採先付某銀行的假定、另建薪資或搬移舊付款。

**APX-DATE-03／月份及排除**：沿 §2.5、§2.5.1 的月份規則：月嫂款按所選月份15日；客戶正常／補助退款按所選月份月底以前的正數未退餘額，含以前月份及部分退款。日期讀原owner既有義務／分期來源，未知不代填，不能因方案、政府晚入款或匯出月份重算／移期。已付清、已結清、取消或其他異常不列可付款Excel；付款清單保留待確認來源與排除原因，不靜默消失。方案未知本身不撤銷已有正式對象及款項依據；新人工安排與歷史辨識的適用依§2.5.5，僅受影響補助款待確認，不整案擋住其他合法到期款，亦不得把尚無依據的預估當可付款。

**APX-NAME-04／月嫂姓名欄**：月嫂列的「客戶or服務人員姓名」顯示 `{union_no} {name}`，例如 `00123 月嫂甲`；`union_no` 取人員主檔正式公會自訂編號，保留字串、前導零及原字元，不替代成資料庫staff_id。缺編號沿既有名冊慣例顯示 `未設定 {name}`，不因此漏列正常應付。原收款姓名與顯示文字分開，仍以staff_id、銀行／帳戶及正式來源辨識／合併，不按姓名文字合併同名人。客戶列沿客戶姓名，不套月嫂編號格式。銀行帳號、銀行代碼、案件編號及編號＋姓名維持Excel文字儲存，金額維持數字、日期維持日期。

**APX-RECIPIENT-05／客戶退款快照**：正式客戶退款沿同一Client Finance帳戶來源與快照規則，建單時在原交易保存可唯一確認的帳戶；不能另寫補助專用快照邏輯或在匯出時用可變名冊帳戶替代。月嫂款讀正式月嫂收款資料，方案三不為此補助建工會退款快照。缺資料保持待補且不偽造；舊退款的事後補登不是建單時資料，不可回填假時間或覆寫已有快照。是否可補登、所用證據及對應owner入口須先核對；原流程不足時列明缺口，另依正式契約收斂，不因本次規格或方案自動建立新writer／API或回填。

2026-11-05帳戶來源補充（本輪僅規格）：名冊退款帳戶維護依33 §5.1，由原Case Import BeClass有效修正流程承接；新LIFF核准建檔的正式欄位銜接及A115001來源補正依17 §5.1.1.1。Client Finance的一般／補助退款共用同一typed有效帳戶來源：唯一bound_case_no之原正式欄位加有效修正，明示清除值保持清除，不從原問卷臨時fallback或拼接其他案件；以同一fresh版本確認完整帳戶後，才可供原退款writer建立快照。帳戶更正不更新既有金融快照、不成立／取消退款、不改已形成日期；補快照仍由有正式依據的原writer執行，Query／Excel零寫入。原始申請及問卷保留不代表已形成可退款義務，本輪未執行正式欄位補登或金融資料更正。

同日最新申請儲存裁決依17 REG-BOUNDARY-01～06：核准前問卷不得進MySQL，核准／拒絕後清除待審內容；上段對既有來源的說明不構成新版申請副本的永久保留要求。原Case Import正式帳戶採納及Client Finance既有快照保護保持，不能為了清除待審內容而刪除尚未完整採納的必要資料。具體獨立Redis及跨儲存核准／清除恢復設計依17 REG-REDIS-01～09，尚未實作／驗收；不以本節授權安裝或移動、刪除、重建金融資料。

**APX-AUDIT-06／既有漏列資料**：先逐筆核對既有退款原始成立事件、正式身分、H／L、T／S／B、已收付及方案／安排，再分類為客戶正式退款、月嫂正式待付款、政府直付或待確認／來源衝突；不能把「已存在subsidy_return」等同「新規格已確認應退客戶」。檢查快照、日期、款項狀態、剩餘金額與歷史證據；只有正式可付款條件完整的列才預期匯出。合法既有義務不只因分類未知便取消，亦不得將既有客戶退款直接改成月嫂款。修復前後另需同案readback及可追溯證據；實際補登、帳務更正、資料回填均需後續明確執行授權。

**APX-READONLY-07／唯讀及相容**：Query、清冊生成及下載不寫入金融資料、不核銷、不改已形成日期；匯出只生成一份workbook bytes，下載與封存相同，保留不可覆蓋檔名及hash驗證。政府補助清單沿原報表模板，與本會計Excel分開；不將新預設方案三套到所有歷史案件。此輪不改公開入口、schema、DB或外部服務，不stage／commit／push。

| 驗收ID | 必要結果（實際執行範圍及限制見原工作包，不以條款存在代替通過） |
|---|---|
| APX-A01 | 一般方案一依正式分配列永豐／台新月嫂款，同案總額不重複；同人同日跨出款銀行分列，同銀行同帳戶可合併且保留各案來源 |
| APX-A02 | 補助市民及原住民分別驗H<L、H=L，L採有效設定，自動免自備／方案一／轉交月嫂；無客戶實付或零額期款記錄不誤擋，非人工免自備審核 |
| APX-A03 | H>L、一般市民或身分／H／L未知不誤套全額例外；舊計價與S＝T／B＝0矛盾有原因，不直接改原金額或產生客戶退款 |
| APX-A04 | 方案二列正式客戶補助未退餘額及台新；方案三不產生工會補助待付款；正常客戶退款列永豐，不改既有付款用途 |
| APX-A05 | 部分付款／退款只列remaining；付清／結清排除；退回／沖正沿正式owner重開，不複製既有實付、不因政府後入重付月嫂 |
| APX-A06 | 公會編號前導零、缺編號、同名不同staff及同人跨銀行分列均正確；客戶名稱不被加上月嫂編號，原收款姓名不變 |
| APX-A07 | 月嫂所選15日、退款月底及前期餘額、跨年、未知日期／帳戶／用途／來源衝突均有明確納入或排除結果；不另訂付款日期 |
| APX-A08 | 逐筆既有漏列記錄有原始依據、候選對象、排除原因及修復前後核對結果；資料未齊只能標待確認，不能以檔案存在或筆數湊齊冒充修復成功 |
| APX-A09 | 一般退款與補助退款共用帳戶判定／快照邏輯，重送不重建款項或覆寫快照；匯出零金融寫入，固定十欄及下載／封存同bytes，原公開入口及政府報表相容 |

實作接線、已知來源缺口、7筆本機觀測及驗證順序見既有「帳務工作台實作工作包」2026-11-05節；觀測筆數不是固定需求或全部應退的裁決。舊固定120／80門檻、所有補助一律退客戶、同人同月無條件合併、所有退款一律台新及只靠補快照修復所有漏列的方案均不適用。

<a id="manual-subsidy-plan-payables-handoff-20261105"></a>

### 2.5.5 人工補助方案與應付流程交接（2026-11-05已核准並實作）

Authority：使用者最新明確要求「按照最新規格，實作人工補助方案與應付流程的交接」，保留既有流水／核銷證據／已形成日期，以實際瀏覽器驗證且不發真實通知。本節是人工方案與應付承接的唯一現行交接契約；三方案受款對象／出款銀行／正式餘額及Excel既有格式仍沿§2.5.4，不複製第二套計算或清單。

**HANDOFF-01／兩項作業的完成條件分開**：進行中案件仍依22 §18，以「客戶需繳各期已齊＋人工方案正式保存」移出；提前保存不跳過未清期款，移出不表示全案金融結清、正式服務已結束或已付款。保存／修改方案只記錄安排，不成立應付款、不產生付款／退款／核銷，也不生成Excel。原正式服務結束成立後，補助及應付流程才依已保存安排接手，服務結束依原owner事實，不從是否移出清單或日期欄非空另造判定；原有合法一般月嫂應付及正常客戶退款仍依既有日期／餘額處理。

**HANDOFF-02／人工安排主導新流程的補助歸屬**：對已由人員正式保存安排的新流程案件，應付承接讀取最後正式保存的人工方案；歷史自動辨識及原直付安排保留為原適用範圍的紀錄與比對，不能自動覆蓋人工方案或冒充已人工設定。歷史分類未知、尚無政府入工會款或自動結果不同，本身不足以推翻人工安排或阻擋承接。尚未保存方案時，補助款保留待確認，不以新案／報表預設方案三、客戶身分或欠缺政府款代選；無新人工安排的歷史案件仍沿原合法來源處理，不批次轉換。

**HANDOFF-03／安排不取代正式應付來源**：三方案的方向及銀行沿§2.5.4對照表；原帳務owner依合法來源負責款項成立、必要更正及核銷，清冊只讀結果。方案一補助轉月嫂是T內的原應付，只處理正式未付餘額，月嫂已收足T不能再加付S；方案二只處理已成立且尚未退還的客戶補助墊款，不以選擇方案直接建立無墊款依據的退款；方案三不新建本補助的工會退款、不追蹤客戶實收政府款。三者均不取消其他合法月嫂款或正常客戶退款，也不重算T／S／B、前三期期款或原全額免自備規則。

**HANDOFF-04／衝突只處理受影響款項**：人工安排若與既有正式應付或真實收付款的對象、用途、金額矛盾，保留人工方案及原事實，僅將受影響款項列待確認並說明原因，交原owner合法更正；不得由安排或匯出搬移、取消、重分配或改收款人。缺方案、缺正式應付或必要來源時，補助款保留待確認，不把未知當0或可付款；其他已有完整合法依據的到期款仍依原規則處理，不因一筆補助待確認而整案阻擋。免自備金額或既有付款與人工安排不一致時同樣保留證據，不為了對齊方案另造客戶墊款或T之外薪資。

**HANDOFF-05／修改與歷史保留**：人員可依原合法流程修改安排並保留各次更正紀錄；改安排不能自動同步改寫已形成應付、流水、allocation、核銷、收款帳戶快照、舊Excel或已形成日期。若款項確須變更，由原帳務owner依既有更正／沖正／調整契約處理，保留原紀錄及原日期的歷史；不因新選方案、政府晚入款或匯出月份重算／移期。下一次清單依正式更正後結果呈現，既有已匯出檔案及封存不覆蓋，不把更正安排當付款證據。

**HANDOFF-06／清冊與外部效果**：清單及Excel沿§2.5.4只讀正式應付款的目前餘額、對象、用途、日期及受款資料；生成／下載／封存不補建款項、不重分類、不代為核銷。方案未定、來源缺失或衝突在原查詢中保留待確認及具體原因，不以預估／分類湊成可付款列；實際出款仍逐筆沿原銀行對帳及owner核銷。政府補助清單仍沿營運週報既有報表及匯出，不與會計應付Excel合成第二套。

| 情況 | 應付承接結果 |
|---|---|
| 已保存人工方案，歷史分類未知／不同，但正式款項依據完整且不衝突 | 採人工安排的補助歸屬承接，歷史結果僅比對，不因此取消合法款項 |
| 尚未保存人工方案，或該補助缺必要正式來源 | 該補助待確認；不代選方案三、不由匯出補寫；其他合法到期款沿原規則 |
| 人工安排與已有正式應付／實收付矛盾 | 只標受影響款項待確認，保留原來源及安排；由原owner更正，不自動改帳 |
| 已形成應付、已付／已核銷或已匯出後修改安排 | 保留原義務、交易、核銷、日期及檔案；必要更正走原流程，不回寫舊版 |

| 驗收ID | 必要可觀測結果 |
|---|---|
| HANDOFF-A01 | 方案可提前保存，未齊仍留進行中；款齊且保存才移出。移出或保存本身不成立應付、不付款、不核銷、不產生Excel；不以移出代替正式服務結束 |
| HANDOFF-A02 | 正式服務結束後採最後正式保存的人工安排；自動分類未知／不同或缺G不單獨阻擋；不得由原直付安排、身分或報表預設冒充人工設定 |
| HANDOFF-A03 | 方案一只清償月嫂正式未付餘額，永豐／台新合計不增加T以外薪資；已付滿T不因補助後入再付S |
| HANDOFF-A04 | 方案二只列正式未退墊款；方案三不新建該補助工會退款、不要求政府或客戶實收證明；其他合法應付／正常退款仍保留 |
| HANDOFF-A05 | 缺方案／正式來源或與既成款項衝突時，只將受影響款項待確認並保留原因；不整案擋住其他合法到期款，也不直接改收款人或回填義務 |
| HANDOFF-A06 | 已形成應付／已核銷／已匯出後改方案，原流水、分配、證據、快照、日期及Excel保持；合法更正及下一次查詢沿原owner結果，不覆蓋舊檔 |
| HANDOFF-A07 | 查詢、清單、下載及封存零金融寫入；只使用正式餘額、日期及受款依據，不將預估變成可付款。原金融owner、三方案與政府報表／會計Excel分工保持 |

狀態：人工方案至應付下游已接線。沿原方案事件表、正式應付來源、Orders完工與Client Finance既有writer／outer UoW承接；沒有新表、migration、付款writer或Query金融寫入。方案一／二／三與既成期款、實收付、免自備或正式金額不相容時只將受影響款項待確認，保留原日期、餘額與證據；修改方案不回寫舊金融事實。HANDOFF-A01～A07已由受影響後端測試及Chromium＋隔離native MySQL流程驗證，Excel沿原固定十欄及封存bytes；真實通知／付款及production部署NOT_RUN。詳細當次結果沿既有帳務工作台實作工作包；先前歷史驗收原樣保留。

**已取代，僅供歷史追溯**：2026-11-05前輪僅授權補規格、禁止改程式及「下游交接NOT_RUN／須另獲施工授權」的階段狀態，由本輪明確實作授權與限定驗收取代，不更動當時的歷史證據。

**已取代，僅供歷史追溯**：先前「交接細節另待草案確認」及僅以「原流程承接」代替交接規則的狀態已由本節取代。歷史自動辨識及原直付安排契約本身仍依原範圍保留，不以本節回寫歷史分類或將過去PASS改為新交接已通過。

### 2.6 Typed errors

| Code | 類型 | 處理 |
|---|---|---|
| `staff_payable_not_found` | not-found | 重新 Query |
| `staff_payable_candidate_stale` | stale | 重新 Preview |
| `idempotency_conflict` | conflict | 拒絕重用不同 payload |
| `staff_obligation_not_exactly_settled` | blocker | 人工核對銀行事實與義務 |
| `staff_bank_account_ambiguous` | blocker | 人工確認唯一有效帳戶 |
| `staff_payout_amount_mismatch` | blocker | 一般 payout 不可套用；改由異常中心選正確 difference action |
| `staff_payout_difference_mode_invalid` | validation | 金額關係與 underpayment／overpayment mode 不符 |
| `staff_overpayment_recovery_target_ambiguous` | blocker | 人工確認唯一月嫂 recovery |
| `staff_overpayment_recovery_adjustment_forbidden` | forbidden | 缺 capability，不可調整 recovery |
| `staff_payout_reversal_invalid` | blocker | 不得 reversal-of-reversal 或超額 |
| `transaction_failed` | transaction | 只有 storage unavailable／deadlock／timeout 標 retryable |
| `accounts_payable_export_has_anomaly` | blocker | 異常中心處理 |
| `accounts_payable_archive_failed` | external | 不宣稱匯出完成 |

### 2.7 人工入口與異常

- 管理員只能從應付款 Query 選定 bank facts 與 obligations 後 Preview／Apply。
- `PAYOUT-001`～`003` 由 root facts 投影；認領／解除不取代修正根事實。
- 退匯／沖正成功後，既有義務重新成為 `payable`。
- 正常且可唯一辨識帳戶、月嫂及完整義務集合的銀行支出，由 Finance Import 的
  Upload → Preview → confirmed Apply 在 borrowed UoW 委派 Staff Payables；React 正常頁到 terminal
  receipt／readback 即結束，不再要求第二次「標記已付」。不唯一、金額不符、退匯、沖正與差額
  才導向本節的 typed 人工入口，不得以 disabled 假按鈕代替。

### 2.8 Legacy exit

1. 所有 `staff_monthly_settlements*` production writer 停止；
2. legacy staff payment transaction route 固定 `410 Gone`；
3. adjustment 不得寫入「下一個未 finalized 月結」；
4. `finance_import_dispatch` 不得再寫 `staff_actual_transfers` 或月結 candidate；
5. writer inventory 與 runtime tests 證明無正式 caller；
6. 保留資料只經 versioned preserve-data migration，不直接 DROP 歷史表。

## 3. Domain：Client Finance／Customer Refund

### 3.1 責任與 SSOT

Client Finance 擁有：

- 客戶 refund obligation；
- canonical bank outflow 與 immutable refund ledger entry；
- refund entry 對 refund obligation 的 exact allocation；
- account version、outbox、receipt 與目前投影；
- receipt reversal 後重新形成的 receivable。

退款不解除已成立的不可逆案件服務資料鎖，也不改變 Orders 已發生的服務事實。

### 3.2 Refund 與 Reversal 排他

| Operation | 根事實 | 結果 |
|---|---|---|
| Customer Refund | 已成立 refund obligation＋正式銀行出款 | 清償退款義務 |
| Subsidy Return | 已確認應退客戶的正式 R台 義務＋真實銀行出款 | 對象與應退依案件方案及 owner 證據；P台 轉交月嫂及政府直付客戶不屬此列。既有 due date、代墊、核銷／沖正保留，不因身分或 S 自動新建退款 |
| Receipt Reversal | 既有有效 receipt ledger event 失效 | append reversal 並重開原 receivable |

禁止：

- 用負數收款表示退款；
- 更新或刪除原 receipt；
- 把 refund 當 receipt reversal；
- reversal-of-reversal；
- 無 refund obligation 時依人工輸入金額直接付款；
- 因退款解鎖服務資料或倒退 Orders lifecycle。

每一筆 canonical bank outflow 必須全額分配，不得留下不明餘額；同一 refund obligation
可以由多筆不可變銀行出款逐步清償，因此 obligation 可以有 `partially_refunded` 投影。
任何 allocation 都不得使累積有效退款超過 obligation amount。

若 canonical bank outflow 確實大於該退款 obligation 的 remaining amount，系統不得丟棄
已發生的出款。它必須：

1. 將 obligation 額度內的金額作為 refund allocation；
2. 將超額金額建立獨立的 `client_over_refund_recovery` 追償應收與 anomaly；
3. 保留原 bank fact、原 refund ledger 與超額追償之間的完整可追溯鏈；
4. 不再建立新的退款應付，亦不得自動以後續客戶款項抵銷；只有後續 canonical 入款或經
   授權的不可變 adjustment 才能結清追償。

一般退款 ledger entry type 固定為 `refund`，其退匯／沖正固定為
`refund_reversal`；客戶補助退還則固定為 `subsidy_return`，其退匯／沖正固定為
`subsidy_return_reversal`。兩條線不得共用 transaction type、remaining balance 或
progress reducer。`reversal` 只可用於原 client receipt 的沖正。

### 3.3 Subsystem：Refund Obligation Planning

Commands：

- `CreateCustomerRefundObligation`
- 已確認應退客戶的本案方案／對象與正式來源，由原 Client Finance owner 規劃應退；既有義務與真實交易依原流程更新核銷，不因本次清理另增手動建立命令。**已取代，僅供歷史追溯**：舊保存計價資料即自動建客戶補助退款的觸發條件。
- `AdjustRefundObligation`
- `ApplyClientReceiptWithOverage`
- `ApplyClientRefundWithOverage`

一般退款 root fact 來自已提交的 cancellation／financial adjustment；客戶補助應退依已確認本案方案／對象及正式來源，由 Client Finance owner 保存，詳規格 04、14 及 `22` §17。不能只因補助資格、計價資料及日期齊全自動新建退款；既有義務、真實交易及其更新仍沿原 owner。政府入款與代墊回收仍以原整期處理，不自行新增逐案分配。
每個 obligation 保存 source event identity、case number、integer amount、reason、
version 與 immutable creation event。

客戶超收是額外的合法 root-fact 來源。`ApplyClientReceiptWithOverage` 僅能在選定的
canonical incoming bank fact、唯一 case、唯一應收義務與人工確認都成立時執行，且須在
同一 outer Unit of Work 內：

1. append 全額實收的 receipt ledger；
2. 將應收額度內的金額 allocation 至原 receivable；
3. 將差額建立 `customer_refund` payable obligation，來源明確指向該 receipt ledger；
4. 寫入超收處置 receipt、version、idempotency receipt 與 outbox。

不得將超收直接視為退款已完成，也不得只把 `client_receipt_overpaid` 留在 alert 而遺失
已收現金的正式表達。案件或義務不唯一、重複匯入、疑似錯誤分類時，仍只能保留 bank fact
與 review，不得建立退款 obligation。

### 3.4 Subsystem：Refund／Reversal Preview and Apply

Queries／Commands：

- `QueryClientRefundReversal`
- `PreviewClientRefund`
- `ApplyClientRefund`
- `PreviewClientSubsidyReturn`
- `ApplyClientSubsidyReturn`
- `PreviewClientReceiptReversal`
- `ApplyClientReceiptReversal`
- `PreviewClientRefundReturn`
- `ApplyClientRefundReturn`
- `PreviewClientRefundReversal`
- `ApplyClientRefundReversal`

Preview：

- 選定 canonical bank fact 與 obligation／reversal target；
- 驗證同一 case、operation purpose、金額、唯一性與目前 account version；
- 建立 deterministic allocation 與 fingerprint；
- 零寫入。

Apply：

1. 檢查 idempotency receipt；
2. 鎖定 Client Finance account、bank facts、obligations 或 reversal targets；
3. 重建 candidate；
4. 驗證 expected account version 與 Preview fingerprint；
5. append ledger entries 與 allocations；
6. 精確套用本次 refund allocation 並重算 remaining；remaining 為零才標示
   `refunded`，receipt reversal 則重開 receivable；
7. 更新 projection、version、outbox 與 receipt；
8. outer Unit of Work 單次 commit。

每一筆選定 bank outflow 的金額必須被完整表達；不足 obligation 全額時形成
`partially_refunded`。超過 remaining refundable amount 時，`ApplyClientRefundWithOverage`
必須依 3.2 建立超額追償應收，而不是拒絕並遺失銀行現金事實。

### 3.5 State machine

Refund obligation 使用兩個正交衍生投影，避免把人工覆核進度混入付款進度：

```text
refund_progress:
not_required
pending ──valid partial allocation──> partially_refunded
pending／partially_refunded ──remaining amount exactly zero──> refunded
refunded ──valid refund return／reversal event──> pending | partially_refunded

refund_review:
normal ↔ review_required
```

`client_over_refund_recovery` 另有獨立的 `open → recovered | adjusted` 投影；它不屬於
refund progress，且不得自動與客戶新應收或其他案件抵銷。

#### 3.5.1 `client_over_refund_recovery` 可執行契約

每筆 recovery root 最少保存：

- `recovery_identity`、case number、client identity；
- 來源 canonical refund outflow bank fact、來源 refund ledger entry、來源 refund obligation；
- `original_amount_ntd`、derived `remaining_amount_ntd`；
- `status=open|partially_recovered|recovered|adjusted`、aggregate version、current event identity；
- 建立時的 actor、reason、evidence、idempotency key 與 correlation id。

不可變 recovery events：

- `established`：退款實際多匯 Apply 同交易建立；
- `cash_recovered`：連結後續 canonical incoming bank fact 與 recovery allocation；
- `authorized_adjustment`：沒有銀行入款，只能由具 capability 的人工裁決追加；
- `reversed`：只修正錯誤分類／錯誤 recovery event，必須指向原 event，不代表現金退回。

Commands：

- `QueryClientOverRefundRecovery`
- `PreviewClientOverRefundRecoveryReceipt`
- `ApplyClientOverRefundRecoveryReceipt`
- `PreviewClientOverRefundRecoveryAdjustment`
- `ApplyClientOverRefundRecoveryAdjustment`

銀行入款結清規則：

1. bank fact 必須是尚未被正式 ledger 使用的 canonical incoming row；
2. 必須由案件、客戶／退款參考或人工證據唯一指向一筆 open recovery；
3. 入款金額不得大於 recovery remaining；超額時停止並建立新的金額異常，不能自動轉作
   客戶一般收款；
4. 預設要求一次足額收回；實際入款不足時仍 append `cash_recovered` 作為疏失補救，狀態為
   `partially_recovered`，remaining 保持可追；
5. 同一 bank fact 只能對一筆 recovery 建立一份正式 allocation；
6. remaining 歸零才轉 `recovered`，並由根事實 projector 自動解除 recovery anomaly。

Adjustment 規則：

- 只允許 `client_finance.recovery.adjust` capability；
- 必須提供 adjustment amount、reason、evidence reference 與 expected version；
- adjustment amount 不得超過 remaining，也不得為負數或零；
- adjustment 只追加不可變 event，不建立虛構銀行 receipt；
- 部分 adjustment 後仍為 `open`，remaining 歸零才為 `adjusted`；
- 不得以 adjustment 偷渡跨案抵扣、改寫原 refund、client receipt 或 Orders lifecycle。

Preview 零寫入；Apply 鎖定 recovery、bank fact（cash only）、account version 與 active anomaly，
fresh rebuild candidate 後同交易 append ledger／event／allocation、CAS projection/version、outbox、
receipt 與 anomaly desired-state event。完全相同 idempotency key＋payload回 existing receipt；
不同 payload conflict。

### 3.6 銀行根事實與逾期提醒

系統不直接接收銀行付款結果。人員匯入的 canonical bank fact 是退款是否實際發生的
唯一根事實；沒有可核銷 bank fact 只表示尚未取得結果，不能建立 `payment_failed`、
`submitted` 或 `bank_pending` 狀態。

當 remaining amount 大於零且 business date 已過 due date，系統以 canonical
obligation／ledger projection 建立 overdue reminder，請人員核對對帳單是否已匯入或需
人工配對。有效 bank fact 經正式 Preview／Apply 精確 allocation 後，提醒自動解除；
它不修改任何 obligation、ledger、allocation 或 Orders lifecycle。

正式 refund ledger event append 後不可改寫。銀行退匯若需要重新應退，必須新增
dedicated reversal／reopen event，不得刪除原 refund。

Refund return／reversal 的 target 必須是仍有效的 refund ledger entry。return 另須綁定
canonical 銀行退匯入款；reversal 需要人工 reason 與 operation capability。兩者都使用
expected account version、Preview fingerprint 與各自 stable idempotency key，在 Client
Finance outer Unit of Work 內 append dedicated reopen event、重算 progress、寫 receipt
與 outbox 後單次 commit。不同 payload 重用 key、stale target、重複 return／reversal
一律 conflict；只有 storage unavailable／deadlock／timeout 可安全重試。

### 3.7 Typed errors

| Code | 類型 | 處理 |
|---|---|---|
| `client_finance_case_not_found` | not-found | 停止 |
| `client_obligation_not_found` | not-found／stale | 重新 Query |
| `client_finance_candidate_stale` | stale | 重新 Preview |
| `client_finance_version_conflict` | conflict | 重新 Query |
| `idempotency_conflict` | conflict | 拒絕不同 payload |
| `invalid_client_refund_intent` | validation | 修正選擇 |
| `client_refund_bank_allocation_incomplete` | blocker | 每筆銀行出款未被完整分配 |
| `client_refund_exceeds_remaining_amount` | blocker | 一般 refund action 拒絕；改走專用 overage action 建立追償應收 |
| `client_refund_return_invalid` | blocker | 退款退匯／沖正目標無效 |
| `client_over_refund_recovery_not_found` | not-found | 重新 Query 異常與 recovery |
| `client_over_refund_recovery_amount_exceeded` | blocker | 入款／adjustment 不得超過 remaining |
| `client_over_refund_recovery_target_ambiguous` | blocker | 人工確認唯一 recovery |
| `client_over_refund_recovery_adjustment_forbidden` | forbidden | 缺 capability，不可調整 |
| `client_receipt_reversal_invalid` | blocker | 不得超額或重複沖正 |
| `client_finance_storage_unavailable` | retryable | 安全重試／查 receipt |

### 3.8 人工入口與異常

- UI 顯示 backend Query 的 bank facts、refund obligations、account version 與 blockers。
- Apply 必須沿用同一次 Preview 的 fingerprint 與 stable idempotency key。
- 金額不符、多義對象、缺 bank identity 或歷史資料不可唯一還原時，維持 open 並進
  Anomalies；不得猜測 allocation。
- overdue reminder 的人工入口只導向 bank fact 匯入、查詢、配對或補正；不得直接把
  提醒標示為已付款。

### 3.9 Legacy exit

- 舊「本階段不支援一般退款」標為 superseded。
- 任何直接更新 `client_payments` summary、負收款、覆寫原 transaction 或跨案抵銷路徑退出。
- Data Browser 不得修改 refund／receipt ledger。

### 3.10 Implementation closure

Client Refund 已具備下列已驗證能力：

1. Finance Import／bank classifier 會產生獨立的 `client_refund` canonical classification；
2. production dispatch 以 borrowed Client Finance Unit of Work 完成退款核銷；
3. `partially_refunded`／`refunded`／`review_required` reducer 維持獨立進度與覆核投影；
4. canonical obligation／ledger projection 導出退款逾期提醒，未匯入銀行對帳單不會誤建為付款失敗；
5. bounded 全域退款待辦提供人工核對入口，根事實核銷後自動解除提醒；
6. Accounts Payable Export 明確區分 `customer_refund` 與 `subsidy_return`；
7. Module、Subsystem、隔離 MySQL Domain 與 Global E2E 均已有可重跑證據；
8. writer inventory 證明負收款、原交易覆寫與 legacy refund caller 已退出。

以上 implementation closure 只適用於既有 exact／partial refund、return／reversal 與清冊能力。
2026-08-11 新增的 client recovery collection／adjustment 與 staff payout difference／recovery
在人工確認及相應 E2E 完成前，不得列為 `proven`。

## 4. 交易與跨 Domain 邊界

- cancellation／adjustment 產生 refund obligation 時，由相應 Global coordinator 的
  outer Unit of Work 同交易委派 Client Finance。
- 實際銀行退款核銷由 Client Finance 擁有，不回寫 Orders lifecycle。
- Accounts Payable Export 可以唯讀合併 staff payable 與 client refund rows，
  但不能在同一 Query 中互相抵銷。
- Finance Import 只提供 canonical bank facts，透過 borrowed Unit of Work 委派
  Client Finance 或 Staff Payables，不直接寫正式 ledger。

### 4.1 Historical payment source priority（2026-08-28 人工裁決）

歷史案件與一般案件都先使用Finance Import匯入的對帳單；只有pre-system且已正式採納的historical
case，在舊銀行／帳務來源不能可靠還原時，才使用owner-specific歷史人工付款／結清Q/P/A。付款是
具payer、payee、direction與exact obligations的event；Client Finance settlement、Staff Payables
completion與Orders Step 11是三個不同projection，不得以單一「已付款」或「已結清」跨owner推定。

客戶補助退款是工會付給客戶的Client Finance `subsidy_return`；Government Subsidy只擁有政府撥款、
claim allocation及政府入款溢撥的合法 offset 處置。工會先墊付客戶補助退款後，政府後續撥款只建立既有墊付款的
settlement link，不新增第二筆客戶退款，也不重開已結清client obligation。

完整source、replay、later-event與UI契約由
`../02_決策與退役執行記錄/PROV-20260828-historical-payment-and-owner-settlement-spec.md`擁有。

## 5. 分層驗收

### Module

- integer NTD、一般 action exact allocation、difference action 金額守恆、deterministic ordering、
  reversal guards；
- payout／refund／remaining／recovery projection reducer；
- workbook aggregation、bytes digest 與 filename。

### Subsystem

- Preview 零寫入；
- Apply replay、idempotency mismatch、stale、rollback、retry；
- refund／reversal 排他；
- payout return／reversal 重開義務；
- staff payout difference、client/staff recovery collection 的 stale、歧義、partial remedy 與 replay；
- archive failure 不宣稱完成。

### Domain

- 隔離 MySQL 驗證 FK、unique、append-only trigger、row lock 與單次 commit；
- 同月嫂多訂單聚合不建立月結；
- 每筆 bank outflow 必須完整表達為 obligation allocation 加上具血緣的 recovery root；
- staff underpayment remaining 與 staff/client recovery collection 均於餘額歸零後才完成。

### Global

- customer over-receipt 3,000／receivable 2,500 → receipt 3,000＋refund obligation 500
  → 5 日退款清冊 → 後續 500 bank outflow → refunded；
- refund obligation 500 → 750 bank outflow → refund allocation 500＋recovery receivable 250
  → anomaly 與後續 canonical incoming recovery；
- cancellation／adjustment→refund obligation→bank refund；
- Payroll→staff payable→payout／return；
- Finance Import dispatch 不繞過 owning Domain；
- client refund 與 staff payout 同批存在但互不抵銷；
- failure injection 證明跨 Domain transaction 全部 rollback。

## 6. 來源追溯

- `04_Client_Finance_Domain.md`
- `05_Staff_Payables_Export_Domain.md`
- `07_跨Domain交易與pytest驗收架構.md`
- `../03_追蹤清單與證據/evidence/2026-08-09_implementation_matrix_revalidation_receipt.md`
- 訂單帳務與資料處理、潛在狀態機歷史合併稿（已由本規格承接並自工作樹移除）
- `document/文件整併工作區/06_欄位權威性與計算邏輯盤點.md`
- `domains/client_finance/client_refund_reversal.py`
- `subsystems/client_finance/client_refund_reversal_workflow.py`
- `domains/staff_payables/reconciliation.py`
- `subsystems/staff_payables/payout_reconciliation.py`
- `subsystems/staff_payables/accounts_payable_export.py`

live files只證明目前已有相符結構，不會因存在而自動取得規格權威。

## 7. 服務中換人的已付義務銜接（2026-10-21）

依使用者核可的服務中換人介面實作，Staff Payables 只消費 Payroll 提供的來源明確 correction，不重算薪資。

- 原付薪 obligation 及實際付款歷史保留。`staff-handover:` 差額不可被付款選單、匯出或自助應付查詢當成另一張獨立 payable；原 obligation 的有效金額包含其換人差額。
- Payroll correction 後同步刷新 Staff Payables projection，實付仍由正式 payout／return／reversal links 推導，不憑儲存換人標記付款或結清。實付大於有效金額時停止該根的付款資格，獨立追償保存該 correction 與原 obligation。
- 只對本次新形成的超付建立追償；重播不得重建，連續換人不得重複計入先前超付。未收回不影響合法排班交接，但不得抵扣其他案件或新月嫂薪資。
- Client Finance 保持原 exact-settlement 契約；換人未改變服務日期、時數、費率或雙薪時，由 owner candidate 證明客戶帳款差額，而非 UI 固定寫零。異常歷史帳款仍阻擋。
