# Module: staff-retirement

## Parent
- domain: `staff`
- subsystem: `staff`

## Responsibility
擁有 Staff lifecycle Query／Preview／Apply transaction，且在退役的 owner boundary fail-closed 檢查既有 Scheduling assignment。真正 `active → retired` transition 透過 typed effect port，在同一 outer Unit of Work 呼叫 LINE-owned staff-role revocation；不直接實作 LINE repository、menu 或 provider 規則。

## Implementation
- `domains/staff/retirement.py`
- `subsystems/staff/retirement_workflow.py`
- `infrastructure/mysql/staff_retirement_repository.py`
- `api/dependencies/staff_retirement.py` — composition only.

## Dependencies
- outbound: `external-integration/line/module:line-identity-management` — `subsystems/line/staff_retirement_effect.py` adapter and existing revocation application contract.

## Verification
- test_root: `tests/domains/staff/subsystems/staff/modules/staff-retirement/`

## Change triggers
- Reconcile when Staff lifecycle owner, retirement transition, outer UoW, LINE effect port, or canonical test root changes.
