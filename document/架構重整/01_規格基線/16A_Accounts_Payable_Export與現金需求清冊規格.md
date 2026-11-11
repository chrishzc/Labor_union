# Accounts Payable Export 與現金需求清冊規格

## 1. 文件邊界與所有權

- 狀態：`current-spec`
- Owner：Global／Reporting Application Subsystem（`subsystems/staff_payables/cash_requirements_query.py`、`accounts_payable_export.py`）
- 單一負責範圍：跨 Domain 唯讀應付清冊組合查詢（`CASHPLAN-01～06`）、`payment_status`／`receipt_status` 完成狀態呈現、會計十欄 Excel 輸出與三方案分類映射（`APX-SOURCE-01～08`）、歷史月嫂款未列入清冊查核入口，以及人工／銀行明細確認方案至下游應付之交接契約（`HANDOFF-01～06`）。
- 關聯引用：見 [Global 共同契約](00_Global_共同契約.md)、[Payroll Domain](03_Payroll_Domain.md)、[Client Finance Domain](04_Client_Finance_Domain.md)、[Staff Payables / Export Domain](05_Staff_Payables_Export_Domain.md)、[Government Subsidy Domain](14_Government_Subsidy_Domain.md)、[Staff Payables 與 Client Refund](16_Staff_Payables與Client_Refund正式規格.md)、[銀行流水對帳與手動補登](22_銀行流水匯入與帳務異常處理正式規格.md)、[案件帳務三方案與補助流向](22A_案件帳務三方案與補助流向正式規格.md)、[帳務差額處置與工作台 UI](22B_帳務差額處置與工作台UI正式規格.md)、[歷史訂單生命週期與服務天數帳務](27_歷史訂單生命週期與服務天數帳務正式規格.md)。

## 2. 核心不變量與資料口徑

- **唯讀組合原則**：Accounts Payable Query／Export 只透過 Staff Payables 與 Client Finance typed view ports 組合輸出，嚴禁持有 ledger、建立正式義務、改寫狀態或觸發銀行匯款。XLSX 檔案與 SHA-256 封存即當次唯讀快照，不另建資料庫月結 entity。
- **名詞規範**：UI 清冊與業務文件稱「月嫂應付款」、「客戶退款單」；內部程式與資料表沿用 `obligation` 識別。
- **統一建立時點**：
  - **月嫂應付款**：排班成功建立時由 Payroll 計算保存（僅填服務說明或確認起始日不建立義務）。
  - **客戶補助退款**：唯依本案有效人工或明細 B 確認為方案二（客戶先墊後退 `R台`）且具備原成立條件時，由 Client Finance 承接正式 `subsidy_return`；不得僅憑補助資格或 `S` 直接新建客戶退款。
  - **應付清冊匯出**：依付款日、未清正餘額、收款資料與無異常等正式條件篩選。

## 3. 公開契約與流程

### 3.1 預估資金需求查詢（`CASHPLAN-01～06`）

- **納入範圍**：
  - 新案件自「確認服務日期與排班」排班成功建立後納入（僅媒合、服務說明或僅存日期不納入）；已完成歷史訂單讀取原合法歷史服務／應付來源。
  - 月嫂款讀取 Payroll／Staff Payables 未付款餘額與付款日（缺少薪資計算依據保留該列並標「待確認」，不建單）；取消案件不再估算未履約支出，已建立之未清義務保留。
  - 補助 `S` 先計算但方案未確認時標待確認（不把 `S` 當作客戶退款）；已有正式一般／補助退款單後即替代同案預估（退款結清後不重估）。
- **API 契約（`GET /api/v1/finance-reports/accounts-payable/cash-requirements`）**：
  - 唯讀管理員 GET（`page_size` 預設 100、允許 1～200，以 `after_case_no` cursor 分頁，結束時交易 rollback）。
  - 回傳 `rows`（`row_id`、案件、受款人、款項類型、預估／已確定、來源、來源金額、未付款額、付款日、日期是否預估、待確認原因）與 `next_cursor`；未知金額／日期回 `null`，不輸出銀行帳號或身分證號。
  - 前端須載完所有批次方計算月份小計；部分失敗不顯示殘缺小計。
