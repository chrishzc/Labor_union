# Module: historical-payment-settlement

## Parent
- domain: `staff-payables`
- subsystem: `staff-payables`

## Responsibility
保存已採納 pre-system historical case 的 Staff Payables 人工 payout／結清證據、exact staff obligation links、current owner overlay、receipt 與同一 outer Unit of Work source intent。不得由 Client payment、Orders status、清冊或政府撥款推定 payout。

## Implementation
- primary:
  - `domains/staff_payables/historical_payout.py` — owner rules, exact staff/case obligations and later-reopen predicate.
  - `subsystems/staff_payables/historical_payment_settlement.py` — Query／Preview／Apply／fresh readback orchestration.
  - `infrastructure/mysql/historical_staff_payout_repository.py` — typed repository implementation without hidden commit.
- entrypoints:
  - `api/routes/staff_payout.py` — authenticated internal owner transport.
  - `api/dependencies/staff_payout.py` — request-scoped repository／outer UoW composition.
  - `api/schemas/staff_payout.py` — bounded strict HTTP request／response views.
- migrations:
  - `db/schema_parts/1020_historical_owner_payment_settlement.sql` — Staff-owned tables only.

## Contracts
- `document/架構重整/02_決策與退役執行記錄/PROV-20260828-historical-payment-and-owner-settlement-spec.md`
- `document/架構重整/01_規格基線/05_Staff_Payables_Export_Domain.md`
- authenticated owner API — `Query → Preview → Apply → fresh readback`; no Client Finance inference or cross-owner transaction.

## Verification
- test_root: `tests/domains/staff-payables/subsystems/staff-payables/modules/historical-payment-settlement/`
- higher_boundary:
  - existing `api/main.py` composition includes the owning `staff_payout` router.

## Provenance
- Owner-specific public operations and boundary — `architecture_declared` — 2026-08-31 latest explicit user adjudication.
- Exact source／test paths — `source_observed` — current workspace.

## Change triggers
- Reconcile when historical eligibility, exact staff/case obligation binding, owner version, outer UoW, receipt/outbox, or canonical test root changes.
