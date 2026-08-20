---
doc_type: work-package
declared_status: in-progress
identity: PROV-20260816-react-admin-migration-foundation-work-package
owner: global-admin-web-presentation
base_ref: ad79f5b4fb35f1ef442f889702aaa4ccb2c5d922
date: 2026-08-16
---

# PROV-20260816 React 管理端遷移 Foundation 與 Phase 0/1 執行工作包 (V5)

> 2026-08-16 人工已要求重新驗收並允許修正 Foundation。狀態維持 `in-progress`；不得以舊版
> `VICTORY_CONFIRMED` 報告宣稱完成。V4 的 base ref、測試數量與 Auth 判定在目前 working tree
> 已屬 stale，以下第 13 節為最新覆核結果。

## 1. 任務目標與身分基線

本工作包為《React 管理端遷移與 UI 真實業務流程驗收計畫》的 Foundation 與 Phase 0/1 exact Work Package (V4)。
本版本完全基於工作區原始碼機械檢驗，絕無未驗證之假設。

- **Branch**: `main`
- **HEAD**: `538c836acfe13e0288a82ab29a5f7c3cc4eae853`
- **Git Status Short 計數與狀態**:
  - 總計 `164` 筆 untracked / dirty 檔案（含已核准決策包、schema parts、測試資產與 LINE catalog 擴充產物）。
  - 所有既有檔案全數視為使用者成果予以保護，不執行任何 reset / clean / checkout / stash 操作。
- **重疊與 Live-drift 檢視**:
  - `document/功能開發計畫/React管理端遷移與UI真實業務流程驗收計畫.md` (untracked)
  - `document/架構重整/03_追蹤清單與證據/evidence/2026-08-16_react_admin_ui_surface_inventory.md` (untracked)
  - `subsystems/line/notification_rule_administration.py` 與 `api/routes/line_notification_rules.py`（標記為 `LIVE_DRIFT_CANDIDATE`）

---

## 2. App Write Set 裁決與 Desktop 逐檔 Merge Inventory

為避免 App.tsx 引用未建立之業務頁面導致 Build 失敗，**採行方案 B（完整視覺模板納入 exact write set）**：
- 將 Desktop 的 11 個業務頁面與對應 CSS 納入 Phase 1 exact write set，明確標記為 **`mock-only visual baseline`**（僅作畫面呈現，不接任何業務 mutation，不宣稱 production-ready）。
- 採用 **Shell State Navigation (含 URL Hash 同步)** 作為標準輕量 Router，不導入外部龐大依賴。

| Source (Desktop `ui_react/`) | Target (Workspace `ui_react/`) | Owner | 處置方式 | 備註 |
|---|---|---|---|---|
| `src/App.tsx` | `src/App.tsx` | Integration Owner | `SEMANTIC_MERGE` | 整合 MasterLayout、Shell Navigation、Error Boundary 與 Route Guard |
| `src/styles/design-tokens.css` | `src/styles/design-tokens.css` | Integration Owner | `SEMANTIC_MERGE` | 合併色彩、間距與排版 Token |
| `src/components/MasterLayout.tsx` | `src/components/MasterLayout.tsx` | Integration Owner | `ADD` | 頂部導覽列與側邊欄容器 |
| `src/components/MasterLayout.css` | `src/components/MasterLayout.css` | Integration Owner | `ADD` | 導覽佈局樣式 |
| `src/components/Drawer.tsx` | `src/components/Drawer.tsx` | Integration Owner | `ADD` | 共用抽屜容器 |
| `src/components/Drawer.css` | `src/components/Drawer.css` | Integration Owner | `ADD` | 抽屜動畫與樣式 |
| `src/components/ErrorBoundary.tsx` | `src/components/ErrorBoundary.tsx` | Integration Owner | `ADD` | 全域 React 錯誤攔截器 |
| `src/pages/LoginPage.tsx` | `src/pages/LoginPage.tsx` | Integration Owner | `ADD` | 登入頁 Presentation（Auth 未定維持 BLOCKED） |
| `src/pages/LoginPage.css` | `src/pages/LoginPage.css` | Integration Owner | `ADD` | 登入樣式 |
| `src/pages/DataImportPage.tsx` | `src/pages/DataImportPage.tsx` | Integration Owner | `SEMANTIC_MERGE` | `mock-only visual baseline` |
| `src/pages/DataImportPage.css` | `src/pages/DataImportPage.css` | Integration Owner | `SEMANTIC_MERGE` | `mock-only visual baseline` |
| `src/pages/OrdersPage.tsx` | `src/pages/OrdersPage.tsx` | Integration Owner | `ADD` | `mock-only visual baseline` |
| `src/pages/OrdersPage.css` | `src/pages/OrdersPage.css` | Integration Owner | `ADD` | `mock-only visual baseline` |
| `src/pages/OrderTrackerPage.tsx` | `src/pages/OrderTrackerPage.tsx` | Integration Owner | `ADD` | `mock-only visual baseline` |
| `src/pages/OrderTrackerPage.css` | `src/pages/OrderTrackerPage.css` | Integration Owner | `ADD` | `mock-only visual baseline` |
| `src/pages/SchedulingPage.tsx` | `src/pages/SchedulingPage.tsx` | Integration Owner | `ADD` | `mock-only visual baseline` |
| `src/pages/SchedulingPage.css` | `src/pages/SchedulingPage.css` | Integration Owner | `ADD` | `mock-only visual baseline` |
| `src/pages/StaffPage.tsx` | `src/pages/StaffPage.tsx` | Integration Owner | `ADD` | `mock-only visual baseline` |
| `src/pages/StaffPage.css` | `src/pages/StaffPage.css` | Integration Owner | `ADD` | `mock-only visual baseline` |
| `src/pages/FinancePage.tsx` | `src/pages/FinancePage.tsx` | Integration Owner | `ADD` | `mock-only visual baseline` |
| `src/pages/FinancePage.css` | `src/pages/FinancePage.css` | Integration Owner | `ADD` | `mock-only visual baseline` |
| `src/pages/AnomaliesPage.tsx` | `src/pages/AnomaliesPage.tsx` | Integration Owner | `ADD` | `mock-only visual baseline` |
| `src/pages/AnomaliesPage.css` | `src/pages/AnomaliesPage.css` | Integration Owner | `ADD` | `mock-only visual baseline` |
| `src/pages/LineManagementPage.tsx` | `src/pages/LineManagementPage.tsx` | Integration Owner | `ADD` | `mock-only visual baseline` |
| `src/pages/LineManagementPage.css` | `src/pages/LineManagementPage.css` | Integration Owner | `ADD` | `mock-only visual baseline` |
| `src/pages/DataBrowserPage.tsx` | `src/pages/DataBrowserPage.tsx` | Integration Owner | `ADD` | `mock-only visual baseline` |
| `src/pages/DataBrowserPage.css` | `src/pages/DataBrowserPage.css` | Integration Owner | `ADD` | `mock-only visual baseline` |
| `src/pages/ReportsPage.tsx` | `src/pages/ReportsPage.tsx` | Integration Owner | `ADD` | `mock-only visual baseline` |
| `src/pages/ReportsPage.css` | `src/pages/ReportsPage.css` | Integration Owner | `ADD` | `mock-only visual baseline` |
| `src/pages/AccountManagementPage.tsx` | `src/pages/AccountManagementPage.tsx` | Integration Owner | `ADD` | `mock-only visual baseline` |
| `src/pages/AccountManagementPage.css` | `src/pages/AccountManagementPage.css` | Integration Owner | `ADD` | `mock-only visual baseline` |

