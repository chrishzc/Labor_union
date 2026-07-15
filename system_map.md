# Master System Map (Version 53.0)

> **ADAD 分層子地圖架構 (Sub-Maps Architecture)**:
> 1. **UI 介面層子地圖**: [`ui/ui_system_map.yaml`](file:///c:/Users/chris/Desktop/project/Labor_union/ui/ui_system_map.yaml) | [`ui/ui_system_map.md`](file:///c:/Users/chris/Desktop/project/Labor_union/ui/ui_system_map.md)
> 2. **Services 服務層子地圖**: [`services/services_system_map.yaml`](file:///c:/Users/chris/Desktop/project/Labor_union/services/services_system_map.yaml) | [`services/services_system_map.md`](file:///c:/Users/chris/Desktop/project/Labor_union/services/services_system_map.md)
> 3. **API 服務層子地圖**: [`api/api_system_map.yaml`](file:///c:/Users/chris/Desktop/project/Labor_union/api/api_system_map.yaml) | [`api/api_system_map.md`](file:///c:/Users/chris/Desktop/project/Labor_union/api/api_system_map.md)

---

## Environment
- State: validated
- Services: [db]

---

### 🏛️ 全局巨觀架構 (Master Hierarchy)

##### Module: Main
- Source: main.py
- Type: entrypoint
- Description: 系統主程式入口。
- Observability: not_required

##### Module: UILayer
- Type: sub_system_layer
- State: `validated`
- Source: ui/app.py
- Description: 使用者介面層，包含 Streamlit 各個頁面與元件。
- Observability: not_required

##### Module: APILayer
- Type: sub_system_layer
- State: `validated`
- Source: api/main.py
- Description: FastAPI 應用程式介面層，負責處理 HTTP 請求。
- Observability: not_required

##### Module: ServicesLayer
- Type: sub_system_layer
- State: `validated`
- Source: services/db_service.py
- Description: 後端服務與資料庫操作層，處理核心商業邏輯與資料庫存取；訂單費用僅保留獨立的純薪資與樓層費，不再讀寫其他加給。
- Invariants:
  - 訂單讀寫介面不得出現 `other_addition`。
  - `service_salary` 與 `floor_fee` 必須維持兩個獨立欄位，不得將樓層費併入純薪資欄位。
- Observability: not_required

##### Module: GenerateFakeData
- Source: scripts/generate_fake_data.py
- Type: script
- Description: 假資料統一生成器。採用「時間軸推進演算法 (Sequential Timeline Generator)」，為每位月嫂維護獨立時間軸游標，確保同月嫂的案件排班前後接續、絕對獨佔且零重疊 (Zero Overlap)。
- Invariants:
  - 不得 INSERT、UPDATE 或查詢 legacy payments；假帳務必須寫入 client_payments 與 client_payment_transactions。
- Verification:
  - must_have_assertions
- Observability: not_required

##### Module: PaymentSchema
- Type: database_schema
- State: `planned`
- Source: db/schema.sql
- Description: 以 `case_no` 建立客戶帳務帳戶，並以服務指派分段承載一案多月嫂的應付帳務；摘要與實際金流明細分離，支援部分付款、替補、重送與沖正。
- Complexity: medium
- Input:
  - case_no: canonical order identifier
  - client_cashflow: three collection stages plus reserved subsidy-return fields; subsidy return is not an active workflow
  - staff_assignments: one or more caregiver service segments per case
  - cash_transactions: immutable client receipts/refunds and staff transfers/reversals
- Output:
  - client_payments: one client ledger summary per case_no
  - client_payment_transactions: many actual client cash events per case_no
  - case_staff_assignments: many caregiver service segments per case_no
  - staff_payments: one payable obligation per caregiver service assignment
  - staff_payment_transactions: many actual transfer events per staff payable
- Algorithm:
  - `client_payments` 一案一筆，欄位依序保存訂金、第一期、第二期的應收／實收金額與日期，最後保存應收總額、實收總額及保留的退還補助金額摘要；各階段實收金額由交易明細加總，實收日期代表該階段完成核銷日。
  - `client_payment_transactions` 逐筆保存入款、退款、沖正與外部交易識別，允許同一階段部分付款及失敗後重送，不以覆寫摘要欄位取代歷史。
  - `case_staff_assignments` 將同一案件拆成一至多個服務區段，每段記錄月嫂、起訖日、核定時數、單價、替補原因及前一服務指派；媒合意願紀錄不得當作正式服務指派。
  - `staff_payments` 以服務指派為應付單位，分列服務時數、服務薪資、分配樓層費、調整金額、應付總額與應付日期；同一月嫂可同時持有不同 `case_no` 的多筆待付款。
  - `staff_payment_transactions` 逐筆保存轉帳、失敗、退匯及沖正；應付摘要的實付總額與結清日由成功交易淨額計算。
  - 樓層費由案件明確分配至各服務指派；結案時計算所有指派的薪資與樓層費，加總後才形成案件對月嫂的總應付。
  - `orders.deposit_service_days` 保存訂單表單選定的訂金天數；可為 null 以保留未補齊的歷史案件，任何自動建帳流程遇到 null 必須停止並回報人工補齊，不得套用舊 5／0 天預設。
- Invariants:
  - `client_payments.case_no` 必須唯一且存在於 `orders.case_no`；`staff_payments.case_no` 不得唯一，唯一應付鍵為正式服務指派。
  - 每筆 `case_staff_assignments` 必須同時關聯有效的 `orders.case_no` 與 `staff.id`；`orders.staff_id` 不得作為正式薪資歸屬來源。
  - 同案所有有效服務指派的核定時數總和不得超過案件實際服務總時數；同一時段若有交接，合計時數仍不得超過該日服務時數。
  - 一個服務指派最多只能產生一筆 `staff_payments` 應付摘要，但同一 `staff_id` 可跨多個案件或多個服務區段持有多筆應付摘要。
  - 同案所有服務指派的 `floor_fee_allocated` 不得重複，任何時點加總不得超過 `orders.floor_fee`，結案時必須恰等於訂單樓層費。
  - 客戶帳務不得包含月嫂實付欄位；月嫂帳務不得包含客戶三階段收款欄位。
  - 實收、實退與實付必須保存於不可直接覆寫的交易明細；成功金額必須大於零並具有實際日期，沖正必須反向關聯原交易。
  - 相同外部交易識別不得重複入帳；失敗或退匯交易不得計入實收或實付淨額。
  - `orders` 不得存在 `other_addition`；`service_salary` 是純薪資，月嫂總應付以 `service_salary + floor_fee` 表示。
  - 客戶帳務的 subsidy_return 欄位只表示退還補助金額，不得用於解約退款；現階段不得建立退還補助交易。
  - `orders.deposit_service_days` 為非負整數且不得超過 `orders.service_days`；不得由身分資格或舊檢視表推測其值。
- Invariants:
  - New-database schema must declare legacy `subsidy_refund_*` compatibility columns and canonical reserved `subsidy_return_*` columns; transaction stage enum must include `subsidy_return`, while application write paths remain disabled.
- Verification:
  - command: {"argv": [".venv\\Scripts\\python.exe", "-c", "from pathlib import Path; s=Path('db/schema.sql').read_text(encoding='utf-8'); assert all(f'CREATE TABLE IF NOT EXISTS {n}' in s for n in ('client_payments','client_payment_transactions','case_staff_assignments','staff_payments','staff_payment_transactions','payment_migration_reviews')); assert all(c in s for c in ('subsidy_refund_receivable', 'subsidy_return_receivable', 'subsidy_return_refunded', 'subsidy_return_due_date', 'subsidy_return_at', \"'subsidy_return'\")); print('PAYMENT SCHEMA DECLARED')"], "cwd": "project", "expect_exit": 0, "expect_stdout_contains": "PAYMENT SCHEMA DECLARED"}
- Observability: not_required

##### Module: PaymentRules
- Type: service
- State: `planned`
- Source: services/payment_rules.py::evaluate_payment_boundary
- Description: 提供可獨立測試的帳務邊界規則：服務指派時數與樓層費分配、同月嫂跨案待付款，以及成功／失敗／沖正交易的淨額計算。
- Complexity: medium
- Input:
  - scenario: assignment_allocation, staff_portfolio or transaction_net
  - payment_data: scenario-specific amounts, assignments or transactions
- Output:
  - validation_result: accepted totals or explicit validation error
- Algorithm:
  - 服務指派時數與樓層費必須為非負值，且加總不得超過訂單總時數與樓層費；結案時兩者必須分別恰等於訂單數值。
  - 同月嫂的待付款依每筆服務指派／case_no 獨立計數，不以 staff_id 覆蓋或合併案件。
  - 只有成功交易計入淨額；失敗交易忽略，沖正與退匯以反向金額抵銷原成功交易。
- Invariants:
  - 不得將同一案件的完整樓層費重複分配給多位月嫂。
  - 不得以 `orders.staff_id` 推測服務指派或月嫂應付款。
  - 交易金額必須大於零；重複外部交易識別必須被拒絕。
- Verification:
  - case: {"input": {"scenario": "assignment_allocation", "order_hours": 180, "floor_fee": 900, "finalized": true, "assignments": [{"staff_id": 7, "hours": 45, "floor_fee": 300}, {"staff_id": 9, "hours": 135, "floor_fee": 600}]}, "expect": {"valid": true, "assigned_hours": 180, "allocated_floor_fee": 900}}
  - case: {"input": {"scenario": "staff_portfolio", "staff_id": 7, "payments": [{"case_no": "115000001", "status": "pending"}, {"case_no": "115000002", "status": "pending"}]}, "expect": {"valid": true, "pending_payment_count": 2, "case_count": 2}}
  - case: {"input": {"scenario": "transaction_net", "positive_types": ["transfer"], "negative_types": ["return", "reversal"], "transactions": [{"external_reference": "a", "transaction_type": "transfer", "transaction_status": "succeeded", "amount": 1000}, {"external_reference": "b", "transaction_type": "transfer", "transaction_status": "failed", "amount": 500}, {"external_reference": "c", "transaction_type": "return", "transaction_status": "succeeded", "amount": 250}]}, "expect": {"valid": true, "net_amount": 750}}
- Observability: not_required

##### Module: OrderAmountCalculator
- Type: service
- State: `planned`
- Source: services/order_amount_calculator.py
- Description: Pure source-of-truth calculation for proposed client receivables, staff payables, subsidy claims, and payment dates before any ledger snapshot is written.
- Complexity: medium
- Input:
  - order_terms: case_no, claim total days/hours, service start date, subsidy eligibility, client floor-fee amount, and actual completion date
  - assignments: optional staff service segments with their own hours, rate, and allocated floor fee
  - collection_schedule: contract-selected deposit day count and deposit due date; first/second stage days and dates are derived by rule
- Output:
  - client_ledger_plan: three receivable stages, total prepaid amount, and reserved subsidy-return amount
  - staff_payment_plans: one payable per assignment, with salary, floor fee, and due date
  - subsidy_plan: claim amount, completion quarter, application month, and eligibility flag
- Algorithm:
  - Derive subsidy hours from eligibility and total service hours: general citizen min(40, total service hours), subsidized citizen min(120, total service hours), non-citizen 0; reject invalid stage day counts and assignment totals above the order total.
  - Derive client rate from eligibility: non-citizen 350, general citizen 300, full-subsidy citizen 0. Calculate client receivables with that rate and explicit client floor fee. First stage days equal min(15, max(0, claim total days minus deposit days)); second stage days equal the remaining days.
  - Calculate each staff payable from its assignment snapshot, keeping service salary and floor fee separate; no adjustment is applied here.
  - Calculate the case-level government subsidy claim by allocating subsidy hours across staff assignments in proportion to actual service hours, then summing allocated hours times each staff service rate. If the client prepaid subsidy amount is positive, reserve that amount as subsidy return; a zero client rate produces no client refund even when subsidy hours are positive.
  - First payment due date equals service start date. The second payment due date is initially null; after the first payment is fully received, ClientPaymentWriteService persists its actual received date plus 15 days. If second stage days are zero, its persisted date remains null and the UI displays 0. Derive staff due date from completion date: next month 15th when client receivable is positive, otherwise the following month 15th; derive subsidy claim quarter and its next-quarter application month.
- Invariants:
  - The calculator is pure and must not import database, UI, or transaction-writing modules.
  - Returned totals are proposals only; persisted payment rows remain immutable snapshots, and manual adjustments are stored separately by ledger writers.
  - A full-subsidy case with client rate zero must have zero client receivable and zero subsidy-return amount.
- Verification:
  - command: {"argv": [".venv\\Scripts\\python.exe", "-m", "pytest", "tests\\test_order_amount_calculator.py", "-q"], "cwd": "project", "expect_exit": 0, "expect_stdout_contains": "passed"}
- Observability: not_required

##### Module: AccountingSourceProjection
- Type: service
- State: `planned`
- Source: services/accounting_source_projection.py
- Description: Read a case's accounting source facts from normalized raw tables, without using legacy payment tables or computed order views.
- Complexity: medium
- Input:
  - case_no: canonical case identifier
- Output:
  - accounting_source: raw client, BeClass, order, and staff-assignment facts keyed by case_no
  - missing_terms: explicit list of contract schedule terms absent from raw data and therefore not eligible for implicit defaults
- Algorithm:
  - Read client identity/contact facts from clients, order service facts from orders, and original application/refund facts from beclass_records by query_no = case_no.
  - Read every staff service segment from case_staff_assignments joined to staff; preserve each segment's actual/planned hours, hourly rate, and allocated floor fee.
  - Return raw source values only. Do not query payments, client_payments, staff_payments, v_order_details, or use fixed subsidy/rate fallbacks.
  - Flag missing contract schedule dates/day splits so the caller must supply the dates selected in the order form before invoking OrderAmountCalculator.
- Invariants:
  - All source reads use case_no; no orders.id or order_id is selected or accepted.
  - Client data comes from clients and beclass_records; staff recipient data comes from staff and case_staff_assignments.
  - Missing money inputs are explicit errors/gaps, never replaced by legacy fixed values.
- Verification:
  - command: {"argv": [".venv\\Scripts\\python.exe", "-m", "pytest", "tests\\test_accounting_source_projection.py", "-q"], "cwd": "project", "expect_exit": 0, "expect_stdout_contains": "passed"}
- Observability: not_required

##### Module: PaymentService
- Type: service
- State: `planned`
- Source: services/payment_service.py
- Description: 提供新帳務表的服務指派、月嫂應付與轉帳寫入服務；所有金額先經 PaymentRules 驗證，舊 payments 不得被讀寫。
- Complexity: medium
- Input:
  - case_no: canonical order identifier
  - assignment: staff, hours, hourly rate and floor-fee allocation
  - staff_payment: assignment-linked payable and transfer transaction
- Output:
  - case_staff_assignment: validated service segment
  - staff_payment: assignment-linked payable with recalculated paid amount
- Algorithm:
  - 建立服務指派前鎖定案件既有分配，交由 PaymentRules 驗證時數與樓層費上限後寫入 case_staff_assignments。
  - 月嫂應付只能由 assignment_id 建立；服務薪資、樓層費與調整金額計算 total_payable，不從 orders.staff_id 推測。
  - 寫入月嫂交易前驗證外部識別不重複，依成功轉帳、退匯與沖正重新計算 amount_paid 與 payment_status。
- Invariants:
  - 不得讀寫 legacy payments 表。
  - 月嫂應付必須關聯一筆正式服務指派；同一指派最多一筆應付摘要。
  - 任何新交易的 external_reference 重複時必須拒絕，失敗交易不得增加 amount_paid。
- Verification:
  - command: {"argv": [".venv\\Scripts\\python.exe", "-m", "pytest", "tests\\test_payment_service.py", "-q"], "cwd": "project", "expect_exit": 0, "expect_stdout_contains": "passed"}
- Observability: not_required

##### Module: StaffPaymentTransactionService
- Type: service
- State: `planned`
- Source: services/staff_payment_transactions.py
- Description: 記錄月嫂實際轉帳、失敗、退匯與沖正，並以成功交易淨額重算 staff_payments.amount_paid、paid_at 與 payment_status。
- Complexity: medium
- Input:
  - staff_payment_id: assignment-linked payable identifier
  - transaction: type, status, amount, occurred_at and external_reference
- Output:
  - staff_payment_state: recalculated amount_paid and payment_status
- Algorithm:
  - 鎖定 staff_payments 與既有交易，拒絕重複 external_reference。
  - 寫入新交易後，以 PaymentRules 將成功 transfer 加總、成功 return/reversal 扣回，失敗交易不計入。
  - 淨額為零時為 pending；介於零與 total_payable 為 partially_paid；等於 total_payable 為 paid；不得超過應付總額。
- Invariants:
  - 不得修改 staff_payments.total_payable 或其他服務指派金額。
  - failed 交易不得增加 amount_paid；重複 external_reference 必須拒絕。
  - 只讀寫 staff_payments 與 staff_payment_transactions，不得讀寫 client_payments 或 legacy payments。
- Verification:
  - command: {"argv": [".venv\\Scripts\\python.exe", "-m", "pytest", "tests\\test_staff_payment_transactions.py", "-q"], "cwd": "project", "expect_exit": 0, "expect_stdout_contains": "passed"}
- Observability: not_required

##### Module: ClientPaymentTransactionService
- Type: service
- State: `planned`
- Source: services/client_payment_transactions.py
- Description: 重算客戶訂金、第一期、第二期實收；退還補助金額尚未啟用，不參與目前交易計算。
- Complexity: medium
- Input:
  - client_payment_id: case-linked client ledger identifier
  - transaction: stage, type, status, amount, occurred_at and external_reference
- Output:
  - client_payment_state: recalculated stage totals and settlement dates
- Algorithm:
  - 鎖定客戶帳務與既有交易，拒絕重複 external_reference。
  - 訂金／第一期／第二期僅以 receipt 減 reversal 計入實收；不得接受 subsidy_refund、subsidy_return 或 refund 交易。
  - 每一階段淨額不得為負或超過該階段應收；三階段實收加總為 amount_received。
- Invariants:
  - 不得讀寫 staff_payments、staff_payment_transactions 或 legacy payments。
  - failed 交易不得改變摘要；重複 external_reference 必須拒絕。
  - 退還補助欄位不參與目前的計算或寫入。
- Verification:
  - command: {"argv": [".venv\\Scripts\\python.exe", "-m", "pytest", "tests\\test_client_payment_transactions.py", "-q"], "cwd": "project", "expect_exit": 0, "expect_stdout_contains": "passed"}
- Observability: not_required

##### Module: ClientPaymentWriteService
- Type: service
- State: `planned`
- Source: services/client_payment_writer.py
- Description: 將客戶金流交易實際寫入新表，並依所有交易重算客戶帳務摘要與各期結清日。
- Complexity: medium
- Input:
  - client_payment_id: case-linked client ledger identifier
  - transaction: stage, type, status, amount, occurred_at and external_reference
- Output:
  - client_payment_state: persisted stage receipts, subsidy refund and amount_received
- Algorithm:
  - 鎖定客戶帳務與既有交易，將候選交易先交 ClientPaymentTransactionService 計算，超額或重複識別一律回滾。
  - 寫入交易，再重算訂金、第一期、第二期摘要；只有三個收款階段計入 amount_received，退款功能暫不啟用。
  - 階段淨額首度等於應收時記錄完成日；應收為零的階段不得產生完成日。第一期首度結清時，若第二期應收大於零，將第二期應收日設為第一期實收日加 15 天；第一期遭沖正而未結清時清空該日期。
  - 訂金首次全額核銷時，僅將目前為洽談中的同一 case_no 案件自動更新為訂單成立；歷史資料仍可在單筆訂單頁以受稽核的人工流程建立。
- Invariants:
  - 不得讀寫 staff_* 或 legacy payments 表。
  - failed 交易不得改變任何摘要金額或結清日。
  - subsidy_refund 與 subsidy_return 不得計入 amount_received 或寫入目前流程。
- Verification:
  - command: {"argv": [".venv\\Scripts\\python.exe", "-m", "pytest", "tests\\test_client_payment_writer.py", "-q"], "cwd": "project", "expect_exit": 0, "expect_stdout_contains": "passed"}
- Observability: not_required

##### Module: LegacyPaymentUIFreeze
- Type: ui_page
- State: `planned`
- Source: ui/pages/02_orders.py::_render_tab3_finance
- Description: Page 2 第三分頁的帳務明細總覽；先呈現全部案件的可篩選帳務摘要，僅在展開案件時才讀取客戶與月嫂交易明細，取代已移除的 legacy payments 編輯器。
- Input:
  - orders_data: current order list
- Output:
  - payment_overview: filterable all-case payment summaries with on-demand ledger details
- Invariants:
  - 不得查詢或寫入 legacy payments。
  - 預設必須以客戶收款總覽與月嫂應付總覽兩張獨立表格顯示全部已有帳務的案件，並提供案件編號、訂單狀態與各自付款狀態篩選；兩張表不得交錯欄位。
  - 客戶表必須顯示訂金、第一期、第二期各自的應收、實收、應收日與實收日，以及合計；有退還補助款時一併顯示。
  - 月嫂表必須逐筆顯示服務時數、單價、服務薪資、樓層費、調整額、應付／實付／餘額與付款日期，並使用 staff_payments 的 amount_paid 與 due_date 欄位。
  - 使用者選擇特定案件後，自動取得並在展開區顯示客戶／月嫂交易明細；不得預先讀取其他案件明細。
  - 實收／實付與日期只能來自交易明細；人工補登交易時必填原因，不得直接覆寫摘要欄位。
  - 不得在此分頁重複實作待匯清單或匯出功能。
- Verification:
  - command: {"argv": [".venv\\Scripts\\python.exe", "-m", "py_compile", "ui\\pages\\02_orders.py"], "cwd": "project", "expect_exit": 0}
- Observability: not_required

##### Module: LegacyPaymentEditFreeze
- Type: ui_page
- State: `planned`
- Source: ui/pages/04_edit_order.py
- Description: 停止訂單編輯頁讀寫舊 payments；訂單資料與狀態仍可儲存，新帳務改由新帳務介面處理。
- Invariants:
  - 不得呼叫 get_table_data('payments') 或 update_payment_details。
  - 訂單主資料與狀態更新不得因停用舊帳務同步而中斷。
- Verification:
  - must_have_assertions
- Observability: not_required

##### Module: LegacyPaymentAPIFreeze
- Type: api_router
- State: `planned`
- Source: api/routes/payments.py
- Description: 停用舊 /api/v1/payments 路由，避免讀寫已淘汰的 payments 表。
- Invariants:
  - 不得呼叫 legacy payments 的資料服務。
  - 所有端點必須回傳明確的 HTTP 410 停用訊息。
- Verification:
  - must_have_assertions
- Observability: not_required

##### Module: LegacyPaymentBrowserFreeze
- Type: ui_page
- State: `planned`
- Source: ui/pages/01_data_browser.py
- Description: 移除資料瀏覽頁所有 legacy payments 選項、欄位標籤與不可達的虛擬帳號／唯讀分支，避免 Contract 後留下過時程式碼。
- Invariants:
  - 原始碼不得包含 legacy payments 表名、caregiver_fee、caregiver_paid_at 或舊帳務虛擬帳號分支。
  - table_options 僅能瀏覽目前仍由 db_service 支援的資料表。
- Verification:
  - command: {"argv": [".venv\\Scripts\\python.exe", "-c", "from pathlib import Path; text=Path('ui/pages/01_data_browser.py').read_text(encoding='utf-8'); forbidden=('payments', 'caregiver_fee', 'caregiver_paid_at'); assert not any(value in text for value in forbidden); print('LEGACY PAYMENT BROWSER PRUNED')"], "cwd": "project", "expect_exit": 0, "expect_stdout_contains": "LEGACY PAYMENT BROWSER PRUNED"}
- Observability: not_required

##### Module: Page2TabNavigation
- Type: ui_page
- State: `planned`
- Source: ui/pages/02_orders.py::show
- Description: 移除訂單頁 show() 對 legacy payments 的剩餘執行期讀取，保留 Tab1、Tab2 與已凍結的 Tab3 入口。
- Invariants:
  - 不得出現 get_table_data('payments')、update_payment_details 或 legacy payments SQL。
  - show() 仍可載入訂單頁所需資料，且不會因查詢不存在的舊表失敗。
  - 不得實作客戶或月嫂新帳務 UI。
- Verification:
  - command: {"argv": [".venv\\Scripts\\python.exe", "-c", "from pathlib import Path; text=Path('ui/pages/02_orders.py').read_text(encoding='utf-8'); assert \"get_table_data('payments')\" not in text; assert 'update_payment_details' not in text; assert '新帳務介面建置中' in text; print('LEGACY ORDER PAYMENTS REMOVED')"], "cwd": "project", "expect_exit": 0, "expect_stdout_contains": "LEGACY ORDER PAYMENTS REMOVED"}
- Observability: not_required

##### Module: ClientPaymentRouter
- Type: api_router
- State: `planned`
- Source: api/routes/client_payments.py
- Description: 提供 `/api/v1/client-payments` 的客戶收款與帳務摘要 API；退還補助款可查閱，解約退款功能不啟用。
- Invariants:
  - Payload 不接受任何月嫂帳務欄位。
  - 新增交易僅接受 deposit、first_payment、second_payment 階段；不得接受解約 refund。
  - 新增交易僅接受 receipt 與必要的 reversal；人工補登必須有非空原因。
- Verification:
  - command: {"argv": [".venv\\Scripts\\python.exe", "-m", "pytest", "tests\\test_payment_routers.py", "-q"], "cwd": "project", "expect_exit": 0}
- Observability: not_required

##### Module: StaffPaymentRouter
- Type: api_router
- State: `planned`
- Source: api/routes/staff_payments.py
- Description: 提供 `/api/v1/staff-payments` 的月嫂應付與一次發薪實付 API。
- Invariants:
  - Payload 不接受任何客戶收款或退款欄位。
  - 人工補登付款交易必須有非空原因，且不得直接覆寫 staff_payments 摘要。
- Observability: not_required

##### Module: PaymentManagementUI
- Type: ui_page
- State: `planned`
- Source: ui/pages/02_orders.py::safe_float,safe_int,safe_date,_render_tab1_overview,_render_tab2_assign
- Description: 將財務管理拆為客戶收款與月嫂應付／轉帳兩個獨立操作區；退還補助金額暫不提供 UI 操作。
- Invariants:
  - 任一區塊儲存時不得覆蓋另一張帳務表。
- Observability: not_required

##### Module: FinanceImport
- Type: import_pipeline
- State: `planned`
- Source: scripts/imports/import_finance_excel.py
- Return-Processing: disabled; import must not read, calculate, or write `subsidy_refund_*` or `subsidy_return_*`.
- Description: 由 file_watcher 觸發匯入財務 Excel 銀行流水；以 `99781699 + 年度 + 流水號後3碼` 虛擬帳號解出 case_no，寫入客戶帳務摘要與交易明細。
- Invariants:
  - 不得以客戶姓名或月嫂姓名作為唯一帳務關聯鍵。
  - 銀行流水只能更新實際金額／日期，不得用實收反推應收。
  - 僅有可解出且存在的 case_no 的客戶入款可寫入 client_payments 與 client_payment_transactions。
  - 沒有明確 case_no 的月嫂支出不得建立 staff_payments 或 staff_payment_transactions，必須列入未處理結果。
- Observability: not_required
- Complexity: medium
- Input:
  - excel_path: 財務 Excel 檔案路徑
- Output:
  - imported_client_transactions: 寫入的客戶交易筆數
  - skipped_transactions: 缺少或無法辨識 case_no 而未寫入的交易筆數
- Algorithm:
  - 讀取案件對照與銀行流水工作表，僅取明確欄位，忽略任何 id 或 order_id 欄位。
  - 由客戶入款的虛擬帳號解出 case_no，先驗證 orders.case_no 存在；建立帳務快照時只讀 orders 的服務天數、每日時數、補助資格、樓層費、訂金天數、訂金日期與服務開始日。
  - `orders.deposit_service_days` 為 null 時不得建立帳務快照，將該案件交易列入待人工補齊；不得使用舊 5／0 天、帳務 Excel 金額、固定 80,000 或 v_order_details。
  - 使用 OrderAmountCalculator 建立三期應收快照；依同一案件的入款時間順序分配收款階段，交由 ClientPaymentWriteService 寫入具唯一 external_reference 的 receipt 交易並重算摘要。
  - 對無法解出 case_no 的入款與月嫂支出只累計為 skipped_transactions，禁止以姓名猜測案件或月嫂。
  - 任一資料庫錯誤須 rollback 並回傳明確錯誤；成功時回傳匯入與略過統計。
- Verification:
  - must_have_assertions
  - command: {"argv": [".venv\\Scripts\\python.exe", "-m", "pytest", "tests\\test_import_finance_excel.py", "-q"], "cwd": "project", "expect_exit": 0, "expect_stdout_contains": "passed"}
  - command: {"argv": [".venv\\Scripts\\python.exe", "-c", "from pathlib import Path; text=Path('scripts/imports/import_finance_excel.py').read_text(encoding='utf-8'); assert 'subsidy_refund' not in text and 'subsidy_return' not in text; print('FINANCE IMPORT RETURN DISABLED')"], "cwd": "project", "expect_exit": 0, "expect_stdout_contains": "FINANCE IMPORT RETURN DISABLED"}

##### Module: MonthlyPaymentPreparation
- Type: service
- State: `planned`
- Source: services/payment_batch_service.py
- Description: 每月 5 日產生當月月嫂一次發薪待匯清單與可匯出批次資料；系統不執行轉帳。
- Complexity: medium
- Input:
  - target_month: month whose staff payment due dates are being prepared
- Output:
  - preparation_rows: unpaid staff payment obligations due in the target month, each retaining staff_payment_id, case_no, staff_id, due_date, and remaining amount
- Invariants:
  - 客戶應付大於 0 的案件，月嫂應匯日為結案後次月 15 日；全額補助且客戶應付為 0 的案件為結案後次次月 15 日。
  - 產生或重跑清單不得建立成功的 staff_payment_transactions，也不得重複列入同一應付項目。
  - 退還補助金額功能未啟用時，不得產生客戶退款待匯項目。
- Algorithm:
  - Use the already-calculated `staff_payments.due_date`; do not recalculate service settlement dates from orders.
  - Select only `pending` or `partially_paid` staff payments whose due date is within target_month and whose remaining amount is positive.
  - Emit one preparation row per staff_payment_id, so one caregiver with multiple cases retains multiple payable rows.
  - Return preparation data only; do not insert or update payment transaction records.
- Verification:
  - command: {"argv": [".venv\\Scripts\\python.exe", "-m", "pytest", "tests\\test_payment_batch_service.py", "-q"], "cwd": "project", "expect_exit": 0}
- Observability: not_required

##### Module: SubsidyClaimReporting
- Type: service
- State: `planned`
- Source: services/subsidy_claim_service.py
- Complexity: medium
- Input:
  - cases: completed case records containing case_no, subsidy_hours, actual_end_date, and end_date
  - application_year: calendar year in which the quarterly claim is due
- Output:
  - quarterly_candidates: cases grouped by the April, July, October, or January claim month
  - annual_overview: application-year totals for expected, submitted, approved, and paid claims
- Description: 依完工季度產生 4／7／10／1 月補助申請清單，並提供年度補助總覽。
- Invariants:
  - 僅納入 subsidy_hours 大於 0、已完工且未列入同一申請批次的案件。
  - 季度歸屬以 actual_end_date 為主，無值時才使用 end_date。
  - 年度總覽必須分別統計應申請、已送件、已核准與已撥款。
- Algorithm:
  - Ignore cases with zero subsidy hours or no completion date; use actual_end_date before end_date.
  - Map completion quarter Q1/Q2/Q3/Q4 to claim due month April/July/October/January, with Q4 due in the following application year.
  - Group only records whose claim due date belongs to application_year.
  - Return expected totals from candidate cases; until claim-status persistence exists, submitted, approved, and paid totals must be explicit zeroes rather than inferred values.
- Verification:
  - command: {"argv": [".venv\\Scripts\\python.exe", "-m", "pytest", "tests\\test_subsidy_claim_service.py", "-q"], "cwd": "project", "expect_exit": 0}
- Observability: not_required

##### Module: FixScheduleConflicts
- Source: scripts/fix_schedule_conflicts.py
- Type: script
- Description: 月嫂檔期衝突檢測與自動修復工具。
- Observability: not_required

##### Module: AccountsPayableExport
- Type: service
- State: `planned`
- Source: services/accounts_payable_export.py
- Description: Build the union's monthly outgoing staff-payroll and client subsidy-return list and downloadable Excel workbook. 解約退款功能不啟用。
- Complexity: low
- Input:
  - target_month: YYYY-MM, the month of transfer due dates
- Output:
  - payable_rows: rows with month-bank-sequence, outgoing bank, recipient identity, recipient bank details, amount, case_no, and transfer date
  - xlsx_bytes: downloadable workbook with the approved fixed column order and per-outgoing-bank totals
- Invariants:
  - Include only positive, unpaid amounts due in target_month; staff rows use pending or partially_paid staff_payments and their due_date.
  - 月嫂款使用出款銀行代碼 31（永豐銀行）；客戶退還補助款使用 633（台新銀行）。解約退款不得納入。
  - Assign serials independently per target month and outgoing bank, beginning at 1; the identifier format is month-outgoing_bank_code-serial.
  - Spreadsheet columns must be 月份-銀行代碼-流水號, 銀行名稱, 客戶or服務人員姓名, 銀行帳號, 銀行代號(碼), 金額, 身分證字號(匯款到永豐才要填), 案件編號, 匯款日期.
  - Export preparation must not create or update any payment transaction.
- Algorithm:
  - Query due staff payment balances and client subsidy-return balances for target_month, enrich each recipient's bank data, and emit Yongfeng and Taishin rows.
  - Sort rows by outgoing bank, transfer date, case_no, and source payment id; then assign independent month-bank serials starting at 1.
  - Create an XLSX workbook with the fixed headers, yellow header styling, rows, and both outgoing-bank totals.
- Verification:
  - command: {"argv": [".venv\\Scripts\\python.exe", "-m", "pytest", "tests\\test_accounts_payable_export.py", "-q"], "cwd": "project", "expect_exit": 0}
- Observability: not_required

##### Module: AccountsPayableExportUI
- Type: ui_page
- State: `planned`
- Source: ui/pages/02_orders.py::_render_tab4_accounts_payable
- Description: Reconnect Page 2's fourth accounts-payable tab and fifth subsidy-reconciliation tab to their read-only FastAPI endpoints.
- Complexity: low
- Invariants:
  - The tab is read-only preparation and download; it must not mark staff or client payments as transferred, paid, refunded, or submitted.
  - The tab must be the fourth Page 2 tab, while the existing frozen third finance tab remains unchanged.
  - 顯示永豐銀行月嫂款與台新銀行退還補助款總額；不得顯示解約退款。
- Algorithm:
  - Read monthly preview and XLSX only through FinanceReportRouter; do not import AccountsPayableExport or db_service directly.
  - Read quarterly and annual reconciliation previews and downloads only through FinanceReportRouter; do not import the reconciliation service directly.
- Verification:
  - command: {"argv": [".venv\\Scripts\\python.exe", "-m", "py_compile", "ui\\pages\\02_orders.py"], "cwd": "project", "expect_exit": 0}
- Observability: not_required

##### Module: SubsidyReconciliationRegister
- Type: service
- State: `planned`
- Source: services/subsidy_reconciliation_register.py
- Description: Build read-only quarterly subsidy reconciliation registers and annual summaries, including downloadable Excel workbooks.
- Complexity: medium
- Input:
  - application_year: year of the quarterly claim application or annual summary
  - quarter: 1 through 4 for a quarterly register
- Output:
  - quarterly_rows: separate general-citizen and subsidized-citizen row sets with XLSX bytes
  - annual_rows: separate general-citizen and subsidized-citizen row sets with XLSX bytes
- Invariants:
  - Include only completed cases with positive subsidy hours; determine the claim quarter from actual_end_date.
  - Use case_no as the city order number, actual_start_date and actual_end_date as the service dates, and the employer's address from clients.
  - Read the employer identity card only from the BeClass survey_details JSON associated by query_no = case_no.
  - subsidy_days equals subsidy_hours divided by service_hours_per_day, rounded to and displayed with exactly two decimal places in the preview and XLSX.
  - General citizens are the upper section; subsidized citizens are a lower independent section only when it has rows.
  - Quarterly XLSX signing cells must always be blank; the service must not write claim, payment, or order data.
- Algorithm:
  - Read eligible completed orders with client, primary staff, and BeClass data, then calculate the claim period from actual_end_date.
  - Classify records by subsidy eligibility. Derive subsidy hours as min(40, total service hours) for general citizens and min(120, total service hours) for subsidized citizens; then derive days, amount, and register fields, and sort each section by case_no.
  - Build quarterly and annual workbooks with their approved column sets and optional lower subsidized-citizen section.
- Verification:
  - command: {"argv": [".venv\\\\Scripts\\\\python.exe", "-m", "pytest", "tests\\\\test_subsidy_reconciliation_register.py", "-q"], "cwd": "project", "expect_exit": 0}
- Observability: not_required

##### Module: SubsidyReconciliationRegisterUI
- Type: ui_page
- State: `planned`
- Source: ui/pages/02_orders.py::_render_tab5_subsidy_reconciliation
- Description: Add Page 2's fifth tab, 核銷補助清冊, with quarterly and annual read-only previews and XLSX downloads.
- Complexity: low
- Invariants:
  - The tab must be the fifth Page 2 tab and must not alter the previous four tabs.
  - Provide separate quarterly and annual views, with downloads only and no data writes.
  - Do not render the subsidized-citizen lower section when it has no rows.
- Algorithm:
  - Read quarterly and annual previews and downloads only through FinanceReportRouter; do not import the reconciliation service directly.
- Verification:
  - command: {"argv": [".venv\\\\Scripts\\\\python.exe", "-m", "py_compile", "ui\\\\pages\\\\02_orders.py"], "cwd": "project", "expect_exit": 0}
- Observability: not_required

##### Module: StaffContractExcelMirror
- Type: ui_component
- State: `planned`
- Source: ui/pages/05_form_management.py::render_excel_contract_mirror
- Description: Register and render the copied staff-service contract workbook through the existing read-only Excel mirror.
- Complexity: low
- Invariants:
  - The staff contract must use db/templates/contracts/服務人員契約.xlsx and must not modify that workbook.
  - Contract template selection must render any registered .xlsx contract through the same mirror path.
  - Only fields available in the selected order may be filled; unmapped template cells remain unchanged.
- Algorithm:
  - Fetch selected staff-contract context from ContractContextRouter by case_no and assignment_id; do not assemble contract facts from db_service directly.
- Verification:
  - command: {"argv": [".venv\\\\Scripts\\\\python.exe", "-m", "py_compile", "ui\\\\pages\\\\05_form_management.py"], "cwd": "project", "expect_exit": 0}
- Observability: not_required

##### Module: StartScript
- Source: start.bat
- Type: script
- Description: 一鍵啟動與部署環境初始化腳本。啟動 Docker、初始化 MySQL、產生並匯入假資料，最後並行啟動 FastAPI 與 Streamlit。
- Observability: not_required
- Invariants:
  - INV-START-01: 腳本必須使用 Python 輪詢確認 MySQL 連線已可被接受，始可開始執行 init_db.py 防止連線逾時崩潰。

##### Module: OnlineScript
- Source: online.bat
- Type: script
- Description: 一鍵啟動上線服務腳本。啟動 Docker、等待 MySQL 連線就緒，但不執行資料庫初始化與假資料生成，最後以並行方式啟動 FastAPI、Streamlit 網頁端以及地端檔案自動監控服務 (file_watcher.py)。
- Observability: not_required
- Invariants:
  - FastAPI 必須以實際 ASGI 入口 `line.main:app` 啟動，不得指向不存在的 `api.main:app`。

##### Module: ContractContextRouter
- Type: api_router
- State: `planned`
- Source: api/routes/contracts.py
- Description: Read-only staff-service contract context by case_no and formal assignment.
- Complexity: medium
- Input:
  - case_no: canonical order identifier
  - assignment_id: optional formal assignment selector
- Output:
  - staff_contract_context: order, client, BeClass, selected assignment and staff facts
- Algorithm:
  - Read order and client contract facts by case_no, then BeClass by query_no = case_no.
  - Read formal case_staff_assignments; require assignment_id when more than one active assignment exists, and never infer the recipient from orders.staff_id.
  - Return null for approved-but-unmapped template fields; never write orders, templates, or payments.
- Invariants:
  - All reads use case_no and optional assignment_id; no orders.id or legacy payment view is used.
  - The endpoint is read-only and does not alter the original contract workbook.
- Verification:
  - command: {"argv": [".venv\\Scripts\\python.exe", "-m", "pytest", "tests\\test_contract_context_router.py", "-q"], "cwd": "project", "expect_exit": 0, "expect_stdout_contains": "passed"}
- Observability: not_required

##### Module: FinanceReportRouter
- Type: api_router
- State: `planned`
- Source: api/routes/finance_reports.py
- Description: Read-only accounts-payable and subsidy-reconciliation previews and XLSX downloads.
- Complexity: low
- Input:
  - target_month: YYYY-MM for accounts payable
  - reconciliation_period: year and optional quarter
- Output:
  - finance_reports: JSON previews and XLSX attachments
- Algorithm:
  - Delegate payable generation to AccountsPayableExport and reconciliation generation to SubsidyReconciliationRegister.
  - Return preview rows without workbook bytes in JSON endpoints; return workbook bytes only from explicit export endpoints.
  - Validate inputs at the API boundary and do not write payment, claim, refund, or order state.
- Invariants:
  - All endpoints are read-only.
  - 解約退款功能停用；但到期且未退還的 client subsidy-return 必須可在預覽與匯出中出現。
- Verification:
  - command: {"argv": [".venv\\Scripts\\python.exe", "-m", "pytest", "tests\\test_finance_report_router.py", "-q"], "cwd": "project", "expect_exit": 0, "expect_stdout_contains": "passed"}
- Observability: not_required

##### Module: FinanceRouterRegistration
- Type: api_entrypoint
- State: `planned`
- Source: line/main.py
- Description: Register contract and finance-report routers with the running FastAPI application.
- Complexity: low
- Invariants:
  - Register each new router exactly once without removing existing routers.
- Verification:
  - command: {"argv": [".venv\\Scripts\\python.exe", "-c", "from pathlib import Path; s=Path('line/main.py').read_text(encoding='utf-8'); assert 'contracts.router' in s and 'finance_reports.router' in s; print('FINANCE ROUTERS REGISTERED')"], "cwd": "project", "expect_exit": 0, "expect_stdout_contains": "FINANCE ROUTERS REGISTERED"}
- Observability: not_required
- Invariants:
  - INV-START-01: 腳本必須使用 Python 輪詢確認 MySQL 連線已可被接受，始可開始啟動後端與監控服務防止連線逾時崩潰。