- **畫面整併與完成狀態（`payment_status`／`receipt_status`）**：
  - 預估需求由「進行中案件（WF-01）」與相關查詢承接；已確定十欄 Excel 匯出整併於「每月帳務（WF-06）」專屬出口。
  - 查詢清單保留已付款與歷史結清項，提供 `payment_status`（`pending | partially_paid | paid | settled`）與 `receipt_status`（`pending | unpaid | partially_received | received | settled`），與 `certainty` 正交；歷史 `paid | settled` 僅於 obligation identity、金額快照與 version 符合目前義務時有效。超付負餘額另列追償提示，不得導致清單查詢失敗。

### 3.2 已確定款項清冊匯出與歷史漏列查核

<a id="historical-payables-review-entry"></a>

- **匯出納入條件**：
  1. 一致性唯讀快照讀取 `payable`／`partially_paid` 月嫂款（取正數 `remaining`，且 `due_date == 所選月份 15 日`）與 `normal` review 的 `pending`／`partially_refunded` 客戶一般／補助退款（`due_date <= 所選月份月底`，包含前期與部分退款未退餘額）。
  2. `anomaly`、`completed`、`refunded`、`review_required` 嚴禁進入 Excel；被排除義務必須於查詢區明確呈現待確認或排除原因。
  3. 月嫂部分付款（`partially_paid`）屬正常可匯出狀態（取正數 `remaining`）。
