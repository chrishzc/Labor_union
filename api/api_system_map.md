# API Layer Sub-System Map (Version 3.2)

> **Scope**: `api/` RESTful API 服務層  
> **Master Reference**: [`../system_map.md`](../system_map.md)

---

### API 功能層模組全覽表

##### Module: OrderRouter
- Sub Map: api_layer
- Source: api/routes/orders.py
- Type: api_router
- State: `planned`
- Description: 訂單、時程精算與明確多月嫂指派同步 API 路由；同步端點接收完整非取消訂單目標值，只委派已部署的 Preview／Apply 服務，不能直接寫入正式資料表。
- Dependencies: [DbService, OrderSchemas, OrderAssignmentSynchronizationPreviewService, OrderAssignmentSynchronizationApplyService]
- Complexity: medium
- Input:
  - case_no: path 中的 canonical order identifier。
  - preview_request: 包含排班關鍵欄位與可編輯訂單主資料完整目標值的 order_change，以及完整明確 assignment_plan。
  - apply_request: preview_request 加上完整 schedule_change_plan.remove_schedule_ids 與非空 applied_by。
- Output:
  - synchronization_preview: target hours、指派時數影響、required_schedule_removals、sync_status 與 blocking_reasons。
  - synchronization_apply_result: 已套用結果、排班生成摘要、時數確認與 audit_id。
- Algorithm:
  - `POST /{case_no}/assignment-synchronization/preview` 驗證完整非取消 order_change（不含 identity_status 或 clients.identity_status）與 HTTP payload 後，僅委派 OrderAssignmentSynchronizationPreviewService，並以 BaseResponse 回傳其完整結果。
  - `POST /{case_no}/assignment-synchronization/apply` 驗證完整移除計畫及 applied_by 後，僅委派 OrderAssignmentSynchronizationApplyService；未套用的 locked、requires_review 或 requires_allocation 結果須回傳明確 HTTP 409 與原因。
  - 服務層的 ValueError 必須轉成明確 HTTP 422；不得由 router 吞掉後回傳成功。
- Invariants:
  - 兩個同步端點不得直接呼叫 db_service 寫入 orders、case_staff_assignments、staff_schedule、付款、月結或稽核表；所有同步商業操作只能委派對應服務。
  - Preview 必須是唯讀；Apply request 必須同時提供完整 assignment_plan、schedule_change_plan.remove_schedule_ids 與非空 applied_by，缺少時不得呼叫 Apply 服務。
  - 同步端點不得自行寫入訂單或客戶主資料；更新必須由 Apply service 的單一 transaction 完成。EditOrderUI 不得以 `/full-details` 先寫入同一份同步變更。
  - API 不得接受 clients.identity_status 或 identity_status；身分資格只能由服務層依 case_no 關聯 clients.identity_status 讀取。
  - Router 不得建立第二個 FastAPI app 或重複註冊；必須沿用既有 `/api/v1/orders` router 與 BaseResponse 包裝。
- Verification:
  - command: {"argv": [".venv\\Scripts\\python.exe", "-m", "pytest", "tests\\test_order_assignment_synchronization_router.py", "tests\\test_order_assignment_synchronization_app_routes.py", "-q", "-p", "no:cacheprovider", "--basetemp", "C:\\tmp\\pytest-order-assignment-router"], "cwd": "project", "timeout": 60, "expect_exit": 0, "expect_stdout_contains": "passed"}
- Observability: not_required

##### Module: MatchRouter
- Sub Map: api_layer
- Source: api/routes/matches.py
- Type: api_router
- State: `validated`
- Description: 案件與配對中心 API 路由。
- Dependencies: [DbService, MatchSchemas]
- Observability: not_required

##### Module: ScheduleRouter
- Sub Map: api_layer
- Source: api/routes/schedule.py
- Type: api_router
- State: `validated`
- Description: 月嫂服務人員行事曆與動態順延排班保存 API 路由。
- Dependencies: [DbService, ScheduleSchemas]
- Observability: not_required

##### Module: ScheduleSchemas
- Sub Map: api_layer
- Source: api/schemas/schedule.py
- Type: api_schema
- State: `validated`
- Description: 驗證案件排班日期、工作日與薪資日標記。
- Dependencies: []
- Observability: not_required

