# Phase 2B Contract Matrix: Orders Safe Mutations

**Document Code**: `PROV-20260816-react-admin-phase2b-orders-contract-matrix`  
**Status**: **FROZEN (G1)**  
**Date**: 2026-08-16  
**Integration Owner**: Integration Owner (`teamwork_preview_orchestrator_3`)  
**Base Commit**: `ad79f5b4fb35f1ef442f889702aaa4ccb2c5d922`  
**Specification**: `PROV-20260816-react-admin-phase2b-orders-safe-mutations-specification.md`  
**Work Package**: `PROV-20260816-react-admin-phase2b-orders-safe-mutations-work-package.md`

---

## 1. Overview & Architectural Invariants

This document establishes the authoritative contract matrix for the two bounded safe mutations in Orders:
1. **Confirmed Service Dates** (`GET /api/v1/orders/{case_no}/service-dates`, `POST .../preview`, `POST .../apply`)
2. **Controlled Order Reopen** (`POST /api/v1/orders/{case_no}/reopen/preview`, `POST .../apply`)

### Invariants:
- Zero DDL, zero schema changes, zero migrations, zero seeds/backfills (`DB_CHANGE_NOT_READY`).
- Pure read-only Preview endpoints (zero database writes).
- Apply endpoints require strict versions, SHA-256 fingerprint, non-empty trimmed reason (1–500 chars), and memory-only `Idempotency-Key`.
- Server receipt must be verified before displaying success; UI must re-query server state to enter `observed` status.
- Receipt 已收到後若 re-query 失敗，狀態為 `observation_failed` 並保留 receipt；只可重試 Query。
- Apply timeouts or 503 errors enter `outcome_unknown`, replayable only with identical payload and identical `Idempotency-Key`.
- `outcome_unknown` 期間所有 payload input 與正常 Apply 控制均鎖定。

---

## 2. HTTP Endpoint & Header Contracts

| Flow | Operation | Endpoint | Method | Required Headers | Success View / Schema | Error Model |
|---|---|---|---|---|---|---|
| **Service Dates** | Query | `/api/v1/orders/{case_no}/service-dates` | GET | `Authorization` | `ServiceDateConfirmationQueryView` | route/workflow typed；pre-route 401/403/422 為 `BACKEND_GAP` |
| **Service Dates** | Preview | `/api/v1/orders/{case_no}/service-dates/preview` | POST | `Authorization`, `X-Correlation-ID` | `ServiceDateConfirmationPreviewView` | route/workflow typed；pre-route validation 為 `BACKEND_GAP` |
| **Service Dates** | Apply | `/api/v1/orders/{case_no}/service-dates/apply` | POST | `Authorization`, `X-Correlation-ID`, `Idempotency-Key` | `ServiceDateConfirmationReceiptView` | route/workflow typed；pre-route validation 為 `BACKEND_GAP` |
| **Controlled Reopen** | Preview | `/api/v1/orders/{case_no}/reopen/preview` | POST | `Authorization`, `X-Correlation-ID` | `OrderReopenPreviewView` | route/workflow typed；pre-route validation 為 `BACKEND_GAP` |
| **Controlled Reopen** | Apply | `/api/v1/orders/{case_no}/reopen/apply` | POST | `Authorization`, `X-Correlation-ID`, `Idempotency-Key` | `OrderReopenReceiptView` | route/workflow typed；pre-route validation 為 `BACKEND_GAP` |

---

## 3. Confirmed Service Dates Contract Field Matrix

### 3.1 Query: `GET /api/v1/orders/{case_no}/service-dates`
- **Request Parameters**: `case_no: str` (path parameter, URL-encoded)
- **Response Envelope**: `BaseResponse[ServiceDateConfirmationQueryView]`

