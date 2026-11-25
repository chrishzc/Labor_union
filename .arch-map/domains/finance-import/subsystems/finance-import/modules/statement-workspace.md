# Module: statement-workspace

## Parent
- domain: `finance-import`
- subsystem: `finance-import`

## Responsibility
以正式入帳證據與 canonical 原列投影成功明細；既有人工備查獨立唯讀查閱、identity-only 判重及跨人員警示解除。組合 Client Finance／Staff Payables typed case queries；不重算應收／薪資、不寫 ledger／allocation、不派送外部服務。

台新成功證據同時承接 Government Subsidy 既有 allocation 與現行整期 entry/member，沿用正式核銷與沖正的案件關聯。

月份查詢組合各 owner 正式到期款與已提交銀行事實；銀行來源單筆只計一次，人工原始明細不列現金，歷史案件標記整案排除統計。跨統計範圍而無正式分配金額的銀行款不拆算，現金結果回 unavailable/null，到期款查詢可繼續。案件歷史人工核銷僅寫 application metadata，保存當下原金額快照、原因、人員與時間，不改 owner 金額或 Orders。

## Implementation
- `ui_react/src/api/shared/case_accounting_changes.ts` — 本頁及跨分頁的 committed case invalidation；Terms／個案計價／取消沿正式成功收據發布，Finance Page／案件抽屜重查。抽屜借用既有 Terms 與個案計價面板，不擁有重算；依銀行 `row_id` 精確重查候選，儲存／未知核銷保留原命令，重新同步使舊預覽失效。
- `ui_react/src/components/HistoricalPayableReview.tsx` — 每月帳務及案件抽屜查核歷史月嫂款，帶入同案、同月嫂，委派缺少的應付或付款日同步至 Payroll，並保留已有應付的更正入口。
- `domains/finance_import/statement_archive.py`
- `subsystems/finance_import/statement_archive.py`
- `subsystems/finance_import/accounting_workspace.py`
- `subsystems/finance_import/monthly_accounting.py`
- `infrastructure/mysql/monthly_accounting_repository.py`
- `infrastructure/mysql/finance_statement_archive_repository.py`
- `infrastructure/mysql/accounting_workspace_repository.py`
- `infrastructure/mysql/subsidy_confirmation_repository.py` — 一般／歷史案件共用補助確認組合：Preview 借用原 Client Refund／Staff Payout 預檢尚未建立的合法款項；台新月嫂出款僅有姓名時，按正式補助撥款月份投影案件候選。多案選擇隨原 batch Preview／Apply 傳遞並重新驗證；原 Apply 鎖定來源後，於同一 outer UoW 確認方案、承接款項與核銷，任一步失敗整筆回滾。已定位但未達服務結束條件時只確認方案。
- `query_case_bank_memos`／typed `CaseBankMemo`：台新備註六碼經 Client Finance 正式帳號對照確認唯一案件，原文逐筆投影至案件 `bank_memos`；不要求有款項、不推用途或計入金流。方案區及既有人工選擇頁顯示原文，沿原方案 metadata writer 明確保存。
- `api/routes/finance_statement_workspace.py`
- `api/routes/finance_import.py` — composed router and existing bank commands
- `subsystems/finance_import/import_workflow.py`、`infrastructure/mysql/finance_import_repository.py` — 待核對跨批次重配借用既有 owner resolve／post；保留跨批次競用與須人工確認的明細。
- 舊版永豐待核對薪資可由原始退款備註與同案唯一正式退款單更正。新分類事件與 Client Finance 核銷共用重配交易，原分類與原流水仍可追溯。
- `ui_react/src/components/FinanceBankReconciliationWorkspace.tsx` — 單一正式明細匯出入口、待核對批次重配及每筆唯一核對入口；交易明細唯讀，案件帳務沿既有整案檢視。
- `api/dependencies/finance_import.py`
- `api/schemas/finance_import.py`
- shared: `api/schemas/base.py`, `ui_react/src/api/shared/exact_ntd.ts` — transport preserves whole NTD above the browser's safe integer range.
- `ui_react/src/api/finance_import/finance_accounting_client.ts`
- `ui_react/src/api/finance_import/monthly_accounting_client.ts`
- `ui_react/src/components/FinanceMonthlyAccounting.tsx`、`FinanceMonthlyAccounting.css`
- `ui_react/src/components/FinanceReceivableItems.tsx` — 按到期月份列出正式應收款，未定日期款分到待確認；同一 typed Query 不建立第二份案件總額。
- `ui_react/src/pages/FinancePage.tsx` — 進行中案件（預設）、銀行對帳、政府補助清單、每月帳務；所有案件入口開同一右側抽屜，原核銷與查證工具保留可達入口。
- `ui_react/src/components/FinanceCaseList.tsx` — 組合完整 Orders 搜尋及十三階段正式投影，第8步起列入，最多四案並行查詢；六欄／單一目前事項／階段時效篩選／20案分頁。沿Domain collection_progress顯示訂金→第一期→第二期→方案確認；客戶款齊且人工或銀行明細已正式確認方案才移出。列表由查看案件進入共用抽屜，各期查看通知共用 LINE 同案期款來源及歷史；不可寄送仍可查閱並顯示原因。
- `ui_react/src/components/FinanceBankReconciliationWorkspace.tsx`、`FinanceBankReconciliationWorkspace.css` — 銀行對帳工作台（WF-03/04），跨批次查原始銀行流水與正式核銷狀態，顯示待核對筆數。所有待核對列從同一主入口開單筆抽屜，缺件及查詢失敗仍保留原流水；用途路由不受批次提示覆蓋。匯入及匯入紀錄從原獨立入口查看。
- 永豐待核對的同案月嫂薪資／一般退款流水可在案件抽屜開啟既有 Orders 取消結算，確認實際服務日、預覽並提交；正式回讀後重查同一筆流水與案件款項。
- 「核對交易」以原流水及名冊候選完成單案人工配對。未核銷的誤匯入來源可排除，保留原列、指紋與排除事件，重新匯入沿原指紋判重。
- 補助確認預檢在原上傳面板顯示金額、受款方向與建款／核銷計畫。同月唯一且可核銷的月嫂補助，沿原批次 Apply 自動核銷；同月多案保留選案及確認套用。六碼已定位且有同案應付款的跨月列可開單筆人工核對，沿原 Staff Payables 確認流程。全部受阻時不提供批次核銷動作。
- `ui_react/src/components/FinanceGovernmentSubsidyList.tsx` — 僅接入 Reporting 既有共用畫面（週報補助統計／季度／年度與 XLSX）；政府補助唯一作業入口，案件仍開原抽屜並在原操作成功後重查報表，沒有內部 CSV 或第二套公式。
- `ui_react/src/api/finance_import/finance_import_query_schemas.ts`
- `ui_react/src/components/FinanceCaseAccounting.tsx`
- 補助退款回讀使用 Client Finance 正式 allocation／ledger 的已核銷、銀行實付及整筆內扣費用；無已成立退款與未確認補助歸屬分開顯示，不因退款清單為空宣告結清。
- `ui_react/src/components/CancellationSettlementAccounting.tsx` — common cancellation readback and notices for case accounting and registry.
- `ui_react/src/components/CaseManualSupplementWorkbench.tsx` — case accounting's existing manual input consumes exact remaining amounts.
- `subsystems/finance_import/case_manual_supplement.py` — typed人工補登命令與完整內容冪等檢查；不含SQL或金融root writer。
- `infrastructure/mysql/case_manual_supplement_repository.py` — 保存人工來源及命令收據，借用route的單一outer transaction呼叫Client Receipt／Staff Payout／Client Refund原正式Preview／Apply；同鍵同內容回原流水／入帳收據，不同內容typed conflict。
- `infrastructure/mysql/manual_supplement_evidence.py` — 驗證人工來源與命令收據、exact row、案件及指定款項的關聯，供原Staff Payout／Client Refund adapter投影typed人工對象證據；不把JSON標記當權威，不補造帳號。
- `ui_react/src/components/CaseDifferenceResolutionWorkbench.tsx` — 案件期款差額處置工作台；雙軌處置（直接銷帳／認列差額）與補繳／退補通知連動。
- `ui_react/src/components/FinanceCaseAccounting.css`
- `ui_react/src/components/FinanceCompactCase.css`
- `ui_react/src/components/FinanceSubsidyPlanForm.tsx` — 原三選一表單顯示獨立補助金額及人工／銀行確認來源；保存前呼叫零寫入預檢，顯示可承接款項、原日期與阻擋原因，沿原保存送出 fingerprint。保留提前保存、CAS、原鍵結果未明恢復與草稿保護。
- `ui_react/src/components/FinanceStatementArchive.tsx`
- `db/schema_parts/235_finance_statement_workspace.sql`
- `db/schema_parts/1057_finance_statement_workspace.sql`
- `db/schema_parts/244_finance_case_arrangements.sql`、`db/schema_parts/1066_finance_case_arrangements.sql` — append-only arrangement events，case/version 與 operation key 唯一，UPDATE／DELETE 禁止。
- `db/schema_parts/241_finance_case_accounting_markers.sql`、`db/schema_parts/1063_finance_case_accounting_markers.sql`