##### Module: PaymentRouter
- Sub Map: api_layer
- Source: api/routes/payments.py::get_all_payments,update_payment
- Type: api_router
- State: `validated`
- Description: 舊 payments API 相容路由；所有端點回傳 HTTP 410。
- Dependencies: [DbService, PaymentSchemas]
- Observability: not_required

##### Module: ClientRouter
- Sub Map: api_layer
- Source: api/routes/clients.py
- Type: api_router
- State: `validated`
- Description: 客戶名冊 API 路由。
- Dependencies: [DbService]
- Observability: not_required

##### Module: StaffRouter
- Sub Map: api_layer
- Source: api/routes/staff.py
- Type: api_router
- State: `validated`
- Description: 服務人員名冊 API 路由。
- Dependencies: [DbService]
- Observability: not_required

##### Module: HolidayRouter
- Sub Map: api_layer
- Source: api/routes/holidays.py
- Type: api_router
- State: `validated`
- Description: 國定假日管理 API 路由。
- Dependencies: [DbService]
- Observability: not_required

##### Module: LegacyPaymentAPIFreeze
- Sub Map: api_layer
- Type: api_router
- State: `planned`
- Source: api/routes/payments.py::_legacy_payments_removed
- Description: 停用舊 /api/v1/payments 路由，避免讀寫已淘汰的 payments 表。
- Invariants:
  - 不得呼叫 legacy payments 的資料服務。
  - 所有端點必須回傳明確的 HTTP 410 停用訊息。
- Verification:
  - must_have_assertions
- Observability: not_required

##### Module: ClientPaymentRouter
- Sub Map: api_layer
- Type: api_router
- State: `planned`
- Source: api/routes/client_payments.py
- Description: 提供 `/api/v1/client-payments` 的客戶收款與帳務摘要 API；退還補助款可查閱，解約退款功能不啟用。
- Invariants:
  - Payload 不接受任何月嫂帳務欄位。
  - 新增交易僅接受 deposit、first_payment、second_payment 階段；不得接受解約 refund。
  - 新增交易僅接受 receipt 與必要的 reversal；人工補登必須有非空原因。
- Verification:
  - command: {"argv": [".venv\\Scripts\\python.exe", "-m", "pytest", "tests\\test_payment_routers.py", "-q"], "cwd": "project", "timeout": 60, "expect_exit": 0}
- Observability: not_required

##### Module: StaffPaymentRouter
- Sub Map: api_layer
- Type: api_router
- State: `planned`
- Source: api/routes/staff_payments.py
- Description: 提供 `/api/v1/staff-payments` 的月嫂應付與一次發薪實付 API。
- Invariants:
  - Payload 不接受任何客戶收款或退款欄位。
  - 人工補登付款交易必須有非空原因，且不得直接覆寫 staff_payments 摘要。
- Observability: not_required

##### Module: ContractContextRouter
- Sub Map: api_layer
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
  - Contract eligibility is read only from clients.identity_status; order facts must not select or return clients.identity_status.
- Verification:
  - command: {"argv": [".venv\\Scripts\\python.exe", "-m", "pytest", "tests\\test_contract_context_router.py", "-q"], "cwd": "project", "timeout": 60, "expect_exit": 0, "expect_stdout_contains": "passed"}
- Observability: not_required

##### Module: FinanceReportRouter
- Sub Map: api_layer
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
  - command: {"argv": [".venv\\Scripts\\python.exe", "-m", "pytest", "tests\\test_finance_report_router.py", "-q"], "cwd": "project", "timeout": 60, "expect_exit": 0, "expect_stdout_contains": "passed"}
- Observability: not_required

##### Module: FinanceAlertRouter
- Sub Map: api_layer
- Type: api_router
- State: `planned`
- Source: api/routes/finance_alerts.py
- Dependencies: [FinanceAlertWorkflowService]
- Description: 提供財務警示清單、詳細資料、人工認領與解除端點；警示建立及正式交易修正不對 UI 開放。
- Complexity: medium
- Input:
  - filters: status、alert_code、source_domain 及分頁條件
  - workflow_action: alert_id、非空 operator reference 與 resolve reason
- Output:
  - alerts: 稽核清單、詳細快照與事件歷程
  - action_result: existing、claimed、resolved 或 conflict