| Field Name | Type | Range / Constraints | Nullable | Description | Provenance / Source Model |
|---|---|---|---|---|---|
| `case_no` | string | non-empty | No | Order case identifier | `ServiceDateConfirmationQueryView.case_no` |
| `order_version` | integer | `>= 0` | No | Current order domain version | `ServiceDateConfirmationQueryView.order_version` |
| `scheduling_version` | integer | `>= 0` | No | Current scheduling domain version | `ServiceDateConfirmationQueryView.scheduling_version` |
| `contracted_service_days` | integer | `> 0` | No | Total required service days | `ServiceDateConfirmationQueryView.contracted_service_days` |
| `suggested_dates` | list[string] | ISO dates `YYYY-MM-DD` | No | System recommended dates | `ServiceDateConfirmationQueryView.suggested_dates` |
| `selectable_dates` | list[string] | ISO dates `YYYY-MM-DD` | No | Available dates allowed for selection | `ServiceDateConfirmationQueryView.selectable_dates` |
| `current_version` | integer | `>= 1` | Yes | Currently confirmed version (if any) | `ServiceDateConfirmationQueryView.current_version` |
| `current_dates` | list[string] | ISO dates `YYYY-MM-DD` | No | Currently confirmed dates (if any) | `ServiceDateConfirmationQueryView.current_dates` |

### 3.2 Preview: `POST /api/v1/orders/{case_no}/service-dates/preview`
- **Request Headers**: `Authorization`, `X-Correlation-ID`
- **Request Body**: `ServiceDatePreviewBody`
  - `service_dates`: `list[string]` (ISO dates `YYYY-MM-DD`, min 1 date, no duplicates)
- **Response Envelope**: `BaseResponse[ServiceDateConfirmationPreviewView]`

| Field Name | Type | Range / Constraints | Nullable | Description | Provenance / Source Model |
|---|---|---|---|---|---|
| `case_no` | string | non-empty | No | Order case identifier | `ServiceDateConfirmationPreviewView.case_no` |
| `order_version` | integer | `>= 0` | No | Current order version | `ServiceDateConfirmationPreviewView.order_version` |
| `scheduling_version` | integer | `>= 0` | No | Current scheduling version | `ServiceDateConfirmationPreviewView.scheduling_version` |
| `current_version` | integer | `>= 1` | Yes | Previous confirmed version | `ServiceDateConfirmationPreviewView.current_version` |
| `service_dates` | list[string] | ISO dates `YYYY-MM-DD` | No | Selected service dates | `ServiceDateConfirmationPreviewView.service_dates` |
| `weeks` | list[object] | Array of `ServiceWeekView` | No | Grouped service weeks | `ServiceDateConfirmationPreviewView.weeks` |
| `weeks[].week_number` | integer | `> 0` | No | Week index (1-based) | `ServiceWeekView.week_number` |
| `weeks[].period_start` | string | ISO date (Sunday) | No | Week start date | `ServiceWeekView.period_start` |
| `weeks[].period_end` | string | ISO date (Saturday) | No | Week end date | `ServiceWeekView.period_end` |
| `weeks[].service_dates` | list[string] | ISO dates `YYYY-MM-DD` | No | Service dates in this week | `ServiceWeekView.service_dates` |
| `weeks[].service_day_count` | integer | `> 0` | No | Days count in this week | `ServiceWeekView.service_day_count` |
| `preview_fingerprint` | string | 64-hex SHA-256 | No | Deterministic payload hash | `ServiceDateConfirmationPreviewView.preview_fingerprint` |

### 3.3 Apply: `POST /api/v1/orders/{case_no}/service-dates/apply`
- **Request Headers**: `Authorization`, `X-Correlation-ID`, `Idempotency-Key`
- **Request Body**: `ServiceDateApplyBody`
  - `service_dates`: `list[string]` (ISO dates `YYYY-MM-DD`, min 1 date, no duplicates)
  - `expected_order_version`: `integer` (`>= 0`)
  - `expected_scheduling_version`: `integer` (`>= 0`)
  - `preview_fingerprint`: `string` (64-hex SHA-256)
  - `reason`: `string` (Trimmed, required, length 1–500 chars)
- **Response Envelope**: `BaseResponse[ServiceDateConfirmationReceiptView]`