- shared composition: `infrastructure/mysql/accounting_workspace_repository.py::build_accounting_workspace` — 案件、清冊與原 owner 退款同步共用 Client Finance 正式繳款來源。僅略過確認為零的缺席期款，工作台與補助交接使用同一應繳、實收結果，既有金融歷史衝突保留。
- 歷史案件由 Client Finance typed payment terms 明示沿原正式款項身分彙總應繳與實收，不套一般訂單三期齊備門檻、不補造缺席期款。同一期多筆、未知期別、未分配款及歷史付款證據逐筆保留。`full_subsidy_eligibility` 區分不適用與來源未知；免自備僅為唯讀呈現，衝突與缺項由 `accounting_pending_reasons` 明示，不改結清證據或付款紀錄。

- `db/schema_parts/245_finance_case_subsidy_plans.sql`、`db/schema_parts/1067_finance_case_subsidy_plans.sql` — 沿原 append-only 方案事件；伺服器保留 `bank-subsidy:<row-id>:<command-digest>` operation key 記錄銀行確認來源，人工命令不能使用該命名空間。不新增 schema 或回填歷史資料。

## Contracts
- `.arch-map/requirements/22_銀行流水匯入與帳務異常處理正式規格.md` §15、§17～18
- archive endpoints beneath `/api/v1/finance-import`: `GET statements/export` 只納入正式owner核銷證據，匯出分銀行原欄位並附「款項用途」（含單一項目與訂金+第一期(組合銷帳)等組合銷帳標示）與「關聯案件」，不顯示內部明細識別與資料來源欄；`GET statements/manual/export` 獨立唯讀匯出既有人工備查；`POST statements/manual` 經認證後回typed 410、無DB writer。React僅提供兩種匯出，不再提供無案件新增表單；案件正式補登仍沿規格22 §19。`POST statements/duplicates` 保留原判重契約。
- `GET /api/v1/finance-import/bank-transactions` — 同一唯讀清單／單筆查詢，以 `row_id` 精確重查原流水，`row_identity=finance-import-row:<row_id>` 供原命令使用。`classification_type` 為正式用途；`cases` 為可查閱案件，不能作核銷資格；`reconciliation_target` 保存 `case_no`、`obligation_identities`、`staff_id` 及 `requires_selection`。無目標與 `reconciliation_unavailable_reason` 不使核對入口消失，查詢失敗不轉成無候選。正式 owner 重驗核銷，不由 Query／UI 寫帳。
- `bank_memo` 為原備註的帳號遮罩投影，不修改銀行原文。單筆 `row_id` 查詢的 `reconciliation_records` 優先讀同筆正式 `finance_import_reconciliation_receipts`，含 `owning_domain`、`amount_ntd`、`recorded_at`。無匯入回執時，讀原 Client Finance 現金收付或 Staff Payables payout 事件，不與匯入回執重複列出。兩者皆無則回空陣列並明示紀錄缺漏，不由已核銷狀態造紀錄；沖正、退匯及其他歷史事件仍由原案件帳務查閱。
- 永豐客戶入款的待核對原因沿原 Apply 收據讀取；多候選合併同一原因並保留當次期別及可空的原到期日，缺日期明示未設定。缺少當次證據時，原因欄明示未留存，並區分依目前期款推得的提示；舊少收／超收及日期／多候選碼只讀對齊新分類，不改歷史收據。退款帳戶缺件只留在明示超收另列退款的操作內。
- 台新客戶補助的當次自動配對失敗原因以 `pending_reason` 進入原 Apply 收據，清單以 `recorded_pending_reason` 讀回；不以備註六碼定位成功證據取代真正的日期、款項、金額、多候選或 owner 資格阻擋。
- 永豐月嫂舊流水的對象辨識紀錄為空時，清單只讀原交易參考編號，沿既有完整帳號解析確認唯一主要帳戶及同案正式月嫂義務後提供核對入口，不回填舊辨識紀錄。缺帳號、帳號不唯一或無同案義務仍待確認；台新及客戶款不採此補充查核，正式 Preview／Apply 仍由原 owner 重驗。
- 台新客戶補助的入口依原始備註六碼或客戶姓名確認案件，並排除命中月嫂姓名的來源。同名客戶依六碼或唯一合格退款月份定位，跨月或無唯一案件留待核對。候選限同案補助待退款；正式 Preview／Apply 重驗原備註、資金資格、日期及核銷規則。
- 台新待核對月嫂補助依流水 occurrence 找最近完成的正式批次，`staff_subsidy_batch_identity` 只對月嫂用途投影。客戶補助退款不產生該提示，前端即使收到舊提示也優先走退款。`staff_subsidy_manual_review_allowed` 由後端沿原 owner 補助資格及來源分期日期查核，僅確認符合例外時為 true；案件、一般應付日期及提示本身都不能替代資格。
- `POST /api/v1/finance-import/batches/preview` 與 `batches/apply` 保留原批次入口；單筆抽屜沿同一契約傳 `review_row_identity`、`staff_subsidy_selections`，只解析及派送指定交易。Apply 重新建立相同 scope，驗證原 fingerprint 與版本，沿原 durable job／outcome 回讀；不因單筆入口核銷同批其他列。
- 客戶退款沿 `POST /api/v1/finance-import/corrections/preview`、`corrections/apply` 與 `GET /api/v1/finance-import/jobs/{job_id}/correction-outcome`，送 `row_identity`、正式 `classification_type`、`target_obligation_identities` 及原預檢版本／fingerprint。原 correction workflow 委派 Client Finance，缺正式退款不自動建款；核對流程與錯誤投影見 `finance-import-correction`。
- `import-history`、`workbooks/ingestion-outcome` — 查每次匯入的保存、核銷結果與原操作結果；待核對歷史筆數沿原匯入／核銷收據保存，缺歷史證據顯示未知。
- manual plan endpoints: GET/POST `cases/{case_no}/accounting/subsidy-plan` 與 POST `cases/{case_no}/accounting/subsidy-plan/preview`；沿原 actor、version CAS、Orders identity lock 與同鍵重播。Preview 零寫入，原保存重驗預檢並借用既有 owner 承接已合資格款項；未具金融資格可保存已預檢的方案但不得建款或核銷。無外部付款及日期重算。
- case/warning endpoints: `cases/{case_no}/accounting`, `cases/{case_no}/accounting/dismiss`, `accounting/warnings`
- monthly endpoints: `accounting/monthly`、`accounting/monthly/export`；marker Query/Apply: `cases/{case_no}/accounting/historical-marker`。
- `accounting/receivables` — readonly 到期月份／全部月份／未定日期清單；沿用分類及歷史標記統計排除。
- marker Apply fresh-locks current owner versions, preserves an immutable amount snapshot, and supports same-key/same-command replay; one application transaction, no cash or service completion effect.
- archive command owns its outer transaction and same-command receipt; acknowledgement fresh-locks owner facts and checks existing version/amounts, writing only acknowledgement.

