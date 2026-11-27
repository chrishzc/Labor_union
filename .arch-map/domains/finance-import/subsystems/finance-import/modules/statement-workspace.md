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
- `infrastructure/mysql/subsidy_confirmation_repository.py` — 一般／歷史案件共用補助確認組合：Preview 借用原 Client Refund／Staff Payout 預檢尚未建立的合法款項；台新月嫂出款僅有姓名時，按正式補助撥款月份投影案件候選。多案選擇隨原 batch Preview／Apply 傳遞並重新驗證；原 Apply 鎖定來源後，用同一 outer UoW 交原 owner 承接款項與核銷，再依正式結果辨識方案。任一步失敗整筆回滾。未達服務結束條件時，保留待核對原因。
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
- `ui_react/src/components/FinanceCaseList.tsx` — 組合完整 Orders 搜尋及十三階段正式投影，第8步起列入，最多四案並行查詢；六欄／單一目前事項／階段時效篩選／20案分頁。沿Domain collection_progress顯示訂金→第一期→第二期→方案確認；依 22B §3.2 判定是否移出，結清進度與方案辨識分開；方案確認來源依 22A §2.2。列表由查看案件進入共用抽屜，各期查看通知共用 LINE 同案期款來源及歷史；不可寄送仍可查閱並顯示原因。
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
- 歷史案件由 Client Finance typed payment terms 明示沿原正式款項身分彙總應繳與實收，不套一般訂單三期齊備門檻、不補造缺席期款。同一期多筆、未知期別、未分配款及歷史付款證據逐筆保留。`full_subsidy_eligibility` 區分不適用與來源未知；免自備僅為唯讀呈現，衝突與缺項由 `accounting_pending_reasons` 明示，不改結清證據或付款紀錄。完全沒有正式期款時不推算應繳或實收；同一查詢結果供款項預檢與收款進度使用。

- `db/schema_parts/245_finance_case_subsidy_plans.sql`、`db/schema_parts/1067_finance_case_subsidy_plans.sql` — 沿原 append-only 方案事件；伺服器保留 `bank-subsidy:<row-id>:<command-digest>` 及 `receipt-subsidy:<ledger-id>:<command-digest>` operation key 記錄正式補助出款與客戶收款來源。人工命令保留自己的 operation key。不新增 schema 或回填歷史資料。

## Contracts

### 從銀行匯入到成功明細匯出 ^statement-export-admission

```yaml archmap-impact
- kind: implements_requirement
  source: statement-export-admission
  target: '.arch-map/requirements/22_銀行流水匯入與帳務異常處理正式規格.md#^bank-statement-export-admission'
```

- Finance Import 保存原始銀行流水及去重識別；預覽、202 受理和待核對都不是入帳。客戶與月嫂實際收付、政府整期入款，分別由原帳務模組重驗及提交。此工作台只組合讀回，不以畫面狀態補寫帳本。
- 驗收：用同一筆合成銀行流水。僅匯入、預覽或留待核對時，「匯出對帳明細」沒有該筆；正式核銷且讀回原帳務模組的成功證據後，匯出恰有一筆原始流水。重新查詢同一筆不會重新入帳或增加匯出列。測試位置見下方 `test_statement_archive_mysql.py`。