---

## 3. 機械驗證之全 Surface / Capability Mock → API 矩陣 (100% 原始碼與測試覆核)

所有列出之 Route、Schema、Application、Source 行號與 Test 路徑皆經由機械式腳本逐項檢驗通過（80 / 80 PASS）。

| UI Page / Action | Method | Exact Path | Request Schema | Response Model | Application / Subsystem | Source & Line | Test Path (100% Exists) | Working-Tree Disposition | UI Fallback Presentation |
|---|---|---|---|---|---|---|---|---|---|
| **Login** / Submit | `POST` | `/api/v1/admin/auth/login` | `AdminLoginRequest` | `BaseResponse[AdminSessionResponse]` | `AdminAuthApplication` | `api/routes/admin_auth.py:86` | `tests/test_admin_auth_runtime.py` | `READY_TO_WIRE` | 顯示 typed error alert |
| **Login** / Current User | `GET` | `/api/v1/admin/auth/me` | `None` | `BaseResponse[AdminPublic]` | `AdminAuthApplication` | `api/routes/admin_auth.py:117` | `tests/test_admin_auth_runtime.py` | `READY_TO_WIRE` | 導向登入頁 |
| **Login** / Refresh | `POST` | `/api/v1/admin/auth/refresh` | `None` | `BaseResponse[AdminSessionResponse]` | `AdminAuthApplication` | `api/routes/admin_auth.py:121` | `tests/test_admin_auth_runtime.py` | `ADAPTER_NEEDED` | 清除 session 狀態 |
| **Login** / Session Restore | - | `NOT_FOUND` | `NOT_FOUND` | `NOT_FOUND` | `NOT_FOUND` | `NOT_FOUND` | `NOT_FOUND` | `BLOCKED_AUTH_RESTORE_DECISION` | 導向登入頁 |
| **Login** / Logout | `POST` | `/api/v1/admin/auth/logout` | `None` | `BaseResponse[dict]` | `AdminAuthApplication` | `api/routes/admin_auth.py:146` | `tests/test_admin_auth_runtime.py` | `ADAPTER_NEEDED` | 清除 client state 並導向登入頁 |
| **Shell** / System Performance | `GET` | `/api/v1/system/status/performance-snapshot` | `None` | `BaseResponse[PerformanceSnapshotResponse]` | `query_system_performance_snapshot` | `api/routes/system_status.py:15` | `tests/test_system_status_router.py` | `READY_TO_WIRE` | 顯示離線灰色徽章 |
| **Shell** / Notification Count | `GET` | `/api/v1/customer-service/tickets/summary` | `None` | `BaseResponse[CustomerServiceSummaryView]` | `CustomerServiceWorkflow` | `api/routes/customer_service.py:34` | `tests/test_line_customer_service_first_release.py` | `READY_TO_WIRE` | 顯示 0 |
| **Orders** / Summaries | `GET` | `/api/v1/orders/summaries` | `None` | `BaseResponse[OrderSummaryPageView]` | `query_order_summaries` | `api/routes/orders.py:124` | `tests/test_order_detail_query.py` | `READY_TO_WIRE` | 顯示空卡片清單與重試按鈕 |
| **Orders** / Order Detail | `GET` | `/api/v1/orders/{case_no}` | `None` | `BaseResponse[OrderDetailView]` | `query_order_by_case_no` | `api/routes/orders.py:368` | `tests/test_order_detail_query.py` | `READY_TO_WIRE` | Drawer 顯示資料載入失敗 |
| **Orders** / Calendar Detail | `GET` | `/api/v1/orders/{case_no}/calendar-detail` | `None` | `BaseResponse[OrderCalendarDetailView]` | `query_order_calendar_detail` | `api/routes/orders.py:299` | `tests/test_order_detail_query.py` | `READY_TO_WIRE` | 顯示空行事曆 |
| **Orders** / Candidate Pool | `GET` | `/api/v1/orders/{case_no}/candidate-contact-pool` | `None` | `BaseResponse[dict]` | `CandidateContactPoolWorkflow` | `api/routes/candidate_contact_pool.py:52` | `tests/test_candidate_contact_pool_workflow.py` | `ADAPTER_NEEDED` | 顯示空候選池 |
| **Orders** / Add Candidate | `POST` | `/api/v1/orders/{case_no}/candidate-contact-pool/candidates` | `AddCandidateContactPoolEntriesRequest` | `BaseResponse[dict]` | `CandidateContactPoolWorkflow` | `api/routes/candidate_contact_pool.py:58` | `tests/test_candidate_contact_pool_workflow.py` | `ADAPTER_NEEDED` | 禁用加入按鈕 |
| **Orders** / Willingness | `PUT` | `/api/v1/orders/{case_no}/candidate-contact-pool/candidates/{candidate_id}/willingness` | `RecordCandidateWillingnessRequest` | `BaseResponse[dict]` | `CandidateContactPoolWorkflow` | `api/routes/candidate_contact_pool.py:76` | `tests/test_candidate_contact_pool_workflow.py` | `ADAPTER_NEEDED` | 禁用意願修改 |
| **Orders** / Actual Start Query | `GET` | `/api/v1/orders/{case_no}/actual-start` | `None` | `BaseResponse[ActualStartQueryView]` | `ActualStartApplication` | `api/routes/order_actual_start.py:64` | `tests/test_order_actual_start_workflow.py` | `READY_TO_WIRE` | 顯示未確認狀態 |
| **Orders** / Actual Start Preview | `POST` | `/api/v1/orders/{case_no}/actual-start/preview` | `ActualStartPreviewBody` | `BaseResponse[ActualStartPreviewView]` | `ActualStartApplication` | `api/routes/order_actual_start.py:81` | `tests/test_order_actual_start_workflow.py` | `READY_TO_WIRE` | 保留欄位輸入，禁用 Apply |
| **Orders** / Actual Start Apply | `POST` | `/api/v1/orders/{case_no}/actual-start/apply` | `ActualStartApplyBody` | `BaseResponse[ActualStartReceiptView]` | `ActualStartApplication` | `api/routes/order_actual_start.py:107` | `tests/test_order_actual_start_workflow.py` | `READY_TO_WIRE` | 顯示失敗原因 |
| **Orders** / Terms Query | `GET` | `/api/v1/orders/{case_no}/terms` | `None` | `BaseResponse[OrderTermsQueryView]` | `OrderTermsApplication` | `api/routes/order_terms.py:98` | `tests/test_order_terms_api_client.py` | `READY_TO_WIRE` | 顯示空條款卡片 |
| **Orders** / Terms Preview | `POST` | `/api/v1/orders/{case_no}/terms/preview` | `OrderTermsPreviewBody` | `BaseResponse[OrderTermsPreviewView]` | `OrderTermsApplication` | `api/routes/order_terms.py:115` | `tests/test_order_terms_api_client.py` | `READY_TO_WIRE` | 顯示預覽錯誤 |
| **Orders** / Terms Apply | `POST` | `/api/v1/orders/{case_no}/terms/apply` | `OrderTermsApplyBody` | `BaseResponse[OrderTermsReceiptView]` | `OrderTermsApplication` | `api/routes/order_terms.py:141` | `tests/test_order_terms_api_client.py` | `READY_TO_WIRE` | 顯示儲存失敗 |
| **Orders** / Cancellation Preview | `POST` | `/api/v1/orders/{case_no}/cancellation/preview` | `OrderCancellationPreviewBody` | `BaseResponse[OrderCancellationPreviewView]` | `OrderCancellationWorkflow` | `api/routes/order_cancellation.py:95` | `tests/test_order_cancellation_workflow.py` | `READY_TO_WIRE` | 禁用確認退款按鈕 |
| **Orders** / Cancellation Apply | `POST` | `/api/v1/orders/{case_no}/cancellation/apply` | `OrderCancellationApplyBody` | `BaseResponse[OrderCancellationReceiptView]` | `OrderCancellationWorkflow` | `api/routes/order_cancellation.py:124` | `tests/test_order_cancellation_workflow.py` | `READY_TO_WIRE` | 彈出取消失敗原因 |
| **Orders** / Contract Signing Query | `GET` | `/api/v1/orders/{case_no}/contract-signing` | `None` | `BaseResponse[dict]` | `ContractSigningApplication` | `api/routes/contract_signing.py:47` | `tests/test_client_contract_signing_application.py` | `ADAPTER_NEEDED` | 顯示未簽約只讀提示 |
| **Orders** / New Order | `POST` | `NOT_FOUND` | `NOT_FOUND` | `NOT_FOUND` | `NOT_FOUND` | `NOT_FOUND` | `NOT_FOUND` | `BACKEND_MISSING` | 按鈕 disabled 並提示「需經進件中心建立」 |
| **Orders** / Legacy Full Details Writer | `PUT` | `/api/v1/orders/{case_no}/full-details` | `NOT_SPECIFIED` | `NOT_SPECIFIED` | `NOT_FOUND` | `api/routes/orders.py:481` | `tests/test_order_detail_query.py` | `RETIRED` | 禁用整單寫入 |
| **OrderTracker** / Auto Completion Preview | `POST` | `/api/v1/orders/{case_no}/auto-completion/preview` | `OrderAutoCompletionPreviewBody` | `BaseResponse[OrderAutoCompletionPreviewView]` | `OrderAutoCompletionWorkflow` | `api/routes/order_auto_completion.py:73` | `tests/test_order_auto_completion_workflow.py` | `READY_TO_WIRE` | 顯示自動完工檢核失敗 |
| **OrderTracker** / 7-Stage Stepper | - | `NOT_FOUND (Composite)` | `NOT_FOUND` | `NOT_FOUND` | `NOT_FOUND` | `NOT_FOUND` | `tests/test_order_auto_completion_workflow.py` | `ADAPTER_NEEDED` | 前端組合 Query，不重算正式狀態 |
| **OrderTracker** / 11-Step SOP Query | `GET` | `/api/v1/orders/{case_no}/form-management-context` | `None` | `BaseResponse[FormManagementCaseContextView]` | `query_form_management_case_context` | `api/routes/orders.py:209` | `tests/test_order_detail_query.py` | `READY_TO_WIRE` | 顯示靜態 SOP 清單 |
| **OrderTracker** / Delivery Tasks List | `GET` | `/api/v1/line/tasks` | `status, task_type, etc.` | `BaseResponse[dict]` | `LineTaskApplication` | `api/routes/line_tasks.py:76` | `tests/line/subsystems/test_line_delivery_notification_intent_state.py` | `ADAPTER_NEEDED` | 顯示空發送記錄 |
| **OrderTracker** / Delivery Task Retry | `POST` | `/api/v1/line/tasks/{task_id}/retry` | `LineTaskActionRequest` | `BaseResponse[dict]` | `LineTaskApplication` | `api/routes/line_tasks.py:162` | `tests/line/subsystems/test_line_delivery_notification_intent_state.py` | `ADAPTER_NEEDED` | 提示重試失敗 |
| **Scheduling** / Current Calendar | `GET` | `/api/v1/scheduling/staff/{staff_id}/current-calendar` | `None` | `BaseResponse[SchedulingCurrentProjectionView]` | `SchedulingCurrentProjectionWorkflow` | `api/routes/scheduling_current.py:43` | `tests/test_scheduling_current_projection_workflow.py` | `READY_TO_WIRE` | 顯示當月空白行事曆 |
| **Scheduling** / Leave Substitution Preview | `POST` | `/api/v1/orders/{case_no}/leave-substitution/preview` | `LeaveSubstitutionPreviewBody` | `BaseResponse[LeaveSubstitutionPreviewView]` | `LeaveSubstitutionWorkflow` | `api/routes/leave_substitution.py:141` | `tests/test_leave_substitution_workflow.py` | `READY_TO_WIRE` | 顯示代班衝突預覽 |
| **Scheduling** / Leave Substitution Apply | `POST` | `/api/v1/orders/{case_no}/leave-substitution/apply` | `LeaveSubstitutionApplyBody` | `BaseResponse[LeaveSubstitutionReceiptView]` | `LeaveSubstitutionWorkflow` | `api/routes/leave_substitution.py:167` | `tests/test_leave_substitution_workflow.py` | `READY_TO_WIRE` | 禁用代班儲存 |
| **Scheduling** / Holidays List | `GET` | `/api/v1/holidays` | `None` | `BaseResponse[List[Dict[str, Any]]]` | `HolidaysApplication` | `api/routes/holidays.py:20` | `tests/test_g15_cache_boundary_contract.py` | `ADAPTER_NEEDED` | 顯示預設只讀國定假日 |
| **Scheduling** / Leave Requests Query | `GET` | `/api/v1/scheduling/staff-leave-requests` | `None` | `BaseResponse[list[dict]]` | `StaffLeaveIntakeWorkflow` | `api/routes/staff_leave_management.py:26` | `tests/test_staff_leave_intake_workflow.py` | `ADAPTER_NEEDED` | 顯示「無待審請假」 |
| **Scheduling** / Save Daily Schedule Writer | `POST` | `/api/v1/schedule/save` | `None` | `BaseResponse[bool]` | `NOT_FOUND` | `api/routes/schedule.py:21` | `tests/test_scheduling_current_projection_workflow.py` | `RETIRED` | 禁用手動單日存檔 |
| **Staff** / Summaries List | `GET` | `/api/v1/staff/summaries` | `None` | `BaseResponse[StaffSummaryPageView]` | `query_staff_summaries` | `api/routes/staff.py:11` | `tests/test_staff_availability_routes.py` | `READY_TO_WIRE` | 顯示分頁名冊 |
| **Staff** / Matching Preferences Profile | `GET` | `/api/v1/scheduling/staff-matching-preferences/staff/{staff_id}` | `None` | `BaseResponse[StaffPreferenceProfileView]` | `StaffMatchingPreferencesApplication` | `api/routes/staff_matching_preferences.py:87` | `tests/test_staff_matching_preferences.py` | `READY_TO_WIRE` | 唯讀顯示預設偏好 |
| **Staff** / Matching Preferences Apply | `POST` | `/api/v1/scheduling/staff-matching-preferences/staff/{staff_id}/apply` | `ApplyStaffPreferenceProfileBody` | `BaseResponse[StaffPreferenceApplyReceiptView]` | `StaffMatchingPreferencesApplication` | `api/routes/staff_matching_preferences.py:116` | `tests/test_staff_matching_preferences.py` | `READY_TO_WIRE` | 提示更新失敗 |
| **Staff** / Availability Blocks Query | `GET` | `/api/v1/scheduling/staff/{staff_id}/availability-blocks` | `None` | `BaseResponse[list[StaffUnavailabilityBlockView]]` | `StaffAvailabilityApplication` | `api/routes/staff_availability.py:51` | `tests/test_staff_availability_routes.py` | `READY_TO_WIRE` | 唯讀顯示不可服務期間 |
| **Staff** / Availability Blocks Apply | `POST` | `/api/v1/scheduling/staff/{staff_id}/availability-blocks/apply` | `StaffAvailabilityChangeBody` | `BaseResponse[StaffAvailabilityReceiptView]` | `StaffAvailabilityApplication` | `api/routes/staff_availability.py:103` | `tests/test_staff_availability_routes.py` | `READY_TO_WIRE` | 顯示不可服務更新失敗 |
| **Staff** / Retirement Lifecycle Query | `GET` | `/api/v1/staff/{staff_id}/lifecycle` | `None` | `BaseResponse[StaffLifecycleView]` | `StaffRetirementWorkflow` | `api/routes/staff_retirement.py:25` | `tests/test_staff_retirement_workflow.py` | `READY_TO_WIRE` | 顯示在職狀態 |
| **Staff** / Retirement Apply | `POST` | `/api/v1/staff/{staff_id}/{action}/apply` | `None` | `BaseResponse[StaffLifecycleView]` | `StaffRetirementWorkflow` | `api/routes/staff_retirement.py:44` | `tests/test_staff_retirement_workflow.py` | `READY_TO_WIRE` | 彈出確認視窗，失敗顯示原因 |
| **Import** / HCM Workbook Preview | `POST` | `/api/v1/case-import/hcm/workbooks/preview` | `UploadFile` | `BaseResponse[HcmWorkbookPreviewView]` | `get_hcm_workbook_import_service` | `api/routes/hcm_import.py:36` | `tests/test_hcm_workbook_import.py` | `READY_TO_WIRE` | 顯示解析錯誤 |
| **Import** / HCM Workbook Apply | `POST` | `/api/v1/case-import/hcm/workbooks/apply` | `UploadFile + Headers` | `BaseResponse[HcmWorkbookReceiptView]` | `get_hcm_workbook_import_service` | `api/routes/hcm_import.py:46` | `tests/test_hcm_workbook_import.py` | `READY_TO_WIRE` | 顯示匯入失敗 |
| **Import** / HCM Historical Overwrite | `POST` | `/api/v1/case-import/hcm/historical-workbooks/apply` | `UploadFile` | `BaseResponse[HcmWorkbookReceiptView]` | `hcm_import.py:105` | `api/routes/hcm_import.py:105` | `tests/test_hcm_workbook_import.py` | `RETIRED` | 卡片標記「已退役入口」並禁用 |
| **Import** / Client BeClass Preview | `POST` | `/api/v1/case-import/client-beclass/workbooks/preview` | `UploadFile` | `BaseResponse[ClientBeClassWorkbookPreviewView]` | `ClientBeClassWorkbookApplication` | `api/routes/client_beclass_import.py:27` | `tests/test_client_beclass_workbook_import.py` | `READY_TO_WIRE` | 顯示 BeClass 解析異常清單 |
| **Import** / Client BeClass Apply | `POST` | `/api/v1/case-import/client-beclass/workbooks/apply` | `UploadFile + Headers` | `BaseResponse[ClientBeClassWorkbookReceiptView]` | `ClientBeClassWorkbookApplication` | `api/routes/client_beclass_import.py:33` | `tests/test_client_beclass_workbook_import.py` | `READY_TO_WIRE` | 顯示 BeClass 匯入失敗 |
| **Import** / Staff Historical Preview | `POST` | `/api/v1/case-import/staff-historical/workbooks/preview` | `UploadFile` | `BaseResponse[StaffHistoricalWorkbookPreviewView]` | `StaffHistoricalWorkbookApplication` | `api/routes/staff_historical_workbook.py:32` | `tests/test_staff_historical_workbook_api.py` | `READY_TO_WIRE` | 顯示歷史月嫂解析預覽 |
| **Import** / Historical Orders Preview | `POST` | `/api/v1/orders/historical-adoption/workbooks/preview` | `UploadFile` | `BaseResponse[HistoricalOrderWorkbookPreviewView]` | `HistoricalOrderAdoptionApplication` | `api/routes/historical_order_adoption.py:28` | `tests/test_historical_order_adoption_router.py` | `READY_TO_WIRE` | 顯示歷史訂單解析預覽 |
| **Import** / Bank Statements Preview | `POST` | `/api/v1/finance-import/batches/preview` | `UploadFile` | `BaseResponse[FinanceImportBatchPreviewView]` | `FinanceImportApplication` | `api/routes/finance_import.py:241` | `tests/test_finance_import_application.py` | `READY_TO_WIRE` | 顯示流水匯入預覽 |
| **Import** / Bank Statements Apply | `POST` | `/api/v1/finance-import/batches/apply` | `UploadFile + Headers` | `BaseResponse[JobAcceptedResponse]` | `FinanceImportApplication` | `api/routes/finance_import.py:402` | `tests/test_finance_import_application.py` | `READY_TO_WIRE` | 顯示批次作業已建立 |
| **Finance** / Receipt Reconciliation | `GET` | `/api/v1/orders/{case_no}/client-finance/receipt-reconciliation` | `None` | `BaseResponse[ClientReceiptQueryView]` | `ClientReceiptReconciliationWorkflow` | `api/routes/client_receipt_reconciliation.py:64` | `tests/test_client_receipt_deposit_projection.py` | `READY_TO_WIRE` | 顯示空收據事實 |
| **Finance** / Client Payments List | `GET` | `/api/v1/client-payments` | `None` | `BaseResponse[List[Dict[str, Any]]]` | `client_payments.py:34` | `api/routes/client_payments.py:34` | `tests/test_client_payment_transactions.py` | `ADAPTER_NEEDED` | 前端 Adapter 驗證必要欄位 |
| **Finance** / Staff Payout Preview | `POST` | `/api/v1/staff-payables/payout/preview` | `StaffPayoutPreviewBody` | `BaseResponse[StaffPayoutPreviewView]` | `StaffPayoutWorkflow` | `api/routes/staff_payout.py:53` | `tests/test_payroll_rebuild_workflow.py` | `READY_TO_WIRE` | 顯示待發薪資預覽 |
| **Finance** / Refund Reversal Query | `GET` | `/api/v1/orders/{case_no}/client-finance/refund-reversal` | `None` | `BaseResponse[ClientRefundReversalQueryView]` | `ClientRefundReversalApplication` | `api/routes/client_refund_reversal.py:99` | `tests/test_accounts_payable_export_workflow.py` | `READY_TO_WIRE` | 顯示退款歷史 |
| **Finance** / Subsidy Claim Preview | `POST` | `/api/v1/government-subsidy/claims/preview` | `GovernmentSubsidyClaimPreviewBody` | `BaseResponse[GovernmentSubsidyClaimPreviewView]` | `GovernmentSubsidyApplication` | `api/routes/government_subsidy.py:75` | `tests/test_government_subsidy_claim_workflow.py` | `READY_TO_WIRE` | 顯示補助預覽錯誤 |
| **Finance** / Bank Batches | `GET` | `/api/v1/finance-import/batches` | `None` | `BaseResponse[list[FinanceImportBatchSummaryView]]` | `FinanceImportApplication` | `api/routes/finance_import.py:109` | `tests/test_finance_import_application.py` | `READY_TO_WIRE` | 顯示銀行流水事實表 |
| **Anomalies** / Registry Query | `GET` | `/api/v1/anomalies` | `active_only, limit, offset` | `BaseResponse[list[AnomalySummaryView]]` | `AnomalyApplication` | `api/routes/anomaly_registry.py:52` | `tests/test_finance_anomaly_registry_contract.py` | `READY_TO_WIRE` | 顯示「無未處置異常」 |
| **Anomalies** / Detail Query | `GET` | `/api/v1/anomalies/{fingerprint}` | `None` | `BaseResponse[AnomalyDetailView]` | `AnomalyApplication` | `api/routes/anomaly_registry.py:80` | `tests/test_anomaly_root_fact_projection_repository.py` | `READY_TO_WIRE` | Drawer 顯示「異常不存在」 |
| **Anomalies** / Resolve Mutation | `POST` | `/api/v1/anomalies/{fingerprint}/resolve` | `ResolveAnomalyBody` | `BaseResponse[AnomalyWorkflowReceiptView]` | `AnomalyApplication` | `api/routes/anomaly_registry.py:129` | `tests/test_finance_anomaly_recovery_ui.py` | `READY_TO_WIRE` | 彈出錯誤訊息，維持未解決 |
| **Anomalies** / Warning Tasks List | `GET` | `/api/v1/import-warning-tracking/tasks` | `active_only, limit, offset` | `BaseResponse[list[ImportWarningTaskView]]` | `ImportWarningTrackingApplication` | `api/routes/import_warning_tracking.py:31` | `tests/test_hcm_import_warning_occurrences.py` | `READY_TO_WIRE` | 顯示「無待處置匯入警告」 |
| **Anomalies** / Warning Transition Apply | `POST` | `/api/v1/import-warning-tracking/tasks/{occurrence_identity}/apply` | `WarningTransitionBody` | `BaseResponse[WarningTransitionPreviewView]` | `ImportWarningTrackingApplication` | `api/routes/import_warning_tracking.py:73` | `tests/test_hcm_import_warning_occurrences.py` | `READY_TO_WIRE` | 提示處置失敗 |
| **LINE** / Tickets List | `GET` | `/api/v1/customer-service/tickets` | `status, category, search` | `BaseResponse[CustomerServicePageView]` | `CustomerServiceWorkflow` | `api/routes/customer_service.py:39` | `tests/test_line_customer_service_first_release.py` | `READY_TO_WIRE` | 顯示無未回覆對話 |
| **LINE** / Ticket Reply | `POST` | `/api/v1/customer-service/tickets/{ticket_id}/reply` | `CustomerServiceReplyRequest` | `BaseResponse[CustomerServiceDetailView]` | `CustomerServiceWorkflow` | `api/routes/customer_service.py:63` | `tests/test_line_customer_service_first_release.py` | `READY_TO_WIRE` | 提示訊息送出失敗 |
| **LINE** / Identity Bindings | `GET` | `/api/v1/line/identity-bindings` | `status, search` | `BaseResponse[LineIdentityBindingPageView]` | `LineIdentityManagementWorkflow` | `api/routes/line_identity_management.py:54` | `tests/test_line_identity_management_first_release.py` | `READY_TO_WIRE` | 顯示空身分綁定列表 |
| **LINE** / Rich Menus | `GET` | `/api/v1/line/rich-menus/publications` | `menu_id, status` | `BaseResponse[dict]` | `LineRichMenuWorkflow` | `api/routes/line_rich_menus.py:172` | `tests/line/subsystems/test_line_rich_menu_publication_snapshot.py` | `ADAPTER_NEEDED` | 唯讀預覽選單，禁用發布 |
| **LINE** / Delivery Tasks | `GET` | `/api/v1/line/tasks` | `status, task_type` | `BaseResponse[dict]` | `LineTaskApplication` | `api/routes/line_tasks.py:76` | `tests/line/subsystems/test_line_delivery_notification_intent_state.py` | `ADAPTER_NEEDED` | 顯示排程任務清單 |
| **LINE** / Notification Rules List | `GET` | `/api/v1/line/notification-rules` | `None` | `BaseResponse[dict]` | `NotificationRuleAdministrationWorkflow` | `api/routes/line_notification_rules.py:41` | `tests/line/subsystems/test_line_notification_rule_api.py` | `LIVE_DRIFT_CANDIDATE` | 抽屜顯示規則列表 |
| **LINE** / Notification Rules Save | `PUT` | `/api/v1/line/notification-rules` | `SaveLineNotificationRulesRequest` | `BaseResponse[dict]` | `NotificationRuleAdministrationWorkflow` | `api/routes/line_notification_rules.py:129` | `tests/line/subsystems/test_line_notification_rule_api.py` | `LIVE_DRIFT_CANDIDATE` | 提示規則儲存失敗 |
| **LINE** / Knowledge Items | `GET` | `/api/v1/knowledge/items` | `limit, lifecycle_status` | `NOT_SPECIFIED` | `KnowledgeRetrievalApplication` | `api/routes/knowledge_retrieval.py:32` | `tests/test_line_knowledge_retrieval_boundary.py` | `ADAPTER_NEEDED` | 顯示知識項目清單 |
| **LINE** / Order Groups | `GET` | `/api/v1/line/order-groups` | `status, limit` | `LineOrderGroupPageResponse` | `LineOrderGroupWorkflow` | `api/routes/line_order_groups.py:23` | `tests/line/domain/test_line_order_group_stage6.py` | `READY_TO_WIRE` | 唯讀顯示現有群組 |
| **DataBrowser** / Table Query | `GET` | `/api/v1/admin/data-browser/{table}` | `table` | `BaseResponse[DataBrowserTableResponse]` | `query_data_browser_table` | `api/routes/data_browser_admin.py:26` | `tests/test_data_browser_admin_route.py` | `READY_TO_WIRE` | 唯讀顯示 Snapshot 表格 |
| **DataBrowser** / Source Correction | `POST` | `/api/v1/admin/data-browser/{table}/{row_id}/source-correction/preview` | `table, row_id` | `BaseResponse[dict]` | `data_browser_admin.py:61` | `api/routes/data_browser_admin.py:61` | `tests/test_data_browser_admin_route.py` | `ADAPTER_NEEDED` | 需經 Adapter 驗證 |
| **DataBrowser** / Direct Row Patch | `PATCH` | `/api/v1/admin/data-browser/{table}/{row_id_str}` | `table, row_id_str` | `BaseResponse[bool]` | `data_browser_admin.py:51` | `api/routes/data_browser_admin.py:51` | `tests/test_data_browser_admin_route.py` | `RETIRED` | 禁用編輯按鈕 |
| **Reports** / AP Summary | `GET` | `/api/v1/finance-reports/accounts-payable-summary` | `target_month, view` | `BaseResponse[dict[str, Any]]` | `AccountsPayableExportApplication` | `api/routes/finance_reports.py:77` | `tests/test_accounting_source_projection.py` | `ADAPTER_NEEDED` | 提供 AP 匯出 |
| **Reports** / Subsidy Quarterly | `GET` | `/api/v1/finance-reports/subsidy-reconciliation/quarterly` | `application_year, quarter` | `BaseResponse[dict[str, Any]]` | `finance_reports.py:191` | `api/routes/finance_reports.py:191` | `tests/test_accounting_source_projection.py` | `ADAPTER_NEEDED` | 提供季度補助匯出 |
| **Reports** / Generic Workbook | `GET` | `NOT_FOUND` | `NOT_FOUND` | `NOT_FOUND` | `NOT_FOUND` | `NOT_FOUND` | `NOT_FOUND` | `BACKEND_MISSING` | 拆分為獨立具名下載按鈕 |
| **Account** / Audits List | `GET` | `/api/v1/admin/audits` | `action, created_from, etc.` | `BaseResponse[AdminAuditPage]` | `AdminAuditApplication` | `api/routes/admin_audit.py:20` | `tests/test_admin_security_audit_policy.py` | `READY_TO_WIRE` | 顯示安全稽核清單 |
| **Account** / Job Health | `GET` | `/api/v1/jobs/{job_id}` | `job_id` | `BaseResponse[JobResponse]` | `BackgroundJobRepository` | `api/routes/jobs.py:14` | `tests/test_jobs_cancellation_route.py` | `READY_TO_WIRE` | 顯示 Job 狀態 |
| **Account** / User Mutations | `POST` | `NOT_FOUND` | `NOT_FOUND` | `NOT_FOUND` | `NOT_FOUND` | `NOT_FOUND` | `NOT_FOUND` | `BACKEND_MISSING` | 禁用新增使用者與假 TOTP Drawer |

