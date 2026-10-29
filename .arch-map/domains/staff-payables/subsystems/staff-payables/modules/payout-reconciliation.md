# Module: payout-reconciliation

## Parent
- domain: `staff-payables`
- subsystem: `staff-payables`

## Responsibility
沿既有 Staff Payables 契約編排銀行出款核銷、退匯與沖正的 Query／Preview／Apply；由同一 outer Unit of Work 保存付款事件、精確義務連結、projection、receipt 與 outbox，不發動銀行匯款。

## Implementation
- `subsystems/staff_payables/case_accounting_query.py`
- `infrastructure/mysql/case_staff_accounting_repository.py` — case-scoped effective obligation, payout and historical evidence; no month filter, no cash writer.
- `domains/staff_payables/reconciliation.py`
- `subsystems/staff_payables/payout_reconciliation.py`
- `infrastructure/mysql/staff_payout_repository.py`

## Contracts
- `document/架構重整/01_規格基線/05_Staff_Payables_Export_Domain.md` §2–3。
- `document/架構重整/01_規格基線/16_Staff_Payables與Client_Refund正式規格.md`。

## Verification
- integration_root: `tests/domains/staff-payables/subsystems/staff-payables/integration/test_staff_payout_reconciliation_workflow.py`
- integration_root: `tests/domains/staff-payables/subsystems/staff-payables/integration/test_staff_payout_repository_recovery.py`
