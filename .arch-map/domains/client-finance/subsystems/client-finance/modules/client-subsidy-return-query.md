# Module: client-subsidy-return-query

## Parent
- domain: `client-finance`
- subsystem: `client-finance`

## Responsibility
唯讀列出有補助資格、需由客戶先付款的案件，取消後已有正式應退補助仍列出；不以正式退款義務存在與否作為查詢前提；排除補助內免墊與已退款案件。Domain 計算明示預估，正式退款 projection 優先；不建立帳務或重定義付款 writer。有效個案計價存在時依其 citizen／social rule、補助上限與客戶補助內費率，不以舊版「補助市民」字串誤排除 40 小時先墊案件；無綁定時依正式一般市民 40 小時原規則。

## Implementation
- primary: `subsystems/client_finance/subsidy_return_query.py`
- rules: `domains/client_finance/subsidy_return_projection.py`
- adapter: `infrastructure/mysql/subsidy_return_query_repository.py`
- composition: `api/dependencies/client_subsidy_return_query.py`
- schema: `api/schemas/client_subsidy_return_query.py`
- entrypoint: `api/routes/finance_reports.py` — `/api/v1/finance-reports/client-subsidy-returns` GET；其餘既有應付帳款入口維持原 owner。

## Contracts
- `document/架構重整/01_規格基線/04_Client_Finance_Domain.md` — 2026-10-01 案件查詢裁決。
- `domains/client_finance/subsidy_coverage.py` 與 `subsidy_advance.py` — 既有補助時數／日期政策。
- outbound: `orders` — canonical lifecycle、服務條件及實際結案日期。
- outbound: `client-finance/pricing-configuration` — adapter 重用 `CASE_PRICING_FACTS_SQL`，typed facts 帶 `CasePricingTerms` 至 Domain，Query 不寫政策／個案設定。
- inbound: `historical-payment-settlement-presentation` — 既有 FinancePage 補助退款頁籤。

## Verification
- test_root: `tests/domains/client-finance/subsystems/client-finance/modules/client-subsidy-return-query/`

## Change triggers
案件資格、正式／預估金額來源、日期來源、GET contract、分頁或寫入邊界改變時重核。