- case Query adds independent stage provenance, T/B/S, current collection gate and conservative scheme projection；S 由 Government Subsidy 單案共用 Query 提供，不以方案或退款義務存在為前提，未知不轉零。方案事件明示人工／銀行來源；未收到政府款不作直付證據。舊 direct arrangement 仍沿原 append-only confirm_direct/withdraw_direct 與其 writer，不回填或改寫。
- arrangement confirmation fresh-reads the original paid-stage, T/B/S and bank facts; insufficient or contradictory sources reject confirmation. Later G/PT/RT or B/T conflicts leave the original arrangement intact and project scheme=unknown. History uses UTC ISO instants and Taipei display; formed service/due dates are untouched.
- bank facts add uniquely proven C/G/PS/PT/RS/RT; monthly by original bank date, single-case totals unavailable for shared sources. Existing ledgers, allocations and due/service dates are read-only.
- 案件抽屜沿既有摘要、客戶期款、補助方案、月嫂應付及客戶退款／政府款檢視。單筆交易核對保存原來源與用途，案件檢視不重作一份交易明細；往返保留原交易、清單篩選與核對／明細入口，返回重查使舊預覽失效，不自動提交。正式核銷資訊只來自原 owner 回讀；通知仍由 LINE owner 負責，各核銷工具保留原 writer。
- 客戶收款面板的全案餘額同時消費既有 Receipt Query 與案件帳務 Query：只彙總版本一致、來源完整的客戶應收正式餘額；缺來源、缺列或未知餘額保留待確認，不從未清清單為空推定結清，也不加入月嫂應付或退款結清門檻。正式成功後依收據版本與回讀再次確認。