| Field Name | Type | Range / Constraints | Nullable | Description | Provenance / Source Model |
|---|---|---|---|---|---|
| `case_no` | string | non-empty | No | Order case identifier | `ServiceDateConfirmationReceiptView.case_no` |
| `confirmed_version` | integer | `> 0` | No | Newly issued confirmation version | `ServiceDateConfirmationReceiptView.confirmed_version` |
| `order_version` | integer | `>= 0` | No | Updated order version | `ServiceDateConfirmationReceiptView.order_version` |
| `scheduling_version` | integer | `>= 0` | No | Updated scheduling version | `ServiceDateConfirmationReceiptView.scheduling_version` |
| `service_dates` | list[string] | ISO dates `YYYY-MM-DD` | No | Confirmed service dates | `ServiceDateConfirmationReceiptView.service_dates` |
| `preview_fingerprint` | string | 64-hex SHA-256 | No | Matching preview fingerprint | `ServiceDateConfirmationReceiptView.preview_fingerprint` |

---

## 4. Controlled Order Reopen Contract Field Matrix

### 4.1 Preview: `POST /api/v1/orders/{case_no}/reopen/preview`
- **Request Headers**: `Authorization`, `X-Correlation-ID`
- **Response Envelope**: `BaseResponse[OrderReopenPreviewView]`

| Field Name | Type | Range / Constraints | Nullable | Description | Provenance / Source Model |
|---|---|---|---|---|---|
| `case_no` | string | non-empty | No | Order case identifier | `OrderReopenPreviewView.case_no` |
| `order_version` | integer | `>= 0` | No | Expected order version | `OrderReopenPreviewView.order_version` |
| `client_finance_version` | integer | `>= 0` | No | Expected client finance version | `OrderReopenPreviewView.client_finance_version` |
| `payroll_version` | integer | `>= 0` | No | Expected payroll version | `OrderReopenPreviewView.payroll_version` |
| `cancellation_event_id` | integer | `> 0` | No | Target cancellation event to un-cancel | `OrderReopenPreviewView.cancellation_event_id` |
| `before_status` | string | literal `cancelled` | No | Status before reopen | `OrderReopenPreviewView.before_status` |
| `after_status` | string | non-empty string | No | Projected status after reopen | `OrderReopenPreviewView.after_status` |
| `requires_fresh_scheduling_preview` | boolean | must be `true` | No | Flag indicating fresh scheduling required | `OrderReopenPreviewView.requires_fresh_scheduling_preview` |
| `restored_assignment_ids` | list[integer] | must be `[]` | No | Restored assignments (must be empty) | `OrderReopenPreviewView.restored_assignment_ids` |
| `restored_schedule_ids` | list[integer] | must be `[]` | No | Restored schedules (must be empty) | `OrderReopenPreviewView.restored_schedule_ids` |
| `restored_lock_ids` | list[integer] | must be `[]` | No | Restored locks (must be empty) | `OrderReopenPreviewView.restored_lock_ids` |
| `preview_fingerprint` | string | 64-hex SHA-256 | No | Deterministic preview fingerprint | `OrderReopenPreviewView.preview_fingerprint` |

### 4.2 Apply: `POST /api/v1/orders/{case_no}/reopen/apply`
- **Request Headers**: `Authorization`, `X-Correlation-ID`, `Idempotency-Key`
- **Request Body**: `OrderReopenApplyBody`
  - `expected_order_version`: `integer` (`>= 0`)
  - `expected_client_finance_version`: `integer` (`>= 0`)
  - `expected_payroll_version`: `integer` (`>= 0`)
  - `preview_fingerprint`: `string` (64-hex SHA-256)
  - `reason`: `string` (Trimmed, required, length 1–500 chars)
- **Response Envelope**: `BaseResponse[OrderReopenReceiptView]`

| Field Name | Type | Range / Constraints | Nullable | Description | Provenance / Source Model |
|---|---|---|---|---|---|
| `case_no` | string | non-empty | No | Order case identifier | `OrderReopenReceiptView.case_no` |
| `order_version` | integer | `>= 0` | No | Reopened order version | `OrderReopenReceiptView.order_version` |
| `lifecycle_status` | string | non-empty string | No | Restored lifecycle status | `OrderReopenReceiptView.lifecycle_status` |
| `cancellation_event_id` | integer | `> 0` | No | Cancellation event un-cancelled | `OrderReopenReceiptView.cancellation_event_id` |
| `requires_fresh_scheduling_preview` | boolean | must be `true` | No | Flag indicating fresh scheduling required | `OrderReopenReceiptView.requires_fresh_scheduling_preview` |
| `preview_fingerprint` | string | 64-hex SHA-256 | No | Matching preview fingerprint | `OrderReopenReceiptView.preview_fingerprint` |

