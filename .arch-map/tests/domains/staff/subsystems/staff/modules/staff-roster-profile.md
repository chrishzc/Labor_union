# Test Module: staff-roster-profile

module: staff-roster-profile
parent_subsystem: staff
architecture: ../../../../../../domains/staff/subsystems/staff/modules/staff-roster-profile.md
layout_status: custom_current
test_root: tests/domains/staff/subsystems/staff/modules/staff-roster-profile/
test_root: ui_react/src/tests/domains/staff/subsystems/staff/modules/staff-roster-profile/

## Canonical roots
- layout_basis: the backend owns the authorized complete-value reader and the separate masked bank command path; the mirrored React module root owns selected-Staff rendering and owner-routed editing.
- tests/domains/staff/subsystems/staff/modules/staff-roster-profile/
- ui_react/src/tests/domains/staff/subsystems/staff/modules/staff-roster-profile/

## Oracles
- `contract/test_staff_profile_query.py` checks that authorized Profile and Roster reads return the complete `account_no` when available plus `account_last4`, and preserve last4-only legacy values. The reader requires the same permission for both entries. IP, LINE User ID and raw source remain excluded.
- `contract/test_staff_registry_mutations.py` separately checks that bank Preview masks the complete account. The read exception does not extend to audit events, receipts, logs or exports; see [requirement #33 §6](../../../../../../requirements/33_案件與月嫂整合名冊正式規格.md#6-月嫂銀行帳戶顯示契約).
- `ui_react/src/tests/staff_directory_page.test.tsx` covers complete-value display and last4 fallback in the roster; `staff_registry_editor.test.tsx` also covers full account display in authorized account selection.
- `contract/test_staff_registry_mutations.py` protects Profile and Bank version conflicts, exact replay, collision handling and safe preview/readback.
- The Drawer loads a selected Staff, labels each owner, and performs separate cancel／preview／apply operations followed by server readback.
- `staff_registry_editor.test.tsx` protects one in-flight bank command, a stable idempotency key, post-error server requery and complete-account input clearing.