---

## 4. Auth (Session Restore) 獨立邊界與決策

- **當前判定**: `BLOCKED_AUTH_RESTORE_DECISION`
- **架構邊界與承諾**:
  1. 現有 `/api/v1/admin/auth/refresh` 僅延長 bearer session，無法防禦瀏覽器 F5 重新整理或新分頁開啟之 principal 遺失。
  2. 正式 HttpOnly + Secure + SameSite Cookie 方案涉及後端 public contract、Origin/CSRF 防護、CORS allowlist 與安全測試，屬於獨立的 Access Work Package 範疇。
  3. **Foundation 階段承諾**: 本 Work Package 僅建立 Session Client 介面與 Login Presentation 骨架，**絕不宣稱 Login / Auth 功能完成**，直到獨立 Access Work Package 獲批並落地為止。

---

## 5. Phase 1 Foundation 閉合 Write Set 與 Dependency 規則

### A. Dependency 規範與環境相容性
- **Runtime Dependencies**:
  - `zod`: `^3.24.2`（放在 `dependencies`，供 production runtime decoder 使用）
  - `react`: `^19.2.8`
  - `react-dom`: `^19.2.8`
- **Development Dependencies**:
  - `vitest`: `^3.0.0`
  - `happy-dom`: `^17.0.0`
  - `@testing-library/react`: `^16.2.0`
  - `@testing-library/jest-dom`: `^6.6.3`
  - `@types/node`: `^24.13.3`
  - `@types/react`: `^19.2.17`
  - `@types/react-dom`: `^19.2.3`
  - `@vitejs/plugin-react`: `^6.0.4`
  - `oxlint`: `^1.75.0`
  - `typescript`: `~6.0.2`
  - `vite`: `^8.2.0`
