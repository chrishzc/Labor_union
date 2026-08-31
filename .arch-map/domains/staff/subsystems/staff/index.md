# Subsystem: staff

## Parent
- domain: `staff`

## Responsibility
編排 Staff lifecycle Query／Preview／Apply、fresh version、receipt 與同一 outer Unit of Work effects。

## Modules
- `staff-retirement` — lifecycle transition and exact LINE staff-role revocation effect; path: `modules/staff-retirement.md`

## Verification routing
- test_root: `tests/domains/staff/subsystems/staff/`
