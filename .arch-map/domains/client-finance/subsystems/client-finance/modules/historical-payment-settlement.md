# Module: historical-payment-settlement

## Parent
- domain: `client-finance`
- subsystem: `client-finance`

## Responsibility
保存已採納 pre-system historical case 的 Client Finance 人工付款／結清證據、exact obligation links、current owner overlay、receipt 與同一 outer Unit of Work source intent。不得偽造 bank row／allocation，也不得推定 Staff Payables 或 Step 11。

## Implementation
- primary:
  - `domains/client_finance/historical_payment.py` — owner rules, direction, exact obligations and later-reopen predicate.
  - `subsystems/client_finance/historical_payment_settlement.py` — Query／Preview／Apply／fresh readback orchestration.
  - `infrastructure/mysql/historical_client_payment_repository.py` — typed repository implementation without hidden commit.
- entrypoints:
  - `api/routes/client_payments.py` — authenticated internal owner transport.
  - `api/dependencies/client_payments.py` — request-scoped repository／outer UoW composition.
  - `api/schemas/client_payments.py` — bounded strict HTTP request／response views.
- migrations:
  - `db/schema_parts/1020_historical_owner_payment_settlement.sql` — Client-owned tables only.

## Contracts
- `document/架構重整/02_決策與退役執行記錄/PROV-20260828-historical-payment-and-owner-settlement-spec.md`
- `.arch-map/requirements/04_Client_Finance_Domain.md`
- authenticated owner API — `Query → Preview → Apply → fresh readback`; no Anomalies writer or cross-owner transaction.

## Verification
- test_root: `tests/domains/client-finance/subsystems/client-finance/modules/historical-payment-settlement/`
- higher_boundary:
  - existing `api/main.py` composition includes the owning `client_payments` router.
- 靜態來源（`subsystems/client_finance/historical_payment_settlement.py` L117–161）：同一命令重播且指紋相符時回原收據；指紋不符、候選過期或受阻時，不到達寫入呼叫。成功路徑在同一外層 UoW 依序呼叫事件、義務連結、投影、來源 outbox 及收據寫入後才提交。此處不證明真實資料庫原子性、授權或實際結算。

## Provenance
- Owner-specific public operations and boundary — `architecture_declared` — 2026-08-31 latest explicit user adjudication.
- Exact source／test paths — `source_observed` — current workspace.

## Change triggers
- Reconcile when historical eligibility, Client direction, exact obligation binding, owner version, outer UoW, receipt/outbox, or canonical test root changes.