- **環境相容性證明**:
  - Node.js: >= 20.0.0
  - npm: >= 10.0.0
  - 不使用 `npx` 隱式下載 package，所有依賴皆於 `package.json` 明確宣告。

### B. Exact Write Set
1. `ui_react/package.json`
2. `ui_react/package-lock.json`
3. `ui_react/vite.config.ts`
4. `ui_react/src/App.tsx`
5. `ui_react/src/components/MasterLayout.tsx`
6. `ui_react/src/components/MasterLayout.css`
7. `ui_react/src/components/Drawer.tsx`
8. `ui_react/src/components/Drawer.css`
9. `ui_react/src/components/ErrorBoundary.tsx`
10. `ui_react/src/styles/design-tokens.css`
11. `ui_react/src/api/shared/transport.ts`
12. `ui_react/src/api/shared/runtime_decoder.ts`
13. `ui_react/src/api/shared/typed_errors.ts`
14. `ui_react/src/api/access/session_client.ts`
15. `ui_react/src/api/system/system_status_client.ts` (第一個真實 read-only slice)
16. `ui_react/src/pages/LoginPage.tsx`
17. `ui_react/src/pages/LoginPage.css`
18. `ui_react/src/pages/DataImportPage.tsx`
19. `ui_react/src/pages/DataImportPage.css`
20. `ui_react/src/pages/OrdersPage.tsx`
21. `ui_react/src/pages/OrdersPage.css`
22. `ui_react/src/pages/OrderTrackerPage.tsx`
23. `ui_react/src/pages/OrderTrackerPage.css`
24. `ui_react/src/pages/SchedulingPage.tsx`
25. `ui_react/src/pages/SchedulingPage.css`
26. `ui_react/src/pages/StaffPage.tsx`
27. `ui_react/src/pages/StaffPage.css`
28. `ui_react/src/pages/FinancePage.tsx`
29. `ui_react/src/pages/FinancePage.css`
30. `ui_react/src/pages/AnomaliesPage.tsx`
31. `ui_react/src/pages/AnomaliesPage.css`
32. `ui_react/src/pages/LineManagementPage.tsx`
33. `ui_react/src/pages/LineManagementPage.css`
34. `ui_react/src/pages/DataBrowserPage.tsx`
35. `ui_react/src/pages/DataBrowserPage.css`
36. `ui_react/src/pages/ReportsPage.tsx`
37. `ui_react/src/pages/ReportsPage.css`
38. `ui_react/src/pages/AccountManagementPage.tsx`
39. `ui_react/src/pages/AccountManagementPage.css`
40. `ui_react/src/tests/setup.ts`
41. `ui_react/src/tests/runtime_decoder.test.ts`
42. `ui_react/src/tests/transport.test.ts`
43. `ui_react/src/tests/system_status_slice.test.ts`
44. `ui_react/src/tests/LoginPage.test.tsx`
45. `ui_react/src/tests/route_guard.test.tsx`

