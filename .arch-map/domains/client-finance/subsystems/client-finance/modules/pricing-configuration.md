# Module: pricing-configuration

## Parent
- domain: `client-finance`
- subsystem: `client-finance`

## Responsibility
Versioned customer pricing/subsidy limits, policy selection at first case creation,
and typed coordination of explicit per-case repricing. Payroll owns salary tiers.
No query writes; one outer transaction and typed stale/idempotency conflicts.

## Implementation
- `domains/client_finance/pricing_policy.py`
- `subsystems/client_finance/pricing_configuration.py`
- `infrastructure/mysql/pricing_configuration_repository.py`
- `infrastructure/mysql/case_category_query.py` — read-only category expression from the bound per-case pricing rule, selected policy identity rule and legacy identity fallback; it creates no classification root or mutation.
- `api/schemas/accounting_pricing.py`
- `api/dependencies/accounting_pricing.py` — 延遲取得 MySQL 連線，並對唯讀 `GET /api/v1/accounting-pricing` 提供選用 Redis＋L1 TTL 投影快取（`POST /api/v1/accounting-pricing/policies` 提交成功後失效；Preview／Apply 一律走 fresh DB 讀取）。
- `api/routes/accounting_pricing.py`
- `ui_react/src/api/client_finance/accounting_pricing_client.ts`
- `ui_react/src/pages/AccountingParametersPage.tsx`
- `ui_react/src/pages/AccountingParametersPage.css`
- `ui_react/src/components/CasePricingAdjustmentPanel.tsx`

## Contracts
- `document/架構重整/01_規格基線/04_Client_Finance_Domain.md` §0 PRICE-01..09.

## Verification
- layout_status: `custom_current`
- layout_basis: Backend module tests use the canonical owner root; React tests mirror that root under ui_react/src/tests for the existing Vitest runtime.
- integration_root: `tests/domains/client-finance/subsystems/client-finance/integration/test_accounting_pricing_mysql.py`
- test_root: `tests/domains/client-finance/subsystems/client-finance/modules/pricing-configuration/`
- test_root: `ui_react/src/tests/domains/client-finance/subsystems/client-finance/modules/pricing-configuration/`

## Dependencies
- outbound: `payroll` — salary calculation/obligations; no duplicate payroll writer.
- inbound: `case-import` — bind only on first case creation.
- inbound: `clients/client-profile` — Drawer composes typed workflow only.
- inbound: `global/reporting` and Client Finance payment queries — reuse the same policy-based case category; case-number spelling does not determine category.
