# Subsystem: staff

## Parent
- domain: `staff`

## Responsibility
編排 Staff lifecycle Query／Preview／Apply、fresh version、receipt 與同一 outer Unit of Work effects。

## Modules
- `staff-retirement` — lifecycle transition and exact LINE staff-role revocation effect; path: `modules/staff-retirement.md`
- `case-preference-manual` — six canonical Staff relation Query／Preview／Apply owner; path: `modules/case-preference-manual.md`
- `staff-roster-profile` — authenticated complete-value personal/contact detail query for one selected Staff; path: `modules/staff-roster-profile.md`
- `staff-qualification-master` — bounded Staff qualification/certification master query; path: `modules/staff-qualification-master.md`

## Verification routing
- layout_status: `custom_current`
- layout_basis: frontend Staff cross-module integration tests use the mirrored subsystem root under `ui_react/src/tests/domains/staff/subsystems/staff/integration/`.
- test_root: `tests/domains/staff/subsystems/staff/`
- integration_root: `ui_react/src/tests/domains/staff/subsystems/staff/integration/`
