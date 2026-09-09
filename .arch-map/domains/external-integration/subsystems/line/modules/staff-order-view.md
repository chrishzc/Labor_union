# Module: staff-order-view

## Parent
- domain: `external-integration`
- subsystem: `line`

## Responsibility
以 verified LINE staff identity 限制有效 assignment 可見集合，並呈現該月嫂的 typed 訂單摘要；案件編號或客戶姓名只作集合內的可選篩選。

## Implementation
- primary:
  - `line/static/staff_order_search.html`
  - `api/routes/line_staff_self_service.py`
  - `api/routes/line_staff_self_service.py::order_search`
  - `api/schemas/line_staff_self_service.py::StaffOrderSearchRequest`
  - `infrastructure/mysql/customer_service_repository.py::MySqlCustomerServiceRepository.staff_orders`

## Dependencies
- outbound: `orders` — 讀取 typed 訂單與客戶摘要。
- outbound: `scheduling` — 以有效 `case_staff_assignments` 限制 staff 可見集合。
- outbound: `external-integration/line/module:line-identity-management` — 驗證 LINE identity 與 staff binding。

## Contracts
- `POST /api/v1/line/staff-self-service/orders` — `api/routes/line_staff_self_service.py`
- Staff Self-Service 訂單查詢 — `document/架構重整/01_規格基線/20_LINE客服與月嫂自助服務正式規格.md` §5.1

## Verification
- test_root: `tests/domains/external-integration/subsystems/line/modules/staff-order-view/`

## Provenance
- assignment-scoped visibility and optional in-set filtering — `architecture_declared` — `document/架構重整/01_規格基線/20_LINE客服與月嫂自助服務正式規格.md` §5.1
- implementation and verification paths — `source_observed` — current repository.

## Change triggers
- Reconcile when staff order visibility, filter behavior, typed response, entrypoint, or focused verification path changes.
