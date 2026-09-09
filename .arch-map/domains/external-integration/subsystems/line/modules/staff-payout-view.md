# Module: staff-payout-view

## Parent
- domain: `external-integration`
- subsystem: `line`

## Responsibility
提供已驗證月嫂依 canonical staff role binding，唯讀查詢本人指定目標付款月份的逐案薪資、應付日、實付日、狀態與交易摘要。月份依 Staff Payables 正式契約的 target payment month（`due_date`）歸屬；LINE 不重算或改寫應付事實。

## Implementation
- entrypoints:
  - `api/routes/line_staff_self_service.py::monthly_payouts`
  - `api/routes/line_identity.py::staff_payout_page`
  - `line/static/staff_payout.html`
- typed transport: `api/schemas/line_staff_self_service.py`
- identity reader: `infrastructure/mysql/customer_service_repository.py::staff_subject`
- Staff Payables query port: `subsystems/staff_payables/staff_payout_self_service_query.py::StaffPayoutSelfServiceQuery`
- adapter: `infrastructure/mysql/staff_payout_self_service_query_repository.py::query_by_staff_and_payment_month`
- composition: `infrastructure/mysql/line_unit_of_work.py`

## Dependencies
- outbound: `staff-payables` — consumes canonical `staff_obligations`, `staff_payable_projections` and immutable payout ledger facts; ownership and payment status remain Staff Payables-owned.
- outbound: `line-identity-management` — resolves the verified LINE user to the canonical active staff binding before any payment query.

## Contracts
- `document/架構重整/01_規格基線/05_Staff_Payables_Export_Domain.md` §2–3 — target payment month and Staff Payables ownership.
- `document/架構重整/01_規格基線/20_LINE客服與月嫂自助服務正式規格.md` — verified staff self-service boundary.

## Verification
- test_root: `tests/domains/external-integration/subsystems/line/modules/staff-payout-view/`
- adapter contract: `tests/domains/external-integration/subsystems/line/modules/staff-payout-view/contract/test_staff_payout_view_contract.py`

## Change triggers
Reconcile when payout month semantics, canonical staff binding, visible payment fields, query owner, or focused verification paths change.
