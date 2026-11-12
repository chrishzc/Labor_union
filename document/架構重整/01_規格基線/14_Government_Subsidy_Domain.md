# Government Subsidy Domain

## 1. 文件邊界與所有權

- 狀態：`current-spec`
- Owner：Government Subsidy Domain（`domains/government_subsidy/`、`subsystems/government_subsidy/`）
- 單一負責範圍：政府補助整期核銷（月／季／年）、整期差額狀態（`已納入本期`／`已核銷`）、政府入款沖正、工會代墊淨額回收，以及政府補助季度／年度核銷報表與「補助案件統計表」年度投影契約。
- 關聯引用：見 [Global 共同契約](00_Global_共同契約.md)、[Payroll Domain](03_Payroll_Domain.md)、[Client Finance Domain](04_Client_Finance_Domain.md)、[External Integration / Access Control](17_External_Integration_LINE_Access正式規格.md)、[Case Import 與非市民待審](17B_Case_Import與非市民Redis待審正式規格.md)、[案件帳務三方案與補助流向](22A_案件帳務三方案與補助流向正式規格.md)、[帳務差額處置與工作台 UI](22B_帳務差額處置與工作台UI正式規格.md)、[營運報表與統計口徑](34_營運報表與統計口徑正式規格.md)。

## 2. 核心不變量與資料模型（SSOT）

- **外部申請原則**：政府以整段期間總額一次撥款；人員於系統外完成申請、送件與核准，系統內不建立逐案申請批次、逐案核准或付款義務關卡。
- **跨 Domain 分責**：
  - Government Subsidy 擁有整期入款、整期沖正與期間案件快照（`government_subsidy_period_years`、`government_subsidy_period_entries`、`government_subsidy_period_members`）。
  - 案件補助金額 `S` 與三方案歸屬、預檢及生效時點遵循 [案件帳務三方案與補助流向](22A_案件帳務三方案與補助流向正式規格.md)；[Client Finance](04_Client_Finance_Domain.md) 擁有客戶應退與實退，[Payroll](03_Payroll_Domain.md) 擁有月嫂薪資，政府整期收款不改寫月嫂薪資亦不重複建立客戶退款。