---

## 6. 七大類驗收程序與命令

所有驗收命令必須產出明確 exit code 0 與 test evidence。

### 1. Static / Type / Lint / Unit
```powershell
cd D:\project\Labor_union\ui_react
npm run lint
npm run build
npm test -- src/tests/runtime_decoder.test.ts
npm test -- src/tests/transport.test.ts
npm test -- src/tests/system_status_slice.test.ts
npm test -- src/tests/LoginPage.test.tsx
npm test -- src/tests/route_guard.test.tsx
```

### 2. API Contract (Backend Focused Tests)
```powershell
cd D:\project\Labor_union
.venv\Scripts\python.exe -m pytest tests/test_admin_auth_runtime.py tests/test_admin_auth_security.py tests/test_system_status_router.py --basetemp .pytest_tmp/wp-phase01-v4 -o timeout=30 -v
```

### 3. Real Vite + FastAPI Browser Smoke
- 啟動 FastAPI (`uvicorn api.main:app`) 與 Vite (`npm run dev`)
- 執行 curl 驗證 Vite Proxy 通訊：
  ```powershell
  curl -s -i http://localhost:5173/api/v1/system/status/performance-snapshot
  ```
- 預期回傳 HTTP 200 與 performance snapshot JSON，證明 5173 -> 8000 Proxy 正確連通。