- `.arch-map/requirements/22_銀行流水匯入與帳務異常處理正式規格.md` §3（成功明細與匯出）、§4（銀行對帳）、§5（帳務警示）、§6（案件補登）
- 銀行明細匯出依 [規格 22 §3.3](../../../../../requirements/22_銀行流水匯入與帳務異常處理正式規格.md#33-成功明細整庫匯出bank-03)。`GET /api/v1/finance-import/statements/export` 只納入原 owner 正式核銷的銀行流水及正式補登，分銀行保留原欄位，附「款項用途」（包括「訂金+第一期(組合銷帳)」等正式組合銷帳）與「關聯案件」，不顯示內部識別及資料來源欄，也不受畫面篩選限制。`GET /api/v1/finance-import/statements/manual/export` 獨立唯讀匯出舊紀錄，標為「歷史人工備查（不代表已核銷）」，不得混入成功明細。
- 舊版新增路徑：授權管理員呼叫 `POST /api/v1/finance-import/statements/manual` 回 `410 legacy_manual_statement_retired`，不開寫入交易。React 不提供此新增表單；要新增案件的正式補登，走 #22 §6 的案件抽屜與原款項 owner。`POST statements/duplicates` 保留原判重契約。
- `GET /api/v1/finance-import/bank-transactions` — 同一唯讀清單／單筆查詢，以 `row_id` 精確重查原流水，`row_identity=finance-import-row:<row_id>` 供原命令使用。`classification_type` 為正式用途；`cases` 為可查閱案件，不能作核銷資格；`reconciliation_target` 保存 `case_no`、`obligation_identities`、`staff_id` 及 `requires_selection`。無目標與 `reconciliation_unavailable_reason` 不使核對入口消失，查詢失敗不轉成無候選。正式 owner 重驗核銷，不由 Query／UI 寫帳。
- `bank_memo` 為原備註的帳號遮罩投影，不修改銀行原文。單筆 `row_id` 查詢的 `reconciliation_records` 優先讀同筆正式 `finance_import_reconciliation_receipts`，含 `owning_domain`、`amount_ntd`、`recorded_at`。無匯入回執時，讀原 Client Finance 現金收付或 Staff Payables payout 事件，不與匯入回執重複列出。兩者皆無則回空陣列並明示紀錄缺漏，不由已核銷狀態造紀錄；沖正、退匯及其他歷史事件仍由原案件帳務查閱。
- 永豐客戶入款的待核對原因沿原 Apply 收據讀取；多候選合併同一原因並保留當次期別及可空的原到期日，缺日期明示未設定。缺少當次證據時，原因欄明示未留存，並區分依目前期款推得的提示；舊少收／超收及日期／多候選碼只讀對齊新分類，不改歷史收據。退款帳戶缺件只留在明示超收另列退款的操作內。
- 台新客戶補助的當次自動配對失敗原因以 `pending_reason` 進入原 Apply 收據，清單以 `recorded_pending_reason` 讀回；不以備註六碼定位成功證據取代真正的日期、款項、金額、多候選或 owner 資格阻擋。
- 永豐月嫂舊流水的對象辨識紀錄為空時，清單只讀原交易參考編號，沿既有完整帳號解析確認唯一主要帳戶及同案正式月嫂義務後提供核對入口，不回填舊辨識紀錄。缺帳號、帳號不唯一或無同案義務仍待確認；台新及客戶款不採此補充查核，正式 Preview／Apply 仍由原 owner 重驗。
- 台新客戶補助的入口依原始備註六碼或客戶姓名確認案件，並排除命中月嫂姓名的來源。同名客戶依六碼或唯一合格退款月份定位，跨月或無唯一案件留待核對。候選限原 owner 可預檢的同案補助退款。正式 Preview／Apply 重驗原備註、資金資格、日期及核銷規則。
- 台新待核對月嫂補助依流水 occurrence 找最近完成的正式批次，`staff_subsidy_batch_identity` 只對月嫂用途投影。客戶補助退款不產生該提示，前端即使收到舊提示也優先走退款。`staff_subsidy_manual_review_allowed` 由後端沿原 owner 補助資格及來源分期日期查核，僅確認符合例外時為 true；案件、一般應付日期及提示本身都不能替代資格。
- `POST /api/v1/finance-import/batches/preview` 與 `batches/apply` 保留原批次入口；單筆抽屜沿同一契約傳 `review_row_identity`、`staff_subsidy_selections`，只解析及派送指定交易。Apply 重新建立相同 scope，驗證原 fingerprint 與版本，沿原 durable job／outcome 回讀；不因單筆入口核銷同批其他列。
- 客戶退款沿 `POST /api/v1/finance-import/corrections/preview`、`corrections/apply` 與 `GET /api/v1/finance-import/jobs/{job_id}/correction-outcome`，送 `row_identity`、正式 `classification_type`、`target_obligation_identities` 及原預檢版本／fingerprint。原 correction workflow 委派 Client Finance。僅在既有款項或擬建款通過預檢時承接；核對流程與錯誤投影見 `finance-import-correction`。
- `import-history`、`workbooks/ingestion-outcome` — 查每次匯入的保存、核銷結果與原操作結果；待核對歷史筆數沿原匯入／核銷收據保存，缺歷史證據顯示未知。
- manual plan endpoints: GET/POST `cases/{case_no}/accounting/subsidy-plan` 與 POST `cases/{case_no}/accounting/subsidy-plan/preview`；沿原 actor、version CAS、Orders identity lock 與同鍵重播。Preview 零寫入，原保存重驗預檢並借用既有 owner 承接已合資格款項；未具金融資格可保存已預檢的方案但不得建款或核銷。無外部付款及日期重算。
- case/warning endpoints: `cases/{case_no}/accounting`, `cases/{case_no}/accounting/dismiss`, `accounting/warnings`
- monthly endpoints: `accounting/monthly`、`accounting/monthly/export`；marker Query/Apply: `cases/{case_no}/accounting/historical-marker`。
- `accounting/receivables` — readonly 到期月份／全部月份／未定日期清單；沿用分類及歷史標記統計排除。
- marker Apply fresh-locks current owner versions, preserves an immutable amount snapshot, and supports same-key/same-command replay; one application transaction, no cash or service completion effect.
- archive command owns its outer transaction and same-command receipt; acknowledgement fresh-locks owner facts and checks existing version/amounts, writing only acknowledgement.

- 工作台 Query 投影期別、應繳、實收與方案來源。收付命令提交成功後重查同案。預檢及正式確認共用辨識規則，見下方「核銷後辨識補助方案」。
- 逐案直付安排依 22A §3 重讀正式總額、有效實收、補助與銀行事實。後續出現衝突時保留原安排並投影原因。時間留 UTC ISO 及臺北顯示，沿原案件服務日與到期日。
- bank facts add uniquely proven C/G/PS/PT/RS/RT; monthly by original bank date, single-case totals unavailable for shared sources. Existing ledgers, allocations and due/service dates are read-only.
- 案件抽屜沿既有摘要、客戶期款、補助方案、月嫂應付及客戶退款／政府款檢視。單筆交易核對保存原來源與用途，案件檢視不重作一份交易明細；往返保留原交易、清單篩選與核對／明細入口，返回重查使舊預覽失效，不自動提交。待核對列使用「核對交易」；已核銷列使用「查看交易」，原始事實和正式核銷明細唯讀。台新出款判為退客戶先墊補助時，只在原流水核對同案客戶退款，不帶入月嫂義務或開「單筆人工核對」。該人工入口限台新月嫂補助出款，須由後端確認同案月嫂、正式應付與人工核對資格。任何不足以核對的列顯示原因；可確認案件時仍可查看本案帳務，查看不等於核銷。正式核銷資訊只來自原 owner 回讀；通知仍由 [LINE payment-overdue-reminders](../../../../external-integration/subsystems/line/modules/payment-overdue-reminders.md) owner 負責，各核銷工具保留原 writer。
- 客戶收款面板的全案餘額同時消費既有 Receipt Query 與案件帳務 Query：只彙總版本一致、來源完整的客戶應收正式餘額；缺來源、缺列或未知餘額保留待確認，不從未清清單為空推定結清，也不加入月嫂應付或退款結清門檻。正式成功後依收據版本與回讀再次確認。

### 結束服務後確認永豐入款 ^sinopac-late-receipt-routing

```yaml archmap-impact
- kind: implements_requirement
  source: sinopac-late-receipt-routing
  target: '.arch-map/requirements/04_Client_Finance_Domain.md#^sinopac-late-receipt-refund'
```

- Finance Import 從原單筆核對入口帶入 `row_identity`、原永豐入款事實及 `service_end_case_no`。款項仍是待核對；能由原流水唯一查回同案，不代表已正式收款。既有 `POST /api/v1/finance-import/corrections/preview` 說明可否配對及結算估算，不寫帳；同一入口確認走 `corrections/apply`，HTTP 202 只表示受理，須讀回原 correction outcome 才能判定正式結果。普通永豐入款仍沿原期款匹配；當已確認同案入款但因零服務取消或提前結束沒有可用期款時，移交 Client Finance 專責結算，不放寬一般無期款入款。提前結束讀 Orders 正式服務結果，不以取消事件為必要條件。
- Client Finance 的 Apply 在同一外層交易重驗來源、案件、結算版本及既有收付，沿原收款與差額／退款 writer 保存可追溯的正式入款與待退款，回傳正式結果。以同一銀行流水與既有命令規則防重；同一操作鍵同內容回原收據，異內容回衝突。失敗不留下單邊紀錄。
- 寫入定位：`FinanceImportCorrectionWorkflow.correct_and_post` 擁有外層交易；Client Finance 由 `client_service_end_receipt_preview.py` 核對歸屬及正式服務證據，再由 `client_service_end_receipt_writer.py` 寫原入款與待退款。現行 writer 重用超收退款投影 SQL，新增待退款的 `due_date` 寫 `NULL`；不把銀行交易日當退款到期日，也不據此宣稱出款配對已驗。既有出款核對仍只結清正式退款，不把這一路徑當退款出款。
- 前端維持「核對交易」單一入口，預覽分列入款、服務應付、適用費用及待退款；確認後重讀原流水及案件帳務。後端驗匯入順序、重送及錯案拒絕；前端驗入款方向不變、待退款與已出款不混淆。業務計算先用替身測試，只對新增持久化行為補交易回滾與防重契約驗證。

## Verification
- layout_status: `custom_current`
- `integration_root`: `tests/domains/finance-import/subsystems/finance-import/integration/test_accounting_event_matrix_mysql.py`：`test_terminal_sinopac_receipt_cancels_without_inventing_receivable`、`test_terminal_sinopac_receipt_uses_formally_shortened_service_without_cancellation`，用隔離 MySQL 驗證取消與提前結束的兩種匯入順序、原入款／待退款落帳，以及不新增出款。
- `test_root`: `ui_react/src/tests/domains/finance-import/subsystems/finance-import/modules/statement-workspace/bank_reconciliation_workspace.test.tsx`：`keeps one terminal Sinopac review mounted from bank selection to a verified receipt`，以模擬 API 驗證單一表單、預覽與手動確認；不代表真實 Chrome 或正式部署驗收。
- test_root: `tests/domains/finance-import/subsystems/finance-import/integration/test_statement_workspace.py` — 既有模擬案例核對現金無法跨統計範圍加總時，到期款查詢與匯出仍可使用。
- integration_root: `tests/domains/finance-import/subsystems/finance-import/integration/test_case_manual_supplement.py`
- integration_root: `tests/domains/finance-import/subsystems/finance-import/integration/test_subsidy_confirmation_mysql.py` — 隔離 MySQL 驗證一般／歷史未確認補助計算、兩種台新受款方案、Preview 零寫入、原 Apply 建款核銷、同月唯一及多案選擇、原六碼備註入庫、提前確認、來源過期與失敗整筆回滾。
- integration_root: `tests/domains/finance-import/subsystems/finance-import/integration/test_case_manual_supplement_mysql.py` — opt-in isolated MySQL：三方向正式核銷、足額／部分／手續費／超收退款／超付追償、完整回滾及同鍵重送／衝突／並行。
- integration_root: `tests/domains/finance-import/subsystems/finance-import/integration/test_statement_archive_mysql.py` — 隔離MySQL驗證410零寫入、原鍵不重放舊新增成功、成功匯出只含正式核銷、歷史備查唯讀不改資料、三種正式補登仍可匯出。
- Higher-boundary MySQL coverage uses the finance-import Subsystem's declared disposable E2E entry.
- test_root: `ui_react/src/tests/domains/finance-import/subsystems/finance-import/modules/statement-workspace/`
- cross-owner evidence: [pricing-configuration 的 MySQL 整合驗證](../../../../client-finance/subsystems/client-finance/modules/pricing-configuration.md#verification)，隔離 MySQL 查詢及帳務 API 回應由專項 CI 暫存傳入 `compact_case_drawer.test.tsx`，核對歷史免自備與原款項契約；不以 UI mock 取代後端驗證。
- `.github/workflows/historical-accounting.yml` 執行本案 Python、隔離 MySQL、React、型別與 lint 專項。

## 核銷後辨識補助方案 ^statement-workspace-scheme-classification

```yaml archmap-impact
- kind: implements_requirement
  source: statement-workspace-scheme-classification
  target: ".arch-map/requirements/22A_案件帳務三方案與補助流向正式規格.md#^scheme-classification"
```

- **資料來源**：Client Finance 的個案計價提供案件總額，Government Subsidy 提供正式補助。Client Finance 原收款核銷與沖正提供有效實收。台新補助出款以原 Staff Payables 或 Client Finance 核對成功證據確認案件與受款對象。客戶期款進度、工會應繳和月嫂應付仍由各 owner 投影供抽屜查閱。
- **正式觸發**：原收款或補助出款命令在成功路徑讀取當下有效事實，依 22A §2.2 判定。預檢可試算同案擬建款和核銷。Apply 經原 owner 重驗，在同一 outer UoW 記錄核銷與符合條件的方案確認。原冪等鍵重送沿用收據。已核銷款項仍由既有 writer 負責。
- **提前完工**：Orders Terms Apply 確認縮短後的天數及正式替代班表，Client Finance 同次承接已入帳實收的差額。若永豐入款在提前完工後才核銷，原 Client Finance 補收 writer 回傳的 ledger 來源在同一 outer UoW 觸發方案判定。用 Pricing owner 依有效班表提供的案件總額，並以正式成功回執重查同案抽屜。零服務取消仍由原取消結算承接。
- **查詢及前端**：案件 Query 提供目前正式方案、`scheme_pending_reason` 與 `scheme_evidence_identities`。單筆預檢另提供明細候選。有效證據變更時重新判讀。失效來源及既有人工決定仍可從歷史查閱。前端收到正式成功回執後重查原單筆及同案，進行中清單依 22B §3.2 使用方案結果與收款進度。
- **逐案直付及其他款項**：逐案直付沿原 append-only `confirm_direct` 與 `withdraw_direct` 事件。前端依 Query 隱藏該筆工會補助退款的操作，一般退款仍走原入口。Payroll 月嫂應付與 Staff Payables 出款資格分別讀取。
- **驗證入口**：按 22A §4 的 STAR 從原收款及出款命令核對兩種順序、同鍵重播、既有確認、沖正及失敗。一般業務矩陣用替身 ports。隔離 MySQL 覆蓋原核銷正式讀回、同交易回滾及冪等。

### 自動核銷與方案確認的邊界 ^subsidy-auto-reconciliation-routing

- 延續單筆原流水身分、主責 writer 及成功回執分工。Finance Import 提供原交易和預檢；Staff Payables 核對方案一月嫂出款，Client Finance 核對方案二客戶退款。只能在已有正式收付款結果或原命令成功提交時按 [方案辨識](../../../../../requirements/22A_案件帳務三方案與補助流向正式規格.md#scheme-classification) 記錄確認。Query、Preview 與 HTTP 202 均不等同正式核銷。
- `subsystems/finance_import/import_workflow.py` 的 `_build_resolved_plan` 自動模式與 `reconcile_pending` 保留各自的背景選入條件。`infrastructure/mysql/subsidy_confirmation_repository.py::resolve_subsidy_confirmation` 與各 owner 預檢提供候選、缺項、既有正式款及擬建款證據。方案二尚無正式退款時，依 [22A §2.4.1](../../../../../requirements/22A_案件帳務三方案與補助流向正式規格.md#subsidy-classification-and-auto-reconciliation) 只在原同名退補助特例符合背景選入條件時自動核銷。人工 Preview／Apply 沿原入口，正式 Apply 沿同一 outer UoW、來源防重及原收據讀回。
- 單案抽屜依 [顯示契約](../../../../../requirements/22B_帳務差額處置與工作台UI正式規格.md#case-drawer-payroll-and-subsidy-readback) 呈現，不承擔 Government Subsidy 整期核銷。方案三沿既有人工確認，不從銀行候選推論；相反方向或一般款項維持各自用途。

## 國定假日計價接線 ^statement-workspace-holiday-pricing

```yaml archmap-impact
- kind: implements_requirement
  source: statement-workspace-holiday-pricing
  target: ".arch-map/requirements/22A_案件帳務三方案與補助流向正式規格.md#^case-accounting-schemes"
```
- 假日對帳接線由下列 owner 實作，驗證見既有測試入口。工作台從 Client Finance 與 Payroll 正式金額投影讀取非市民工會收入差額，不以同額不變量誤報異常。正式銀行核銷／月嫂清償來源由原 owner 判定，假日設定入口借用 fresh facts；全額免自備加成差額交既有對帳結果顯示待決策，不假建交易或更改政府補助。

- 既有案件／對帳查詢承接假日與日期調整回執的逐案結果、未重算原因、重算金額與已入帳金額；依22A區分待人工對帳差額，不把未指定負擔差額列工會收入。設定成功、帳務重算成功與付款／核銷事實各自呈現。
