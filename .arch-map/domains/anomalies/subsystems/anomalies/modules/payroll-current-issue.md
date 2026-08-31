# Module: payroll-current-issue

## Parent
- domain: `anomalies`
- subsystem: `anomalies`

## Responsibility
只消費Payroll-owned PAYOUT-002 typed owner snapshot並投影current issue；不計算delta、不寫Payroll或Staff
Payables root。

## Implementation
- `subsystems/anomalies/payroll_current_issue_consumer.py`

## Verification
- test_root: `tests/domains/anomalies/subsystems/anomalies/modules/payroll-current-issue/`