- **補助身分與時數原則**：
  - 正式身分類別為「一般市民」（預設 40 小時）、「補助市民」（社福資格，預設 120 小時）與「原住民」（帳務參數管理，預設 80 小時），實際上限與兩段費率由 [Client Finance 參數與計價規則](04_Client_Finance_Domain.md#2-核心不變量與計價規則) 決定；非市民補助時數為 `0`（不限制建立 `A` 字頭自費案）。未知身分維持待確認，不猜填為零元。
  - 雙胞胎案件依 Case Import 正式胎數事實使用 `450` 元／小時；服務開始前合法 BeClass 胎數更正須納入重算，服務開始後不得變更胎數。非雙胞胎案件缺少 Payroll 快照時必須 fail closed，不得退回固定 300／350 猜算。

### 2.1 整期狀態與防重不變量（`GOV-STATUS-01`）

| 整期處理進度 | 期間款項狀態 | 所含案件狀態 |
|---|---|---|
| 差額尚未處理完成（含首次部分入款） | 顯示實收及剩餘差額（例：待補撥金額） | **已納入本期** |
| 補撥、追回或已確認適用之差額處理完成且整期結清 | **本期已結清** | **已核銷** |

- 首筆政府部分入款即固定該期所含案件與本期應收快照；後續若因案件資料更正產生金額變化，另列獨立更正差額義務處理，不得回寫已固定之期間案件／金額快照。
- 已納入本期案件維持原期間歸屬，不得重疊納入任何重疊的月／季／年再次核銷。
- 查閱已核銷季度或年度內之單月時，案件狀態顯示「已核銷」並並列實際歸屬期間，不得拆造虛構月入款或逐案現金分配。

## 3. 公開契約與流程

### 3.1 整期核銷、少撥／多撥差額與整期沖正

- **期間歸屬規則**：月、季、年皆以「有效服務結束日」（實際服務結束日，尚無實際值時取預定服務結束日）劃分，採「含起日、不含次期起日」；同年各月合計必須等於各季及年度合計。中途取消案件僅按已確認實際服務時數計算。
- **Query／Apply 分離**：查詢零寫入，案件金額缺值或目前排班關聯指向無效／非 effective 版本時列為「待確認」並禁止整期核銷（不以缺排班阻擋尚無排班版本之合法案件，不以零元湊數）。Apply 在單一 outer UoW 內鎖定案件、年度 root 與銀行事實，重讀最新合計並驗證版本。
- **銀行待核對批次重配**：政府入款依正式有效服務結束日查找月、季、年期別，僅考慮全期案件有效服務結束日均不晚於銀行交易日的期別。只有唯一未核銷期別的正式總額與銀行實收完全相符，且當期案件資料完整、未被其他期間或明細占用，才由整期 owner 自動核銷。月、季、年分別視為獨立候選，即使所含案件相同。多期吻合、資料不足、來源有衝突、重配後候選改變或需處理差額時，原銀行明細維持待核對。
- **少撥與多撥差額**：人員指定期間與銀行來源後區分少撥／多撥，可先記實收（`已納入本期`）、等候補撥或由人員主動指定適用差額處置（依 [帳務差額處置規則](22B_帳務差額處置與工作台UI正式規格.md#finance-differences) 分列補撥、LOSS 損失認列或台新政府來源標記之差額退回）；政府整期多撥退回指定原期間或差額項目，保持銀行原始方向與金額不變。
- **整期沖正與防重**：同一 bank fact 僅能綁定一個 period receipt。整期退款／銀行沖正須指定原 `period receipt` 與等額實際出款 bank fact 追加 reversal evidence，保留原快照並解除原核銷狀態。`subsidy_claim_batches` 等 legacy 申請批次與逐案核准入口僅保留唯讀歷史證據與既有交易沖正，禁止建立新申請或逐案入款。

### 3.2 代墊回收

- 僅對工會實際經手且已正式入款之期間，於同一 outer UoW 依 `period members` 與 Client Finance 既有不可變出款 ledger／沖正證據彙總該期淨未回收代墊額；不新增逐案銷帳表或逐案核准關卡，亦不形成第二筆銀行入款或客戶退款。延後補登的出款或沖正即時反映於查詢；發生整期沖正時，代墊狀態回復待資金支應。

### 3.3 現行 API 與存取權限

- `GET /api/v1/government-subsidy/periods?unit=month|quarter|year&year=YYYY&index=N`
- `GET /api/v1/government-subsidy/periods/bank-rows`（最多回傳 200 筆尚未消費之政府銀行事實）
- `GET /api/v1/government-subsidy/periods/cases/{case_no}`（案件補助額、服務歸屬、核銷狀態與歸屬期間）
- `POST /api/v1/government-subsidy/periods/reconcile`（`unit`、`year`、`index`、`bank_row_id`、`expected_version`、`idempotency_key`）
- `POST /api/v1/government-subsidy/periods/reverse`（`receipt_id`、整筆出款 `bank_row_id`、`idempotency_key`）
- 權限沿用帳務管理權限；所有入口嚴禁發送 LINE、發布選單或觸發自動銀行轉帳。

### 3.4 法定報表與營運年度投影

- **季度／年度核銷報表**（UI 唯一入口見 [帳務工作台 UI `WF-05`](22B_帳務差額處置與工作台UI正式規格.md#finance-six-surfaces-ui)）：
  - 納入資格：訂單已因有效訂金進入 `訂單成立`、`服務中`、`訂單完成`，或具有同等已付訂金語意之 `歷史訂單－未服務 | 服務中 | 服務完成 | 帳務完成`；洽談中及零服務時數之已取消案件不納入；中途取消有實際服務時數者僅納入實際時數。不以存在 `subsidy_claim_batches` 作納入門檻。
  - 格式與來源：季度報表固定 15 欄 XLSX／React 明細、年度報表固定 10 欄；雇主身分證沿用 `survey_details` 既有值（不另造 `clients` 欄位）；非雙胞胎案件缺乏 Payroll 快照時 fail closed。
- **營運報表「補助案件統計表」年度投影**（14 欄）：
  - 以查詢區間 `end_date` 所屬西元年為 `report_year`，固定涵蓋該年 `01-01` 至 `12-31`（不依單週／跨月／跨年選取範圍裁切，跨年僅取 `end_date` 所屬年）。
  - 季度與年度歸屬固定採該列「年度季度」計算（依有效服務結束日決定年度與 `YYYY年第一季`～`第四季`，React 與 XLSX 同名欄位「年度季度」），只納入年度等於 `report_year` 之列。`submitted_at` 僅作送件顯示，不作納入門檻；補助時數、單價與金額統一由 Government Subsidy reconciliation formula 計算。

## 4. 驗收標準

1. 同年同範圍下月／季／年報表與整期查詢之來源集合及總額完全一致；來源缺值、無案件、零元、金額不符及版本過期皆回傳 typed conflict 且零寫入。
2. 同案與同一銀行列不得跨越重疊月／季／年重複核銷，案例日期異動亦不得改寫已核銷期間之歷史快照。
3. `GOV-STATUS-01` 少撥部分入款後所含案件顯示「已納入本期」且固定名單，差額結清後方顯示「已核銷」；整期沖正可完整恢復待核銷與代墊狀態。
4. 季度 15 欄、年度 10 欄與營運週報內「補助案件統計表」（14 欄）皆納入有效歷史訂單、雙胞胎優先 `450` 費率，並正確套用 `report_year = end_date.year` 與 `年度季度` 分組，桌面與手機 UI 可操作且匯出一致。
