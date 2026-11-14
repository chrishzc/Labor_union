# Client Finance Domain

## 1. 文件邊界與所有權

- 狀態：`current-spec`
- Owner：Client Finance Domain（`domains/client_finance/`、`subsystems/client_finance/`）
- 單一負責範圍：帳務參數與個案分段計價、客戶身份計價邊界與非市民定金、客戶應收／分期／調整／一般退款與補助退還義務、不可變客戶帳本（`client_ledger_entries`）與 `M:N` 核銷分配、取消結算與違約金、專屬虛擬帳號與單案修改，以及歷史付款證據與未收訂金釋放確認。
- 關聯引用：見 [Global 共同契約](00_Global_共同契約.md)、[Payroll Domain](03_Payroll_Domain.md)、[Government Subsidy Domain](14_Government_Subsidy_Domain.md)、[Staff Payables 與 Client Refund](16_Staff_Payables與Client_Refund正式規格.md)、[Case Import 與非市民待審](17B_Case_Import與非市民Redis待審正式規格.md)、[LINE 客服與月嫂自助服務](20_LINE客服與月嫂自助服務正式規格.md)、[Contract Signing 正式規格](21_Contract_Signing_Commitment與正常驗收資料鏈正式規格.md)、[銀行流水對帳與手動補登](22_銀行流水匯入與帳務異常處理正式規格.md)、[案件帳務三方案與補助流向](22A_案件帳務三方案與補助流向正式規格.md)、[帳務差額處置與工作台 UI](22B_帳務差額處置與工作台UI正式規格.md)、[歷史訂單生命週期與服務天數帳務](27_歷史訂單生命週期與服務天數帳務正式規格.md)、[營運報表與統計口徑](34_營運報表與統計口徑正式規格.md)。

## 2. 核心不變量與計價規則

### 2.1 正式身分與資格保護（`IDENTITY-FIX`、`QUAL-FIN`）