**STRICT RECEIPT INVARIANT**: The receipt schema MUST NOT contain `client_finance_version`, `payroll_version`, `created_at`, or `idempotency_key`.

---

## 5. Reason Validation & Hardening Matrix

| Flow | Parameter | Constraints | Negative Test Cases | Positive Test Cases |
|---|---|---|---|---|
| Service Dates Apply | `reason` | Trimmed, 1–500 chars | Empty `""`, Whitespace `"   "`, `> 500` chars | Single char `"a"`, 500 chars, Chinese `"變更服務日期"` |
| Reopen Apply | `reason` | Trimmed, 1–500 chars | Empty `""`, Whitespace `"   "`, `> 500` chars | Single char `"r"`, 500 chars, Chinese `"客戶重啟訂單"` |

---

## 6. Stable ID Inventory & Control Transition

### 6.1 Enabled Flow Controls (Exactly 6):
1. `orders.date.service-date-select` — Calendar/date selection slot
2. `orders.date.service-date-preview` — Preview button for service date changes
3. `orders.date.service-date-apply` — Apply button for confirmed service dates
4. `orders.card.reopen` — Reopen action button on cancelled order card
5. `orders.reopen.reason` — Reason input in Reopen dialog
6. `orders.reopen.apply` — Confirm Reopen action button

### 6.2 Preserved Native-Disabled Controls

以實際 stable-ID inventory 逐項驗收，不以固定數量替代完整性；任何新增、刪除或改名均須重新盤點。
- Service Date Drawer: `orders.date.actual-start`, `orders.date.update-service-hours`, `orders.date.send-actuarial-schedule`, `orders.date.customer-confirm-phone`, `orders.date.staff-confirm-phone`, `orders.date.convert-formal-fulfillment`.
- Matching Drawer: `orders.matching.pool-select`, `orders.matching.candidate-info-1`, `orders.matching.candidate-info-2`, `orders.matching.willingness-toggle`, `orders.matching.resume-modal`, `orders.matching.client-decision-confirm`.
- Terms Drawer: `orders.terms.contract-progress`, `orders.terms.preview-terms`, `orders.terms.apply-terms`.
- Cancellation Drawer: `orders.cancellation.reason-select`, `orders.cancellation.refund-calculate`, `orders.cancellation.payout-calculate`, `orders.cancellation.preview-apply`.
- Order Tracker: `tracker.sop.step-action-1` through `tracker.sop.step-action-11` (all SOP manual toggles), `tracker.notifications.replay`.

---

## 7. Write-Set Baseline Hashes

| Path | Size (Bytes) | SHA-256 Hash |
|---|---:|---|
| `api/routes/service_date_confirmation.py` | 4183 | `a56f3f284f8841f728fbf311ec385bddfc3596be8eac42b0ca4b65288f19dc0d` |
| `api/schemas/service_date_confirmation.py` | 1435 | `3a37b4ac8a3fdd77b9322b83584b13bc8d3bc65273d986dfaa01f4474d2efa06` |
| `api/routes/order_reopen.py` | 8386 | `0c41d099d2c7b8fbda99442d880c5f22cd0455f808c5e26ef73d5245736b2339` |
| `tests/test_service_date_confirmation.py` | 1550 | `8f34071ec2110af8c34c14590765c49d055cc2253a9ad3cd80c6c6ba8cb17a4d` |
| `tests/test_order_reopen_workflow.py` | 2219 | `d12e3a6cdcef139a72981f71274904cd6ecfddb6310b75892abcc6aaa33a45b4` |
| `ui_react/src/pages/OrdersPage.tsx` | 29062 | `f09362fec8cfccd18b09f178dac3053a676cdf597951adcc02fc1b82db0cae01` |
| `ui_react/src/pages/OrdersPage.css` | 3786 | `eeb6b9171be7f311a919e7017024e1054c1aa05f7f2270d40028a12a7dade5c6` |
| `ui_react/src/tests/orders_no_fake_mutation.test.ts` | 10763 | `e0b3dfc814fc12ad9f8963d8b2d201553f9d04db7eb7624ff40f8f96a4144eb6` |
