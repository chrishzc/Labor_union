# Orders Query Page-Slice Contract Matrix

狀態：candidate frozen for local verification；browser evidence 尚未執行。矩陣依 2026-08-17 fresh source 建立，不以 fixture 取代 Pydantic。

| Stable ID | GET | Pydantic authority | Strict Zod | OrdersPage disposition |
|---|---|---|---|---|
| `ORD-QRY-001` | `/api/v1/orders/summaries` | `api/schemas/order_summary.py::OrderSummaryPageView` | `OrderSummaryPageSchema` | 初始列表；只顯示 raw `order_status`，七階段 filter disabled |
| `ORD-QRY-002` | `/api/v1/orders/{case_no}` | `api/schemas/order_detail.py::OrderDetailView` | `OrderDetailSchema` | Date／Matching／Contract Drawer detail facts |
| `ORD-QRY-003` | `/api/v1/orders/{case_no}/calendar-detail` | `api/schemas/order_calendar_detail.py::OrderCalendarDetailView` | `OrderCalendarDetailSchema` | Date Drawer `service_mode` |
| `ORD-QRY-004` | `/api/v1/orders/{case_no}/terms` | `api/schemas/order_terms.py::OrderTermsQueryView` | `OrderTermsSchema` | Contract Drawer typed terms |
| `ORD-QRY-005` | `/api/v1/orders/{case_no}/form-management-context` | `api/schemas/form_management.py::FormManagementCaseContextView` | `FormManagementContextSchema` | allowlist 保留；OrdersPage 未預抓 |
| `ORD-QRY-006` | `/api/v1/orders/{case_no}/actual-start` | `api/schemas/order_actual_start.py::ActualStartQueryView` | `ActualStartSchema` | Date Drawer；只顯示 current actual start |
| `ORD-QRY-007` | `/api/v1/orders/{case_no}/contract-completion` | `api/schemas/order_contract_completion.py::ContractCompletionQueryView` | `ContractCompletionSchema` | Contract Drawer completion／deposit blockers |
| `ORD-QRY-008` | `/api/v1/orders/{case_no}/assignment-plan` | `api/schemas/assignment_plan.py::AssignmentPlanQueryView` | `AssignmentPlanSchema` | Matching Drawer 顯示正式執行排班，明示非推薦 |

共同信封由 `createOrderQueryEnvelopeSchema` 嚴格要求 `success/message/data/error` 四欄且禁止 extra key。所有 object 使用 strict schema；required、nullable 與 optional 依 Pydantic 分開，沒有 `.default()`、`z.record()`、`.passthrough()`、`z.any()` 或 `z.unknown()`。

未列入 allowlist 的 candidate pool、recommend-staff、active matching、contact state、lifecycle-control-state、contract-signing、cancellation、service-dates、schedule-confirmation 與 statistics 均沒有 query client method。Service Dates 由既有 Phase 2B mutation client 擁有。