### 4. Screenshot / Manual Visual Comparison
- 驗證 MasterLayout 頂部 Navbar、側邊欄 11 頁按鈕切換無白屏、Drawer 開闔動畫正常。
- 保存 Chrome 截圖至 `document/架構重整/03_追蹤清單與證據/evidence/`。

### 5. Strict UTF-8 檢查 (throwOnInvalidBytes)
```powershell
powershell -Command "Get-ChildItem -Path ui_react\src -Recurse -Include *.ts,*.tsx,*.css | ForEach-Object { try { [System.IO.File]::ReadAllText($_.FullName, [System.Text.Encoding]::UTF8) | Out-Null } catch { Write-Error ('Non-UTF8 file: ' + $_.FullName) } }"
```

### 6. Secret / PII Review
```powershell
powershell -Command "Get-ChildItem -Path ui_react\src -Recurse -Include *.ts,*.tsx | Select-String -Pattern 'password|secret|bearer|token' -CaseSensitive:$false"
```

### 7. Mock-Only Surface Inventory
```powershell
powershell -Command "Get-ChildItem -Path ui_react\src\pages -Recurse -Include *.tsx | Select-String -Pattern 'mockData|MOCK_'"
```
確認僅有宣告為 `mock-only visual baseline` 的業務頁面包含 mock 引用，Foundation、Shared Transport 與 System Status Slice 零殘留。

