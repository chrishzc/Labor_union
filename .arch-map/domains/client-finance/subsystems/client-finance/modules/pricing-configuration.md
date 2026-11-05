# Module: pricing-configuration

## Parent
- domain: `client-finance`
- subsystem: `client-finance`

## Responsibility
Versioned customer pricing/subsidy limits, policy selection at first case creation,
and typed coordination of explicit per-case repricing. Payroll owns salary tiers.
No query writes; one outer transaction and typed stale/idempotency conflicts.
一般市民為 citizen（預設 40）、補助市民為 social（預設 120）。新政策只用正式名稱；既有舊命名政策依保存的 rule／金額讀取，前端只轉換新稿與顯示標籤，保留原版名稱及自訂身分。新一般／補助案件遇到舊命名的有效政策回報 typed bootstrap blocker，避免錯綁。

## Implementation
- `domains/client_finance/pricing_policy.py`
- `subsystems/client_finance/pricing_configuration.py`
- `infrastructure/mysql/pricing_configuration_repository.py` — `CASE_PRICING_FACTS_SQL` 以人工設定優先、綁定政策次之提供唯讀計價投影；新舊政策名稱依綁定版本判別，不修改既有 schema view 或政策版本。
- `infrastructure/mysql/case_category_query.py` — read-only category expression from the bound per-case pricing rule, selected policy identity rule and legacy identity fallback; it creates no classification root or mutation.
- `api/schemas/accounting_pricing.py`
- `api/dependencies/accounting_pricing.py` — 延遲取得 MySQL 連線，並對唯讀 `GET /api/v1/accounting-pricing` 提供選用 Redis＋L1 TTL 投影快取（`POST /api/v1/accounting-pricing/policies` 提交成功後失效；Preview／Apply 一律走 fresh DB 讀取）。
- `api/routes/accounting_pricing.py`
- `ui_react/src/api/client_finance/accounting_pricing_client.ts`
- `ui_react/src/pages/AccountingParametersPage.tsx`
- `ui_react/src/pages/AccountingParametersPage.css`
- `ui_react/src/components/CasePricingAdjustmentPanel.tsx`

## Contracts
- Reporting borrows read-only `case_total_amount` from complete current `CasePricingFacts`; Domain `calculate_case_total_amount` retains covered service before funding, double-pay and one fixed floor fee. It does not reuse salary or receipt totals — `15` §15.4 / `04` §0 Reporting 唯讀投影.
- `document/架構重整/01_規格基線/04_Client_Finance_Domain.md` §0 PRICE-01..09.
- 同節 IDENTITY-FIX-01..03：正式身分修正與歷史綁定相容；舊版讀取只供仍綁定舊政策的案件，不供新政策發布，待無舊版綁定使用者後才可另評估退役。

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
- inbound: `government-subsidy/reconciliation-register-query` 與 Orders 補助投影 adapter — 重用 `CASE_PRICING_FACTS_SQL` 的有效補助上限／費率，不由消費端重解讀舊政策名稱。
