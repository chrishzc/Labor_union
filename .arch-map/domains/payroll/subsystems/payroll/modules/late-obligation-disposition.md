# Module: late-obligation-disposition

## Parent
- domain: `payroll`
- subsystem: `payroll`

## Responsibility
對late source計算delta並append唯一Payroll disposition；只有已付款後的合法超付才經typed Staff Payables port建立recovery。

## Verification
- test_root: `tests/domains/payroll/subsystems/payroll/integration/`
- Payroll owner evidence currently lives in owner-local adjustment／rebuild／staff-payment transaction coverage；paid-overage recovery 留在 Staff Payables owner boundary。
- 不存在 dedicated `late-obligation-disposition` module test root；此 routing 不代表存在 current Anomalies consumer。