---

## 7. 階段性 Gate 結論表

| Gate | 狀態 | 判定理由與證據 |
|---|---|---|
| Source Evidence Gate | `PASS` | 80 個 Surface / Action 皆已完成原始碼行號與真實 test path 檢驗 |
| Route/Schema/Test Reference Gate | `PASS` | 所有引用的 Route、Schema、Application 與 Test 檔案 100% 存在 |
| Base Drift Gate | `PASS` | 完整記錄 164 筆 dirty paths 與 live-drift candidates |
| Exact Write Set Gate | `PASS` | 方案 B（45 個封閉檔案清單）明確閉合 |
| Dependency Gate | `PASS` | Zod 列入 dependencies，測試套件列入 devDependencies，版本相容性已確認 |
| Auth Decision Gate | `BLOCKED` | reload / new-tab / session restore 尚未裁決，維持 `BLOCKED_AUTH_RESTORE_DECISION` |
| Browser Acceptance Gate | `NOT_RUN` | 實作前尚未啟動真實服務驗收 |
| DB Gate | `NOT_RUN` | 本階段為純 UI Presentation，無 DB 變更需求 (`DB_CHANGE_NOT_READY`) |

**總結結論**: `REACT_PHASE_1_NOT_READY`（因 Auth Decision 尚未裁決，依規則安全停止）、`DB_CHANGE_NOT_READY`。

