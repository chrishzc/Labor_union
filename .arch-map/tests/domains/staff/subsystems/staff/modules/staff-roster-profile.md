# Test Module: staff-roster-profile

module: staff-roster-profile
parent_subsystem: staff
architecture: ../../../../../../domains/staff/subsystems/staff/modules/staff-roster-profile.md
layout_status: custom_current
test_root: tests/domains/staff/subsystems/staff/modules/staff-roster-profile/
test_root: ui_react/src/tests/domains/staff/subsystems/staff/modules/staff-roster-profile/

## Canonical roots
- layout_basis: backend contract owns authenticated complete-value projection and bounded SQL; the mirrored React module root owns selected-Staff rendering.
- tests/domains/staff/subsystems/staff/modules/staff-roster-profile/
- ui_react/src/tests/domains/staff/subsystems/staff/modules/staff-roster-profile/

## Oracles
- The API returns the requested Staff identity and complete personal/contact/bank-account fields required by the internal roster UI, while IP, LINE User ID and raw source never cross the response boundary.
- The Drawer loads the profile only for a selected Staff and renders complete identity, contact and bank-account facts without source-detail annotations.
