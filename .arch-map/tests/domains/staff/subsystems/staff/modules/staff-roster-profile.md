# Test Module: staff-roster-profile

module: staff-roster-profile
parent_subsystem: staff
architecture: ../../../../../../domains/staff/subsystems/staff/modules/staff-roster-profile.md
layout_status: custom_current
test_root: tests/domains/staff/subsystems/staff/modules/staff-roster-profile/
test_root: ui_react/src/tests/domains/staff/subsystems/staff/modules/staff-roster-profile/

## Canonical roots
- layout_basis: backend contract owns authenticated profile mutation and masked bank projection/commands; the mirrored React module root owns selected-Staff rendering and owner-routed editing.
- tests/domains/staff/subsystems/staff/modules/staff-roster-profile/
- ui_react/src/tests/domains/staff/subsystems/staff/modules/staff-roster-profile/

## Oracles
- The API returns the requested Staff identity and personal/contact fields while bank accounts expose only last4, primary and active state; IP, LINE User ID, full account number and raw source never cross a query/event/receipt boundary.
- `contract/test_staff_registry_mutations.py` protects Profile and Bank version conflicts, exact replay, collision handling and safe preview/readback.
- The Drawer loads a selected Staff, labels each owner, and performs separate cancel／preview／apply operations followed by server readback.
- `staff_registry_editor.test.tsx` protects one in-flight bank command, a stable idempotency key, post-error server requery and complete-account input clearing.
