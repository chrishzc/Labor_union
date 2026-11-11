# Module: tiered-payroll

## Parent
- domain: `payroll`
- subsystem: `payroll`

## Responsibility
Calculate assignment salary using case-wide subsidy-hour consumption and four-rate
pricing. Preserve service ownership, floor-fee conservation and original
payments; customer/subsidy installments use service-end month+1/+2 respectively.
Preliminary caregiver information may read a quantity-only estimate using these same rates and funding dates; estimates do not create official assignment facts or obligations.

## Implementation
- `domains/payroll/calculation.py`
- `domains/payroll/tiered_rates.py`
- `domains/payroll/estimate.py` — quantity-only preliminary staff quote; reuses Payroll tiers and funding dates without creating assignments, service dates or obligations.
- `domains/payroll/installments.py`
- `infrastructure/mysql/payroll_installments.py`
- 方案一共同核銷沿規格16 §2.4.1，以 `confirmed_subsidy_installments` 及 insert-only `establish_confirmed_subsidy_installments` 承接單一既有應付的缺席來源分期；自備款保留原日期、補助沿既有+2月15日政策。借用 Staff Payables outer UoW，沒有新增薪資或自行 commit，不覆寫既有分期／付款。

## Contracts
- `document/架構重整/01_規格基線/03_Payroll_Domain.md`
- `document/架構重整/01_規格基線/04_Client_Finance_Domain.md` PRICE-04..08.

## Verification
- test_root: `tests/domains/payroll/subsystems/payroll/modules/tiered-payroll/`