- **IDENTITY-FIX-01／02／04**：正式補助身分為「一般市民」（預設 40 小時，`citizen`）、「補助市民」（社福／低收入戶／中低收入戶別名來源，預設 120 小時，`social`）、「原住民」（`原民`／`原住民市民`別名來源，帳務參數管理，預設 80 小時／350 元）與「非市民」（0 小時）。HCM 匯入與保留資料升級必須保持一般市民、補助市民與原住民獨立存在，禁止將一般市民併入或重算為補助市民；新進件須綁定具正確正式命名之政策（缺命名時回 typed error），既有綁定案件按原快照讀取。
- **QUAL-FIN-01～04**：
  - 補助資格與自費服務受理分開：社福資格不符但符合一般市民資格者歸一般市民；非市民補助為 `0`，仍可依 [Case Import 與非市民待審](17B_Case_Import與非市民Redis待審正式規格.md) 另案核准建立 `A＋民國年度＋3碼流水號` 自費案，原 HCM 報名作廢。
  - 補助資格與工會經手方案分開：除 [全額補助免自備例外](22A_案件帳務三方案與補助流向正式規格.md#full-subsidy-no-advance) 外，身分與固定時數門檻不決定三方案或是否先墊。
- **Reporting 案件總額唯讀投影**：`case_total_amount`（`calculate_case_total_amount`）由完整有效 `CasePricingFacts` 組合服務費及一次樓層費（含補助內與超額），報表不得以扣補助後應繳或實收替代整案金額。

### 2.2 帳務參數與個案分段計價（`PRICE-01～09`）

- **PRICE-01**：帳務作業左側設獨立「帳務參數設定」，維護版本、生效日、各身分補助上限、客戶及月嫂「補助內／用盡後」時薪、各身分訂金天數、胎數費率與選填說明。
- **PRICE-02**：案件首次建立時（臺灣時間當日 `00:00` 已生效之最新政策）立即綁定版本（待補件亦同）；後續補件或新政策發布不換版。
- **PRICE-03**：客戶名冊右側抽屜「個案計價調整」可直接設定本案補助上限與四段時薪；原因選填（留白存空字串），一次點擊直接儲存（不提供影響預覽或額外確認，亦不覆寫已形成期款或到期日）。
- **PRICE-04**：補助內時數於整案服務日期累計，`補助內時數 = min(有效服務時數, 本案上限)`，超額按用盡後時薪計算。國定假日的正式服務工時與其他正式服務工時使用相同的計價規則，並以同一口徑計算應收分期與案件總額。
- **PRICE-05／06／07／08／09**：月嫂客戶負擔於服務結束月 `+ 1` 月 15 日、直接補助部分於 `+ 2` 月 15 日給付；設定 application 於單一 outer UoW 同步未結清義務，已核銷交易、已簽文件及已核銷政府期間快照保持不可變，差額沿 adjustment／refund／追償承接；涉已核銷政府期間快照異動而無入口時回 typed blocker 且零寫入。
- **補助內時薪防護與退款欄位放寬**：
  - 一般／補助市民與原住民之補助內預設：一般市民 `300` 元／時、補助市民與原住民 `350` 元／時；補助範圍內客戶時薪必須等於月嫂時薪且為正整數（Domain Preview／Apply 違反回 typed `422` 零寫入）。非市民補助時數與補助內費率皆為 `0`，全額自費採自費／用盡後費率。
  - `amount_correction` 衍生之客戶退款允許暫無退款帳號（`require_complete=False`），AP 出款清冊依既有規則檢核受款帳戶。永豐銀行對帳以原始備註或正式人工配對驗證案件，詳見銀行流水匯入正式規格 §4.2。

### 2.3 非市民付款與案件類別篩選（`NC-FIN-01～06`）

- 正式核准之非市民案件依 `PRICE-02` 綁定政策全額自費（不另造固定費率），定金收取 `5` 天服務費（加一次樓層費），第一／二期與零金額日期規則沿本 Domain 公式，退款帳戶保留 BeClass 原必填檢核。
- 帳務統計提供「案件類別」篩選：**補助案件（預設）**、**非市民案件**、**全部案件**（兩類聯集不重複計數），以正式身分規則區分，查詢明細、件數與合計維持同集一致，不覆蓋 Reporting 原獨立統計。

### 2.4 SSOT 資料表與寫入邊界

| 概念 | 唯一權威 |
|---|---|
| 付款條款與到期日 | `PaymentTerms` root facts（`client_payment_terms`） |
| 專屬虛擬帳號 | Client Finance（§8 定義；Finance Import 消費同一 typed 結果） |
| 應收／退款／補助退還義務 | append-only obligation events（`client_obligations` projection） |
| 收款／退款／adjustment／reversal | immutable `client_ledger_entries` |
| 核銷分配 | append-only `M:N` allocations |
| 餘額與結清時間 | obligation 與 ledger reducer（`client_payments` 僅相容投影） |

- 不擁有 Orders lifecycle、assignment、正式服務日、銀行原始流水或 Alert workflow。
- 一般期款正式核銷須完整分配所選銀行流水，且所選義務在同一次 Apply 後精確歸零；明示部分收款、取消補收／退款與 0～100 元手續費依各自契約。

## 3. 公開契約與流程

### 3.1 分期規劃、實際開始日同步與通知資格（`CF-DEPOSIT-01～02`）

- **訂金天數與分期規則（`CF-DEPOSIT-01／02`）**：
  - 帳務參數於「補助身分與分段時薪」逐身分設定訂金天數（留空沿用身分規則；`0` 免收訂金服務費；正整數取前 `N` 個有應繳服務費日期計訂金，接著最多 `15` 日列第一期，其餘列第二期）；樓層費計入訂金且整案僅一次。`CF-SCHEME-FULL` 成立時三期應繳皆為 `0`。
  - 服務本金固定為 `有效正式服務時數 × 有效服務單價`（雙胞胎 `450`）；服務前合法胎數更正同交易同步 open 義務，完工確認即凍結本金。
- **第一／二期到期日**：
  - 第一期到期日採 Orders 正式 `actual_start_date`（未確定時暫採預計開始日）；月嫂接受／工會代班保存實際開始日時同交易委派 Client Finance 同步第一、二期到期日（局部代班不重設第一期日）。
  - 第二期有應付正額時，`client_payment_terms.second_payment_due_date` 固定為 `first_payment_due_date + 15 個曆日`（第二期金額為零時存 `NULL`）。
- **雙方簽約完成與 LINE 通知資格**：
  - 訂金繳費提醒與各期逾期待辦須同時滿足「客戶及所有月嫂簽約完成」（同案 `order_contract_flow_events.event_type = contract_completed` 且 `contract_identity` 等於現行 Orders 契約識別），逾期於臺灣到期日隔天起且餘額為正成立。
  - 正式訂金核銷於 `orders_deposit_reconciled` outbox payload 保存 `line_deposit_notification=true`；第一期正式核銷於 `projection_refresh` 保存 `line_first_payment_notification=true`（供 LINE 衍生內部通知待辦）；第二期正式核銷保存 `line_second_payment_notification=true`。所有 Query 與歷史無標記資料均不觸發通知。
<a id="unpaid-deposit-override"></a>

- **未付訂金人工放行（`GET /api/v1/orders/{case_no}/client-finance/deposit-skip`、`POST /api/v1/orders/{case_no}/client-finance/deposit-skip/preview`、`POST /api/v1/orders/{case_no}/client-finance/deposit-skip/apply`）**：遇突發狀況時，admin 可經專用 Preview／Apply 放行一般市民、補助市民、原住民及非市民案件。身分別名依 `IDENTITY-FIX-01／02／04` 對照，案件須有尚未付清的訂金應收。放行透過 outbox 交 Orders 推至 `訂單成立`，Operational Stage 標示「定金未付，已人工放行」。Payment terms 異動使放行失效。LINE 案件群組綁定仍要求 `settlement_state = settled`。

<a id="client-cancellation-settlement"></a>

### 3.2 取消結算、違約金與 `direction` 契約

- **取消 Preview／Apply 公開 `direction`（Server-owned Enum）**：每筆 impact 必帶必填 `direction`、非負整數 `direction_amount_ntd` 與比較基準欄位（`before_amount_ntd`／`after_amount_ntd` 為調整前後 obligation target，`current_settled_amount_ntd` 為由不可變 ledger／allocation reducer 重建之目前已結算金額；UI 嚴禁由正負號或 `action_kind` 推定）：

| `direction` / `action_kind` | 條件 | `direction_amount_ntd` | `obligation_amount_ntd` |
|---|---|---:|---:|
| `refund_due`（`create_refund`） | `after - current_settled < 0` | `current_settled - after` | `current_settled - after` |
| `additional_charge_due`（`create_stage` / `create_adjustment`） | 新增或 `after - current_settled > 0` | `after - current_settled` | `after - current_settled` |
| `additional_charge_due`（`replace_open`） | `after > before` | `after - before` | `abs(after - before)` |
| `no_finance_change`（`replace_open` / `cancel_open` / `unchanged`） | 未收減額／取消／無異動 | `0` | 視 `before` 變動 |

- **全案取消結算與違約金**：
  - `最終應付 = 服務應付 S + 取消違約金 F`（`F` 不計入月嫂薪資或政府補助）。`淨實收 R` 計入同案有效已入帳收款減去有效退款與沖正。
  - `應退款 = max(0, R - S - F)` 建立一般待退款單；`應補收 = max(0, S + F - R)` 建立待補收（分列服務費與違約金待收）；皆為 `0` 即結清。
  - **抵扣順序與營收認列**：實收先抵 `S`，餘額再抵 `F`；`已收違約金 = min(F, max(0, R - S))` 列公會營收，以**正式提交／核銷當月（臺灣時間）**歸月（與銀行交易日獨立並存於月報）。
  - 退款核銷支持 `0～100` 元手續費結清與超過 `100` 元人工部分退款；補收分次入款按「服務費優先」分配並即時增加違約金營收；全額結清後提供通知來源予 [LINE 客服與月嫂自助服務 §4.5](20_LINE客服與月嫂自助服務正式規格.md)。

### 3.3 差額處理與人工金額更正契約（`CF-DIFF-01～10`、`CF-SCHEME-*`）

- Client Finance 與 [案件帳務三方案](22A_案件帳務三方案與補助流向正式規格.md) 及 [帳務差額處置](22B_帳務差額處置與工作台UI正式規格.md) 共用規則，嚴禁另設第二套三方案或手續費公式：
  - **CF-DIFF-01／09**：支持系統應收／應退款人工結果更正並維持「自動計算／人工更正」模式切換（`DIFF-RECALC-01`）。
  - **CF-DIFF-02／03／04／10**：少收保留餘額追收／協調合繳；多收另列退款、超退另列追償（詳細追償與手續費結清見 [Staff Payables 與 Client Refund](16_Staff_Payables與Client_Refund正式規格.md)）；歷史原因無法查明之案件人工核銷僅作案件標記並排除實際統計；同案多筆入款並列明細與合計直接核銷。
  - **CF-DIFF-05／06／07／08**：分別對應「同意減收服務費（不改月嫂薪資）」、「由工會負擔客戶入款手續費（月嫂薪資不變）」、「工會承擔客戶退款超付追償不再追回」、「確認不用再補付／退款（僅限客戶退款少退與多付款不用退回，不另存同意證明／操作紀錄）」。
  - **退匯例外**：僅允許已有「客戶退匯」分類且唯一案件確認之流水於抽屜人工選取本案有效原退款走 `refund-return` Preview／Apply 核銷並重開原退款。

### 3.4 不可變帳本、補助退還分離、調整單與釋放確認

- **收款統計與禁止連環沖正**：收款工作區「已收款」依 `entry_type=receipt` 計 `receipt_entry_count`（不含調整、退款、沖正）。原交易永不 UPDATE；嚴禁 `reversal-of-reversal`，疑似錯誤沖正僅能於警示核查後由 Preview／Apply 建立新調整單。
- **一般退款與補助退還業務線嚴格分離**：

| 業務線 | payout entry | return／reversal entry | obligation projection |
|---|---|---|---|
| 一般客戶退款 | `refund` | `refund_reversal` | `pending → partially_refunded → refunded` |
| 客戶補助退還 | `subsidy_return` | `subsidy_return_reversal` | 獨立 `subsidy_return` 進度，不與一般退款互抵 |
| 客戶收款沖正 | — | `reversal` | 僅重開 `receivable` |

- `GET /api/v1/finance-reports/client-subsidy-returns` 維持 bounded cursor、缺值不填零、缺帳號不隱藏案件。
- **Adjustment Scope**：`client_only` 不檢查或遞增 Payroll 版本；`client_and_staff` 強制 client delta 等於 staff allocation 合計且同交易 CAS 兩端版本；沖正必須沿用原 scope。
- **Historical `paid | settled` 證據**：無法取得銀行事證時允許綁定 `historical_adoption`、方向、exact obligation、`actor`、`reason`、`evidence`、版本、fingerprint 與 receipt 之歷史處分（未知日期存 `null/unknown`）。
- **未收訂金釋放確認（`UnreceivedDepositConfirmation`）**：Scheduling 釋放已保留但尚未建立訂金應收之檔期時，借用外層交易鎖定 Finance account 並確認零義務／事件／ledger 歷史；存在異常或正式歷史時回 `deposit_receipt_unconfirmed`。

### 3.5 專屬虛擬帳號與單案修改（`99781699`、`VA-01～06`）

- **帳號來源**：以案件編號的民國年度判斷。一般案 115 年含以前只使用匯入對照，缺對照或對照不唯一時待確認。115 年含以前非市民案有唯一有效登錄時使用實際配號，無登錄時使用非市民公式，有歧義時待確認。登錄後本案退出公式反查。116 年起的一般案與非市民案沿各自公式，名冊單案設定唯讀。名冊設定及帳務匯出保留匯入及內建來源，後續契約與繳款資訊讀取有效帳號。
- **公式與撞號**：固定前綴 `99781699`；9 碼案件號取前三碼民國年＋後轉三碼序號；非市民取民國年＋`(流水號 + 500)` 三碼（如 `A115001` → `99781699115501`）。有效匯入對照優先，公式號碼若已被匯入對照占用，或命中多個公式案件，不提供該公式帳號。收款帳號須可唯一反查至本案。
- **永豐客戶存入 3 階段判定**：(1) 解析 14 碼銷帳編號定位唯一案件 → (2) 單一未清期款金額完全一致自動精確核銷 → (3) 無法以金額定位時比對交易日與到期日年月（同月唯一等額自動核銷；同月唯一不同額呈現差額；跨月／多候選／缺日期進待核對並於案件抽屜呈現）。
- **單案虛擬帳號修改（`VA-01～06`）**：
  - Endpoint：`GET /api/v1/admin/client-finance/cases/{case_no}/virtual-account` 與 `POST /apply`。
  - 115 年含以前直接儲存，沿用 `expected_mapping_ids` 防止過期更新。同一交易取代本案全部匯入對照並保存 `admin_command_receipts`。一般案仍拒絕他案占用。
  - 歷史非市民更正檢查實際登錄的占用。若占用案皆為 Orders 目前正式取消，經 NAS 專用程序只移除其指定帳號，同交易登錄本案並記錄轉出案號。若任一占用案有效、已重開或無法確認正式取消，拒絕寫入並回報衝突案號。提交時重驗歸屬及狀態。帳號更正保留已簽契約、既有帳本及分配。
- **Excel 帳號對照**：一般案保留既有批次新增、略過、同案多筆歷史對照及重送規則。一般案列欲新增的號碼若已有唯一生效的非市民匯入對照，略過該列並顯示占用案號，其餘有效列照常匯入。支援 115 年含以前的已建檔非市民案，預覽列出適用性、轉出或衝突案號。套用前重驗對照與取消狀態。涉及非市民列的同檔帳號跨案衝突，以及同一非市民案被指定多號時，拒絕衝突群組。非市民案已有不同對照時，透過單案確認取代。正式切換前唯讀確認現存且即將生效的非市民對照。

### 3.6 Typed Commands、Errors、Ports 與 Live Writer Exit

- **輸入 Ports**：`OrdersTermsFactsPort`、`OfficialServiceDaysPort`、`ClientEligibilityPolicyPort`、`FinanceImportCanonicalIncomingFactsPort`、`FinanceImportClientReceiptDispatchPort`、`FinancialAdjustmentFactsPort`、`GovernmentSubsidyReceiptAllocationFactsPort`。
- **輸出 Ports**：`ClientFinanceImpactPreviewPort`、`ClientSettlementFactsPort`、`ClientFinanceRootFactsOutboxPort`、`ClientFinanceQueryPort`。
- **Commands**：`QueryClientFinance`、`Query/Preview/ApplyClientDepositSkip`、`Preview/ApplyClientReceiptReconciliation`、`Preview/ApplyClientRefund`、`Preview/ApplyClientAdjustment`、`Preview/ApplyClientReversal`、`Preview/ApplyClientSubsidyReturn`、`Query/Preview/ApplyClientSubsidyAdvance`、`RebuildClientObligationsForCase`、`Query/Preview/ApplyHistoricalClientPaymentRepair`。
- **Stable Errors**：`client_finance_case_not_found`、`invalid_client_finance_intent`、`bank_fact_not_eligible`、`bank_transaction_date_missing`、`bank_currency_not_twd`、`client_subsidy_memo_recipient_unconfirmed`、`client_obligation_not_found`、`allocation_not_exact`、`client_receipt_underpaid`、`client_receipt_overpaid`、`client_finance_identity_ambiguous`、`reversal_target_invalid`、`reversal_amount_exceeded`、`adjustment_evidence_required`、`client_finance_candidate_stale`、`idempotency_conflict`、`transaction_failed`、`subsidy_advance_not_due`、`subsidy_advance_already_recovered`、`subsidy_advance_settlement_ambiguous`、`client_finance_direction_missing`、`client_finance_direction_amount_mismatch`、`deposit_receipt_unconfirmed`、`historical_client_payment_not_eligible`、`historical_client_payment_direction_ambiguous`、`historical_client_payment_obligation_binding_invalid`。
- **Writer Exit**：僅 Client Finance adapters 可寫 obligation event、client ledger、allocation、refund、adjustment、reversal 與 settled projection；`services/client_payment_writer.py`、`client_payment_transactions.py`、`client_receipt_reconciliation.py`、`client_subsidy_return_*.py`、`client_payment_snapshots.py` 與 `db_service.py` 不得寫入根事實。

## 4. 驗收標準

### 4.1 歷史非市民虛擬帳號

| S 情境 | T 任務 | A 操作 | R 通過條件 |
|---|---|---|---|
| 115 年含以前非市民案使用內建號 | 單案更正實際配號 | 在名冊儲存並回讀兩個來源欄位，再查完整帳號及六碼 | 唯一實際號生效，原公式號退出本案反查。116 年起維持唯讀。 |
| 同號已登錄給其他案件 | 判斷能否轉入 | 以正式取消案與仍有效或已重開的來源分別提交 | 只移轉取消案的指定對照，保留來源其餘對照。有效案占用時零寫入並顯示案號。 |
| 非市民案已取得實際號 | 避免後續 Excel 改變帳號歸屬 | 匯入含同號衝突列及另一筆有效一般案列的工作簿 | 衝突列略過且顯示占用案號，非市民帳號持續生效，有效列照常匯入。 |
| 115 年含以前一般案有唯一、缺少或歧義對照 | 保留銀行匯入辨識 | 用同一批原始永豐及台新流水執行升級前後匯入 | 逐筆比較是否入庫、分類、案件、對象及待核對原因，結果一致。 |
| 同批一般案流水具備入款或出款核銷條件 | 保留實際入帳結果 | 在升級前後執行重配與核銷，回讀帳本並重送 | 每筆案件、對象、款項、金額及分配一致，重送只入帳一次。 |

1. 補助內客戶與月嫂時薪一致驗證（違規 422）、非市民 5 天訂金與 `A` 字頭帳號 `115501` 映射、案件類別三篩選互斥與合計一致皆零寫入誤差。
2. 取消結算在違約金 `0／500／2,000／2,500` 及跨月補收／手續費 `0～100` 元情境下，`refund_due`／`additional_charge_due`／營收歸月與公會實付一致；`client_only`／`client_and_staff` 調整與 `refund`／`subsidy_return` 分離無混淆。
3. 永豐三階段配對、同案多筆合計核銷與 `VA-A1..A5` 單案帳號修改防跨案／stale 409／同命令重播全數成立；`UnreceivedDepositConfirmation` 在空財務歷史下放行、有正式歷史時回 `deposit_receipt_unconfirmed`。
