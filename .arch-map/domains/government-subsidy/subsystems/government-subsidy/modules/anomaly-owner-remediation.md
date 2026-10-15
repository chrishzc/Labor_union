# Module: anomaly-owner-remediation

## Parent
- domain: `government-subsidy`
- subsystem: `government-subsidy`

## Responsibility
提供 Government Subsidy normal accounting／review／correction 的 deterministic validation與 owner readback；
`GOVSUB-003/005`均不形成 runtime Anomalies current issue，structural ambiguity與不完整owner facts fail closed。

## Implementation
- `domains/government_subsidy/overpayment.py`
- `domains/government_subsidy/payer_master.py` — receipt／offset 共用的 canonical payer identity 常數，已無退款帳戶模型。
- `api/dependencies/government_subsidy.py` — receipt／claim／offset 與 owner Query 的 request-scoped composition。
- `subsystems/government_subsidy/ledger_workflow.py`
- `subsystems/government_subsidy/overpayment_query.py`
- `subsystems/government_subsidy/overpayment_workflow.py`
- `infrastructure/mysql/government_subsidy_repository.py`
- `api/routes/government_subsidy.py` (receipt／offset transport)
- `api/schemas/government_subsidy.py`

## Verification
- higher_boundary: tests/domains/government-subsidy/subsystems/government-subsidy/integration/
- focused: `test_government_subsidy_overpayment.py`, `test_government_subsidy_overpayment_workflow.py`

## Transaction boundary
- Government Subsidy receipt／offset Query／Preview／Apply 維持單一 outer UoW 與 fresh readback。退回、退款核銷及追償 operation 已移除；歷史資料與 release schema 保留。
