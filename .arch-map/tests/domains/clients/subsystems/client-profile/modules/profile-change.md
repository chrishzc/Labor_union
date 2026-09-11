module: profile-change
parent_subsystem: client-profile
architecture: ../../../../../../domains/clients/subsystems/client-profile/modules/profile-change.md
layout_status: custom_current
test_root: tests/domains/clients/subsystems/client-profile/modules/profile-change/
test_root: ui_react/src/tests/domains/clients/subsystems/client-profile/modules/profile-change/

## Canonical roots
- layout_basis: Backend contract tests own Client Profile and BeClass query/mutation boundaries; the mirrored React root owns the case-centered registry interaction.
- tests/domains/clients/subsystems/client-profile/modules/profile-change/
- ui_react/src/tests/domains/clients/subsystems/client-profile/modules/profile-change/

# Owned verification
- `contract/test_application.py` — Client profile applicant／reviewer workflow, version conflict, idempotent replay and owner readback.
- `contract/test_client_registry_query.py` — case-centered bounded composition, binding result, owner/editability metadata and cursor contract.
- `contract/test_client_binding_port.py` — verified binding evidence and role scope boundary.
- `ui_react/.../client_registry_page.test.tsx` — case selection, zero-write cancel, owner preview/apply, stable idempotency key and server readback refresh.
