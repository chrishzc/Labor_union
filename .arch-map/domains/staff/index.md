# Domain: staff

## Responsibility
擁有月嫂 lifecycle 根事實與正式退役／復職 transition；不擁有 LINE identity 或 Rich Menu provider 狀態。

## Subsystems
- `staff` — Staff lifecycle Query／Preview／Apply；path: `subsystems/staff/index.md`

## Relationships
- outbound: `external-integration/line` — 只有正式 retirement transition 在同一 outer UoW 呼叫既有 staff-role revocation application contract。

## Contracts
- `document/架構重整/01_規格基線/24_Staff_Matching_Preferences與不可服務期間正式規格.md`
- `domains/staff/retirement.py`

## Verification routing
- test_root: `tests/domains/staff/`
