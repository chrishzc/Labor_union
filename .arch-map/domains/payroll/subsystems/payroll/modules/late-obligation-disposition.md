# Module: late-obligation-disposition

## Parent
- domain: `payroll`
- subsystem: `payroll`

## Responsibility
對late source計算delta並append唯一Payroll disposition；只有已付款後的合法超付才經typed Staff Payables port建立recovery。

## Implementation
- `domains/payroll/late_obligation.py`
- `subsystems/payroll/late_obligation_workflow.py`
- `infrastructure/mysql/payroll_late_obligation_repository.py`
- `infrastructure/mysql/payroll_current_issue_adapter.py`

## Verification
- test_root: `tests/domains/payroll/subsystems/payroll/modules/late-obligation-disposition/`
