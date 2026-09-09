# Module: staff-payout-self-service-query

## Parent
- domain: `staff-payables`
- subsystem: `staff-payables`

## Responsibility
從 canonical `staff_obligations`、`staff_payable_projections` 與 immutable payout ledger，依 `staff_id + target payment month` 組成逐案唯讀明細。歸月以 `due_date` 為準；付款狀態與 net paid 不從 LINE 或 legacy `staff_payments` 重算。

## Implementation
- primary:
  - `subsystems/staff_payables/staff_payout_self_service_query.py`
  - `infrastructure/mysql/staff_payout_self_service_query_repository.py`

## Dependencies
- inbound: `external-integration/line/module:staff-payout-view` — verified staff subject only.
- outbound: Staff Payables canonical obligations, projections and ledger.

## Contracts
- `document/架構重整/01_規格基線/05_Staff_Payables_Export_Domain.md` §2–3.

## Verification
- test_root: `tests/domains/staff-payables/subsystems/staff-payables/modules/staff-payout-self-service-query/`

## Change triggers
Reconcile when target payment month, payable aggregation, net-paid status or ledger transaction projection changes.