- **歷史月嫂款未列入清冊查核（每月帳務 → 應付清冊「查未列入原因」）**：依案號或月嫂查詢（不要求先有付款日），將缺應付、缺日期／收款資料、已有已付線索但未關聯等原因分流帶回同案抽屜：補登應付（Payroll）、補齊資料或更正（原 owner）、補登已付交易（[手動補登 §6](22_銀行流水匯入與帳務異常處理正式規格.md#case-manual-accounting-supplement) 或 [Staff Payables 歷史付款契約](05_Staff_Payables_Export_Domain.md)），完成且條件俱全後方進下次清冊。

### 3.3 三方案映射與十欄會計 Excel 規範（`APX-SOURCE-01～08`）

| 規範 ID | 核心契約 |
|---|---|
| `APX-SOURCE-01` | 清冊與案件抽屜消費相同 owner 來源；補助流向依 `HANDOFF` 有效確認，禁止由身分、`directly_subsidized` 舊標記或銀行名稱反推方案 |
| `APX-ROUTE-02` | 出款銀行依正式用途 `P永／P台／R永／R台` 分流（與收款人帳戶銀行分開）；月嫂僅在 `staff_id + 付款日 + 出款銀行 + 收款帳戶` 完全相同時合併（永豐與台新必須分列） |
| `APX-DATE-03` | 月嫂款按所選月份 15 日、客戶退款按所選月底前之正數未退餘額；日期讀原義務，未知標待確認，不因政府晚撥移期 |
| `APX-NAME-04` | 月嫂姓名欄顯示 `{union_no} {name}`（保留字串與前導零，缺編號顯示 `未設定 {name}`），維持 staff_id 合併、客戶列沿客戶原名 |
| `APX-RECIPIENT-05` | 正式客戶退款共用 Client Finance 同源有效帳戶快照（`bound_case_no` 原正式欄＋有效修正）；建單時寫入，查詢與 Excel 零寫入 |
| `APX-AUDIT-06` | 既有漏列補查先驗原始事件、身分、`H/L`、`T/S/B`、已收付與方案確認，缺項維持待確認 |
| `APX-READONLY-07` | Query／生成／下載／SHA-256 封存全程零金融寫入；回應 bytes 與封存檔案完全一致；不將方案三套至不適用歷史案件 |
| `APX-ORDER-08` | Excel 列順序固定：**永豐出款列在上、台新出款列在下**，各銀行內依既有序列並保留各自流水號與文字前置零 |

| 方案／正式款項 | 受款人與出款銀行 | 會計清冊行為 |
|---|---|---|
| 方案一（分別入款） | 月嫂；`P永`（永豐）／`P台`（台新） | 按分配、到期日與正數餘額分列，合計不高於 `T` |
| 方案一全額免自備例外 | 月嫂；`P台`（台新） | 補助市民／原住民 `H <= L` 自動成立 `S = T, B = 0`；列待付，不建客戶 `R台` |
| 方案二（先墊後退） | 客戶；`R台`（台新） | 列正式未退餘額與既有到期日，須通過收款快照檢查；不增加月嫂薪資 |
| 方案三（政府直付客戶） | — | 不建立／匯出此補助之工會待付款；原月嫂薪資與一般退款照常 |
| 一般客戶退款 | 客戶；`R永`（永豐） | 與補助退款區分，不因受款人為客戶就設為台新 |

<a id="manual-subsidy-plan-payables-handoff"></a>

### 3.4 補助方案確認與下游應付交接（`HANDOFF-01～06`）

1. **`HANDOFF-01`（B 生效時點與計畫承接）**：一般／歷史案件先計算 `S`；銀行原列保存與預覽僅為候選，僅「人工明確保存」或經「B 套用／確認處理成功」始成為正式確認來源，並依通過預檢之計畫由原 owner 承接合法款項與接續核銷（未到成立時點則僅確認方案並明示本次不建款）。案件移出 `WF-01` 仍要求期款齊全且具正式確認來源。
2. **`HANDOFF-02`（確認來源與金額口徑）**：兩類確認來源可各自追溯、不互相冒充。金額口徑依 [三方案統一金額口徑](22A_案件帳務三方案與補助流向正式規格.md#subsidy-flow)（`S`、應付月嫂／待付、應退客戶／待退、銀行實付、已核銷各守其源）；[全額補助免自備](22A_案件帳務三方案與補助流向正式規格.md#full-subsidy-no-advance) 不以手動確認為前置。
3. **`HANDOFF-03`（安排不取代應付成立條件）**：方案一僅承接 `T` 內月嫂未付餘額（付滿 `T` 不再加付 `S`）；方案二僅承接具備合法墊款／已繳紀錄與未退額之退款；方案三不建補助工會退款。三者皆不改動 `T／S／B` 或前三期義務與日期。
4. **`HANDOFF-04`（套用前預檢）**：訂單／歷史訂單來源計算階段提前檢查必要缺件（歷史讀原合法資料，不強求逐日排班）；預覽須涵蓋擬建／沿用款項與接續核銷檢查並明示真正缺件與不可套用動作，Apply 於同交易重讀執行（同命令前序合法建款所致版本變化不自我判定 stale）。
5. **`HANDOFF-05`（來源保護）**：嚴守唯一案件／同案對象攔截，不補造假資料或回寫不可變歷史封存。
6. **`HANDOFF-06`（清冊唯讀）**：清冊與 Excel 僅讀已成立之正數未清餘額；未定或衝突項於查詢標示原因。

## 4. 驗收標準

1. **`CASHPLAN-01～06`**：從排班建立納入、月嫂多筆守恆、補助 `S` 與方案分離預檢、日期缺值存 `null`、四主入口位置一致與分批游標零寫入皆驗證通過。
2. **`APX-A01～A10`**：涵蓋一般方案一分銀行列、全額免自備（`H < L`／`H = L`）、`H > L`／未知不誤套、方案二 `R台`／方案三無工會退款／一般退款 `R永`、部分付款只列 `remaining`、公會編號 `{union_no} {name}` 保留前導零、永豐在前台新在後排序、封存與下載同 bytes，以及歷史月嫂未列入查核補登回流。
3. **`HANDOFF-A01～A07`**：涵蓋人工保存與明細 B 套用一致生效、預檢擬建款與核銷不依賴既有資料庫目標、缺墊款／未達成立時點區分處理、方案一不超出 `T`、統一金額口徑全介面同義同源。
