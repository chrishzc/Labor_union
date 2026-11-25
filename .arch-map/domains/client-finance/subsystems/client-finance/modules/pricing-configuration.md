# Module: pricing-configuration

## Parent
- domain: `client-finance`
- subsystem: `client-finance`

## Responsibility

歷史完成案件以 `CasePricingFacts.historical_service_hours` 借用已採納／已確認服務量計價，不建逐日資料或套現代分期。typed historical repricing plan 把價格差額分配至原期款、既有補助退款及原月嫂應付，交各原金額更正 writer 在同一外層交易處理；人工金額控制與現金 lineage 保留。
各身分的歷史已完成案件，Terms 樓層費更正讀取既有歷史服務天數與訂金資料，將樓層費差額交給 Client Finance 差額 writer 更正原訂金或建立訂金應收。規則見歷史訂單規格 §6.3。
Versioned customer pricing/subsidy limits, policy selection at first case creation,
and typed coordination of explicit per-case repricing. Payroll owns salary tiers.
No query writes; one outer transaction and typed stale/idempotency conflicts.
一般市民為 citizen（預設 40）、補助市民為 social（預設 120）、原住民（含別名 `原民`、`原住民市民`）預設上限 80 小時／350 元。新政策只用正式名稱；既有舊命名政策依保存的 rule／金額讀取，前端只轉換新稿與顯示標籤，保留原版名稱及自訂身分。新一般／補助／原住民案件遇到舊命名的有效政策回報 typed bootstrap blocker，避免錯綁。
`domains/client_finance/subsidy_coverage.py` 與 `AccountingParametersDrawer` 同步對齊原住民預設 80h／350 元。

## Implementation
- `domains/client_finance/pricing_policy.py`
- `subsystems/client_finance/pricing_configuration.py`
- `infrastructure/mysql/pricing_configuration_repository.py` — `CASE_PRICING_FACTS_SQL` 以人工設定優先、綁定政策次之提供唯讀計價投影；新舊政策名稱依綁定版本判別，不修改既有 schema view 或政策版本。
- `infrastructure/mysql/holiday_repricing.py` — 借用正式計價投影與原帳務 writer；待核對金額維持未知，缺計算依據時沿既有 savepoint 回滾該案。
- `infrastructure/mysql/case_category_query.py` — read-only category expression from the bound per-case pricing rule, selected policy identity rule and legacy identity fallback; it creates no classification root or mutation.
- `api/schemas/accounting_pricing.py`
- `api/dependencies/accounting_pricing.py` — 延遲取得 MySQL 連線，並對唯讀 `GET /api/v1/accounting-pricing` 提供選用 Redis＋L1 TTL 投影快取（`POST /api/v1/accounting-pricing/policies` 提交成功後失效；Preview／Apply 一律走 fresh DB 讀取）。
- `api/routes/accounting_pricing.py`
- `ui_react/src/api/client_finance/accounting_pricing_client.ts`
- `ui_react/src/pages/AccountingParametersPage.tsx`
- `ui_react/src/pages/AccountingParametersPage.css`
- `ui_react/src/components/CasePricingAdjustmentPanel.tsx`
- `ui_react/src/components/HistoricalCorrectionAccounting.tsx` — 名冊與帳務抽屜共用的 typed 歷史差額及待核對投影。
- `ui_react/src/components/AccountingParametersCard.tsx`
- AccountingParametersCard 僅顯示正式 CasePricing terms／impact 及傳入 owner 金額；讀取失敗或缺來源時維持待確認，不補 0 小時、160 小時、預設費率或在瀏覽器重算總額。應繳與應付金額各自優先顯示傳入的正式帳務金額；該欄未傳入時才顯示已提供的 CasePricing impact 對應金額。缺 CasePricing 時顯示計價依據待確認，已傳入的正式金額仍照常顯示。
- `ui_react/src/components/AccountingParametersBar.tsx`
- `ui_react/src/components/AccountingParametersDrawer.tsx`
- `ui_react/src/components/AccountingParameters.css`

## 歷史服務完成後更正