## Verification
- layout_status: `custom_current`
- test_root: `tests/domains/finance-import/subsystems/finance-import/integration/test_statement_workspace.py` — 既有模擬案例核對現金無法跨統計範圍加總時，到期款查詢與匯出仍可使用。
- integration_root: `tests/domains/finance-import/subsystems/finance-import/integration/test_case_manual_supplement.py`
- integration_root: `tests/domains/finance-import/subsystems/finance-import/integration/test_subsidy_confirmation_mysql.py` — 隔離 MySQL 驗證一般／歷史未確認補助計算、兩種台新受款方案、Preview 零寫入、原 Apply 建款核銷、同月唯一及多案選擇、原六碼備註入庫、提前確認、來源過期與失敗整筆回滾。
- integration_root: `tests/domains/finance-import/subsystems/finance-import/integration/test_case_manual_supplement_mysql.py` — opt-in isolated MySQL：三方向正式核銷、足額／部分／手續費／超收退款／超付追償、完整回滾及同鍵重送／衝突／並行。
- integration_root: `tests/domains/finance-import/subsystems/finance-import/integration/test_statement_archive_mysql.py` — 隔離MySQL驗證410零寫入、原鍵不重放舊新增成功、成功匯出只含正式核銷、歷史備查唯讀不改資料、三種正式補登仍可匯出。
- Higher-boundary MySQL coverage uses the finance-import Subsystem's declared disposable E2E entry.
- test_root: `ui_react/src/tests/domains/finance-import/subsystems/finance-import/modules/statement-workspace/`
- cross-owner evidence: [pricing-configuration 的 MySQL 整合驗證](../../../../client-finance/subsystems/client-finance/modules/pricing-configuration.md#verification)，隔離 MySQL 查詢及帳務 API 回應由專項 CI 暫存傳入 `compact_case_drawer.test.tsx`，核對歷史免自備與原款項契約；不以 UI mock 取代後端驗證。
- `.github/workflows/historical-accounting.yml` 執行本案 Python、隔離 MySQL、React、型別與 lint 專項。

## 國定假日計價接線 ^statement-workspace-holiday-pricing

```yaml archmap-impact
- kind: implements_requirement
  source: statement-workspace-holiday-pricing
  target: ".arch-map/requirements/22A_案件帳務三方案與補助流向正式規格.md#^case-accounting-schemes"
```
- 假日對帳接線由下列 owner 實作，驗證見既有測試入口。工作台從 Client Finance 與 Payroll 正式金額投影讀取非市民工會收入差額，不以同額不變量誤報異常。正式銀行核銷／月嫂清償來源由原 owner 判定，假日設定入口借用 fresh facts；全額免自備加成差額交既有對帳結果顯示待決策，不假建交易或更改政府補助。

- 既有案件／對帳查詢承接假日與日期調整回執的逐案結果、未重算原因、重算金額與已入帳金額；依22A區分待人工對帳差額，不把未指定負擔差額列工會收入。設定成功、帳務重算成功與付款／核銷事實各自呈現。