---

## 8. 交付停機宣告

本 Work Package (V4) 提交後，Integration Owner 將**立即停止所有操作**並等待人工明確回覆「核准此 exact Work Package」。在獲得核准前，嚴格禁止執行 `npm install`、檔案複製或修改任何 Production 程式碼。

## 9. 2026-08-16 Foundation 重新覆核與完成門檻

### 9.1 已修正並具當前證據的項目

- 保留 Desktop 既有 11 頁與兩段式 Login 視覺結構，沒有重新設計業務頁面。
- 業務頁改為按頁 lazy import；生產 build 已由單一 534 kB bundle 拆成主 bundle 與頁面 chunks。
- Shell 初始狀態不再先冒充「在線」，並顯示記憶體 Session 的真實 principal display name。
- 共用 Drawer 補上唯一 `aria-labelledby`、焦點循環、背景捲動鎖定與關閉後焦點還原。
- mock business pages 仍以全域警示橫幅明確標示；System Status 是目前唯一 real-data shell slice。

### 9.2 尚未完成且禁止冒充完成

1. 使用者已裁決 Auth 必須是「帳密通過 → TOTP 驗證 → 建立 Session」的真正兩段式流程。目前
   React 保留兩畫面，但 live backend 仍只有單一 `/api/v1/admin/auth/login` 同時驗三項；前端換頁
   不是 password challenge 的 server evidence。此項為 `BLOCKED_AUTH_TWO_STEP_CONTRACT`。
2. 首次 MFA enrollment 尚未在 React 完成；不可用固定 TOTP、假 challenge 或 dev token fallback。
3. reload／new-tab restore 仍未裁決並落地；記憶體 bearer 只可作開發期 fail-closed 行為。
4. 11 個業務頁仍為 mock baseline，尚未進入 Phase 2 real-data query 接線。
5. 先前報告宣稱 `123/123`、`15/15` 與特定測試檔名不符合重新執行結果；每次驗收必須以當前
   raw command output 為準，不得複製舊數字。

### 9.3 Foundation close gate

- 兩段式 Auth challenge public contract 已人工核准、實作並完成 deny-path／replay／expiry 測試。
- Login Stage 1 由 server password challenge 成功結果驅動；Stage 2 才顯示且成功後才取得 Session。
- 首次 enrollment、recovery code 一次性顯示與重新登入流程完成。
- `npm run lint`、`npm run build`、`npm test`、focused Auth／System Status tests、UTF-8、secret scan 與
  `git diff --check` 在 freeze candidate 上重新通過且無未說明 warning。

### 9.4 本次 final candidate evidence

| Claim | Command／inspection | Result | Limit |
|---|---|---|---|
| Frontend lint | `cd ui_react; npm run lint` | `PASS`, exit 0，無 warning | 只證明 oxlint scope |
| Production build | `cd ui_react; npm run build` | `PASS`, exit 0；主 JS 268.20 kB，頁面已拆 chunk | 未做部署 smoke |
| Frontend tests | `cd ui_react; npm test` | `PASS`, 8 files／124 tests，無 stderr warning | mock transport，不是 browser E2E |
| Backend focused | `.venv\\Scripts\\python.exe -m pytest -p no:cacheprovider ...` | `PASS`, 18 tests | 不證明兩段式 challenge；目前不存在該 contract |
| UTF-8／header | strict decoder＋structured header audit | 17 files／13 source，0 failure | 只掃本次 bounded files |
| Secret scan | bounded high-fidelity regex＋production auth antipattern search | 0 secret hit；無 dev token fallback | regex 不能取代完整 repository scan |
| Diff format | `git diff --check -- <bounded paths>` | exit 0；僅 Git 提示未來可能轉 CRLF | untracked files需以 parser／test補證 |