- Invariants:
  - Router 只提供 list、detail、claim、resolve；不得提供任意 PATCH、任意事件建立或由 UI 建立警示的端點。
  - claim／resolve 必須委派 FinanceAlertWorkflowService，不得直接更新 finance_alerts、finance_alert_events 或任何正式帳務表。
  - conflict、not found 與 invalid transition 必須使用明確 HTTP 狀態；不得吞掉成成功。
  - resolve reason 與 operator reference 必須非空；本階段不在 B6 內另建 RBAC 或身份系統。
- Algorithm:
  - 驗證查詢與 action payload，將 list/detail/claim/resolve 委派給 FinanceAlertWorkflowService。
  - 回傳候選 snapshot、expected/actual/difference 與事件歷程；不推測候選或觸發正式核銷。
- Verification:
  - must_have_assertions
  - command: {"argv": [".venv\\Scripts\\python.exe", "-m", "pytest", "tests\\test_finance_alert_router.py", "-q", "-p", "no:cacheprovider", "--basetemp", "C:\\tmp\\pytest-b6-finance-alert-router"], "cwd": "project", "expect_exit": 0, "expect_stdout_contains": "passed"}
- Observability: not_required

##### Module: FinanceRouterRegistration
- Sub Map: api_layer
- Type: api_entrypoint
- State: `planned`
- Source: api/main.py
- Description: Register contract, finance-report, finance-alert and multi-caregiver schedule routers with the running FastAPI application.
- Dependencies: [MultiCaregiverScheduleRouter, MultiCaregiverScheduleReadRouter, MultiCaregiverCaseAssignmentListRouter]
- Complexity: low
- Invariants:
  - Register each new router exactly once without removing existing routers.
  - finance_alerts.router 必須只註冊一次；不得用另一個 FastAPI app 或重複 prefix 規避既有入口。
  - multi_caregiver_schedule.router 必須只註冊一次；不得建立另一個 FastAPI app、重複 prefix 或呼叫 legacy schedule router。
  - multi_caregiver_schedule_read.router 必須只註冊一次；不得建立另一個 FastAPI app、重複 prefix 或改以 legacy schedule router 提供查詢。
  - multi_caregiver_case_assignments.router 必須只註冊一次；不得建立另一個 FastAPI app、重複 prefix 或以 legacy 排班資料合成案件指派選單。
- Verification:
  - command: {"argv": [".venv\\Scripts\\python.exe", "-c", "from pathlib import Path; s=Path('api/main.py').read_text(encoding='utf-8'); assert 'contracts.router' in s and 'finance_reports.router' in s and 'finance_alerts.router' in s and 'multi_caregiver_schedule.router' in s and 'multi_caregiver_schedule_read.router' in s and 'multi_caregiver_case_assignments.router' in s; assert s.count('app.include_router(finance_alerts.router)') == 1; assert s.count('app.include_router(multi_caregiver_schedule.router)') == 1; assert s.count('app.include_router(multi_caregiver_schedule_read.router)') == 1; assert s.count('app.include_router(multi_caregiver_case_assignments.router)') == 1; print('ADMIN ROUTERS REGISTERED')"], "cwd": "project", "timeout": 60, "expect_exit": 0, "expect_stdout_contains": "ADMIN ROUTERS REGISTERED"}
- Observability: not_required
- Invariants:
  - INV-START-01: 腳本必須使用 Python 輪詢確認 MySQL 連線已可被接受，始可開始啟動後端與監控服務防止連線逾時崩潰。

##### Module: OrderSchemas
- Sub Map: api_layer
- Type: api_schema
- State: `planned`
- Source: api/schemas/orders.py
- Description: 訂單完整更新、狀態更新與排班試算的 API 請求資料模型；訂金應收日期可空，客戶身分資格不屬於可提交訂單欄位。
- Dependencies: []
- Invariants:
  - deposit_date 必須允許 null，且不得以今天或其他期款日期作為預設值。
  - 不得定義 clients.identity_status 或 identity_status 為可寫入的訂單 API 欄位。
- Observability: not_required

##### Module: MatchSchemas
- Sub Map: api_layer
- Type: api_schema
- State: `planned`
- Source: api/schemas/matches.py
- Description: 媒合回覆與服務人員指派的 API 請求資料模型。
- Dependencies: []
- Observability: not_required

##### Module: PaymentSchemas
- Sub Map: api_layer
- Type: api_schema
- State: `planned`
- Source: api/schemas/payments.py
- Description: 舊付款更新相容路由的 API 請求資料模型。
- Dependencies: []
- Observability: not_required
