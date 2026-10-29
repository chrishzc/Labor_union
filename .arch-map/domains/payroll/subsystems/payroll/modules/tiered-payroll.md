# Module: tiered-payroll

## Parent
- domain: `payroll`
- subsystem: `payroll`

## Responsibility
Calculate assignment salary using case-wide subsidy-hour consumption and four-rate
pricing. Preserve service ownership, double pay, floor-fee conservation and original
payments; customer/subsidy installments use service-end month+1/+2 respectively.

## Implementation
- `domains/payroll/calculation.py`
- `domains/payroll/tiered_rates.py`
- `domains/payroll/installments.py`
- `infrastructure/mysql/payroll_installments.py`

## Contracts
- `document/架構重整/01_規格基線/03_Payroll_Domain.md`
- `document/架構重整/01_規格基線/04_Client_Finance_Domain.md` PRICE-04..08.

## Verification
- test_root: `tests/domains/payroll/subsystems/payroll/modules/tiered-payroll/`
