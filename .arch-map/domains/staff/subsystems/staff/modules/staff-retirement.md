# Module: staff-retirement

## Parent
- domain: `staff`
- subsystem: `staff`

## Responsibility
擁有 Staff lifecycle Query／Preview／Apply transaction，且在退役的 owner boundary fail-closed 檢查既有 Scheduling assignment。真正 `active → retired` transition 透過 typed effect port，在同一 outer Unit of Work 呼叫 LINE-owned staff-role revocation，並以 committed retirement receipt 投影 current configured LINE notification；不直接實作 LINE repository、menu、template 或 provider 規則。

## Implementation
- `domains/staff/retirement.py`
- `subsystems/staff/retirement_workflow.py`
- `infrastructure/mysql/staff_retirement_repository.py`
- `api/dependencies/staff_retirement.py` — composition only.

## Dependencies
- outbound: `external-integration/line/module:line-identity-management` — `subsystems/line/staff_retirement_effect.py` adapter、existing revocation application contract 與 current notification registry projection；缺少有效 staff binding 時不造 recipient／task。

## Verification
- test_root: `tests/domains/staff/subsystems/staff/modules/staff-retirement/`

## Change triggers
- Reconcile when Staff lifecycle owner, retirement transition, outer UoW, LINE effect port、configured retirement notification projection, or canonical test root changes.