歷史計價以 `HistoricalPricingPerson` 保存各採納指派的已確認服務量，以 `HistoricalRepricingPlan` 區分客戶、逐人應付、補助差額與待核對。缺少某人的原應付不再阻擋其他可確認部分。已證實免自備且沒有原客戶義務時不補建期款；原期款或歸屬缺證據則列待核對。Preview 唯讀並綁定原帳來源與 owner versions，Apply 交既有 Client Finance／Payroll 數額更正 writer，在原外層交易保存差額與結果。待核對保存於既有 pricing event，查詢及重送讀回正式結果。原款身分、收付、核銷、付款日與費率快照保留。驗收依[歷史服務完成後更正](../../../../../requirements/27_歷史訂單生命週期與服務天數帳務正式規格.md#historical-completed-fact-correction)。

`HistoricalAccountingCarry` 沿既有 pricing event 與歷史天數事件的財務計畫保存未處理的計算基準與來源。後續胎數、服務資料或個案計價更正接續同一基準，補證後才能清除對應待核對，不能只算最近一次變更或以無變更操作消除舊差額。服務量或原計算基準未知時，預覽金額與差額為 `null`，不以零元冒充已確認。

未綁個案政策或人工計價的歷史案件，服務資料更正沿各指派的正式費率快照計算，未改的指派不套用他人的時數或費率。明確儲存個案計價才採用承辦人確認的整案費率。胎數更正依正式費率來源判斷，人工費率不因數值恰好等於政策費率就被替換；缺正式新費率時保存更正與待核對，不把畫面建議值升格為正式價格。

## Contracts
- Reporting borrows read-only `case_total_amount` from complete current `CasePricingFacts`; Domain `calculate_case_total_amount` retains covered service before funding and one fixed floor fee. It does not reuse salary or receipt totals — `15` §15.4 / `04` §0 Reporting 唯讀投影.
- `.arch-map/requirements/04_Client_Finance_Domain.md` §0 PRICE-01..09.
- 同節 IDENTITY-FIX-01..03：正式身分修正與歷史綁定相容；舊版讀取只供仍綁定舊政策的案件，不供新政策發布，待無舊版綁定使用者後才可另評估退役。

## Verification
- layout_status: `custom_current`
- layout_basis: Backend module tests use the canonical owner root; React tests mirror that root under ui_react/src/tests for the existing Vitest runtime.
- integration_root: `tests/domains/client-finance/subsystems/client-finance/integration/test_accounting_pricing_mysql.py`
- test_root: `tests/domains/client-finance/subsystems/client-finance/modules/pricing-configuration/`
- test_root: `ui_react/src/tests/domains/client-finance/subsystems/client-finance/modules/pricing-configuration/`

## Dependencies
- outbound: `payroll` — salary calculation/obligations; no duplicate payroll writer.
- outbound: `orders/historical-service-accounting` — 對帳的帳務參數抽屜借用同案歷史服務天數工作台。
- outbound: `case-import/pairing-current-facts` — 帳務參數抽屜透過客戶名冊讀取正式胎數與更正資格，使用既有 BeClass Preview／Apply 更正胎數，個案費率仍由 Client Finance 保存。
- inbound: `case-import` — bind only on first case creation.
- inbound: `clients/client-profile` — Drawer composes typed workflow only.
- inbound: `global/reporting` and Client Finance payment queries — reuse the same policy-based case category; case-number spelling does not determine category.
- inbound: `government-subsidy/reconciliation-register-query` 與 Orders 補助投影 adapter — 重用 `CASE_PRICING_FACTS_SQL` 的有效補助上限／費率，不由消費端重解讀舊政策名稱。

## 國定假日計價接線 ^pricing-configuration-holiday-pricing

```yaml archmap-impact
- kind: implements_requirement
  source: pricing-configuration-holiday-pricing
  target: ".arch-map/requirements/04_Client_Finance_Domain.md#^holiday-service-pricing"
```
- 假日計價讀回接線由下列 owner 實作，驗證見既有測試入口。`pricing_policy.py` 的案件總額與 obligation planning 使用同一客戶服務費投影。帳務 API 提供案件總額、客戶應收、月嫂應付及工會收入的 owner 結果，`AccountingParametersCard` 與帳務工作台直接呈現；瀏覽器不重算乘數。

- `holiday_repricing.py` 在設定寫入前鎖定並取得有正式收付案件的原 `case_total_amount`，保存於既有假日／日期調整 receipt JSON；讀取優先使用此原定價快照，不把人工應收當案件總額。正式應收及應付各讀原義務，工會收入由後端投影。已凍結案件缺少正式費率級距分解時，分解欄位回 null，不從新日曆捏造。

- 正式 Query 的月嫂應付取 Payroll 現有義務有效金額合計，工會收入以該結果及案件服務定價投影，不以個案政策的月嫂基準費率覆蓋各指派自己的正式結果。個案改價 Preview 仍計算候選影響，與正式 Query 分開。

- 未綁政策／個案覆寫的補助案件沒有另一個正式有效上限來源。定價 Query 不把讀取相容用的預設 120／80 視為已確認上限；Client Finance 與 Payroll 仍依已知服務時數及費率更新可計算結果，補助及未分配差額沿 22A 的 L 未知契約交原 owner 查核。

- 全額免自備依22A §2.3提供可持久讀回的重算結果，正式 Query 區分重算金額、原已入帳金額與待對帳差額；不以缺少負擔人把可計算服務費留在暫態候選。若既有資料模型缺少必要欄位，回報具體缺口，不以預設0或隱藏原價補足。
